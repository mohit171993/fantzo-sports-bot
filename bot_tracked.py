import logging
import os
from urllib.parse import urlencode

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    MenuButtonWebApp,
    ReplyKeyboardMarkup,
    WebAppInfo,
)
from telegram.ext import CommandHandler

import bot_persistent as app
import fantzo_analytics as analytics
import fantzo_live_tv
import fantzo_reminders as reminders
import ibetin_hub as hub
import ibetin_creatives
import ibetin_news as news
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
IBETIN_LIVE_RESULTS_URL = os.getenv("IBETIN_LIVE_RESULTS_URL", IBETIN_RESULTS_URL).strip()
IBETIN_PAYMENT_URL = os.getenv(
    "IBETIN_PAYMENT_URL", f"{IBETIN_HOME_URL}/information/payment"
).strip()
IBETIN_SUPPORT_URL = os.getenv(
    "IBETIN_SUPPORT_URL", f"{IBETIN_HOME_URL}/information/contacts"
).strip()
_IBETIN_APP_BASE_URL = (
    os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/")
    or "https://ibetin-app-production.up.railway.app"
)
IBETIN_LIVE_LINE_URL = os.getenv(
    "IBETIN_LIVE_LINE_URL", f"{_IBETIN_APP_BASE_URL}/liveline"
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
                "⚡ <b>IBETIN</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "Quick access without a crowded menu.\n\n"
                "🚀 Join IBETIN Mini App\n"
                "🏏 Live Line\n"
                "🔴 Live now\n"
                "🏆 Sports\n"
                "📰 Sports News\n"
                "🔔 Match Alerts\n"
                "🛟 Support\n\n"
                "More sections are available inside the Mini App.\n\n"
                "🔞 18+ • Play responsibly • T&Cs apply"
            ),
            "explore": (
                "🌐 <b>IBETIN MINI APP HUB</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "Every navigation button opens inside Telegram.\n\n"
                "🔞 18+ • Play responsibly • T&Cs apply"
            ),
            "join": (
                "🌐 <b>OPEN IBETIN</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "Continue inside Telegram using the IBETIN Mini App.\n\n"
                "🔞 18+ • Play responsibly • T&Cs apply"
            ),
            "settings": (
                "⚙️ <b>IBETIN SETTINGS</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "Open settings in the IBETIN Mini App."
            ),
        }
    )

    hi = app.core.TEXT.get("hi", {})
    hi.update(
        {
            "welcome": (
                "⚡ <b>IBETIN</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "कम विकल्प, तेज़ access.\n\n"
                "🚀 IBETIN Mini App\n"
                "🏏 Live Line\n"
                "🔴 Live\n"
                "🏆 Sports\n"
                "📰 Sports News\n"
                "🔔 Match Alerts\n"
                "🛟 Support\n\n"
                "बाकी सभी sections Mini App के अंदर उपलब्ध हैं।\n\n"
                "🔞 18+ • जिम्मेदारी से खेलें • T&Cs लागू"
            ),
            "explore": (
                "🌐 <b>IBETIN MINI APP HUB</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "सभी navigation विकल्प Telegram के अंदर खुलेंगे।\n\n"
                "🔞 18+ • जिम्मेदारी से खेलें • T&Cs लागू"
            ),
            "join": (
                "🌐 <b>OPEN IBETIN</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "IBETIN को Telegram Mini App के अंदर खोलें।\n\n"
                "🔞 18+ • जिम्मेदारी से खेलें • T&Cs लागू"
            ),
        }
    )


_install_ibetin_hub_copy()


# =========================================================
# TELEGRAM BUTTON STYLES
# =========================================================

# Telegram supports three native button colors: primary (blue), success
# (green), and danger (red). PTB 21.6 predates the explicit `style` argument,
# so inject the current Bot API field when serializing buttons. This applies
# consistently to all InlineKeyboardButton/KeyboardButton instances used by
# the IBETIN runtime, including Business DM menus, reminders, alerts and news.
def _button_style(text: str) -> str:
    value = (text or "").casefold()
    if any(token in value for token in ("live", "stop", "delete", "remove", "off")):
        return "danger"
    if any(
        token in value
        for token in (
            "join ibetin",
            "open ibetin",
            "ibetin mini app",
            "mini app home",
        )
    ):
        return "success"
    return "primary"


def _install_native_button_styles() -> None:
    if getattr(InlineKeyboardButton, "_ibetin_styles_installed", False):
        return

    original_inline_to_dict = InlineKeyboardButton.to_dict
    original_keyboard_to_dict = KeyboardButton.to_dict

    def inline_to_dict(self, *args, **kwargs):
        data = original_inline_to_dict(self, *args, **kwargs)
        data.setdefault("style", _button_style(getattr(self, "text", "")))
        return data

    def keyboard_to_dict(self, *args, **kwargs):
        data = original_keyboard_to_dict(self, *args, **kwargs)
        data.setdefault("style", _button_style(getattr(self, "text", "")))
        return data

    InlineKeyboardButton.to_dict = inline_to_dict
    KeyboardButton.to_dict = keyboard_to_dict
    InlineKeyboardButton._ibetin_styles_installed = True
    KeyboardButton._ibetin_styles_installed = True
    logger.info("IBETIN native Telegram button colors installed")


_install_native_button_styles()


# =========================================================
# MINI APP HELPERS
# =========================================================

def tracked_url(content: str) -> str:
    return analytics.tracking_url(content)


def mini_app_button(label: str, content: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(label, web_app=WebAppInfo(url=tracked_url(content)))


def site_button(label: str, url: str) -> InlineKeyboardButton:
    """Open an IBETIN web section inside Telegram WebApp instead of external browser."""
    return InlineKeyboardButton(label, web_app=WebAppInfo(url=url))


def hub_button(label: str, section: str = "home") -> InlineKeyboardButton:
    return hub.webapp_button(label, section)


def sky_admin_url() -> str:
    if not SKY_ADMIN_BASE_URL or not SKY_ADMIN_TEST_TOKEN:
        return ""
    query = urlencode({"key": SKY_ADMIN_TEST_TOKEN})
    return f"{SKY_ADMIN_BASE_URL}/open?{query}"


# Persistent quick-access keyboard is now a WebApp button too.
app.QUICK_MENU = ReplyKeyboardMarkup(
    [[KeyboardButton("⚡ OPEN IBETIN MINI APP", web_app=WebAppInfo(url=hub.hub_url("home")))]],
    resize_keyboard=True,
    is_persistent=True,
    input_field_placeholder="Open IBETIN Mini App",
)


# Convert URL/callback buttons produced by the assistant/reminder modules to Mini Apps.
def _mini_only_button(text: str, url=None, callback_data=None, **kwargs):
    if url:
        return InlineKeyboardButton(text, web_app=WebAppInfo(url=url))
    callback_map = {
        "back": hub.hub_url("home"),
        "settings": hub.hub_url("settings"),
        "subscribe": hub.hub_url("alerts"),
        "find_team": IBETIN_SPORTS_URL,
        "cricket": IBETIN_LIVE_RESULTS_URL,
        "football": IBETIN_LIVE_RESULTS_URL,
        "live_now": IBETIN_LIVE_URL,
        "trending": IBETIN_SPORTS_URL,
        "upcoming": IBETIN_SPORTS_URL,
        "results": IBETIN_RESULTS_URL,
        "explore": hub.hub_url("home"),
        "join_fantzo": IBETIN_HOME_URL,
    }
    if callback_data in callback_map:
        return InlineKeyboardButton(text, web_app=WebAppInfo(url=callback_map[callback_data]))
    return InlineKeyboardButton(text, callback_data=callback_data, **kwargs)


app.fantzo_autoreply.InlineKeyboardButton = _mini_only_button
app.fantzo_business.InlineKeyboardButton = _mini_only_button
reminders.InlineKeyboardButton = _mini_only_button


# =========================================================
# MAIN IBETIN HUB — COMPACT SIX-ACTION MENU
# =========================================================

def premium_main_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [hub_button("🚀 JOIN IBETIN", "home")],
        [site_button("🏏 WATCH IBETIN LIVE LINE", IBETIN_LIVE_LINE_URL)],
        [
            site_button("🔴 LIVE NOW", IBETIN_LIVE_URL),
            site_button("🏆 SPORTS", IBETIN_SPORTS_URL),
        ],
        [
            news.news_webapp_button("📰 NEWS"),
            hub_button("🔔 MATCH ALERTS", "alerts"),
        ],
        [site_button("🛟 SUPPORT", IBETIN_SUPPORT_URL)],
    ]

    if LIVE_TV_MODE == "public":
        url = sky_admin_url()
        if url:
            rows.insert(
                3,
                [InlineKeyboardButton("📺 WATCH LIVE TV", web_app=WebAppInfo(url=url))],
            )

    return InlineKeyboardMarkup(rows)


def premium_join_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [site_button("🌐 OPEN IBETIN", IBETIN_HOME_URL)],
            [
                site_button("🏆 SPORTS", IBETIN_SPORTS_URL),
                site_button("🔴 LIVE", IBETIN_LIVE_URL),
            ],
            [
                site_button("🎰 LIVE CASINO", IBETIN_CASINO_URL),
                site_button("🎮 GAMES", IBETIN_GAMES_URL),
            ],
            [hub_button("⚡ IBETIN MINI APP HOME", "home")],
        ]
    )


def premium_explore_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [hub_button("🌐 IBETIN MINI APP HOME", "home")],
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
        [news.news_webapp_button("📰 SPORTS NEWS")],
        [site_button("🛟 SUPPORT", IBETIN_SUPPORT_URL)],
        [hub_button("⚡ MINI APP HOME", "home")],
    ]

    if LIVE_TV_MODE == "public":
        url = sky_admin_url()
        if url:
            rows.insert(-1, [InlineKeyboardButton("📺 OPEN LIVE TV", web_app=WebAppInfo(url=url))])

    return InlineKeyboardMarkup(rows)


app.core.main_keyboard = premium_main_keyboard
app.core.join_keyboard = premium_join_keyboard
app.core.explore_keyboard = premium_explore_keyboard


# =========================================================
# TRACKING / REMINDER HOOKS
# =========================================================

_original_track = app.core.track
_original_touch_user = app.core.touch_user
_original_admin = app.core.admin
_original_callback_router = app.core.callback_router


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
# COMMANDS — RETURN MINI APP LAUNCHERS ONLY
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

    await app.show_home(update, context)
    await update.effective_message.reply_text(
        "⚡ <b>Mini App quick access enabled</b>\n\n"
        "Use the button below anytime. Every IBETIN navigation button now stays inside Telegram.",
        parse_mode="HTML",
        reply_markup=app.QUICK_MENU,
    )


app.start = smart_start


async def _mini_launcher(update, title: str, button: InlineKeyboardButton, action: str) -> None:
    user = update.effective_user
    message = update.effective_message
    if not message:
        return
    if user:
        try:
            app.core.track(user.id, action)
        except Exception:
            pass
    await message.reply_text(
        f"{title}\n\nOpen it inside Telegram below.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[button]]),
        disable_web_page_preview=True,
    )


async def website_command(update, context) -> None:
    await _mini_launcher(update, "🌐 <b>IBETIN MINI APP</b>", hub_button("OPEN IBETIN MINI APP", "home"), "website_hub")


async def live_command(update, context) -> None:
    await _mini_launcher(update, "🔴 <b>IBETIN LIVE</b>", site_button("OPEN LIVE", IBETIN_LIVE_URL), "live")


async def support_command(update, context) -> None:
    await _mini_launcher(update, "🛟 <b>IBETIN SUPPORT</b>", site_button("OPEN SUPPORT", IBETIN_SUPPORT_URL), "support")


async def news_command(update, context) -> None:
    await _mini_launcher(update, "📰 <b>IBETIN SPORTS NEWS</b>", news.news_webapp_button("OPEN SPORTS NEWS"), "news:latest")


async def sports_command(update, context) -> None:
    await _mini_launcher(update, "🏆 <b>IBETIN SPORTS</b>", site_button("OPEN SPORTS", IBETIN_SPORTS_URL), "sports")


async def team_command(update, context) -> None:
    await _mini_launcher(update, "🔎 <b>FIND A TEAM</b>", site_button("OPEN SPORTS SEARCH", IBETIN_SPORTS_URL), "find_team")


async def help_command(update, context) -> None:
    message = update.effective_message
    if not message:
        return
    await message.reply_text(
        "⚡ <b>IBETIN HELP</b>\n\nEvery option below opens as a Telegram Mini App.",
        parse_mode="HTML",
        reply_markup=premium_main_keyboard(),
        disable_web_page_preview=True,
    )


# These assignments make the handlers registered inside bot_persistent.run()
# use the Mini-App-only command versions.
app.core.sports_command = sports_command
app.core.team_command = team_command
app.core.help_command = help_command


async def smart_callback_router(update, context) -> None:
    # Legacy callbacks can still arrive from old messages; keep them compatible.
    await _original_callback_router(update, context)


app.core.callback_router = smart_callback_router


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
            BotCommand("start", "Open IBETIN Mini App Hub"),
            BotCommand("news", "Open Sports News Mini App"),
            BotCommand("website", "Open IBETIN Mini App"),
            BotCommand("live", "Open Live Mini App"),
            BotCommand("sports", "Open Sports Mini App"),
            BotCommand("team", "Open team search"),
            BotCommand("support", "Open Support Mini App"),
            BotCommand("help", "IBETIN Mini App menu"),
        ]
    )

    await application.bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text="Open IBETIN",
            web_app=WebAppInfo(url=hub.hub_url("home")),
        )
    )

    application.add_handler(CommandHandler("news", news_command))
    application.add_handler(CommandHandler("website", website_command))
    application.add_handler(CommandHandler("live", live_command))
    application.add_handler(CommandHandler("support", support_command))
    application.add_handler(CommandHandler("livetvadmin", live_tv_admin_command))

    reminders.ensure_tables()
    reminders.start_background_loop(application)
    ibetin_creatives.install(application)


app.configure_telegram_ui = configure_telegram_ui


# =========================================================
# START IBETIN
# =========================================================

if __name__ == "__main__":
    hub.install_on_tracking_handler(analytics)
    private_apk_upload.install_on_tracking_handler(analytics)
    trial_live_tv.install_on_tracking_handler(analytics)
    fantzo_live_tv.install_on_tracking_handler(analytics)
    analytics.start_tracking_server()
    logger.info("Starting IBETIN Mini-App-first bot with LIVE_TV_MODE=%s", LIVE_TV_MODE)
    app.run()
