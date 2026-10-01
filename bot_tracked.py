import logging
import os
import re
from urllib.parse import urlencode

from telegram import (
    BotCommand,
    BotCommandScopeChat,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    MenuButtonCommands,
    MenuButtonWebApp,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    WebAppInfo,
)
from telegram.error import BadRequest, Forbidden
from telegram.ext import ApplicationHandlerStop, CommandHandler, MessageHandler, filters

import bot_persistent as app
import fantzo_analytics as analytics
import fantzo_business
import fantzo_live_tv
import fantzo_reminders as reminders
import ibetin_hub as hub
import ibetin_creatives
import public_start_banner
import ibetin_leads
import ibetin_news as news
import ibetin_phone_verify as phone_verify
import ibetin_reports
import private_apk_upload
import trial_live_tv

logger = logging.getLogger(__name__)

# =========================================================
# DURASPORTS WEBSITE
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
IBETIN_CHANNEL_URL = "https://t.me/durasportsofficial"

# =========================================================
# LIVE TV SETTINGS
# =========================================================

SKY_ADMIN_BASE_URL = os.getenv("SKY_ADMIN_BASE_URL", "").strip().rstrip("/")
SKY_ADMIN_TEST_TOKEN = os.getenv("SKY_ADMIN_TEST_TOKEN", "").strip()
LIVE_TV_MODE = os.getenv("LIVE_TV_MODE", "admin").strip().lower()
if LIVE_TV_MODE not in {"off", "admin", "public"}:
    LIVE_TV_MODE = "admin"


# =========================================================
# DURASPORTS BRAND COPY
# =========================================================

def _install_ibetin_hub_copy() -> None:
    en = app.core.TEXT.get("en", {})
    en.update(
        {
            "welcome": (
                "⚡ <b>WELCOME TO DURASPORTS</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "Your front page for live sport, right inside Telegram.\n\n"
                "🏏 <b>Live Line</b> · ball-by-ball scores\n"
                "🔴 <b>Live now</b> · matches in play\n"
                "🏆 <b>Sports</b> · fixtures and results\n"
                "📰 <b>Sports News</b> · fresh headlines\n"
                "🔔 <b>Match Alerts</b> · straight to your chat\n"
                "🛟 <b>Support</b> · real people, fast help\n\n"
                "👇 Tap a button below to begin.\n\n"
                ""
            ),
            "explore": (
                "🌐 <b>DURASPORTS MINI APP HUB</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "📲 Every section opens right here in Telegram.\n"
                "👇 Pick where you want to go.\n\n"
                ""
            ),
            "join": (
                "🌐 <b>OPEN DURASPORTS</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "📲 Continue in the DURASPORTS Mini App, right inside Telegram.\n"
                "👇 Tap below to open.\n\n"
                ""
            ),
            "settings": (
                "⚙️ <b>DURASPORTS SETTINGS</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "🌐 Language, alerts and preferences in one place.\n"
                "👇 Open settings in the DURASPORTS Mini App."
            ),
        }
    )

    hi = app.core.TEXT.get("hi", {})
    hi.update(
        {
            "welcome": (
                "⚡ <b>DURASPORTS में आपका स्वागत है</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "लाइव खेल, सीधे Telegram के अंदर।\n\n"
                "🏏 <b>Live Line</b> · बॉल-बाय-बॉल स्कोर\n"
                "🔴 <b>Live</b> · अभी चल रहे मैच\n"
                "🏆 <b>Sports</b> · फिक्स्चर और रिज़ल्ट\n"
                "📰 <b>Sports News</b> · ताज़ा खबरें\n"
                "🔔 <b>Match Alerts</b> · सीधे आपकी चैट में\n"
                "🛟 <b>Support</b> · तुरंत मदद\n\n"
                "👇 शुरू करने के लिए नीचे बटन दबाएँ।\n\n"
                ""
            ),
            "explore": (
                "🌐 <b>DURASPORTS MINI APP HUB</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "📲 हर सेक्शन यहीं Telegram के अंदर खुलेगा।\n"
                "👇 जहाँ जाना है, चुनें।\n\n"
                ""
            ),
            "join": (
                "🌐 <b>OPEN DURASPORTS</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "📲 DURASPORTS Mini App को Telegram के अंदर खोलें।\n"
                "👇 खोलने के लिए नीचे टैप करें।\n\n"
                ""
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
# the DURASPORTS runtime, including Business DM menus, reminders, alerts and news.
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
    logger.info("DURASPORTS native Telegram button colors installed")


_install_native_button_styles()


# =========================================================
# MINI APP HELPERS
# =========================================================

def tracked_url(content: str) -> str:
    return analytics.tracking_url(content)


def mini_app_button(label: str, content: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(label, web_app=WebAppInfo(url=tracked_url(content)))


def site_button(label: str, url: str) -> InlineKeyboardButton:
    """Open an DURASPORTS web section inside Telegram WebApp instead of external browser."""
    return InlineKeyboardButton(label, web_app=WebAppInfo(url=url))


def hub_button(label: str, section: str = "home") -> InlineKeyboardButton:
    return hub.webapp_button(label, section)


def sky_admin_url() -> str:
    if not SKY_ADMIN_BASE_URL or not SKY_ADMIN_TEST_TOKEN:
        return ""
    query = urlencode({"key": SKY_ADMIN_TEST_TOKEN})
    return f"{SKY_ADMIN_BASE_URL}/open?{query}"


# Persistent bottom keyboard: a visible START entry plus direct DURASPORTS access.
app.QUICK_MENU = ReplyKeyboardMarkup(
    [[
        KeyboardButton("▶️ START", api_kwargs={"style": "primary"}),
        KeyboardButton("⚡ OPEN DURASPORTS", web_app=WebAppInfo(url=hub.hub_url("home")), api_kwargs={"style": "success"}),
    ]],
    resize_keyboard=True,
    is_persistent=True,
    input_field_placeholder="Tap START or open DURASPORTS",
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

PREVERIFY_COMMANDS = (
    BotCommand("start", "Get started"),
    BotCommand("help", "Help and quick guide"),
    BotCommand("support", "Contact support"),
)

VERIFIED_COMMANDS = (
    BotCommand("start", "Open the DURASPORTS hub"),
    BotCommand("news", "Latest sports news"),
    BotCommand("website", "Open DURASPORTS Mini App"),
    BotCommand("live", "Matches live now"),
    BotCommand("liveline", "Ball-by-ball DURASPORTS Live Line"),
    BotCommand("sports", "Fixtures, scores and results"),
    BotCommand("team", "Find your team"),
    BotCommand("support", "Talk to DURASPORTS support"),
    BotCommand("help", "DURASPORTS menu and help"),
    BotCommand("reports", "Admin report center"),
)


def _is_stop_text(value: str) -> bool:
    return " ".join(str(value or "").casefold().split()) in STOP_PHRASES


async def _set_user_menu_button(bot, user_id: int, verified: bool) -> None:
    try:
        if verified:
            await bot.set_chat_menu_button(
                chat_id=int(user_id),
                menu_button=MenuButtonWebApp(
                    text="Open DURASPORTS",
                    web_app=WebAppInfo(url=hub.hub_url("home")),
                ),
            )
        else:
            await bot.set_chat_menu_button(
                chat_id=int(user_id),
                menu_button=MenuButtonCommands(),
            )
        await bot.set_my_commands(
            VERIFIED_COMMANDS if verified else PREVERIFY_COMMANDS,
            scope=BotCommandScopeChat(chat_id=int(user_id)),
        )
    except Exception:
        logger.exception("Could not update DURASPORTS per-user menu button")


async def _require_verified(update, context, source: str = "bot_start") -> bool:
    if not _is_private_chat(update):
        await _open_private_chat_prompt(update, context)
        return False
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
# MAIN DURASPORTS HUB — COMPACT SIX-ACTION MENU
# =========================================================

def premium_main_keyboard(user_id: int = 0) -> InlineKeyboardMarkup:
    if user_id and phone_verify.is_verified(user_id):
        live_line_button = site_button(
            "🏏 OPEN DURASPORTS LIVE LINE",
            phone_verify.live_line_url(user_id, IBETIN_LIVE_LINE_URL),
        )
    else:
        live_line_button = InlineKeyboardButton(
            "🏏 OPEN DURASPORTS LIVE LINE",
            callback_data="liveline_access",
        )

    rows = [
        [hub_button("🚀 JOIN DURASPORTS", "home")],
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
            [hub_button("🚀 JOIN DURASPORTS", "home")],
            [site_button("🏏 OPEN DURASPORTS LIVE LINE", live_url)],
            [InlineKeyboardButton("📢 JOIN CHANNEL", url=IBETIN_CHANNEL_URL)],
        ]
    )


def premium_join_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [site_button("🌐 OPEN DURASPORTS", IBETIN_HOME_URL)],
            [
                site_button("🏆 SPORTS", IBETIN_SPORTS_URL),
                site_button("🔴 LIVE", IBETIN_LIVE_URL),
            ],
            [
                site_button("🎰 LIVE CASINO", IBETIN_CASINO_URL),
                site_button("🎮 GAMES", IBETIN_GAMES_URL),
            ],
            [hub_button("⚡ DURASPORTS MINI APP HOME", "home")],
        ]
    )


def premium_explore_keyboard(user_id: int = 0) -> InlineKeyboardMarkup:
    rows = [
        [hub_button("🌐 DURASPORTS MINI APP HOME", "home")],
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
    try:
        banner = ibetin_creatives.pick_creative("channel", key=user.id)
    except Exception:
        logger.exception("Could not select DURA home creative")
        banner = None
    markup = premium_main_keyboard(user.id)

    if banner:
        try:
            await ibetin_creatives._send_creative_as_photo(
                context.bot,
                banner,
                {
                    "chat_id": message.chat_id,
                    "caption": app.core.TEXT[lang]["welcome"],
                    "parse_mode": "HTML",
                    "reply_markup": markup,
                },
            )
            return
        except Exception as exc:
            logger.warning("DURASPORTS banner send failed, falling back to text: %s", exc)

    await message.reply_text(
        app.core.TEXT[lang]["welcome"],
        parse_mode="HTML",
        reply_markup=markup,
        disable_web_page_preview=True,
    )


app.show_home = smart_show_home


async def safe_setbanner_command(update, context) -> None:
    if not ibetin_creatives._is_admin(update):
        await update.effective_message.reply_text("This command is restricted.")
        return
    await update.effective_message.reply_text(
        "DURA home images use the reviewed creative library. "
        "Use /bulkcreatives, then /creativepreview ID and /creativeapprove ID."
    )


async def blocked_legacy_banner_upload(update, context) -> None:
    return


app.setbanner_command = safe_setbanner_command
app.banner_upload = blocked_legacy_banner_upload


def _verification_reply_keyboard() -> ReplyKeyboardMarkup:
    """Keep START and contact verification visible until verification succeeds."""
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📱 VERIFY & CONTINUE", request_contact=True, api_kwargs={"style": "primary"})]],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
        input_field_placeholder="Tap VERIFY & CONTINUE",
    )


def _is_private_chat(update) -> bool:
    chat = getattr(update, "effective_chat", None) or getattr(
        getattr(update, "effective_message", None), "chat", None
    )
    return getattr(chat, "type", None) == "private"


async def _open_private_chat_prompt(update, context) -> None:
    message = update.effective_message
    if not message:
        return
    username = str(getattr(context.bot, "username", "") or "").lstrip("@")
    markup = None
    if re.fullmatch(r"[A-Za-z0-9_]{5,32}", username):
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("OPEN PRIVATE CHAT", url=f"https://t.me/{username}?start=verify")
        ]])
    try:
        await message.reply_text(
            "Open this bot in a private chat and send /start to continue.",
            reply_markup=markup,
            disable_web_page_preview=True,
        )
    except (BadRequest, Forbidden):
        # Some groups and channels do not allow the bot to send messages.
        # Verification continues only when the user opens the private chat.
        logger.info("DURA private-chat prompt could not be posted in this chat")


async def _prompt_mobile_verification(update, context, source: str = "bot_start") -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return
    if not _is_private_chat(update):
        await _open_private_chat_prompt(update, context)
        return

    source = str(source or "bot_start")[:64]

    # Verification is account-level and one-time. If already verified, never
    # ask again; continue directly to the requested destination.
    if phone_verify.is_verified(user.id):
        await _set_user_menu_button(context.bot, user.id, True)
        await message.reply_text("✅ <b>Quick access is ready</b>\n👇 Your shortcuts are pinned below the chat.", parse_mode="HTML", reply_markup=app.QUICK_MENU)
        if source == "liveline":
            await message.reply_text(
                "🏏 <b>DURASPORTS LIVE LINE</b>\n\n⚡ Ball-by-ball scores and full scorecards.\n👇 Open Live Line below.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton(
                        "🏏 OPEN DURASPORTS LIVE LINE",
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
                "✅ <b>You're verified and all set.</b>\n\n"
                "👇 Choose what you want to do next.",
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
        logger.exception("Could not register DURASPORTS verification reminder")

    detail = "Verify your Telegram-linked mobile once to continue."

    await message.reply_text(
        "📱 <b>VERIFY MOBILE TO CONTINUE</b>\n\n"
        f"🔐 {detail}\n\n"
        "👇 Tap <b>📱 VERIFY &amp; CONTINUE</b> below. Telegram will share your linked mobile number.\n\n"
        "📞 By continuing, you agree that the DURA team may contact you by "
        "<b>phone call or WhatsApp</b>. You can opt out anytime.",
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
                "🆕 <b>NEW VERIFIED DURASPORTS LEAD</b>\n"
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
        logger.exception("Could not send DURASPORTS verified lead alert")


async def mobile_contact_handler(update, context) -> None:
    user = update.effective_user
    message = update.effective_message
    contact = message.contact if message else None
    if not user or not message or not contact:
        return
    if not _is_private_chat(update):
        await _open_private_chat_prompt(update, context)
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
    await message.reply_text("✅ Verification complete. Use START or OPEN DURASPORTS below.", reply_markup=app.QUICK_MENU)

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
        logger.exception("Could not track DURASPORTS mobile verification")

    logger.info(
        "DURASPORTS mobile verified user_id=%s source=%s campaign=%s",
        user.id,
        source,
        campaign,
    )

    if not was_verified:
        await _notify_verified_lead(context, user, phone, source, campaign)

    if source == "liveline":
        success_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton(
                "🏏 OPEN DURASPORTS LIVE LINE",
                web_app=WebAppInfo(
                    url=phone_verify.live_line_url(user.id, IBETIN_LIVE_LINE_URL)
                ),
            )]]
        )
        success_text = (
            "✅ <b>Mobile verified</b>\n"
            f"<code>{masked}</code>\n\n"
            "🏏 Live Line is ready."
        )
    elif source == "business_dm":
        success_markup = fantzo_business.business_keyboard(user.id)
        success_text = (
            "✅ <b>Mobile verified</b>\n"
            f"<code>{masked}</code>\n\n"
            "Choose what you want to do next."
        )
    else:
        success_markup = conversion_keyboard(user.id)
        success_text = (
            "✅ <b>Mobile verified</b>\n"
            f"<code>{masked}</code>\n\n"
            "Choose what you want to do next."
        )

    await message.reply_text(
        success_text,
        parse_mode="HTML",
        reply_markup=success_markup,
    )
    return


async def pending_verification_text_handler(update, context) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message or not message.text:
        return
    if phone_verify.is_verified(user.id):
        return
    if not _is_private_chat(update):
        await _open_private_chat_prompt(update, context)
        raise ApplicationHandlerStop
    await _set_user_menu_button(context.bot, user.id, False)

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
        logger.exception("Could not register DURASPORTS verification reminder from text gate")
    await message.reply_text(
        "📱 <b>Verification needed</b>\n\n"
        "Typed numbers cannot verify your account. Tap <b>📱 VERIFY & CONTINUE</b> below.",
        parse_mode="HTML",
        reply_markup=_verification_reply_keyboard(),
    )
    raise ApplicationHandlerStop


async def pending_verification_command_handler(update, context) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message or phone_verify.is_verified(user.id):
        return
    # /start owns the verification handoff and the stopreminders opt-out link.
    if (message.text or "").split(maxsplit=1)[0].split("@", 1)[0].lower() == "/start":
        return
    await _set_user_menu_button(context.bot, user.id, False)
    await _prompt_mobile_verification(update, context, "bot_start")
    raise ApplicationHandlerStop


async def pending_verification_media_handler(update, context) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message or phone_verify.is_verified(user.id):
        return
    await _set_user_menu_button(context.bot, user.id, False)
    await _prompt_mobile_verification(update, context, "bot_start")
    raise ApplicationHandlerStop


async def verified_fixed_reply_handler(update, context) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message or not message.text:
        return
    if not _is_private_chat(update):
        return
    if not phone_verify.is_verified(user.id):
        return
    text = message.text.strip()
    if not text or text in {"▶️ START", "⚡ DURASPORTS Menu"}:
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
            "You can still use DURASPORTS and official support anytime.",
            parse_mode="HTML",
        )
        return

    if not app.fantzo_autoreply.is_enabled():
        return

    category, reply, markup = fantzo_business.classify_business_dm(text, user.id)
    try:
        app.core.touch_user(update)
        app.core.track(user.id, f"bot_text:{category}")
    except Exception:
        logger.exception("Could not track DURASPORTS fixed reply")

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
    if not _is_private_chat(update):
        await _open_private_chat_prompt(update, context)
        return

    # Telegram does not report chat deletion. A new /start is the tester's
    # explicit entry point; the in-chat START button keeps the current visit.
    start_words = str(message.text or "").split(None, 1)
    if (
        int(user.id) == phone_verify.TEST_REVERIFY_USER_ID
        and start_words
        and start_words[0].split("@", 1)[0].lower() == "/start"
    ):
        revoked = phone_verify.reset_test_verification_on_start(user.id)
        logger.info("TEST_VERIFICATION_RESET_ON_START user_id=%s revoked=%s", user.id, revoked)

    if arg == "stopreminders":
        reminders.set_opt_out("bot", user.id, True)
        reminders.set_opt_out("business_dm", user.id, True)
        await message.reply_text(
            "🔕 <b>Reminders are off.</b>", parse_mode="HTML"
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
        logger.exception("Could not track DURASPORTS campaign start")

    # Fantzo-style global onboarding gate: first DURASPORTS entry requires a
    # Telegram self-contact verification. Once verified, all DURASPORTS features
    # including Live Line reuse the same record and do not ask again.
    if not phone_verify.is_verified(user.id):
        await _set_user_menu_button(context.bot, user.id, False)
        try:
            app.core.touch_user(update)
            reminders.touch_user("bot", user.id, "verification")
            app.core.track(user.id, "mobile_verify:bot_start")
        except Exception:
            logger.exception("Could not track DURASPORTS bot-start verification")
        await _prompt_mobile_verification(update, context, "bot_start")
        return

    await _set_user_menu_button(context.bot, user.id, True)
    await message.reply_text("✅ <b>Quick access is ready</b>\n👇 Your shortcuts are pinned below the chat.", parse_mode="HTML", reply_markup=app.QUICK_MENU)
    await message.reply_text(
        "👋 <b>Welcome back to DURASPORTS</b>\n\n🏏 Live Line · 📊 Scorecards · 📰 News\n👇 Choose what you want to do next.",
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
    await _mini_launcher(update, "🌐 <b>DURASPORTS MINI APP</b>", hub_button("OPEN DURASPORTS MINI APP", "home"), "website_hub")


async def live_command(update, context) -> None:
    if not await _require_verified(update, context):
        return
    await _mini_launcher(update, "🔴 <b>DURASPORTS LIVE</b>", site_button("OPEN LIVE", IBETIN_LIVE_URL), "live")


async def support_command(update, context) -> None:
    if not await _require_verified(update, context):
        return
    await _mini_launcher(update, "🛟 <b>DURASPORTS SUPPORT</b>", site_button("OPEN SUPPORT", IBETIN_SUPPORT_URL), "support")


async def news_command(update, context) -> None:
    if not await _require_verified(update, context):
        return
    await _mini_launcher(update, "📰 <b>DURASPORTS SPORTS NEWS</b>", news.news_webapp_button("OPEN SPORTS NEWS"), "news:latest")


async def sports_command(update, context) -> None:
    if not await _require_verified(update, context):
        return
    await _mini_launcher(update, "🏆 <b>DURASPORTS SPORTS</b>", site_button("OPEN SPORTS", IBETIN_SPORTS_URL), "sports")


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
        "⚡ <b>DURASPORTS MENU</b>\n━━━━━━━━━━━━━━━━━━\n\n🏏 Live Line and full scorecards\n📰 Sports news\n🔔 Match alerts\n🛟 Support\n\n👇 Choose an option below.",
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
    query = update.callback_query
    user = update.effective_user
    if not _is_private_chat(update):
        if query:
            try:
                await query.answer()
            except Exception:
                pass
        await _open_private_chat_prompt(update, context)
        return
    if query and query.data == "dura_link_unavailable":
        await query.answer("This option is temporarily unavailable. Please try again later.", show_alert=True)
        return
    if user and not phone_verify.is_verified(user.id):
        if query:
            try:
                await query.answer()
            except Exception:
                pass
        await _set_user_menu_button(context.bot, user.id, False)
        await _prompt_mobile_verification(update, context, "bot_start")
        return

    if await ibetin_reports.handle_callback(update, context):
        return

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
    if app.core.is_admin_user(user.id):
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
        "📺 <b>DURASPORTS LIVE TV · ADMIN</b>\n"
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

async def _set_active_bot_username(bot) -> str:
    # Resolve the running bot before building verification links. If Telegram
    # cannot provide an identity, continue with neutral copy and no deep link.
    username = str(getattr(bot, "username", "") or "").lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", username):
        try:
            me = await bot.get_me()
            username = str(getattr(me, "username", "") or "").lstrip("@")
        except Exception:
            logger.warning("Could not resolve DURA bot username for verification links")
    if re.fullmatch(r"[A-Za-z0-9_]{5,32}", username):
        os.environ["IBETIN_BOT_USERNAME"] = username
        logger.info("DURA active Telegram bot username: @%s", username)
        return username
    else:
        os.environ.pop("IBETIN_BOT_USERNAME", None)
        logger.warning("DURA verification deep links disabled until bot identity is available")
        return ""


async def configure_telegram_ui(application) -> None:
    public_start_banner.install(application)
    await _set_active_bot_username(application.bot)
    # Telegram shows these before a new user verifies their account.
    await application.bot.set_my_short_description(
        "🗞 Live line, full scorecards and sports news, every match as it happens."
    )
    await application.bot.set_my_description(
        "🗞 Your front page for live sport.\n🏏 Live line and full scorecards\n⚽ Live scores from the top leagues\n📰 Sports updates as they happen\n🔔 Match alerts straight to your chat\nTap START and stay ahead of the game!"
    )
    await application.bot.set_my_commands(PREVERIFY_COMMANDS)

    # The global bot profile stays neutral; verified chats get the Mini App menu.
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
            filters.UpdateType.MESSAGE & filters.COMMAND,
            pending_verification_command_handler,
        ),
        group=-15,
    )
    application.add_handler(
        MessageHandler(
            filters.UpdateType.MESSAGE & ~(filters.TEXT | filters.CONTACT),
            pending_verification_media_handler,
        ),
        group=-15,
    )
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
            & ~filters.Regex(r"^(?:▶️ START|⚡ DURASPORTS Menu)$"),
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
        logger.info("DURASPORTS Live Line verification reset applied rows=%s", reset_count)

    username_reset_count = phone_verify.apply_requested_username_reset()
    if username_reset_count:
        logger.info(
            "DURASPORTS mobile verification username reset applied rows=%s",
            username_reset_count,
        )

    user_id_reset_count = phone_verify.apply_requested_user_id_reset()
    if user_id_reset_count:
        logger.info(
            "DURASPORTS mobile verification exact-user reset applied rows=%s",
            user_id_reset_count,
        )
    reminders.ensure_tables()
    reminders.start_background_loop(application)
    ibetin_creatives.install(application)


app.configure_telegram_ui = configure_telegram_ui


# =========================================================
# START DURASPORTS
# =========================================================

if __name__ == "__main__":
    hub.install_on_tracking_handler(analytics, install_runtime_ui=False)
    private_apk_upload.install_on_tracking_handler(analytics)
    trial_live_tv.install_on_tracking_handler(analytics)
    fantzo_live_tv.install_on_tracking_handler(analytics)
    analytics.start_tracking_server()
    logger.info("Starting DURASPORTS Mini-App-first bot with LIVE_TV_MODE=%s", LIVE_TV_MODE)
    app.run()
