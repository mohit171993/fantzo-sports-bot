import logging
import os
import re
import secrets
from pathlib import Path

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
    ApplicationHandlerStop,
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
from fantzo_brand import has_foreign_brand

logger = logging.getLogger(__name__)

QUICK_MENU_LABEL = "⚡ Fantzo Menu"
QUICK_MENU = ReplyKeyboardMarkup(
    [[QUICK_MENU_LABEL]],
    resize_keyboard=True,
    is_persistent=True,
    input_field_placeholder="Tap Fantzo Menu anytime",
)

BANNER_ENV = "FANTZO_BANNER_FILE_ID"
WELCOME_BANNER = Path(__file__).resolve().parent / "assets" / "fantzo_home_welcome.jpg"
MINI_APP_URL = os.getenv("FANTZO_MINI_APP_URL", "https://www.fantzo.com").strip()


def tracked_url(content: str) -> str:
    return analytics.tracking_url(content)


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
    caption = core.TEXT[lang]["welcome"]
    markup = core.main_keyboard()
    banner_file_id = get_banner_file_id()

    if banner_file_id:
        try:
            await update.effective_message.reply_photo(
                photo=banner_file_id,
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup,
            )
            return
        except Exception as exc:
            logger.warning("Fantzo banner send failed, falling back to text: %s", exc)

    if WELCOME_BANNER.is_file():
        try:
            with WELCOME_BANNER.open("rb") as image:
                await update.effective_message.reply_photo(
                    photo=image,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=markup,
                )
            return
        except Exception as exc:
            logger.warning("Fantzo welcome image skipped, falling back to text: %s", exc)

    await update.effective_message.reply_text(
        caption,
        parse_mode="HTML",
        reply_markup=markup,
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
        "You will see a preview to approve before the home banner changes.",
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

    if has_foreign_brand(caption):
        await message.reply_text("⛔ This upload mentions another brand. Send a Fantzo banner.")
        raise ApplicationHandlerStop

    file_id = message.photo[-1].file_id
    token = secrets.token_hex(8)
    context.user_data["pending_fantzo_home_banner"] = (token, file_id)
    context.user_data["awaiting_fantzo_banner"] = False
    await message.reply_photo(
        photo=file_id,
        caption="Fantzo home banner preview. Approve only if this visual belongs to Fantzo.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ APPROVE FANTZO", callback_data=f"fantzo_home_banner_approve_{token}"),
            InlineKeyboardButton("🗑 REJECT", callback_data=f"fantzo_home_banner_reject_{token}"),
        ]]),
    )
    raise ApplicationHandlerStop


async def home_banner_review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if not query or not user or user.id != core.ADMIN_USER_ID:
        if query:
            await query.answer("Restricted", show_alert=True)
        raise ApplicationHandlerStop

    match = re.fullmatch(r"fantzo_home_banner_(approve|reject)_([0-9a-f]{16})", str(query.data or ""))
    pending = context.user_data.get("pending_fantzo_home_banner")
    if not match or not pending or pending[0] != match.group(2):
        await query.answer("This preview expired. Upload the banner again.", show_alert=True)
        raise ApplicationHandlerStop

    context.user_data.pop("pending_fantzo_home_banner", None)
    approved = match.group(1) == "approve"
    if approved:
        save_banner_file_id(pending[1])
    await query.answer("Fantzo home banner saved" if approved else "Banner rejected")
    try:
        await query.edit_message_caption(
            caption="✅ Fantzo home banner saved." if approved else "🗑 Rejected. The home banner was not changed."
        )
    except Exception:
        logger.warning("Could not update Fantzo home banner review preview")
    raise ApplicationHandlerStop


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

    # Telegram Business integration: connection updates + incoming customer DMs.
    # Do not restrict this handler to TEXT: the first DM may be a sticker, photo,
    # voice note, video, document, or other Telegram message type.
    app.add_handler(BusinessConnectionHandler(fantzo_business.business_connection_update))
    app.add_handler(
        MessageHandler(
            filters.UpdateType.BUSINESS_MESSAGE,
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
            & filters.Regex(r"^⚡ Fantzo Menu$"),
            quick_menu,
        )
    )
    # Normal direct messages to @fantzoofficialbot remain supported separately.
    app.add_handler(
        MessageHandler(
            filters.UpdateType.MESSAGE & filters.TEXT & ~filters.COMMAND,
            fantzo_autoreply.auto_reply,
        )
    )
    app.add_handler(MessageHandler(filters.UpdateType.MESSAGE & filters.PHOTO, banner_upload))
    app.add_handler(
        CallbackQueryHandler(home_banner_review, pattern=r"^fantzo_home_banner_"),
        group=-8,
    )
    app.add_handler(CallbackQueryHandler(core.callback_router))

    logger.info(
        "Starting Fantzo Premium Sports Hub with direct-chat and Telegram Business DM auto reply"
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    run()
