import logging
import os
from urllib.parse import urlencode

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    WebAppInfo,
)
from telegram.ext import CommandHandler

import bot_persistent as app
import fantzo_analytics as analytics
import fantzo_live_tv
import fantzo_reminders as reminders
import private_apk_upload
import trial_live_tv

logger = logging.getLogger(__name__)

SKY_ADMIN_BASE_URL = os.getenv("SKY_ADMIN_BASE_URL", "").strip().rstrip("/")
SKY_ADMIN_TEST_TOKEN = os.getenv("SKY_ADMIN_TEST_TOKEN", "").strip()
LIVE_TV_MODE = os.getenv("LIVE_TV_MODE", "admin").strip().lower()
if LIVE_TV_MODE not in {"off", "admin", "public"}:
    LIVE_TV_MODE = "admin"


def tracked_url(content: str) -> str:
    return analytics.tracking_url(content)


def mini_app_button(label: str, content: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        label,
        web_app=WebAppInfo(url=tracked_url(content)),
    )


def sky_admin_url() -> str:
    if not SKY_ADMIN_BASE_URL or not SKY_ADMIN_TEST_TOKEN:
        return ""
    return f"{SKY_ADMIN_BASE_URL}/open?{urlencode({'key': SKY_ADMIN_TEST_TOKEN})}"


def premium_main_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [mini_app_button("🔥 JOIN FANTZO NOW 🔥", "home_join_cta")],
        [
            InlineKeyboardButton("🔴 Live Now", callback_data="live_now"),
            InlineKeyboardButton("🔥 Featured", callback_data="trending"),
        ],
    ]
    if LIVE_TV_MODE == "public" and fantzo_live_tv.is_public_enabled():
        rows.append([InlineKeyboardButton(     "📺 LIVE TV",     web_app=WebAppInfo(url=sky_admin_url()) )("📺 LIVE TV")])
    rows.extend(
        [
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
    return InlineKeyboardMarkup(rows)


def premium_join_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [mini_app_button("🔥 JOIN FANTZO NOW 🔥", "join_screen_cta")],
            [mini_app_button("✨ OPEN FANTZO", "join_screen_explore")],
            [InlineKeyboardButton("⬅️ Back to Home", callback_data="back")],
        ]
    )


def premium_explore_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [mini_app_button("✨ OPEN FANTZO", "explore_home")],
        [mini_app_button("🚀 JOIN FANTZO NOW", "explore_join")],
    ]
    if LIVE_TV_MODE == "public" and fantzo_live_tv.is_public_enabled():
        rows.append([InlineKeyboardButton(     "📺 LIVE TV",     web_app=WebAppInfo(url=sky_admin_url()) )("📺 OPEN LIVE TV")])
    rows.append([InlineKeyboardButton("⬅️ Back to Home", callback_data="back")])
    return InlineKeyboardMarkup(rows)


app.core.main_keyboard = premium_main_keyboard
app.core.join_keyboard = premium_join_keyboard
app.core.explore_keyboard = premium_explore_keyboard


# Capture Fantzo activity without rewriting the existing bot/business handlers.
_original_track = app.core.track
_original_touch_user = app.core.touch_user
_original_start = app.start
_original_admin = app.core.admin


def _business_connection_id() -> str:
    try:
        with app.core.db() as conn:
            row = conn.execute(
                "SELECT connection_id FROM business_connections WHERE enabled = 1 ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
        return str(row["connection_id"]) if row and row["connection_id"] else ""
    except Exception:
        return ""


def _category_from_action(action: str) -> str:
    if ":" in action:
        return action.split(":", 1)[1]
    if action in {"cricket", "football", "sports", "live_now", "trending"}:
        return action
    return "general"


def tracked_core_event(user_id: int, action: str):
    result = _original_track(user_id, action)
    try:
        if action.startswith("business_dm:"):
            reminders.touch_user(
                "business_dm",
                user_id,
                _category_from_action(action),
                _business_connection_id(),
            )
        else:
            reminders.touch_user("bot", user_id, _category_from_action(action))
    except Exception:
        logger.exception("Could not update Fantzo reminder activity from track event")
    return result


def tracked_touch_user(update):
    result = _original_touch_user(update)
    try:
        user = update.effective_user
        if user:
            reminders.touch_user("bot", user.id, "general")
    except Exception:
        logger.exception("Could not update Fantzo reminder activity from user touch")
    return result


app.core.track = tracked_core_event
app.core.touch_user = tracked_touch_user


async def smart_start(update, context) -> None:
    user = update.effective_user
    arg = (context.args[0].lower() if context.args else "")
    if user and arg == "stopreminders":
        reminders.set_opt_out("bot", user.id, True)
        reminders.set_opt_out("business_dm", user.id, True)
        await update.effective_message.reply_text(
            "🔕 <b>Fantzo reminders are OFF.</b>\n\nYou can still use Fantzo normally anytime.",
            parse_mode="HTML",
        )
        return
    await _original_start(update, context)


app.start = smart_start


async def smart_admin(update, context) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message or user.id != app.core.ADMIN_USER_ID:
        return

    await _original_admin(update, context)

    if LIVE_TV_MODE not in {"admin", "public"}:
        return

    url = sky_admin_url()
    if not url:
        await message.reply_text(
            "⚠️ <b>Live TV mode is enabled, but the private Sky admin URL is not configured.</b>",
            parse_mode="HTML",
        )
        return

    await message.reply_text(
        f"📺 <b>LIVE TV CONTROL</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"Current mode: <b>{LIVE_TV_MODE.upper()}</b>\n\n"
        "Open the private Sky test below.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("📺 OPEN LIVE TV", web_app=WebAppInfo(url=url))]]
        ),
        disable_web_page_preview=True,
    )


app.core.admin = smart_admin


async def stop_reminders_command(update, context) -> None:
    user = update.effective_user
    if not user:
        return
    reminders.set_opt_out("bot", user.id, True)
    reminders.set_opt_out("business_dm", user.id, True)
    await update.effective_message.reply_text(
        "🔕 <b>Fantzo reminders are OFF.</b>\n\nYou can still open the bot and Fantzo whenever you want.",
        parse_mode="HTML",
    )


async def reminder_stats_command(update, context) -> None:
    user = update.effective_user
    if not user or user.id != app.core.ADMIN_USER_ID:
        return
    data = reminders.stats()
    await update.effective_message.reply_text(
        "📊 <b>Fantzo Reminder Stats</b>\n\n"
        f"Eligible users: <b>{data['users']}</b>\n"
        f"Business DM: <b>{data['dm']}</b>\n"
        f"Bot users: <b>{data['bot']}</b>\n"
        f"Reminders sent: <b>{data['sent']}</b>",
        parse_mode="HTML",
    )


async def live_tv_admin_command(update, context) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message or user.id != app.core.ADMIN_USER_ID:
        return

    if LIVE_TV_MODE == "off":
        await message.reply_text(
            "⛔ <b>Live TV mode is OFF.</b>",
            parse_mode="HTML",
        )
        return

    url = sky_admin_url()
    if not url:
        await message.reply_text(
            "⚠️ <b>Sky admin Live TV is not configured.</b>",
            parse_mode="HTML",
        )
        return

    try:
        app.core.track(user.id, "admin_sky_live_open")
    except Exception:
        logger.exception("Could not track admin Sky Live open")

    await message.reply_text(
        "📺 <b>FANTZO LIVE TV · ADMIN</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"Current mode: <b>{LIVE_TV_MODE.upper()}</b>\n"
        "Private Sky Live test with the existing admin flow.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("▶ OPEN SKY LIVE · ADMIN", web_app=WebAppInfo(url=url))]]
        ),
        disable_web_page_preview=True,
    )


async def configure_telegram_ui(application) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Open Fantzo Sports Hub"),
            BotCommand("team", "Find a cricket or football team"),
            BotCommand("sports", "View Fantzo sports coverage"),
            BotCommand("help", "Fantzo quick guide"),
            BotCommand("stop", "Stop Fantzo reminders"),
            BotCommand("setbanner", "Change the Fantzo home banner"),
        ]
    )
    await application.bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text="Join Fantzo",
            web_app=WebAppInfo(url=tracked_url("telegram_native_menu")),
        )
    )
    application.add_handler(CommandHandler("stop", stop_reminders_command))
    application.add_handler(CommandHandler("reminderstats", reminder_stats_command))
    application.add_handler(CommandHandler("livetvadmin", live_tv_admin_command))
    reminders.ensure_tables()
    reminders.start_background_loop(application)
    logger.info(
        "Fantzo tracked Mini App menu, Live TV single-switch mode=%s, and smart reminder engine configured",
        LIVE_TV_MODE,
    )


app.configure_telegram_ui = configure_telegram_ui


if __name__ == "__main__":
    private_apk_upload.install_on_tracking_handler(analytics)
    trial_live_tv.install_on_tracking_handler(analytics)
    fantzo_live_tv.install_on_tracking_handler(analytics)
    analytics.start_tracking_server()
    logger.info("Starting Fantzo with LIVE_TV_MODE=%s", LIVE_TV_MODE)
    app.run()
