import logging
import os
from urllib.parse import urlencode

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    ReplyKeyboardMarkup,
    Update,
    WebAppInfo,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import bot as core

logger = logging.getLogger(__name__)

QUICK_MENU_LABEL = "⚡ Fantzo Menu"
QUICK_MENU = ReplyKeyboardMarkup(
    [[QUICK_MENU_LABEL]],
    resize_keyboard=True,
    is_persistent=True,
    input_field_placeholder="Tap Fantzo Menu anytime",
)

BANNER_ENV = "FANTZO_BANNER_FILE_ID"
MINI_APP_URL = os.getenv("FANTZO_MINI_APP_URL", "https://www.fantzo.com").strip()


def tracked_url(content: str) -> str:
    separator = "&" if "?" in MINI_APP_URL else "?"
    query = urlencode(
        {
            "utm_source": "telegram",
            "utm_medium": "bot",
            "utm_campaign": "fantzo_sports_hub",
            "utm_content": content,
        }
    )
    return f"{MINI_APP_URL}{separator}{query}"


def mini_app_button(label: str, content: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(label, web_app=WebAppInfo(url=tracked_url(content)))


def premium_main_keyboard() -> InlineKeyboardMarkup:
    """Fantzo home menu with Join Fantzo as the dominant Mini App CTA."""
    return InlineKeyboardMarkup(
        [
            [mini_app_button("🔥 JOIN FANTZO NOW 🔥", "home_join_cta")],
            [
                InlineKeyboardButton("🔴 Live Now", callback_data="live_now"),
                InlineKeyboardButton("🔥 Featured", callback_data="trending"),
            ],
            [
                InlineKeyboardButton("🏏 Cricket", callback_data="cricket"),
                InlineKeyboardButton("⚽ Football", callback_data="football"),
            ],
            [
                InlineKeyboardButton("🗓 Upcoming", callback_data="upcoming"),
                InlineKeyboardButton("✅ Results", callback_data="results"),
            ],
            [
                InlineKeyboardButton("🔎 Find Team", callback_data="find_team"),
                InlineKeyboardButton("🔔 Match Alerts", callback_data="subscribe"),
            ],
            [
                InlineKeyboardButton("✨ Explore Fantzo", callback_data="explore"),
                InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
            ],
        ]
    )


def premium_join_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [mini_app_button("🔥 JOIN FANTZO NOW 🔥", "join_screen_cta")],
            [mini_app_button("✨ OPEN FANTZO", "join_screen_explore")],
            [InlineKeyboardButton("⬅️ Back to Home", callback_data="back")],
        ]
    )


# Override the core menus everywhere, including Back to Home and Join actions.
core.main_keyboard = premium_main_keyboard
core.join_keyboard = premium_join_keyboard


def ensure_settings_table() -> None:
    with core.db() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"
        )


def get_banner_file_id() -> str:
    env_value = os.getenv(BANNER_ENV, "").strip()
    if env_value:
        return env_value

    try:
        ensure_settings_table()
        with core.db() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = 'home_banner_file_id'"
            ).fetchone()
        return str(row["value"]).strip() if row and row["value"] else ""
    except Exception as exc:
        logger.warning("Could not read Fantzo banner setting: %s", exc)
        return ""


def save_banner_file_id(file_id: str) -> None:
    ensure_settings_table()
    with core.db() as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES('home_banner_file_id', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (file_id,),
        )


async def configure_telegram_ui(application: Application) -> None:
    """Configure Telegram native UI with a direct tracked Fantzo Mini App launcher."""
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Open Fantzo Sports Hub"),
            BotCommand("team", "Find a cricket or football team"),
            BotCommand("sports", "View Fantzo sports coverage"),
            BotCommand("help", "Fantzo quick guide"),
            BotCommand("setbanner", "Change the Fantzo home banner"),
        ]
    )
    await application.bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text="Join Fantzo",
            web_app=WebAppInfo(url=tracked_url("telegram_native_menu")),
        )
    )
    logger.info("Fantzo Telegram Mini App menu configured")


async def show_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    core.touch_user(update)
    lang = core.get_user_lang(update.effective_user.id)
    banner_file_id = get_banner_file_id()

    if banner_file_id:
        try:
            await update.effective_message.reply_photo(
                photo=banner_file_id,
                caption=core.TEXT[lang]["welcome"],
                parse_mode="HTML",
                reply_markup=core.main_keyboard(),
            )
            return
        except Exception as exc:
            logger.warning("Fantzo banner send failed, falling back to text: %s", exc)

    await update.effective_message.reply_text(
        core.TEXT[lang]["welcome"],
        parse_mode="HTML",
        reply_markup=core.main_keyboard(),
        disable_web_page_preview=True,
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_home(update, context)
    await update.effective_message.reply_text(
        "⚡ <b>Quick access enabled</b>\n\n"
        "Tap <b>⚡ Fantzo Menu</b> below anytime for sports.\n"
        "Telegram's <b>Join Fantzo</b> Menu button opens Fantzo inside Telegram.",
        parse_mode="HTML",
        reply_markup=QUICK_MENU,
    )


async def quick_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    core.track(update.effective_user.id, "quick_menu")
    await show_home(update, context)


async def setbanner_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return

    if user.id != core.ADMIN_USER_ID:
        await message.reply_text("This command is restricted.")
        return

    context.user_data["awaiting_fantzo_banner"] = True
    await message.reply_text(
        "🖼 <b>Send the Fantzo banner now.</b>\n\n"
        "Send it as a normal Telegram <b>photo</b>. No caption is required.\n"
        "I will save Telegram's own image reference and confirm when it is ready.",
        parse_mode="HTML",
    )


async def banner_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or user.id != core.ADMIN_USER_ID or not message or not message.photo:
        return

    caption = (message.caption or "").strip().lower()
    waiting = bool(context.user_data.get("awaiting_fantzo_banner"))
    caption_trigger = caption in {"/setbanner", "setbanner"}

    if not waiting and not caption_trigger:
        return

    file_id = message.photo[-1].file_id
    save_banner_file_id(file_id)
    context.user_data["awaiting_fantzo_banner"] = False
    logger.info("Fantzo home banner captured successfully")

    await message.reply_text(
        "✅ <b>Fantzo banner saved.</b>\n\n"
        "It will now appear above the premium home menu.\n"
        "Tap <b>⚡ Fantzo Menu</b> to test it.",
        parse_mode="HTML",
        reply_markup=QUICK_MENU,
    )


def run() -> None:
    if not core.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is required")

    core.init_db()
    ensure_settings_table()
    app = (
        Application.builder()
        .token(core.BOT_TOKEN)
        .post_init(configure_telegram_ui)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", core.help_command))
    app.add_handler(CommandHandler("sports", core.sports_command))
    app.add_handler(CommandHandler("team", core.team_command))
    app.add_handler(CommandHandler("admin", core.admin))
    app.add_handler(CommandHandler("broadcast", core.broadcast))
    app.add_handler(CommandHandler("setbanner", setbanner_command))
    app.add_handler(
        MessageHandler(filters.TEXT & filters.Regex(r"^⚡ Fantzo Menu$"), quick_menu)
    )
    app.add_handler(MessageHandler(filters.PHOTO, banner_upload))
    app.add_handler(CallbackQueryHandler(core.callback_router))

    logger.info("Starting Fantzo Premium Sports Hub with Join Fantzo Mini App CTA")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    run()
