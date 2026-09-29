import os
import sqlite3
import logging
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

# =========================
# КЛАТЧЕР — Telegram Bot
# =========================

BOT_TOKEN = os.getenv("8938904147:AAGLfXJbLibjEumIG4lzyueKCnqR3cBv28A")
ADMIN_ID = 8919996108
DB_PATH = "clutcher.db"

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("clutcher")


# ---------- Database ----------

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            joined_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team1 TEXT NOT NULL,
            team2 TEXT NOT NULL,
            match_time TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            winner INTEGER DEFAULT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            user_id INTEGER NOT NULL,
            match_id INTEGER NOT NULL,
            choice INTEGER NOT NULL,
            created_at TEXT,
            PRIMARY KEY (user_id, match_id)
        )
    """)

    conn.commit()
    conn.close()


def save_user(user):
    conn = db()
    conn.execute("""
        INSERT INTO users (user_id, username, first_name, joined_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username=excluded.username,
            first_name=excluded.first_name
    """, (
        user.id,
        user.username,
        user.first_name,
        datetime.utcnow().isoformat()
    ))
    conn.commit()
    conn.close()


# ---------- Keyboards ----------

def main_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📰 Предложить новость", callback_data="news")
        ],
        [
            InlineKeyboardButton("🔮 Предикты", callback_data="predictions"),
            InlineKeyboardButton("📢 Новости", callback_data="channel")
        ],
        [
            InlineKeyboardButton("💬 Связь с редакцией", callback_data="contact")
        ]
    ])


def admin_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Добавить матч", callback_data="admin_add")
        ],
        [
            InlineKeyboardButton("📋 Матчи", callback_data="admin_matches"),
            InlineKeyboardButton("🏆 Завершить матч", callback_data="admin_finish")
        ],
        [
            InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
            InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast")
        ]
    ])


def back_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Главное меню", callback_data="home")]
    ])


# ---------- Helpers ----------

async def send_home(update: Update, text=None):
    message = update.callback_query.message if update.callback_query else update.message
    await message.reply_text(
        text or "🤖 *КЛАТЧЕР*\n\nНовости • Матчи • Турниры",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu()
    )


def is_admin(user_id):
    return user_id == ADMIN_ID


# ---------- /start ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user)
    context.user_data.clear()

    await update.message.reply_text(
        "🤖 *КЛАТЧЕР*\n\n"
        "Новости • Матчи • Турниры\n\n"
        "Выберите действие:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu()
    )


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return

    context.user_data.clear()
    await update.message.reply_text(
        "🔐 *АДМИН-ПАНЕЛЬ*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=admin_menu()
    )


# ---------- User callbacks ----------

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    save_user(query.from_user)

    data = query.data

    if data == "home":
        context.user_data.clear()
        await query.edit_message_text(
            "🤖 *КЛАТЧЕР*\n\nНовости • Матчи • Турниры\n\nВыберите действие:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu()
        )
        return

    if data == "news":
        context.user_data["state"] = "suggest_news"
        await query.edit_message_text(
            "📰 *Предложить новость*\n\n"
            "Отправьте текст новости, фото или видео.\n"
            "Сообщение будет передано редакции.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_menu()
        )
        return

    if data == "contact":
        context.user_data["state"] = "contact"
        await query.edit_message_text(
            "💬 *Связь с редакцией*\n\n"
            "Напишите сообщение — оно будет передано редакции.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_menu()
        )
        return

    if data == "channel":
        await query.edit_message_text(
            "📢 *КЛАТЧЕР*\n\n"
            "Здесь позже можно добавить ссылку на ваш Telegram-канал.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_menu()
        )
        return

    if data == "predictions":
        await show_predictions(query)
        return

    if data.startswith("vote:"):
        match_id = int(data.split(":")[1])
        choice = int(data.split(":")[2])
        await vote(query, match_id, choice)
        return

    # Admin
    if data.startswith("admin_"):
        if not is_admin(query.from_user.id):
            await query.edit_message_text("⛔ Доступ запрещён.")
            return

        if data == "admin_add":
            context.user_data["state"] = "add_team1"
            await query.edit_message_text(
                "➕ *Добавление матча*\n\nВведите первую команду:",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=back_menu()
            )
            return

        if data == "admin_matches":
            await admin_matches(query)
            return

        if data == "admin_finish":
            await admin_finish_list(query)
            return

        if data == "admin_stats":
            await admin_stats(query)
            return

        if data == "admin_broadcast":
            context.user_data["state"] = "broadcast"
            await query.edit_message_text(
                "📢 *Рассылка*\n\n"
                "Отправьте текст, фото или видео для рассылки.\n"
                "После этого бот попросит подтверждение.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=back_menu()
            )
            return

    if data.startswith("finish:"):
        match_id = int(data.split(":")[1])
        await finish_match_menu(query, match_id)
        return

    if data.startswith("winner:"):
        parts = data.split(":")
        match_id = int(parts[1])
        winner = int(parts[2])
        await finish_match(query, match_id, winner)
        return

    if data == "broadcast_confirm":
        await perform_broadcast(query, context)
        return

    if data == "broadcast_cancel":
        context.user_data.clear()
        await query.edit_message_text(
            "❌ Рассылка отменена.",
            reply_markup=admin_menu()
        )
        return


# ---------- Predictions ----------

async def show_predictions(query):
    conn = db()
    rows = conn.execute("""
        SELECT * FROM matches
        WHERE status='active'
        ORDER BY match_time ASC
    """).fetchall()
    conn.close()

    if not rows:
        await query.edit_message_text(
            "🔮 *ПРЕДИКТЫ*\n\n"
            "Сейчас активных матчей нет.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_menu()
        )
        return

    buttons = []
    for m in rows:
        buttons.append([
            InlineKeyboardButton(
                f"⚔️ {m['team1']} vs {m['team2']}",
                callback_data=f"match:{m['id']}"
            )
        ])

    # Add a temporary handler-like behavior by using match: in callbacks below.
    buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data="home")])

    await query.edit_message_text(
        "🔮 *ПРЕДИКТЫ*\n\nВыберите матч:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def show_match_prediction(query, match_id):
    conn = db()
    match = conn.execute(
        "SELECT * FROM matches WHERE id=? AND status='active'",
        (match_id,)
    ).fetchone()
    conn.close()

    if not match:
        await query.edit_message_text(
            "Матч не найден или предикт уже закрыт.",
            reply_markup=back_menu()
        )
        return

    await query.edit_message_text(
        f"⚔️ *{match['team1']} vs {match['team2']}*\n\n"
        f"📅 {match['match_time']}\n\n"
        "Кто победит?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    f"🟢 {match['team1']}",
                    callback_data=f"vote:{match_id}:1"
                ),
                InlineKeyboardButton(
                    f"🟡 {match['team2']}",
                    callback_data=f"vote:{match_id}:2"
                )
            ],
            [InlineKeyboardButton("⬅️ Назад", callback_data="predictions")]
        ])
    )


async def vote(query, match_id, choice):
    conn = db()
    match = conn.execute(
        "SELECT * FROM matches WHERE id=? AND status='active'",
        (match_id,)
    ).fetchone()

    if not match:
        conn.close()
        await query.answer("Предикт уже закрыт.", show_alert=True)
        return

    existing = conn.execute(
        "SELECT choice FROM predictions WHERE user_id=? AND match_id=?",
        (query.from_user.id, match_id)
    ).fetchone()

    if existing:
        conn.close()
        await query.answer("Вы уже проголосовали за этот матч.", show_alert=True)
        return

    conn.execute("""
        INSERT INTO predictions (user_id, match_id, choice, created_at)
        VALUES (?, ?, ?, ?)
    """, (
        query.from_user.id,
        match_id,
        choice,
        datetime.utcnow().isoformat()
    ))
    conn.commit()

    counts = conn.execute("""
        SELECT choice, COUNT(*) AS total
        FROM predictions
        WHERE match_id=?
        GROUP BY choice
    """, (match_id,)).fetchall()
    conn.close()

    c1 = next((r["total"] for r in counts if r["choice"] == 1), 0)
    c2 = next((r["total"] for r in counts if r["choice"] == 2), 0)
    total = c1 + c2

    p1 = round(c1 / total * 100) if total else 0
    p2 = round(c2 / total * 100) if total else 0

    chosen = match["team1"] if choice == 1 else match["team2"]

    await query.edit_message_text(
        f"✅ *Ваш предикт принят!*\n\n"
        f"⚔️ {match['team1']} vs {match['team2']}\n\n"
        f"Ваш выбор: *{chosen}*\n\n"
        f"📊 {match['team1']} — {p1}%\n"
        f"📊 {match['team2']} — {p2}%",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_menu()
    )


# ---------- Admin: matches ----------

async def admin_matches(query):
    conn = db()
    rows = conn.execute(
        "SELECT * FROM matches ORDER BY id DESC"
    ).fetchall()
    conn.close()

    if not rows:
        await query.edit_message_text(
            "📋 Матчей пока нет.",
            reply_markup=admin_menu()
        )
        return

    text = "📋 *МАТЧИ*\n\n"
    for m in rows:
        status = "🟢 активен" if m["status"] == "active" else "🏁 завершён"
        text += f"#{m['id']} — {m['team1']} vs {m['team2']}\n"
        text += f"📅 {m['match_time']} • {status}\n\n"

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=admin_menu()
    )


async def admin_finish_list(query):
    conn = db()
    rows = conn.execute("""
        SELECT * FROM matches
        WHERE status='active'
        ORDER BY match_time ASC
    """).fetchall()
    conn.close()

    if not rows:
        await query.edit_message_text(
            "🏆 Активных матчей нет.",
            reply_markup=admin_menu()
        )
        return

    buttons = []
    for m in rows:
        buttons.append([
            InlineKeyboardButton(
                f"🏆 {m['team1']} vs {m['team2']}",
                callback_data=f"finish:{m['id']}"
            )
        ])
    buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data="admin_home")])

    await query.edit_message_text(
        "Выберите завершённый матч:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def finish_match_menu(query, match_id):
    conn = db()
    m = conn.execute(
        "SELECT * FROM matches WHERE id=? AND status='active'",
        (match_id,)
    ).fetchone()
    conn.close()

    if not m:
        await query.edit_message_text(
            "Матч не найден.",
            reply_markup=admin_menu()
        )
        return

    await query.edit_message_text(
        f"🏆 *{m['team1']} vs {m['team2']}*\n\nКто победил?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    f"🏆 {m['team1']}",
                    callback_data=f"winner:{match_id}:1"
                ),
                InlineKeyboardButton(
                    f"🏆 {m['team2']}",
                    callback_data=f"winner:{match_id}:2"
                )
            ],
            [InlineKeyboardButton("⬅️ Назад", callback_data="admin_finish")]
        ])
    )


async def finish_match(query, match_id, winner):
    conn = db()
    conn.execute("""
        UPDATE matches
        SET status='finished', winner=?
        WHERE id=?
    """, (winner, match_id))
    conn.commit()

    m = conn.execute(
        "SELECT * FROM matches WHERE id=?",
        (match_id,)
    ).fetchone()

    stats = conn.execute("""
        SELECT
            SUM(CASE WHEN choice=1 THEN 1 ELSE 0 END) AS c1,
            SUM(CASE WHEN choice=2 THEN 1 ELSE 0 END) AS c2
        FROM predictions
        WHERE match_id=?
    """, (match_id,)).fetchone()
    conn.close()

    winner_name = m["team1"] if winner == 1 else m["team2"]
    c1 = stats["c1"] or 0
    c2 = stats["c2"] or 0

    await query.edit_message_text(
        f"🏁 *Матч завершён!*\n\n"
        f"⚔️ {m['team1']} vs {m['team2']}\n"
        f"🏆 Победитель: *{winner_name}*\n\n"
        f"🔮 Предикты: {m['team1']} — {c1}, {m['team2']} — {c2}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=admin_menu()
    )


# ---------- Admin: statistics ----------

async def admin_stats(query):
    conn = db()
    users = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    matches = conn.execute("SELECT COUNT(*) AS n FROM matches").fetchone()["n"]
    votes = conn.execute("SELECT COUNT(*) AS n FROM predictions").fetchone()["n"]
    active = conn.execute(
        "SELECT COUNT(*) AS n FROM matches WHERE status='active'"
    ).fetchone()["n"]
    conn.close()

    await query.edit_message_text(
        "📊 *СТАТИСТИКА*\n\n"
        f"👤 Пользователей: {users}\n"
        f"⚔️ Всего матчей: {matches}\n"
        f"🟢 Активных матчей: {active}\n"
        f"🔮 Предиктов: {votes}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=admin_menu()
    )


# ---------- Text / media input ----------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user)

    state = context.user_data.get("state")

    if not state:
        await update.message.reply_text(
            "Выберите действие в меню:",
            reply_markup=main_menu()
        )
        return

    # Add match wizard
    if state == "add_team1":
        context.user_data["team1"] = update.message.text.strip()
        context.user_data["state"] = "add_team2"
        await update.message.reply_text("Введите вторую команду:")
        return

    if state == "add_team2":
        context.user_data["team2"] = update.message.text.strip()
        context.user_data["state"] = "add_time"
        await update.message.reply_text(
            "Введите дату и время матча.\n"
            "Например: 30.09.2026 18:00"
        )
        return

    if state == "add_time":
        team1 = context.user_data["team1"]
        team2 = context.user_data["team2"]
        match_time = update.message.text.strip()

        conn = db()
        conn.execute("""
            INSERT INTO matches (team1, team2, match_time)
            VALUES (?, ?, ?)
        """, (team1, team2, match_time))
        conn.commit()
        conn.close()

        context.user_data.clear()

        await update.message.reply_text(
            f"✅ Матч добавлен!\n\n"
            f"⚔️ {team1} vs {team2}\n"
            f"📅 {match_time}",
            reply_markup=admin_menu()
        )
        return

    # News / contact
    if state in ("suggest_news", "contact"):
        kind = "📰 НОВАЯ НОВОСТЬ" if state == "suggest_news" else "💬 СООБЩЕНИЕ В РЕДАКЦИЮ"

        text = (
            f"{kind}\n\n"
            f"👤 {user.full_name}"
            f"{f' (@{user.username})' if user.username else ''}\n"
            f"🆔 {user.id}\n\n"
        )

        if update.message.text:
            text += update.message.text

        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=text
            )
            # Forward media when present
            if update.message.photo:
                await context.bot.forward_message(
                    chat_id=ADMIN_ID,
                    from_chat_id=update.effective_chat.id,
                    message_id=update.message.message_id
                )
            elif update.message.video:
                await context.bot.forward_message(
                    chat_id=ADMIN_ID,
                    from_chat_id=update.effective_chat.id,
                    message_id=update.message.message_id
                )
        except Exception as e:
            logger.exception("Could not send user message to admin: %s", e)

        context.user_data.clear()

        await update.message.reply_text(
            "✅ Сообщение отправлено редакции. Спасибо!",
            reply_markup=main_menu()
        )
        return

    # Broadcast wizard
    if state == "broadcast":
        context.user_data["broadcast_message_id"] = update.message.message_id
        context.user_data["broadcast_chat_id"] = update.effective_chat.id

        await update.message.reply_text(
            "📢 *Предпросмотр готов.*\n\n"
            "Если это сообщение нужно отправить всем пользователям бота, нажмите подтверждение.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Отправить всем", callback_data="broadcast_confirm"),
                    InlineKeyboardButton("❌ Отмена", callback_data="broadcast_cancel")
                ]
            ])
        )
        return


# ---------- Broadcast ----------

async def perform_broadcast(query, context):
    if not is_admin(query.from_user.id):
        return

    source_chat = context.user_data.get("broadcast_chat_id")
    source_message = context.user_data.get("broadcast_message_id")

    if not source_chat or not source_message:
        await query.edit_message_text(
            "❌ Сообщение для рассылки не найдено.",
            reply_markup=admin_menu()
        )
        return

    conn = db()
    users = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()

    sent = 0
    failed = 0

    await query.edit_message_text("📢 Рассылка запущена...")

    for row in users:
        try:
            await context.bot.copy_message(
                chat_id=row["user_id"],
                from_chat_id=source_chat,
                message_id=source_message
            )
            sent += 1
        except Exception:
            failed += 1

    context.user_data.clear()

    await query.message.reply_text(
        f"📢 *Рассылка завершена*\n\n"
        f"✅ Отправлено: {sent}\n"
        f"❌ Ошибок: {failed}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=admin_menu()
    )


# ---------- Main ----------

def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "Не задан BOT_TOKEN. Добавьте переменную окружения BOT_TOKEN."
        )

    init_db()

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_command))

    # Match selection has to be handled before generic callbacks.
    async def match_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        match_id = int(query.data.split(":")[1])
        await show_match_prediction(query, match_id)

    application.add_handler(
        CallbackQueryHandler(match_callback, pattern=r"^match:\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(callbacks)
    )

    application.add_handler(
        MessageHandler(filters.ALL & ~filters.COMMAND, handle_message)
    )

    logger.info("Клатчер бот запущен.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
