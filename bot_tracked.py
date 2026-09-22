import logging
import os
from urllib.parse import urlencode

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    MenuButtonCommands,
    MenuButtonWebApp,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    WebAppInfo,
)
from telegram.ext import ApplicationHandlerStop, CommandHandler, MessageHandler, filters

import bot_persistent as app
import fantzo_analytics as analytics
import fantzo_live_tv
import fantzo_reminders as reminders
import ibetin_hub as hub
import ibetin_creatives
import ibetin_leads
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


STOP_PHRASES = {
    "stop",
    "unsubscribe",
    "do not contact",
    "dont contact",
    "don't contact",
    "no calls",
    "no whatsapp",
}


def _is_stop_text(value: str) -> bool:
    return " ".join(str(value or "").casefold().split()) in STOP_PHRASES


async def _set_user_menu_button(bot, user_id: int, verified: bool) -> None:
    try:
        if verified:
            await bot.set_chat_menu_button(
                chat_id=int(user_id),
                menu_button=MenuButtonWebApp(
                    text="Open IBETIN",
                    web_app=WebAppInfo(url=hub.hub_url("home")),
                ),
            )
        else:
            await bot.set_chat_menu_button(
                chat_id=int(user_id),
                menu_button=MenuButtonCommands(),
            )
    except Exception:
        logger.exception("Could not update IBETIN per-user menu button")


async def _require_verified(update, context, source: str = "bot_start") -> bool:
    user = update.effective_user
    if not user:
        return False
    if phone_verify.is_verified(user.id):
        await _set_user_menu_button(context.bot, user.id, True)
        return True
    await _set_user_menu_button(context.bot, user.id, False)
    await _prompt_mobile_verification(update, context, source)
    return False


# =========================================================
# MAIN IBETIN HUB — COMPACT SIX-ACTION MENU
# =========================================================

def premium_main_keyboard(user_id: int = 0) -> InlineKeyboardMarkup:
    if user_id and phone_verify.is_verified(user_id):
        live_line_button = site_button(
            "🏏 OPEN IBETIN LIVE LINE",
            phone_verify.live_line_url(user_id, IBETIN_LIVE_LINE_URL),
        )
    else:
        live_line_button = InlineKeyboardButton(
            "🏏 OPEN IBETIN LIVE LINE",
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


def conversion_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Focused post-verification menu for paid-traffic conversion."""
    live_url = phone_verify.live_line_url(user_id, IBETIN_LIVE_LINE_URL)
    return InlineKeyboardMarkup(
        [
            [hub_button("🚀 JOIN IBETIN", "home")],
            [site_button("🏏 OPEN IBETIN LIVE LINE", live_url)],
            [InlineKeyboardButton("📢 JOIN CHANNEL", url=IBETIN_CHANNEL_URL)],
        ]
    )


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


def _verification_reply_keyboard() -> ReplyKeyboardMarkup:
    """Keep the contact-verification button visible until verification succeeds."""
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📱 VERIFY & CONTINUE", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
        input_field_placeholder="Tap VERIFY & CONTINUE",
    )


async def _prompt_mobile_verification(update, context, source: str = "bot_start") -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return

    source = str(source or "bot_start")[:64]

    # Verification is account-level and one-time. If already verified, never
    # ask again; continue directly to the requested destination.
    if phone_verify.is_verified(user.id):
        if source == "liveline":
            await message.reply_text(
                "🏏 <b>IBETIN LIVE LINE</b>\n\nOpen Live Line below.",
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

        if source == "business_dm":
            import fantzo_business
            await message.reply_text(
                "✅ <b>Your Telegram mobile is already verified.</b>\n\n"
                "Choose what you want to do next.",
                parse_mode="HTML",
                reply_markup=fantzo_business.business_keyboard(user.id),
            )
            return

        await smart_start(update, context)
        return

    context.user_data["ibetin_mobile_verify_pending"] = True
    context.user_data["ibetin_mobile_verify_source"] = source
    try:
        # Verification happens in the normal bot chat even when the user came
        # from Live Line or a Telegram Business handoff, so use the bot route.
        reminders.touch_user("bot", user.id, "verification")
    except Exception:
        logger.exception("Could not register IBETIN verification reminder")

    if source == "business_dm":
        detail = (
            "Before continuing from IBETIN Business DM, verify the mobile number "
            "linked to your Telegram account."
        )
    elif source == "liveline":
        detail = (
            "Verify the mobile number linked to your Telegram account once. "
            "After verification, Live Line will open without asking again."
        )
    else:
        detail = (
            "Before using IBETIN Bot, verify the mobile number linked to your "
            "Telegram account. You only need to do this once."
        )

    await message.reply_text(
        "📱 <b>VERIFY MOBILE TO CONTINUE</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"{detail}\n\n"
        "✅ Verify once to unlock IBETIN, Live Line and quick access.\n\n"
        "Tap <b>📱 VERIFY & CONTINUE</b> below. Telegram will share the "
        "mobile number linked to your own Telegram account.\n\n"
        "By tapping Verify & Continue, you agree that the IBETIN team may "
        "contact you about your request by <b>phone call and WhatsApp</b>. "
        "You can opt out anytime.\n\n"
        "Numbers from <b>any country</b> are accepted. Typed numbers are not accepted.\n"
        "🔞 <b>18+ only • Play responsibly</b>",
        parse_mode="HTML",
        reply_markup=_verification_reply_keyboard(),
    )


async def _notify_verified_lead(context, user, phone: str, source: str, campaign: str) -> None:
    username = f"@{user.username}" if getattr(user, "username", None) else "—"
    first_name = str(getattr(user, "first_name", "") or "—")
    try:
        await context.bot.send_message(
            chat_id=ibetin_reports.notification_admin_user_id(),
            text=(
                "🆕 <b>NEW VERIFIED IBETIN LEAD</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                f"👤 Name: <b>{first_name}</b>\n"
                f"🔗 Telegram: <b>{username}</b>\n"
                f"📱 Mobile: <code>{phone}</code>\n"
                f"🎯 Campaign: <code>{campaign or 'direct'}</code>\n"
                f"📥 Source: <b>{source}</b>\n"
                "☎️ Follow-up: <b>Call + WhatsApp</b>\n\n"
                "Update the lead status below after follow-up."
            ),
            parse_mode="HTML",
            reply_markup=ibetin_reports.lead_status_keyboard(int(user.id)),
            disable_web_page_preview=True,
        )
    except Exception:
        logger.exception("Could not send IBETIN verified lead alert")


async def mobile_contact_handler(update, context) -> None:
    user = update.effective_user
    message = update.effective_message
    contact = message.contact if message else None
    if not user or not message or not contact:
        return

    was_verified = phone_verify.is_verified(user.id)

    # A valid Telegram self-contact is enough even if the in-memory pending
    # flag was lost after a Railway restart or the user came from a reminder.
    if was_verified and not context.user_data.get("ibetin_mobile_verify_pending"):
        return

    if contact.user_id is None or int(contact.user_id) != int(user.id):
        await message.reply_text(
            "⚠️ <b>Verification failed.</b>\n\n"
            "Please tap <b>📱 VERIFY & CONTINUE</b> and share the mobile number "
            "linked to your own Telegram account.",
            parse_mode="HTML",
            reply_markup=_verification_reply_keyboard(),
        )
        return

    lead = ibetin_leads.get_lead(user.id) or {}
    source = str(
        context.user_data.pop("ibetin_mobile_verify_source", "")
        or lead.get("source")
        or "bot_start"
    )
    if source == "bot":
        source = "bot_start"
    campaign = str(
        context.user_data.pop("ibetin_campaign", "")
        or lead.get("campaign")
        or "direct"
    )

    if not phone_verify.verify_user(
        user.id,
        contact.phone_number,
        source=source,
        campaign=campaign,
        contact_consent=True,
    ):
        await message.reply_text(
            "⚠️ <b>A valid Telegram-linked mobile number is required.</b>\n\n"
            "Please tap <b>📱 VERIFY & CONTINUE</b> and try again.",
            parse_mode="HTML",
            reply_markup=_verification_reply_keyboard(),
        )
        return

    context.user_data.pop("ibetin_mobile_verify_pending", None)
    await _set_user_menu_button(context.bot, user.id, True)

    phone = phone_verify.normalize_phone(contact.phone_number)
    masked = phone
    if len(phone) > 8:
        masked = phone[:4] + "••••" + phone[-4:]

    try:
        app.core.touch_user(update)
        if source != "business_dm":
            reminders.touch_user("bot", user.id, "general")
        app.core.track(user.id, f"mobile_verified:{source}")
    except Exception:
        logger.exception("Could not track IBETIN mobile verification")

    logger.info(
        "IBETIN mobile verified user_id=%s source=%s campaign=%s",
        user.id,
        source,
        campaign,
    )

    await message.reply_text(
        "✅ <b>Telegram mobile verified</b>\n\n"
        f"Verified number: <code>{masked}</code>\n"
        "You will not be asked to verify again.",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )

    if not was_verified:
        await _notify_verified_lead(context, user, phone, source, campaign)

    if source == "liveline":
        await message.reply_text(
            "🏏 <b>IBETIN Live Line is ready.</b>",
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

    if source == "business_dm":
        await message.reply_text(
            "Choose what you want to do next 👇",
            reply_markup=fantzo_business.business_keyboard(user.id),
        )
        return

    await message.reply_text(
        "🎯 <b>You're ready.</b> Choose what you want to do next 👇",
        parse_mode="HTML",
        reply_markup=conversion_keyboard(user.id),
    )


async def pending_verification_text_handler(update, context) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message or not message.text:
        return
    if phone_verify.is_verified(user.id):
        return

    if _is_stop_text(message.text):
        ibetin_leads.set_status(user.id, "dnc")
        reminders.set_opt_out("bot", user.id, True)
        reminders.set_opt_out("business_dm", user.id, True)
        await message.reply_text(
            "✅ <b>Contact preference updated.</b>\n\n"
            "Promotional follow-up is stopped. You can still use official support anytime.",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove(),
        )
        raise ApplicationHandlerStop

    context.user_data["ibetin_mobile_verify_pending"] = True
    context.user_data.setdefault("ibetin_mobile_verify_source", "bot_start")
    try:
        reminders.touch_user("bot", user.id, "verification")
    except Exception:
        logger.exception("Could not register IBETIN verification reminder from text gate")
    await message.reply_text(
        "🔐 <b>Telegram verification is required.</b>\n\n"
        "Please tap <b>📱 VERIFY & CONTINUE</b> below. "
        "Typed mobile numbers cannot verify your account.",
        parse_mode="HTML",
        reply_markup=_verification_reply_keyboard(),
    )
    raise ApplicationHandlerStop


async def verified_fixed_reply_handler(update, context) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message or not message.text:
        return
    if not phone_verify.is_verified(user.id):
        return

    text = message.text.strip()
    if not text or text in {"▶️ START", "⚡ IBETIN Menu"}:
        return

    normalized = " ".join(text.casefold().split())
    if normalized in {
        "stop",
        "unsubscribe",
        "do not contact",
        "dont contact",
        "don't contact",
        "no calls",
        "no whatsapp",
    }:
        ibetin_leads.set_status(user.id, "dnc")
        reminders.set_opt_out("bot", user.id, True)
        reminders.set_opt_out("business_dm", user.id, True)
        await message.reply_text(
            "✅ <b>Contact preference updated.</b>\n\n"
            "We will stop promotional follow-up to this Telegram lead. "
            "You can still use IBETIN and official support anytime.",
            parse_mode="HTML",
        )
        return

    category, reply, markup = fantzo_business.classify_business_dm(text, user.id)
    try:
        app.core.touch_user(update)
        app.core.track(user.id, f"bot_text:{category}")
    except Exception:
        logger.exception("Could not track IBETIN fixed reply")

    await message.reply_text(
        reply,
        parse_mode="HTML",
        reply_markup=markup,
        disable_web_page_preview=True,
    )


async def liveline_command(update, context) -> None:
    user = update.effective_user
    if user and phone_verify.is_verified(user.id):
        await _prompt_mobile_verification(update, context, "liveline")
        return
    await _prompt_mobile_verification(update, context, "liveline")


async def start_button_handler(update, context) -> None:
    await smart_start(update, context)


async def smart_start(update, context) -> None:
    user = update.effective_user
    message = update.effective_message
    arg = context.args[0].lower() if context.args else ""

    if not user or not message:
        return

    if arg == "stopreminders":
        reminders.set_opt_out("bot", user.id, True)
        reminders.set_opt_out("business_dm", user.id, True)
        await message.reply_text(
            "🔕 <b>IBETIN reminders are OFF.</b>", parse_mode="HTML"
        )
        return

    if arg in {"verify_business_dm", "business_verify"}:
        ibetin_leads.record_start(user.id, source="business_dm")
        context.user_data["ibetin_mobile_verify_source"] = "business_dm"
        await _prompt_mobile_verification(update, context, "business_dm")
        return

    if arg in {"verifyliveline", "liveline", "livelineverify"}:
        ibetin_leads.record_start(user.id, source="liveline")
        context.user_data["ibetin_mobile_verify_source"] = "liveline"
        await _prompt_mobile_verification(update, context, "liveline")
        return

    campaign = ibetin_leads.clean_campaign(arg or "direct")
    ibetin_leads.record_start(user.id, campaign=campaign, source="bot")
    context.user_data["ibetin_campaign"] = campaign
    context.user_data["ibetin_mobile_verify_source"] = "bot_start"
    try:
        app.core.track(user.id, f"campaign_start:{campaign}")
    except Exception:
        logger.exception("Could not track IBETIN campaign start")

    # Fantzo-style global onboarding gate: first IBETIN entry requires a
    # Telegram self-contact verification. Once verified, all IBETIN features
    # including Live Line reuse the same record and do not ask again.
    if not phone_verify.is_verified(user.id):
        await _set_user_menu_button(context.bot, user.id, False)
        try:
            app.core.touch_user(update)
            reminders.touch_user("bot", user.id, "verification")
            app.core.track(user.id, "mobile_verify:bot_start")
        except Exception:
            logger.exception("Could not track IBETIN bot-start verification")
        await _prompt_mobile_verification(update, context, "bot_start")
        return

    await _set_user_menu_button(context.bot, user.id, True)
    await message.reply_text(
        "👋 <b>Welcome to IBETIN</b>\n\n"
        "Your mobile is already verified. Choose what you want to do next 👇",
        parse_mode="HTML",
        reply_markup=conversion_keyboard(user.id),
        disable_web_page_preview=True,
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
    if not await _require_verified(update, context):
        return
    await _mini_launcher(update, "🌐 <b>IBETIN MINI APP</b>", hub_button("OPEN IBETIN MINI APP", "home"), "website_hub")


async def live_command(update, context) -> None:
    if not await _require_verified(update, context):
        return
    await _mini_launcher(update, "🔴 <b>IBETIN LIVE</b>", site_button("OPEN LIVE", IBETIN_LIVE_URL), "live")


async def support_command(update, context) -> None:
    if not await _require_verified(update, context):
        return
    await _mini_launcher(update, "🛟 <b>IBETIN SUPPORT</b>", site_button("OPEN SUPPORT", IBETIN_SUPPORT_URL), "support")


async def news_command(update, context) -> None:
    if not await _require_verified(update, context):
        return
    await _mini_launcher(update, "📰 <b>IBETIN SPORTS NEWS</b>", news.news_webapp_button("OPEN SPORTS NEWS"), "news:latest")


async def sports_command(update, context) -> None:
    if not await _require_verified(update, context):
        return
    await _mini_launcher(update, "🏆 <b>IBETIN SPORTS</b>", site_button("OPEN SPORTS", IBETIN_SPORTS_URL), "sports")


async def team_command(update, context) -> None:
    if not await _require_verified(update, context):
        return
    await _mini_launcher(update, "🔎 <b>FIND A TEAM</b>", site_button("OPEN SPORTS SEARCH", IBETIN_SPORTS_URL), "find_team")


async def help_command(update, context) -> None:
    user = update.effective_user
    message = update.effective_message
    if not message or not user:
        return
    if not await _require_verified(update, context):
        return
    await message.reply_text(
        "⚡ <b>IBETIN HELP</b>\n\nEvery option below opens as a Telegram Mini App.",
        parse_mode="HTML",
        reply_markup=premium_main_keyboard(user.id),
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
        await _prompt_mobile_verification(update, context, "liveline")
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


async def admin_crm_text_handler(update, context) -> None:
    """Consume Search/Note input before normal verified-user text routing."""
    if await ibetin_reports.admin_text_handler(update, context):
        raise ApplicationHandlerStop


# =========================================================
# TELEGRAM UI
# =========================================================

async def configure_telegram_ui(application) -> None:
    # Telegram shows these before a new user presses START. Keep the copy
    # factual, sports-focused and useful for paid-traffic landing clarity.
    await application.bot.set_my_short_description(
        "IBETIN Sports Hub • Live Line • Match updates • News • Alerts"
    )
    await application.bot.set_my_description(
        "Welcome to IBETIN Sports Hub. Follow cricket and football updates, "
        "open IBETIN Live Line, view match results and sports news, manage "
        "match alerts, and access official support. Verify your Telegram-linked "
        "mobile once to continue. 18+ • Play responsibly."
    )

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

    # Default menu is Commands so an unverified user cannot bypass the
    # verification gate through Telegram's native Menu button. A per-user
    # "Open IBETIN" WebApp menu is enabled immediately after verification.
    await application.bot.set_chat_menu_button(
        menu_button=MenuButtonCommands()
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
        ),
        group=-10,
    )
    application.add_handler(
        MessageHandler(
            filters.UpdateType.MESSAGE & filters.TEXT & ~filters.COMMAND,
            pending_verification_text_handler,
        ),
        group=-10,
    )
    application.add_handler(
        MessageHandler(
            filters.UpdateType.MESSAGE & filters.TEXT & ~filters.COMMAND,
            admin_crm_text_handler,
        ),
        group=-5,
    )
    application.add_handler(
        MessageHandler(
            filters.UpdateType.MESSAGE
            & filters.TEXT
            & filters.Regex(r"^▶️ START$"),
            start_button_handler,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.UpdateType.MESSAGE
            & filters.TEXT
            & ~filters.COMMAND
            & ~filters.Regex(r"^(?:▶️ START|⚡ IBETIN Menu)$"),
            verified_fixed_reply_handler,
        ),
        group=10,
    )
    application.add_handler(CommandHandler("livetvadmin", live_tv_admin_command))

    phone_verify.ensure_tables()
    ibetin_leads.ensure_tables()
    ibetin_reports.ensure_tables()
    ibetin_reports.log_admin_diagnostics()
    await ibetin_reports.push_report_center_to_unlocked_admin(application)
    reset_count = phone_verify.apply_requested_reset()
    if reset_count:
        logger.info("IBETIN Live Line verification reset applied rows=%s", reset_count)

    username_reset_count = phone_verify.apply_requested_username_reset()
    if username_reset_count:
        logger.info(
            "IBETIN mobile verification username reset applied rows=%s",
            username_reset_count,
        )

    user_id_reset_count = phone_verify.apply_requested_user_id_reset()
    if user_id_reset_count:
        logger.info(
            "IBETIN mobile verification exact-user reset applied rows=%s",
            user_id_reset_count,
        )
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
