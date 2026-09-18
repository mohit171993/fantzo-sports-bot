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
    ReplyKeyboardRemove,
    WebAppInfo,
)
from telegram.ext import CommandHandler, MessageHandler, filters

import bot_persistent as app
import fantzo_analytics as analytics
import fantzo_live_tv
import fantzo_reminders as reminders
import ibetin_hub as hub
import ibetin_creatives
import ibetin_news as news
import ibetin_phone_verify as phone_verify
import ibetin_reports
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
IBETIN_CHANNEL_URL = "https://t.me/ibetinoffcial"

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


# Persistent bottom keyboard: a visible START entry plus direct IBETIN access.
app.QUICK_MENU = ReplyKeyboardMarkup(
    [[
        KeyboardButton("▶️ START"),
        KeyboardButton("⚡ OPEN IBETIN", web_app=WebAppInfo(url=hub.hub_url("home"))),
    ]],
    resize_keyboard=True,
    is_persistent=True,
    input_field_placeholder="Tap START or open IBETIN",
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

def premium_main_keyboard(user_id: int = 0) -> InlineKeyboardMarkup:
    if user_id and phone_verify.is_verified(user_id):
        live_line_button = site_button(
            "🏏 WATCH IBETIN LIVE LINE",
            phone_verify.live_line_url(user_id, IBETIN_LIVE_LINE_URL),
        )
    else:
        live_line_button = InlineKeyboardButton(
            "🏏 WATCH IBETIN LIVE LINE",
            callback_data="liveline_access",
        )

    rows = [
        [hub_button("🚀 JOIN IBETIN", "home")],
        [live_line_button],
        [
            site_button("🔴 LIVE NOW", IBETIN_LIVE_URL),
            site_button("🏆 SPORTS", IBETIN_SPORTS_URL),
        ],
        [
            news.news_webapp_button("📰 NEWS"),
            hub_button("🔔 MATCH ALERTS", "alerts"),
        ],
        [
            InlineKeyboardButton("📢 JOIN CHANNEL", url=IBETIN_CHANNEL_URL),
            site_button("🛟 SUPPORT", IBETIN_SUPPORT_URL),
        ],
    ]

    if LIVE_TV_MODE == "public":
        url = fantzo_live_tv.minitv_url(user_id)
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


def premium_explore_keyboard(user_id: int = 0) -> InlineKeyboardMarkup:
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
        url = fantzo_live_tv.minitv_url(user_id)
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

async def smart_show_home(update, context) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return
    app.core.touch_user(update)
    lang = app.core.get_user_lang(user.id)
    banner_file_id = app.get_banner_file_id()
    markup = premium_main_keyboard(user.id)

    if banner_file_id:
        try:
            await message.reply_photo(
                photo=banner_file_id,
                caption=app.core.TEXT[lang]["welcome"],
                parse_mode="HTML",
                reply_markup=markup,
            )
            return
        except Exception as exc:
            logger.warning("IBETIN banner send failed, falling back to text: %s", exc)

    await message.reply_text(
        app.core.TEXT[lang]["welcome"],
        parse_mode="HTML",
        reply_markup=markup,
        disable_web_page_preview=True,
    )


app.show_home = smart_show_home


async def _prompt_mobile_verification(update, context) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return

    if phone_verify.is_verified(user.id):
        await message.reply_text(
            "✅ <b>Mobile number already verified.</b>\n\nOpen Live Line below.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton(
                    "🏏 OPEN IBETIN LIVE LINE",
                    web_app=WebAppInfo(
                        url=phone_verify.live_line_url(user.id, IBETIN_LIVE_LINE_URL)
                    ),
                )]]
            ),
        )
        return

    await message.reply_text(
        "📱 <b>Mobile verification required</b>\n\n"
        "To access IBETIN Live Line, share the mobile number linked to your Telegram account. "
        "There is no country restriction.\n\n"
        "Tap <b>📱 VERIFY MOBILE NUMBER</b> below.",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("📱 VERIFY MOBILE NUMBER", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True,
            input_field_placeholder="Verify mobile number",
        ),
    )


async def mobile_contact_handler(update, context) -> None:
    user = update.effective_user
    message = update.effective_message
    contact = message.contact if message else None
    if not user or not message or not contact:
        return

    # Only accept Telegram's own-account contact share. A manually forwarded or
    # different person's contact must never unlock Live Line.
    if not contact.user_id or int(contact.user_id) != int(user.id):
        await message.reply_text(
            "❌ Please use <b>📱 VERIFY MOBILE NUMBER</b> and share your own Telegram number.",
            parse_mode="HTML",
        )
        return

    if not phone_verify.verify_user(user.id, contact.phone_number):
        await message.reply_text(
            "❌ Mobile verification failed. Please try again.",
            reply_markup=app.QUICK_MENU,
        )
        return

    logger.info("IBETIN Live Line mobile verified user_id=%s", user.id)
    await message.reply_text(
        "✅ <b>Mobile number verified.</b>",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.reply_text(
        "🏏 <b>IBETIN Live Line is unlocked.</b>\n\nTap below to continue.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton(
                "🏏 OPEN IBETIN LIVE LINE",
                web_app=WebAppInfo(
                    url=phone_verify.live_line_url(user.id, IBETIN_LIVE_LINE_URL)
                ),
            )]]
        ),
    )
    await message.reply_text(
        "Use <b>▶️ START</b> anytime to reopen the main menu.",
        parse_mode="HTML",
        reply_markup=app.QUICK_MENU,
    )


async def liveline_command(update, context) -> None:
    await _prompt_mobile_verification(update, context)


async def start_button_handler(update, context) -> None:
    await smart_start(update, context)


async def smart_start(update, context) -> None:
    user = update.effective_user
    arg = context.args[0].lower() if context.args else ""

    if user and arg in {"verifyliveline", "liveline", "livelineverify"}:
        await _prompt_mobile_verification(update, context)
        return

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
    if await ibetin_reports.handle_callback(update, context):
        return

    query = update.callback_query
    if query and query.data == "liveline_access":
        try:
            await query.answer()
        except Exception:
            pass
        await _prompt_mobile_verification(update, context)
        return

    # Legacy callbacks can still arrive from old messages; keep them compatible.
    await _original_callback_router(update, context)


app.core.callback_router = smart_callback_router


# =========================================================
# ADMIN PANEL
# =========================================================

async def smart_admin(update, context) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return
    if not ibetin_reports.is_authorized_admin(user.id):
        await message.reply_text("This command is restricted.")
        return

    # Preserve the original legacy admin statistics for the original admin.
    # Alternate explicitly-unlocked operators go straight to the new report center.
    if int(user.id) == int(app.core.ADMIN_USER_ID):
        await _original_admin(update, context)

    await ibetin_reports.send_menu(update, context)

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
    if not user or not message:
        return
    if not ibetin_reports.is_authorized_admin(user.id):
        await message.reply_text("This command is restricted.")
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
            BotCommand("liveline", "Open IBETIN Live Line"),
            BotCommand("sports", "Open Sports Mini App"),
            BotCommand("team", "Open team search"),
            BotCommand("support", "Open Support Mini App"),
            BotCommand("help", "IBETIN Mini App menu"),
            BotCommand("reports", "Admin report center"),
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
    application.add_handler(CommandHandler("liveline", liveline_command))
    application.add_handler(CommandHandler("reports", ibetin_reports.reports_command))
    application.add_handler(
        MessageHandler(
            filters.UpdateType.MESSAGE & filters.CONTACT,
            mobile_contact_handler,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.UpdateType.MESSAGE
            & filters.TEXT
            & filters.Regex(r"^▶️ START$"),
            start_button_handler,
        )
    )
    application.add_handler(CommandHandler("livetvadmin", live_tv_admin_command))

    phone_verify.ensure_tables()
    ibetin_reports.ensure_tables()
    ibetin_reports.log_admin_diagnostics()
    await ibetin_reports.push_report_center_to_unlocked_admin(application)
    reset_count = phone_verify.apply_requested_reset()
    if reset_count:
        logger.info("IBETIN Live Line verification reset applied rows=%s", reset_count)
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
