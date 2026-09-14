import asyncio
import logging
import os
from datetime import datetime, timezone
from html import escape
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


# =========================================================
# LIVE TV SETTINGS
# =========================================================

SKY_ADMIN_BASE_URL = os.getenv("SKY_ADMIN_BASE_URL", "").strip().rstrip("/")
SKY_ADMIN_TEST_TOKEN = os.getenv("SKY_ADMIN_TEST_TOKEN", "").strip()

LIVE_TV_MODE = os.getenv("LIVE_TV_MODE", "admin").strip().lower()
if LIVE_TV_MODE not in {"off", "admin", "public"}:
    LIVE_TV_MODE = "admin"

# Public Live TV availability override.
# auto = decide from today's sports data
# on   = always show the Live TV open option
# off  = always show the unavailable screen
LIVE_TV_STATUS = os.getenv("LIVE_TV_STATUS", "auto").strip().lower()
if LIVE_TV_STATUS not in {"auto", "on", "off"}:
    LIVE_TV_STATUS = "auto"


# =========================================================
# NORMAL FANTZO HELPERS
# =========================================================

def tracked_url(content: str) -> str:
    return analytics.tracking_url(content)


def mini_app_button(label: str, content: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        label,
        web_app=WebAppInfo(url=tracked_url(content)),
    )


# =========================================================
# PREMIUM SPORTS UI COPY
# =========================================================

def install_premium_ui_copy() -> None:
    """Keep the first screen short, sports-first, and easy to scan."""

    app.core.TEXT["en"]["welcome"] = (
        "🏟 <b>FANTZO SPORTS</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "<b>Your sports. Live.</b>\n\n"
        "🔴 Live scores & match action\n"
        "🏏 Cricket   •   ⚽ Football\n"
        "📅 Fixtures   •   🏆 Results\n"
        "🔔 Match alerts & fast updates\n\n"
        "Choose what you want to follow 👇"
    )

    app.core.TEXT["hi"]["welcome"] = (
        "🏟 <b>FANTZO SPORTS</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "<b>आपके खेल। लाइव।</b>\n\n"
        "🔴 लाइव स्कोर और मैच अपडेट\n"
        "🏏 क्रिकेट   •   ⚽ फुटबॉल\n"
        "📅 फिक्स्चर   •   🏆 रिज़ल्ट\n"
        "🔔 मैच अलर्ट और तेज़ अपडेट\n\n"
        "अपना स्पोर्ट चुनें 👇"
    )

    app.core.TEXT["en"]["explore"] = (
        "✨ <b>EXPLORE FANTZO</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Discover featured sports, find a team, or open the full Fantzo experience."
    )

    app.core.TEXT["hi"]["explore"] = (
        "✨ <b>EXPLORE FANTZO</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Featured sports देखें, अपनी team खोजें या पूरा Fantzo experience खोलें।"
    )


install_premium_ui_copy()


# =========================================================
# PRIVATE SKY ADMIN ROUTE
# =========================================================

def sky_admin_url() -> str:
    if not SKY_ADMIN_BASE_URL or not SKY_ADMIN_TEST_TOKEN:
        return ""

    query = urlencode({"key": SKY_ADMIN_TEST_TOKEN})
    return f"{SKY_ADMIN_BASE_URL}/open?{query}"


# =========================================================
# PUBLIC LIVE TV STATUS GATE
# =========================================================

def _public_live_tv_status_button(label: str = "📺 WATCH LIVE TV") -> InlineKeyboardButton:
    return InlineKeyboardButton(label, callback_data="live_tv_status")


def _back_home_button() -> InlineKeyboardButton:
    return InlineKeyboardButton("⬅️ BACK TO HOME", callback_data="back")


def _match_local_datetime(match):
    dt = app.core._match_datetime(match)
    if not dt:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(app.core.APP_TIMEZONE)


def _match_title(match, sport: str) -> str:
    icon = "🏏" if sport == "cricket" else "⚽"
    home = escape(app.core._team_name(match, "home"))
    away = escape(app.core._team_name(match, "away"))
    return f"{icon} <b>{home}</b> vs <b>{away}</b>"


def _match_time_text(match) -> str:
    dt = _match_local_datetime(match)
    if not dt:
        return "Time TBA"
    return dt.strftime("%I:%M %p").lstrip("0")


async def _today_live_tv_snapshot():
    """Return (all_today, live_now, future_today) for cricket + football."""

    today = datetime.now(app.core.APP_TIMEZONE).date().isoformat()
    now = datetime.now(app.core.APP_TIMEZONE)

    cricket_result, football_result = await asyncio.gather(
        app.core.get_sport_matches_for_date("cricket", today),
        app.core.get_sport_matches_for_date("football", today),
        return_exceptions=True,
    )

    results = [
        ("cricket", cricket_result),
        ("football", football_result),
    ]

    all_today = []
    live_now = []
    future_today = []
    successful_sources = 0

    for sport, result in results:
        if isinstance(result, Exception):
            logger.warning("Live TV status lookup failed for %s: %s", sport, result)
            continue

        successful_sources += 1
        matches = result if isinstance(result, list) else []

        for match in matches:
            if not isinstance(match, dict):
                continue

            all_today.append((sport, match))

            if app.core._is_live(match, sport):
                live_now.append((sport, match))
                continue

            match_dt = _match_local_datetime(match)
            if match_dt and match_dt > now:
                future_today.append((match_dt, sport, match))

    if successful_sources == 0:
        raise RuntimeError("Sports data is temporarily unavailable")

    future_today.sort(key=lambda item: item[0])
    return all_today, live_now, future_today


def _live_available_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [fantzo_live_tv.live_tv_button("▶ OPEN LIVE TV")],
        [
            InlineKeyboardButton("🔄 CHECK STATUS", callback_data="live_tv_status"),
            InlineKeyboardButton("🔴 LIVE SCORES", callback_data="live_now"),
        ],
        [_back_home_button()],
    ])


def _not_live_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 CHECK AGAIN", callback_data="live_tv_status"),
            InlineKeyboardButton("📅 TODAY'S FIXTURES", callback_data="upcoming"),
        ],
        [_back_home_button()],
    ])


async def live_tv_status_screen(update, context) -> None:
    query = update.callback_query
    if not query:
        return

    await query.answer("Checking Live TV…")

    if LIVE_TV_MODE != "public":
        await query.edit_message_text(
            "📺 <b>FANTZO LIVE TV</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Live TV is not currently available for public viewing.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[_back_home_button()]]),
        )
        return

    if LIVE_TV_STATUS == "off":
        await query.edit_message_text(
            "📺 <b>FANTZO LIVE TV</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "😴 <b>No live broadcast right now.</b>\n\n"
            "Check today's fixtures or come back later.",
            parse_mode="HTML",
            reply_markup=_not_live_keyboard(),
        )
        return

    if LIVE_TV_STATUS == "on":
        await query.edit_message_text(
            "📺 <b>FANTZO LIVE TV</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "🔴 <b>Live TV is available now.</b>\n\n"
            "Tap below to open the Fantzo MiniTV player.",
            parse_mode="HTML",
            reply_markup=_live_available_keyboard(),
        )
        return

    try:
        all_today, live_now, future_today = await _today_live_tv_snapshot()
    except Exception:
        logger.exception("Could not check Live TV match status")
        await query.edit_message_text(
            "📺 <b>FANTZO LIVE TV</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "⚠️ <b>Match status is temporarily unavailable.</b>\n\n"
            "Please check again in a moment.",
            parse_mode="HTML",
            reply_markup=_not_live_keyboard(),
        )
        return

    if live_now:
        lines = [
            "📺 <b>FANTZO LIVE TV</b>",
            "━━━━━━━━━━━━━━━━━━",
            "",
            f"🔴 <b>{len(live_now)} match{'es' if len(live_now) != 1 else ''} live now</b>",
            "",
        ]

        for sport, match in live_now[:3]:
            lines.append(_match_title(match, sport))

        if len(live_now) > 3:
            lines.append(f"➕ {len(live_now) - 3} more live")

        lines.extend(["", "Tap below to open Live TV."])

        await query.edit_message_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=_live_available_keyboard(),
        )
        return

    if future_today:
        next_dt, sport, match = future_today[0]
        await query.edit_message_text(
            "📺 <b>FANTZO LIVE TV</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "😴 <b>No live match right now.</b>\n\n"
            "📅 <b>Next match today</b>\n"
            f"{_match_title(match, sport)}\n"
            f"🕒 {_match_time_text(match)} Dubai time\n\n"
            "Check again when the match starts.",
            parse_mode="HTML",
            reply_markup=_not_live_keyboard(),
        )
        return

    if all_today:
        await query.edit_message_text(
            "📺 <b>FANTZO LIVE TV</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "🏁 <b>No live match right now.</b>\n\n"
            "Today's listed matches have finished or are no longer live.\n\n"
            "Check upcoming fixtures for the next action.",
            parse_mode="HTML",
            reply_markup=_not_live_keyboard(),
        )
        return

    await query.edit_message_text(
        "📺 <b>FANTZO LIVE TV</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "🏟 <b>NO MATCHES TODAY</b>\n\n"
        "There are no scheduled cricket or football matches today.\n\n"
        "Check upcoming fixtures or come back later.",
        parse_mode="HTML",
        reply_markup=_not_live_keyboard(),
    )


# =========================================================
# MAIN HOME KEYBOARD
# =========================================================

def premium_main_keyboard() -> InlineKeyboardMarkup:
    """Sports-first home with fewer, stronger primary actions."""

    rows = [
        [InlineKeyboardButton("🔴 LIVE NOW", callback_data="live_now")],
        [
            InlineKeyboardButton("🏏 CRICKET", callback_data="cricket"),
            InlineKeyboardButton("⚽ FOOTBALL", callback_data="football"),
        ],
        [
            InlineKeyboardButton("📅 FIXTURES", callback_data="upcoming"),
            InlineKeyboardButton("🏆 RESULTS", callback_data="results"),
        ],
    ]

    if LIVE_TV_MODE == "public":
        rows.append([_public_live_tv_status_button()])

    rows.extend([
        [
            InlineKeyboardButton("🔔 MATCH ALERTS", callback_data="subscribe"),
            InlineKeyboardButton("⚙️ SETTINGS", callback_data="settings"),
        ],
        [
            InlineKeyboardButton("✨ EXPLORE", callback_data="explore"),
            InlineKeyboardButton("🔎 FIND TEAM", callback_data="find_team"),
        ],
        [mini_app_button("✨ OPEN FANTZO", "home_open_fantzo")],
    ])

    return InlineKeyboardMarkup(rows)


# =========================================================
# JOIN KEYBOARD
# =========================================================

def premium_join_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [mini_app_button("✨ OPEN FANTZO", "join_screen_open")],
        [
            InlineKeyboardButton("🔴 LIVE NOW", callback_data="live_now"),
            InlineKeyboardButton("📅 FIXTURES", callback_data="upcoming"),
        ],
        [_back_home_button()],
    ])


# =========================================================
# EXPLORE KEYBOARD
# =========================================================

def premium_explore_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("🔥 FEATURED", callback_data="trending"),
            InlineKeyboardButton("🔎 FIND TEAM", callback_data="find_team"),
        ],
        [mini_app_button("✨ OPEN FANTZO", "explore_open_fantzo")],
    ]

    if LIVE_TV_MODE == "public":
        rows.append([_public_live_tv_status_button()])

    rows.append([_back_home_button()])
    return InlineKeyboardMarkup(rows)


# =========================================================
# INSTALL KEYBOARDS + CALLBACK ROUTER
# =========================================================

app.core.main_keyboard = premium_main_keyboard
app.core.join_keyboard = premium_join_keyboard
app.core.explore_keyboard = premium_explore_keyboard

_original_callback_router = app.core.callback_router


async def smart_callback_router(update, context) -> None:
    query = update.callback_query

    if query and query.data == "live_tv_status":
        user = update.effective_user
        if user:
            app.core.track(user.id, "live_tv_status")
        await live_tv_status_screen(update, context)
        return

    await _original_callback_router(update, context)


app.core.callback_router = smart_callback_router


# =========================================================
# TRACKING / REMINDER HOOKS
# =========================================================

_original_track = app.core.track
_original_touch_user = app.core.touch_user
_original_admin = app.core.admin


def _business_connection_id() -> str:
    try:
        with app.core.db() as conn:
            row = conn.execute(
                """
                SELECT connection_id
                FROM business_connections
                WHERE enabled = 1
                ORDER BY updated_at DESC
                LIMIT 1
                """
            ).fetchone()

        if row and row["connection_id"]:
            return str(row["connection_id"])
    except Exception:
        pass

    return ""


def _category_from_action(action: str) -> str:
    if ":" in action:
        return action.split(":", 1)[1]

    if action in {
        "cricket",
        "football",
        "sports",
        "live_now",
        "trending",
        "live_tv_status",
    }:
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
            reminders.touch_user(
                "bot",
                user_id,
                _category_from_action(action),
            )
    except Exception:
        logger.exception("Could not update reminder activity")

    return result


def tracked_touch_user(update):
    result = _original_touch_user(update)

    try:
        user = update.effective_user
        if user:
            reminders.touch_user("bot", user.id, "general")
    except Exception:
        logger.exception("Could not update reminder user")

    return result


app.core.track = tracked_core_event
app.core.touch_user = tracked_touch_user


# =========================================================
# /START
# =========================================================

async def smart_start(update, context) -> None:
    user = update.effective_user
    arg = context.args[0].lower() if context.args else ""

    if user and arg == "stopreminders":
        reminders.set_opt_out("bot", user.id, True)
        reminders.set_opt_out("business_dm", user.id, True)

        await update.effective_message.reply_text(
            "🔕 <b>Fantzo reminders are OFF.</b>",
            parse_mode="HTML",
        )
        return

    await app.show_home(update, context)


app.start = smart_start


# =========================================================
# ADMIN PANEL
# =========================================================

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
            "⚠️ <b>Private Sky admin URL is not configured.</b>",
            parse_mode="HTML",
        )
        return

    await message.reply_text(
        "📺 <b>LIVE TV CONTROL</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"Current mode: <b>{LIVE_TV_MODE.upper()}</b>\n"
        f"Public status: <b>{LIVE_TV_STATUS.upper()}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📺 OPEN LIVE TV",
                    web_app=WebAppInfo(url=url),
                )
            ]
        ]),
        disable_web_page_preview=True,
    )


app.core.admin = smart_admin


# =========================================================
# /LIVETVADMIN
# =========================================================

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

    await message.reply_text(
        "📺 <b>FANTZO LIVE TV · ADMIN</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"Current mode: <b>{LIVE_TV_MODE.upper()}</b>\n"
        f"Public status: <b>{LIVE_TV_STATUS.upper()}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "▶ OPEN SKY LIVE · ADMIN",
                    web_app=WebAppInfo(url=url),
                )
            ]
        ]),
        disable_web_page_preview=True,
    )


# =========================================================
# TELEGRAM UI
# =========================================================

async def configure_telegram_ui(application) -> None:
    await application.bot.set_my_commands([
        BotCommand("start", "Open Fantzo Sports"),
        BotCommand("team", "Find a cricket or football team"),
        BotCommand("sports", "View Fantzo sports coverage"),
        BotCommand("help", "Fantzo quick guide"),
    ])

    await application.bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text="Open Fantzo",
            web_app=WebAppInfo(url=tracked_url("telegram_native_menu")),
        )
    )

    application.add_handler(
        CommandHandler("livetvadmin", live_tv_admin_command)
    )

    reminders.ensure_tables()
    reminders.start_background_loop(application)


app.configure_telegram_ui = configure_telegram_ui


# =========================================================
# START FANTZO
# =========================================================

if __name__ == "__main__":
    private_apk_upload.install_on_tracking_handler(analytics)
    trial_live_tv.install_on_tracking_handler(analytics)
    fantzo_live_tv.install_on_tracking_handler(analytics)

    analytics.start_tracking_server()

    logger.info(
        "Starting Fantzo with LIVE_TV_MODE=%s LIVE_TV_STATUS=%s",
        LIVE_TV_MODE,
        LIVE_TV_STATUS,
    )

    app.run()
