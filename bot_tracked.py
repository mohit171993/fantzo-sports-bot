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

# =========================================================
# IBETIN WEBSITE
# =========================================================

IBETIN_HOME_URL = os.getenv("IBETIN_HOME_URL", "https://ibetin.com").strip().rstrip("/")
IBETIN_SPORTS_URL = os.getenv("IBETIN_SPORTS_URL", f"{IBETIN_HOME_URL}/line").strip()
IBETIN_LIVE_URL = os.getenv("IBETIN_LIVE_URL", f"{IBETIN_HOME_URL}/live").strip()
IBETIN_CASINO_URL = os.getenv("IBETIN_CASINO_URL", f"{IBETIN_HOME_URL}/casino").strip()
IBETIN_GAMES_URL = os.getenv("IBETIN_GAMES_URL", f"{IBETIN_HOME_URL}/games").strip()
IBETIN_RESULTS_URL = os.getenv("IBETIN_RESULTS_URL", f"{IBETIN_HOME_URL}/results").strip()
IBETIN_PAYMENT_URL = os.getenv(
    "IBETIN_PAYMENT_URL", f"{IBETIN_HOME_URL}/information/payment"
).strip()
IBETIN_SUPPORT_URL = os.getenv(
    "IBETIN_SUPPORT_URL", f"{IBETIN_HOME_URL}/information/contacts"
).strip()

# =========================================================
# LIVE TV SETTINGS
# =========================================================

SKY_ADMIN_BASE_URL = os.getenv("SKY_ADMIN_BASE_URL", "").strip().rstrip("/")
SKY_ADMIN_TEST_TOKEN = os.getenv("SKY_ADMIN_TEST_TOKEN", "").strip()
LIVE_TV_MODE = os.getenv("LIVE_TV_MODE", "admin").strip().lower()
if LIVE_TV_MODE not in {"off", "admin", "public"}:
    LIVE_TV_MODE = "admin"


# =========================================================
# IBETIN BRAND COPY
# =========================================================

def _install_ibetin_hub_copy() -> None:
    en = app.core.TEXT.get("en", {})
    en.update(
        {
            "welcome": (
                "⚡ <b>IBETIN HUB</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "Your quick gateway to the main IBETIN sections.\n\n"
                "🏆 Sports & pre-match\n"
                "🔴 Live events\n"
                "🎰 Live Casino\n"
                "🎮 Games\n"
                "📊 Results\n"
                "💳 Payment information\n\n"
                "You can also use the bot for cricket and football scores, team search and match alerts.\n\n"
                "Choose where you want to go 👇\n\n"
                "🔞 18+ • Play responsibly • T&Cs apply"
            ),
            "explore": (
                "🌐 <b>EXPLORE IBETIN</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "Open Sports, Live, Live Casino, Games, Results, Payments or Support directly from Telegram.\n\n"
                "🔞 18+ • Play responsibly • T&Cs apply"
            ),
            "join": (
                "🌐 <b>OPEN IBETIN</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "Open the official IBETIN website to log in, register or browse available sections.\n\n"
                "🔞 18+ • Play responsibly • T&Cs apply"
            ),
            "settings": (
                "⚙️ <b>IBETIN SETTINGS</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "Choose your language and sports-alert preferences."
            ),
        }
    )

    hi = app.core.TEXT.get("hi", {})
    hi.update(
        {
            "welcome": (
                "⚡ <b>IBETIN HUB</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "IBETIN के मुख्य सेक्शन सीधे Telegram से खोलें।\n\n"
                "🏆 Sports\n"
                "🔴 Live\n"
                "🎰 Live Casino\n"
                "🎮 Games\n"
                "📊 Results\n"
                "💳 Payments\n\n"
                "साथ में cricket/football scores, team search और match alerts भी उपलब्ध हैं।\n\n"
                "अपना विकल्प चुनें 👇\n\n"
                "🔞 18+ • जिम्मेदारी से खेलें • T&Cs लागू"
            ),
            "explore": (
                "🌐 <b>EXPLORE IBETIN</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "Sports, Live, Live Casino, Games, Results, Payments और Support खोलें।\n\n"
                "🔞 18+ • जिम्मेदारी से खेलें • T&Cs लागू"
            ),
            "join": (
                "🌐 <b>OPEN IBETIN</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "Login, registration या browsing के लिए official IBETIN website खोलें।\n\n"
                "🔞 18+ • जिम्मेदारी से खेलें • T&Cs लागू"
            ),
        }
    )


_install_ibetin_hub_copy()


# =========================================================
# HELPERS
# =========================================================

def tracked_url(content: str) -> str:
    return analytics.tracking_url(content)


def mini_app_button(label: str, content: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(label, web_app=WebAppInfo(url=tracked_url(content)))


def site_button(label: str, url: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(label, url=url)


def sky_admin_url() -> str:
    if not SKY_ADMIN_BASE_URL or not SKY_ADMIN_TEST_TOKEN:
        return ""
    query = urlencode({"key": SKY_ADMIN_TEST_TOKEN})
    return f"{SKY_ADMIN_BASE_URL}/open?{query}"


# =========================================================
# MAIN IBETIN HUB
# =========================================================

def premium_main_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [mini_app_button("🌐 OPEN IBETIN", "home_open_ibetin")],
        [
            site_button("🏆 SPORTS", IBETIN_SPORTS_URL),
            site_button("🔴 LIVE", IBETIN_LIVE_URL),
        ],
        [
            site_button("🎰 LIVE CASINO", IBETIN_CASINO_URL),
            site_button("🎮 GAMES", IBETIN_GAMES_URL),
        ],
        [
            site_button("📊 RESULTS", IBETIN_RESULTS_URL),
            site_button("💳 PAYMENTS", IBETIN_PAYMENT_URL),
        ],
        [
            InlineKeyboardButton("🏏 Cricket Scores", callback_data="cricket"),
            InlineKeyboardButton("⚽ Football Scores", callback_data="football"),
        ],
        [
            InlineKeyboardButton("🔎 Find Team", callback_data="find_team"),
            InlineKeyboardButton("🔔 Match Alerts", callback_data="subscribe"),
        ],
        [
            site_button("🛟 SUPPORT", IBETIN_SUPPORT_URL),
            InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
        ],
    ]

    if LIVE_TV_MODE == "public":
        url = sky_admin_url()
        if url:
            rows.insert(
                4,
                [InlineKeyboardButton("📺 WATCH LIVE TV", web_app=WebAppInfo(url=url))],
            )

    return InlineKeyboardMarkup(rows)


def premium_join_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [mini_app_button("🌐 OPEN IBETIN", "join_open_ibetin")],
            [
                site_button("🏆 SPORTS", IBETIN_SPORTS_URL),
                site_button("🔴 LIVE", IBETIN_LIVE_URL),
            ],
            [
                site_button("🎰 LIVE CASINO", IBETIN_CASINO_URL),
                site_button("🎮 GAMES", IBETIN_GAMES_URL),
            ],
            [InlineKeyboardButton("⬅️ Back to Home", callback_data="back")],
        ]
    )


def premium_explore_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [mini_app_button("🌐 OPEN IBETIN WEBSITE", "explore_home")],
        [
            site_button("🏆 SPORTS", IBETIN_SPORTS_URL),
            site_button("🔴 LIVE", IBETIN_LIVE_URL),
        ],
        [
            site_button("🎰 LIVE CASINO", IBETIN_CASINO_URL),
            site_button("🎮 GAMES", IBETIN_GAMES_URL),
        ],
        [
            site_button("📊 RESULTS", IBETIN_RESULTS_URL),
            site_button("💳 PAYMENTS", IBETIN_PAYMENT_URL),
        ],
        [site_button("🛟 SUPPORT", IBETIN_SUPPORT_URL)],
    ]

    if LIVE_TV_MODE == "public":
        url = sky_admin_url()
        if url:
            rows.append(
                [InlineKeyboardButton("📺 OPEN LIVE TV", web_app=WebAppInfo(url=url))]
            )

    rows.append([InlineKeyboardButton("⬅️ Back to Home", callback_data="back")])
    return InlineKeyboardMarkup(rows)


app.core.main_keyboard = premium_main_keyboard
app.core.join_keyboard = premium_join_keyboard
app.core.explore_keyboard = premium_explore_keyboard


# =========================================================
# TRACKING / REMINDER HOOKS
# =========================================================

_original_track = app.core.track
_original_touch_user = app.core.touch_user
_original_start = app.start
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
# START / WEBSITE COMMANDS
# =========================================================

async def smart_start(update, context) -> None:
    user = update.effective_user
    arg = context.args[0].lower() if context.args else ""

    if user and arg == "stopreminders":
        reminders.set_opt_out("bot", user.id, True)
        reminders.set_opt_out("business_dm", user.id, True)
        await update.effective_message.reply_text(
            "🔕 <b>IBETIN reminders are OFF.</b>", parse_mode="HTML"
        )
        return

    await _original_start(update, context)


app.start = smart_start


async def website_command(update, context) -> None:
    user = update.effective_user
    message = update.effective_message
    if not message:
        return
    if user:
        try:
            app.core.track(user.id, "website_hub")
        except Exception:
            pass
    await message.reply_text(
        "🌐 <b>IBETIN WEBSITE HUB</b>\n\nChoose a section below.",
        parse_mode="HTML",
        reply_markup=premium_explore_keyboard(),
        disable_web_page_preview=True,
    )


async def live_command(update, context) -> None:
    message = update.effective_message
    if not message:
        return
    await message.reply_text(
        "🔴 <b>IBETIN LIVE</b>\n\nOpen live sports or Live Casino.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [
                [site_button("🔴 LIVE SPORTS", IBETIN_LIVE_URL)],
                [site_button("🎰 LIVE CASINO", IBETIN_CASINO_URL)],
                [InlineKeyboardButton("⬅️ Back to Home", callback_data="back")],
            ]
        ),
        disable_web_page_preview=True,
    )


async def support_command(update, context) -> None:
    message = update.effective_message
    if not message:
        return
    await message.reply_text(
        "🛟 <b>IBETIN SUPPORT</b>\n\nOpen the official IBETIN contacts/support page below.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[site_button("🛟 OPEN SUPPORT", IBETIN_SUPPORT_URL)]]
        ),
        disable_web_page_preview=True,
    )


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
            "⚠️ <b>Private Sky admin URL is not configured.</b>", parse_mode="HTML"
        )
        return

    await message.reply_text(
        "📺 <b>LIVE TV CONTROL</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"Current mode: <b>{LIVE_TV_MODE.upper()}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("📺 OPEN LIVE TV", web_app=WebAppInfo(url=url))]]
        ),
        disable_web_page_preview=True,
    )


app.core.admin = smart_admin


async def live_tv_admin_command(update, context) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message or user.id != app.core.ADMIN_USER_ID:
        return

    if LIVE_TV_MODE == "off":
        await message.reply_text("⛔ <b>Live TV mode is OFF.</b>", parse_mode="HTML")
        return

    url = sky_admin_url()
    if not url:
        await message.reply_text(
            "⚠️ <b>Sky admin Live TV is not configured.</b>", parse_mode="HTML"
        )
        return

    await message.reply_text(
        "📺 <b>IBETIN LIVE TV · ADMIN</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"Current mode: <b>{LIVE_TV_MODE.upper()}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("▶ OPEN SKY LIVE · ADMIN", web_app=WebAppInfo(url=url))]]
        ),
        disable_web_page_preview=True,
    )


# =========================================================
# TELEGRAM UI
# =========================================================

async def configure_telegram_ui(application) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Open IBETIN Hub"),
            BotCommand("website", "Open IBETIN website sections"),
            BotCommand("live", "Open IBETIN live sections"),
            BotCommand("sports", "View sports scores and fixtures"),
            BotCommand("team", "Find a cricket or football team"),
            BotCommand("support", "Open official IBETIN support"),
            BotCommand("help", "IBETIN quick guide"),
        ]
    )

    await application.bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text="Open IBETIN",
            web_app=WebAppInfo(url=tracked_url("telegram_native_menu")),
        )
    )

    application.add_handler(CommandHandler("website", website_command))
    application.add_handler(CommandHandler("live", live_command))
    application.add_handler(CommandHandler("support", support_command))
    application.add_handler(CommandHandler("livetvadmin", live_tv_admin_command))

    reminders.ensure_tables()
    reminders.start_background_loop(application)


app.configure_telegram_ui = configure_telegram_ui


# =========================================================
# START IBETIN
# =========================================================

if __name__ == "__main__":
    private_apk_upload.install_on_tracking_handler(analytics)
    trial_live_tv.install_on_tracking_handler(analytics)
    fantzo_live_tv.install_on_tracking_handler(analytics)
    analytics.start_tracking_server()
    logger.info("Starting IBETIN with LIVE_TV_MODE=%s", LIVE_TV_MODE)
    app.run()
