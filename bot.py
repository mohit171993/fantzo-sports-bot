import os
import sqlite3
import logging
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "8992664481"))

FANTZO_HOME = "https://fantzo.com"
FANTZO_LIVE = "https://fantzo.com/en/live"
FANTZO_SLOTS = "https://fantzo.com/en/slots"
FANTZO_REGISTER = "https://fantzo.com/en/registration"

DB_PATH = os.getenv("DB_PATH", "fantzo_bot.db")

TEXT = {
    "en": {
        "welcome": (
            "⚡ <b>Welcome to Fantzo Sports Updates</b>\n\n"
            "Live scores • Fixtures • Results • Sports news\n"
            "Fast updates for cricket, football and more.\n\n"
            "Choose what you want below 👇"
        ),
        "live": "🔴 <b>Live Now</b>\n\nLive score integration is being connected. Use the Fantzo Live button meanwhile.",
        "cricket": "🏏 <b>Cricket</b>\n\nLive scores, fixtures, results and match alerts will appear here.",
        "football": "⚽ <b>Football</b>\n\nLive scores, fixtures, results and match alerts will appear here.",
        "upcoming": "🗓 <b>Upcoming Matches</b>\n\nUpcoming fixtures will appear here.",
        "results": "✅ <b>Latest Results</b>\n\nCompleted match results will appear here.",
        "news": "📰 <b>Sports News</b>\n\nBreaking sports headlines and quick summaries will appear here.",
        "sub_on": "🔔 <b>Updates ON</b>\n\nYou are subscribed to Fantzo sports alerts.",
        "sub_off": "🔕 <b>Updates OFF</b>\n\nYou will no longer receive Fantzo sports alerts.",
        "settings": "⚙️ <b>Settings</b>\n\nChoose your language and notification preferences.",
        "explore": "🌐 <b>Explore Fantzo</b>\n\nOpen any Fantzo destination below.",
        "lang_saved": "✅ Language changed to English.",
    },
    "hi": {
        "welcome": (
            "⚡ <b>Fantzo Sports Updates में आपका स्वागत है</b>\n\n"
            "लाइव स्कोर • फिक्स्चर • रिज़ल्ट • स्पोर्ट्स न्यूज़\n"
            "क्रिकेट, फुटबॉल और अन्य खेलों के तेज़ अपडेट।\n\n"
            "नीचे अपना विकल्प चुनें 👇"
        ),
        "live": "🔴 <b>Live Now</b>\n\nलाइव स्कोर इंटीग्रेशन जोड़ा जा रहा है। अभी Fantzo Live बटन इस्तेमाल करें।",
        "cricket": "🏏 <b>Cricket</b>\n\nलाइव स्कोर, फिक्स्चर, रिज़ल्ट और मैच अलर्ट यहाँ दिखेंगे।",
        "football": "⚽ <b>Football</b>\n\nलाइव स्कोर, फिक्स्चर, रिज़ल्ट और मैच अलर्ट यहाँ दिखेंगे।",
        "upcoming": "🗓 <b>Upcoming Matches</b>\n\nआने वाले मैच यहाँ दिखेंगे।",
        "results": "✅ <b>Latest Results</b>\n\nपूरे हुए मैचों के नतीजे यहाँ दिखेंगे।",
        "news": "📰 <b>Sports News</b>\n\nब्रेकिंग स्पोर्ट्स न्यूज़ और छोटे अपडेट यहाँ दिखेंगे।",
        "sub_on": "🔔 <b>Updates ON</b>\n\nआप Fantzo sports alerts के लिए subscribe हैं।",
        "sub_off": "🔕 <b>Updates OFF</b>\n\nआपको Fantzo sports alerts नहीं मिलेंगे।",
        "settings": "⚙️ <b>Settings</b>\n\nभाषा और notification preferences चुनें।",
        "explore": "🌐 <b>Explore Fantzo</b>\n\nनीचे से Fantzo destination खोलें।",
        "lang_saved": "✅ भाषा हिंदी कर दी गई है।",
    },
}


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                language TEXT DEFAULT 'en',
                subscribed INTEGER DEFAULT 0,
                created_at TEXT,
                last_seen TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS clicks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
                created_at TEXT
            )
        """)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def touch_user(update: Update):
    user = update.effective_user
    if not user:
        return
    with db() as conn:
        conn.execute(
            """
            INSERT INTO users(user_id, username, first_name, created_at, last_seen)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name,
                last_seen=excluded.last_seen
            """,
            (user.id, user.username, user.first_name, now_iso(), now_iso()),
        )


def track(user_id: int, action: str):
    with db() as conn:
        conn.execute(
            "INSERT INTO clicks(user_id, action, created_at) VALUES (?, ?, ?)",
            (user_id, action, now_iso()),
        )


def get_user_lang(user_id: int) -> str:
    with db() as conn:
        row = conn.execute(
            "SELECT language FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
    return row["language"] if row and row["language"] in TEXT else "en"


def is_subscribed(user_id: int) -> bool:
    with db() as conn:
        row = conn.execute(
            "SELECT subscribed FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
    return bool(row["subscribed"]) if row else False


def set_subscription(user_id: int, value: bool):
    with db() as conn:
        conn.execute(
            "UPDATE users SET subscribed = ?, last_seen = ? WHERE user_id = ?",
            (1 if value else 0, now_iso(), user_id),
        )


def set_language(user_id: int, lang: str):
    with db() as conn:
        conn.execute(
            "UPDATE users SET language = ?, last_seen = ? WHERE user_id = ?",
            (lang, now_iso(), user_id),
        )


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔴 Live Now", callback_data="live_now"),
                InlineKeyboardButton("🏏 Cricket", callback_data="cricket"),
            ],
            [
                InlineKeyboardButton("⚽ Football", callback_data="football"),
                InlineKeyboardButton("📰 Sports News", callback_data="news"),
            ],
            [
                InlineKeyboardButton("🗓 Upcoming", callback_data="upcoming"),
                InlineKeyboardButton("✅ Results", callback_data="results"),
            ],
            [
                InlineKeyboardButton("🔔 Subscribe", callback_data="subscribe"),
                InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
            ],
            [
                InlineKeyboardButton("🌐 Explore Fantzo", callback_data="explore"),
            ],
        ]
    )


def explore_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🌐 Fantzo Home", url=FANTZO_HOME)],
            [
                InlineKeyboardButton("🔴 Live", url=FANTZO_LIVE),
                InlineKeyboardButton("📝 Register", url=FANTZO_REGISTER),
            ],
            [InlineKeyboardButton("🎰 Slots", url=FANTZO_SLOTS)],
            [InlineKeyboardButton("⬅️ Back", callback_data="back")],
        ]
    )


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
                InlineKeyboardButton("🇮🇳 हिंदी", callback_data="lang_hi"),
            ],
            [InlineKeyboardButton("⬅️ Back", callback_data="back")],
        ]
    )


def subscription_keyboard(current: bool) -> InlineKeyboardMarkup:
    label = "🔕 Turn OFF" if current else "🔔 Turn ON"
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(label, callback_data="toggle_sub")],
            [InlineKeyboardButton("⬅️ Back", callback_data="back")],
        ]
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    touch_user(update)
    lang = get_user_lang(update.effective_user.id)
    await update.effective_message.reply_text(
        TEXT[lang]["welcome"],
        parse_mode="HTML",
        reply_markup=main_keyboard(),
        disable_web_page_preview=True,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    touch_user(update)
    await update.effective_message.reply_text(
        "Use /start to open Fantzo Sports Updates.\n"
        "Use /admin for the admin dashboard if you are the owner.",
        reply_markup=main_keyboard(),
    )


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    touch_user(update)
    if update.effective_user.id != ADMIN_USER_ID:
        await update.effective_message.reply_text("This command is restricted.")
        return

    with db() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        subs = conn.execute(
            "SELECT COUNT(*) c FROM users WHERE subscribed = 1"
        ).fetchone()["c"]
        clicks = conn.execute("SELECT COUNT(*) c FROM clicks").fetchone()["c"]
        top = conn.execute(
            """
            SELECT action, COUNT(*) c
            FROM clicks
            GROUP BY action
            ORDER BY c DESC
            LIMIT 5
            """
        ).fetchall()

    top_text = "\n".join(f"• {r['action']}: {r['c']}" for r in top) or "No activity yet."
    await update.effective_message.reply_text(
        "🛠 <b>Fantzo Admin</b>\n\n"
        f"👥 Users: <b>{total}</b>\n"
        f"🔔 Subscribers: <b>{subs}</b>\n"
        f"📊 Button actions: <b>{clicks}</b>\n\n"
        f"<b>Top actions</b>\n{top_text}\n\n"
        "Broadcast: <code>/broadcast your message</code>",
        parse_mode="HTML",
    )


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_USER_ID:
        await update.effective_message.reply_text("This command is restricted.")
        return

    message = " ".join(context.args).strip()
    if not message:
        await update.effective_message.reply_text("Usage: /broadcast your message")
        return

    with db() as conn:
        users = conn.execute(
            "SELECT user_id FROM users WHERE subscribed = 1"
        ).fetchall()

    sent = 0
    failed = 0
    for row in users:
        try:
            await context.bot.send_message(chat_id=row["user_id"], text=message)
            sent += 1
        except Exception:
            failed += 1

    await update.effective_message.reply_text(
        f"Broadcast complete.\nSent: {sent}\nFailed: {failed}"
    )


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    touch_user(update)

    user_id = update.effective_user.id
    action = query.data
    track(user_id, action)
    lang = get_user_lang(user_id)

    if action == "back":
        await query.edit_message_text(
            TEXT[lang]["welcome"],
            parse_mode="HTML",
            reply_markup=main_keyboard(),
            disable_web_page_preview=True,
        )
        return

    if action == "explore":
        await query.edit_message_text(
            TEXT[lang]["explore"],
            parse_mode="HTML",
            reply_markup=explore_keyboard(),
            disable_web_page_preview=True,
        )
        return

    if action == "settings":
        await query.edit_message_text(
            TEXT[lang]["settings"],
            parse_mode="HTML",
            reply_markup=settings_keyboard(),
        )
        return

    if action in ("lang_en", "lang_hi"):
        new_lang = "en" if action == "lang_en" else "hi"
        set_language(user_id, new_lang)
        await query.edit_message_text(
            TEXT[new_lang]["lang_saved"],
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Back", callback_data="back")]]
            ),
        )
        return

    if action == "subscribe":
        current = is_subscribed(user_id)
        await query.edit_message_text(
            TEXT[lang]["sub_on"] if current else TEXT[lang]["sub_off"],
            parse_mode="HTML",
            reply_markup=subscription_keyboard(current),
        )
        return

    if action == "toggle_sub":
        new_value = not is_subscribed(user_id)
        set_subscription(user_id, new_value)
        await query.edit_message_text(
            TEXT[lang]["sub_on"] if new_value else TEXT[lang]["sub_off"],
            parse_mode="HTML",
            reply_markup=subscription_keyboard(new_value),
        )
        return

    key_map = {
        "live_now": "live",
        "cricket": "cricket",
        "football": "football",
        "upcoming": "upcoming",
        "results": "results",
        "news": "news",
    }
    text_key = key_map.get(action)
    if text_key:
        extra_buttons = [[InlineKeyboardButton("⬅️ Back", callback_data="back")]]
        if action == "live_now":
            extra_buttons.insert(
                0,
                [InlineKeyboardButton("🔴 Open Fantzo Live", url=FANTZO_LIVE)],
            )
        await query.edit_message_text(
            TEXT[lang][text_key],
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(extra_buttons),
            disable_web_page_preview=True,
        )
        return

    await query.edit_message_text(
        TEXT[lang]["welcome"],
        parse_mode="HTML",
        reply_markup=main_keyboard(),
    )


def run() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is required")

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CallbackQueryHandler(callback_router))

    logger.info("Starting Fantzo Sports Updates bot")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    run()
