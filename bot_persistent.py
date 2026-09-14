import logging
import os

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
    BusinessConnectionHandler,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import bot as core
import fantzo_analytics as analytics
import fantzo_autoreply
import fantzo_business
import trial_live_tv

logger = logging.getLogger(__name__)


def _install_ibetin_core_branding() -> None:
    """Rebrand the locked Fantzo core at runtime without changing its behavior."""
    replacements = (
        ("FANTZO", "IBETIN"),
        ("Fantzo", "IBETIN"),
        ("fantzo.com", "ibetin.com"),
    )

    for language in core.TEXT.values():
        for key, value in list(language.items()):
            if not isinstance(value, str):
                continue
            branded = value
            for old, new in replacements:
                branded = branded.replace(old, new)
            language[key] = branded

    home = os.getenv("IBETIN_HOME_URL", "https://ibetin.com").strip().rstrip("/")
    core.FANTZO_HOME = home
    core.FANTZO_LIVE = os.getenv("IBETIN_LIVE_URL", f"{home}/en/live").strip()
    core.FANTZO_SLOTS = os.getenv("IBETIN_SLOTS_URL", f"{home}/en/slots").strip()
    core.FANTZO_REGISTER = os.getenv(
        "IBETIN_REGISTER_URL", f"{home}/en/registration"
    ).strip()


_install_ibetin_core_branding()

QUICK_MENU_LABEL = "⚡ IBETIN Menu"
QUICK_MENU = ReplyKeyboardMarkup(
    [[QUICK_MENU_LABEL]],
    resize_keyboard=True,
    is_persistent=True,
    input_field_placeholder="Tap IBETIN Menu anytime",
)

BANNER_ENV = "IBETIN_BANNER_FILE_ID"
MINI_APP_URL = os.getenv(
    "IBETIN_MINI_APP_URL",
    os.getenv("FANTZO_MINI_APP_URL", "https://ibetin.com"),
).strip()


def tracked_url(content: str) -> str:
    return analytics.tracking_url(content)


def mini_app_button(label: str, content: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(label, web_app=WebAppInfo(url=tracked_url(content)))


def premium_main_keyboard() -> InlineKeyboardMarkup:
    """IBETIN home menu with Join IBETIN as the dominant Mini App CTA."""
    return InlineKeyboardMarkup(
        [
            [mini_app_button("🔥 JOIN IBETIN NOW 🔥", "home_join_cta")],
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
                InlineKeyboardButton("✨ Explore IBETIN", callback_data="explore"),
                InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
            ],
        ]
    )


def premium_join_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [mini_app_button("🔥 JOIN IBETIN NOW 🔥", "join_screen_cta")],
            [mini_app_button("✨ OPEN IBETIN", "join_screen_explore")],
            [InlineKeyboardButton("⬅️ Back to Home", callback_data="back")],
        ]
    )


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
        logger.warning("Could not read IBETIN banner setting: %s", exc)
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
    """Configure Telegram native UI with a direct tracked IBETIN Mini App launcher."""
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Open IBETIN Sports Hub"),
            BotCommand("team", "Find a cricket or football team"),
            BotCommand("sports", "View IBETIN sports coverage"),
            BotCommand("help", "IBETIN quick guide"),
            BotCommand("setbanner", "Change the IBETIN home banner"),
        ]
    )
    await application.bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text="Join IBETIN",
            web_app=WebAppInfo(url=tracked_url("telegram_native_menu")),
        )
    )
    logger.info("IBETIN Telegram Mini App menu configured")


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
            logger.warning("IBETIN banner send failed, falling back to text: %s", exc)

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
        "Tap <b>⚡ IBETIN Menu</b> below anytime for sports.\n"
        "Telegram's <b>Join IBETIN</b> Menu button opens IBETIN inside Telegram.",
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

    context.user_data["awaiting_ibetin_banner"] = True
    await message.reply_text(
        "🖼 <b>Send the IBETIN banner now.</b>\n\n"
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
    waiting = bool(context.user_data.get("awaiting_ibetin_banner"))
    caption_trigger = caption in {"/setbanner", "setbanner"}

    if not waiting and not caption_trigger:
        return

    file_id = message.photo[-1].file_id
    save_banner_file_id(file_id)
    context.user_data["awaiting_ibetin_banner"] = False
    logger.info("IBETIN home banner captured successfully")

    await message.reply_text(
        "✅ <b>IBETIN banner saved.</b>\n\n"
        "It will now appear above the premium home menu.\n"
        "Tap <b>⚡ IBETIN Menu</b> to test it.",
        parse_mode="HTML",
        reply_markup=QUICK_MENU,
    )


def run() -> None:
    if not core.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is required")

    core.init_db()
    ensure_settings_table()
    analytics.ensure_tables()
    fantzo_autoreply.ensure_setting()
    fantzo_business.ensure_tables()

    app = (
        Application.builder()
        .token(core.BOT_TOKEN)
        .post_init(configure_telegram_ui)
        .build()
    )

    app.add_handler(BusinessConnectionHandler(fantzo_business.business_connection_update))
    app.add_handler(
        MessageHandler(
            filters.UpdateType.BUSINESS_MESSAGE & filters.TEXT,
            fantzo_business.business_auto_reply,
        )
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", core.help_command))
    app.add_handler(CommandHandler("sports", core.sports_command))
    app.add_handler(CommandHandler("team", core.team_command))
    app.add_handler(CommandHandler("admin", core.admin))
    app.add_handler(CommandHandler("stats", analytics.stats_command))
    app.add_handler(CommandHandler("trialtv", trial_live_tv.trial_tv_command))
    app.add_handler(CommandHandler("autoreply", fantzo_autoreply.autoreply_command))
    app.add_handler(CommandHandler("broadcast", core.broadcast))
    app.add_handler(CommandHandler("setbanner", setbanner_command))
    app.add_handler(
        MessageHandler(
            filters.UpdateType.MESSAGE
            & filters.TEXT
            & filters.Regex(r"^⚡ IBETIN Menu$"),
            quick_menu,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.UpdateType.MESSAGE & filters.TEXT & ~filters.COMMAND,
            fantzo_autoreply.auto_reply,
        )
    )
    app.add_handler(MessageHandler(filters.UpdateType.MESSAGE & filters.PHOTO, banner_upload))
    app.add_handler(CallbackQueryHandler(core.callback_router))

    logger.info(
        "Starting IBETIN Premium Sports Hub with direct-chat and Telegram Business DM auto reply"
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    run()
