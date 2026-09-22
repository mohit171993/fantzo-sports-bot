import asyncio
import logging
import os
import re
import time
from urllib.parse import quote

from telegram import InlineKeyboardButton as TelegramInlineKeyboardButton
from telegram import InlineKeyboardMarkup, Update
from telegram.error import BadRequest, RetryAfter
from telegram.ext import ApplicationHandlerStop, ContextTypes

import bot as core
import fantzo_autoreply
import ibetin_phone_verify as phone_verify
import ibetin_leads

logger = logging.getLogger(__name__)

BOT_USERNAME = os.getenv("IBETIN_BOT_USERNAME", "Ibtnofficialbot").strip().lstrip("@") or "Ibtnofficialbot"
LIVELINE_MINI_APP_URL = os.getenv(
    "IBETIN_LIVELINE_MINI_APP_DEEP_LINK",
    f"https://t.me/{BOT_USERNAME}/liveline?startapp=liveline",
).strip()
LIVE_LINE_DIRECT_URL = os.getenv(
    "IBETIN_LIVE_LINE_URL",
    "https://ibetin-app-production.up.railway.app/liveline",
).strip()
ALLOWED_MINI_APP_SECTIONS = {
    "home",
    "sports",
    "live",
    "liveline",
    "news",
    "casino",
    "games",
    "results",
    "payments",
    "alerts",
    "support",
    "settings",
}

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


WELCOME_REPLY = (
    "👋 <b>Welcome to IBETIN</b>\n\n"
    "Choose an option below or type what you need."
)

VERIFY_REPLY = (
    "📱 <b>VERIFY MOBILE TO CONTINUE</b>\n\n"
    "Verify your Telegram-linked mobile once to continue with IBETIN Live Line.\n\n"
    "Tap <b>📱 VERIFY & CONTINUE</b> below. By continuing, you agree that the "
    "IBETIN team may contact you by <b>phone call or WhatsApp</b>. "
    "You can opt out anytime.\n\n"
    "🔞 <b>18+ • Play responsibly</b>"
)


def telegram_mini_app_url(section: str = "home") -> str:
    section = (section or "home").strip().lower()
    if section not in ALLOWED_MINI_APP_SECTIONS:
        section = "home"
    return f"https://t.me/{BOT_USERNAME}?startapp={quote(section, safe='')}"


def _business_url(section: str = "home", customer_id: int = 0) -> str:
    section = (section or "home").strip().lower()
    if section == "liveline":
        if customer_id and phone_verify.is_verified(customer_id):
            return phone_verify.live_line_url(customer_id, LIVE_LINE_DIRECT_URL)
        return phone_verify.verification_bot_url()
    return telegram_mini_app_url(section)


def _button(label: str, section: str, customer_id: int = 0) -> TelegramInlineKeyboardButton:
    return TelegramInlineKeyboardButton(label, url=_business_url(section, customer_id))


def business_reply_text() -> str:
    return WELCOME_REPLY


def verification_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[
            TelegramInlineKeyboardButton(
                "📱 VERIFY & CONTINUE",
                url=phone_verify.verification_bot_url("verify_business_dm"),
            )
        ]]
    )


def business_keyboard(customer_id: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_button("🚀 JOIN IBETIN", "home", customer_id)],
            [_button("🏏 OPEN IBETIN LIVE LINE", "liveline", customer_id)],
            [
                TelegramInlineKeyboardButton(
                    "📢 JOIN CHANNEL",
                    url="https://t.me/ibetinoffcial",
                )
            ],
        ]
    )


def _sports_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_button("🏆 SPORTS", "sports"), _button("🔴 LIVE NOW", "live")],
            [_button("📊 RESULTS", "results"), _button("📰 NEWS", "news")],
        ]
    )


def _payments_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_button("💳 PAYMENTS", "payments")],
            [_button("🛟 SUPPORT", "support"), _button("⚡ IBETIN HOME", "home")],
        ]
    )


def _support_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[_button("🛟 OPEN SUPPORT", "support")], [_button("⚡ IBETIN HOME", "home")]]
    )


def _single_keyboard(label: str, section: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[_button(label, section)]])


def ensure_tables() -> None:
    with core.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS business_connections (
                connection_id TEXT PRIMARY KEY,
                owner_user_id INTEGER,
                owner_username TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS business_customers (
                connection_id TEXT NOT NULL,
                customer_id INTEGER NOT NULL,
                username TEXT DEFAULT '',
                first_name TEXT DEFAULT '',
                last_seen TEXT NOT NULL,
                PRIMARY KEY (connection_id, customer_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS business_welcomes (
                connection_id TEXT NOT NULL,
                customer_id INTEGER NOT NULL,
                welcomed_at TEXT NOT NULL,
                PRIMARY KEY (connection_id, customer_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS business_reply_state (
                connection_id TEXT NOT NULL,
                customer_id INTEGER NOT NULL,
                last_category TEXT DEFAULT '',
                last_text TEXT DEFAULT '',
                last_reply_ts INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (connection_id, customer_id)
            )
            """
        )


def _save_connection(connection) -> None:
    ensure_tables()
    owner = connection.user
    with core.db() as conn:
        conn.execute(
            """
            INSERT INTO business_connections(
                connection_id, owner_user_id, owner_username, enabled, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(connection_id) DO UPDATE SET
                owner_user_id = excluded.owner_user_id,
                owner_username = excluded.owner_username,
                enabled = excluded.enabled,
                updated_at = excluded.updated_at
            """,
            (
                connection.id,
                owner.id if owner else None,
                owner.username if owner else None,
                1 if connection.is_enabled else 0,
                core.now_iso(),
            ),
        )


def _owner_user_id(connection_id: str):
    if not connection_id:
        return None
    ensure_tables()
    with core.db() as conn:
        row = conn.execute(
            "SELECT owner_user_id FROM business_connections WHERE connection_id = ?",
            (connection_id,),
        ).fetchone()
    return int(row["owner_user_id"]) if row and row["owner_user_id"] is not None else None


def _save_business_customer(connection_id: str, user) -> None:
    if not connection_id or not user:
        return
    ensure_tables()
    with core.db() as conn:
        conn.execute(
            """
            INSERT INTO business_customers(
                connection_id, customer_id, username, first_name, last_seen
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(connection_id, customer_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_seen = excluded.last_seen
            """,
            (
                connection_id,
                int(user.id),
                str(user.username or ""),
                str(user.first_name or ""),
                core.now_iso(),
            ),
        )


def _has_been_welcomed(connection_id: str, customer_id: int) -> bool:
    if not connection_id or not customer_id:
        return False
    ensure_tables()
    with core.db() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM business_welcomes
            WHERE connection_id = ? AND customer_id = ?
            LIMIT 1
            """,
            (connection_id, customer_id),
        ).fetchone()
    return bool(row)


def _mark_welcomed(connection_id: str, customer_id: int) -> None:
    if not connection_id or not customer_id:
        return
    ensure_tables()
    with core.db() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO business_welcomes(connection_id, customer_id, welcomed_at)
            VALUES (?, ?, ?)
            """,
            (connection_id, customer_id, core.now_iso()),
        )


def _normalize_business_text(text: str) -> str:
    return " ".join(str(text or "").casefold().split())[:500]


def _should_suppress_business_reply(
    connection_id: str,
    customer_id: int,
    category: str,
    text: str,
) -> bool:
    if not connection_id or not customer_id:
        return False

    ensure_tables()
    normalized = _normalize_business_text(text)
    now = int(time.time())
    with core.db() as conn:
        row = conn.execute(
            """
            SELECT last_category, last_text, last_reply_ts
            FROM business_reply_state
            WHERE connection_id = ? AND customer_id = ?
            """,
            (connection_id, int(customer_id)),
        ).fetchone()

    if not row:
        return False

    last_category = str(row["last_category"] or "")
    last_text = str(row["last_text"] or "")
    elapsed = max(0, now - int(row["last_reply_ts"] or 0))

    # Verified users should never experience a silent chat. Only suppress
    # an accidental exact duplicate sent within a few seconds.
    if normalized and normalized == last_text and elapsed < 3:
        return True

    return False


def _mark_business_reply(
    connection_id: str,
    customer_id: int,
    category: str,
    text: str,
) -> None:
    if not connection_id or not customer_id:
        return
    ensure_tables()
    with core.db() as conn:
        conn.execute(
            """
            INSERT INTO business_reply_state(
                connection_id, customer_id, last_category, last_text, last_reply_ts
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(connection_id, customer_id) DO UPDATE SET
                last_category = excluded.last_category,
                last_text = excluded.last_text,
                last_reply_ts = excluded.last_reply_ts
            """,
            (
                connection_id,
                int(customer_id),
                str(category or "general"),
                _normalize_business_text(text),
                int(time.time()),
            ),
        )


def _touch_business_reminder(customer_id: int, connection_id: str, category: str = "general") -> None:
    if not customer_id or not connection_id:
        return
    try:
        import fantzo_reminders as reminders
        reminders.touch_user(
            "business_dm",
            int(customer_id),
            category or "general",
            str(connection_id),
        )
    except Exception:
        logger.exception("Could not persist IBETIN Business DM reminder contact")


def _contains(text: str, words) -> bool:
    return any(re.search(rf"\b{re.escape(word)}\b", text) for word in words)


def classify_business_dm(text: str, customer_id: int = 0):
    t = " ".join((text or "").lower().strip().split())

    if _contains(t, ["hi", "hello", "hey", "hii", "hola", "namaste"]):
        return "greeting", "👋 Hi! How can I help you?", None

    if (
        "live line" in t
        or "liveline" in t
        or "watch live line" in t
        or "cricket line" in t
    ):
        return (
            "liveline",
            "🏏 <b>IBETIN Live Line</b>\n\nOpen IBETIN Live Line below.",
            InlineKeyboardMarkup(
                [[_button("🏏 OPEN IBETIN LIVE LINE", "liveline", customer_id)]]
            ),
        )

    if _contains(
        t,
        [
            "join",
            "join ibetin",
            "i want to join",
            "want to join",
            "play",
            "play now",
            "start",
            "start playing",
            "open ibetin",
            "go to ibetin",
            "signup",
            "sign up",
            "register",
            "registration",
        ],
    ):
        return (
            "join",
            "🚀 <b>Join IBETIN</b>\n\nOpen IBETIN below to continue.",
            InlineKeyboardMarkup(
                [[_button("🚀 JOIN IBETIN", "home", customer_id)]]
            ),
        )

    if _contains(t, ["cricket", "ipl", "t20", "odi", "test", "wicket", "football", "soccer", "goal", "match", "score", "sports"]):
        return (
            "sports",
            "🏆 <b>Sports & live action</b>\n\nOpen sports, live matches, results or the latest news below.",
            _sports_keyboard(),
        )

    if "live tv" in t or "watch live" in t or "live stream" in t or _contains(t, ["live"]):
        return (
            "live",
            "🔴 <b>Live now</b>\n\nOpen the IBETIN live section inside Telegram.",
            _single_keyboard("🔴 OPEN LIVE", "live"),
        )

    if _contains(t, ["news", "update", "updates", "headline", "headlines"]):
        return (
            "news",
            "📰 <b>Sports News</b>\n\nOpen the latest IBETIN sports updates below.",
            _single_keyboard("📰 OPEN SPORTS NEWS", "news"),
        )

    if _contains(t, ["alert", "alerts", "notification", "notifications", "notify", "reminder", "reminders"]):
        return (
            "alerts",
            "🔔 <b>Match Alerts</b>\n\nManage your Telegram sports notifications inside IBETIN.",
            _single_keyboard("🔔 MANAGE ALERTS", "alerts"),
        )

    if _contains(t, ["deposit", "add money", "payment", "pay", "upi", "recharge", "withdraw", "withdrawal", "payout", "cashout", "cash out"]):
        return (
            "payments",
            "💳 <b>Payments</b>\n\nOpen IBETIN payment information or official support. Never share passwords or OTPs in chat.",
            _payments_keyboard(),
        )

    if _contains(t, ["login", "password", "otp", "account", "bonus", "offer", "promo", "promotion"]):
        return (
            "account",
            "👤 <b>Account Help</b>\n\nOpen IBETIN to continue. For account problems, use official support and never send passwords or OTPs here.",
            _payments_keyboard(),
        )

    if _contains(t, ["support", "help", "problem", "issue", "complaint", "failed", "pending", "stuck"]):
        return (
            "support",
            "🛟 <b>IBETIN Support</b>\n\nOpen official support below. If the issue involves a transaction, keep the reference ID ready but do not send passwords, OTPs or full banking credentials.",
            _support_keyboard(),
        )

    if _contains(t, ["thanks", "thank", "thx", "ok", "okay"]):
        return (
            "thanks",
            "🙏 You're welcome. Open IBETIN anytime below.",
            _single_keyboard("⚡ OPEN IBETIN", "home"),
        )

    return (
        "general",
        "🤖 <b>IBETIN Assistant</b>\n\n"
        "I can help you open IBETIN, Live Line or the official channel. "
        "Choose an option below.",
        business_keyboard(customer_id),
    )


async def business_connection_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    connection = update.business_connection
    if not connection:
        return
    _save_connection(connection)
    logger.info(
        "IBETIN business connection update: id=%s owner=%s enabled=%s",
        connection.id,
        connection.user.id if connection.user else None,
        connection.is_enabled,
    )


def _retry_seconds(exc: RetryAfter) -> float:
    value = exc.retry_after
    if hasattr(value, "total_seconds"):
        value = value.total_seconds()
    try:
        return max(1.0, float(value))
    except (TypeError, ValueError):
        return 1.0


async def _reply_with_retry(message, reply: str, markup=None) -> None:
    kwargs = {
        "parse_mode": "HTML",
        "reply_markup": markup,
        "disable_web_page_preview": True,
    }

    for attempt in range(3):
        try:
            await message.reply_text(reply, **kwargs)
            return
        except BadRequest as exc:
            if kwargs.get("reply_markup") is not None:
                logger.warning("IBETIN Business DM keyboard failed: %s", exc)
                kwargs["reply_markup"] = None
                continue
            raise
        except RetryAfter as exc:
            if attempt >= 2:
                logger.error("IBETIN Business DM still rate-limited after retries: %s", exc)
                raise
            delay = _retry_seconds(exc) + 1.0
            logger.warning(
                "IBETIN Business DM rate-limited; retrying in %.1f seconds (attempt %s/3)",
                delay,
                attempt + 2,
            )
            await asyncio.sleep(delay)


async def business_verification_guard(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Hard gate that runs before every normal IBETIN Business-DM handler."""
    message = update.business_message
    if not message:
        return
    if not fantzo_autoreply.is_enabled():
        return
    if message.sender_business_bot:
        return

    connection_id = message.business_connection_id or ""
    owner_id = _owner_user_id(connection_id)
    if owner_id and message.from_user and message.from_user.id == owner_id:
        return

    customer_id = message.from_user.id if message.from_user else 0
    if not customer_id:
        return

    if connection_id and message.from_user:
        _save_business_customer(connection_id, message.from_user)

    ibetin_leads.record_start(customer_id, source="business_dm")

    if _is_stop_text(message.text or ""):
        import fantzo_reminders as reminders
        ibetin_leads.set_status(customer_id, "dnc")
        reminders.set_opt_out("business_dm", customer_id, True)
        reminders.set_opt_out("bot", customer_id, True)
        await _reply_with_retry(
            message,
            "✅ <b>Contact preference updated.</b>\n\n"
            "Promotional follow-up is stopped. You can still use official support anytime.",
            None,
        )
        raise ApplicationHandlerStop

    if phone_verify.is_verified(customer_id):
        return

    await _reply_with_retry(message, VERIFY_REPLY, verification_keyboard())
    _mark_business_reply(
        connection_id,
        customer_id,
        "verification",
        message.text or "",
    )
    try:
        core.track(customer_id, "business_dm:verify_required")
    except Exception:
        logger.exception("Could not track IBETIN Business verification requirement")

    logger.info(
        "IBETIN Business verification guard sent alert and stopped update: "
        "connection=%s customer=%s",
        connection_id,
        customer_id,
    )
    raise ApplicationHandlerStop


async def business_auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.business_message
    if not message:
        return
    if not fantzo_autoreply.is_enabled():
        return
    if message.sender_business_bot:
        return

    connection_id = message.business_connection_id or ""
    owner_id = _owner_user_id(connection_id)
    if owner_id and message.from_user and message.from_user.id == owner_id:
        return

    customer_id = message.from_user.id if message.from_user else 0
    if customer_id and connection_id and message.from_user:
        _save_business_customer(connection_id, message.from_user)

    if customer_id and not phone_verify.is_verified(customer_id):
        verify_text = message.text or ""
        await _reply_with_retry(message, VERIFY_REPLY, verification_keyboard())
        _mark_business_reply(
            connection_id,
            customer_id,
            "verification",
            verify_text,
        )
        try:
            core.track(customer_id, "business_dm:verify_required")
        except Exception:
            logger.exception("Could not track IBETIN Business verification requirement")
        logger.info(
            "IBETIN Business DM verification alert sent: connection=%s customer=%s",
            connection_id,
            customer_id,
        )
        return

    if customer_id and connection_id:
        _touch_business_reminder(customer_id, connection_id, "general")

    if customer_id and connection_id and not _has_been_welcomed(connection_id, customer_id):
        await _reply_with_retry(message, WELCOME_REPLY, business_keyboard(customer_id))
        _mark_welcomed(connection_id, customer_id)
        _mark_business_reply(connection_id, customer_id, "welcome", message.text or "")
        try:
            core.track(customer_id, "business_dm:welcome")
        except Exception:
            logger.exception("Could not track IBETIN Business DM welcome")
        logger.info(
            "IBETIN Business DM welcome sent: connection=%s customer=%s",
            connection_id,
            customer_id,
        )
        return

    if not message.text:
        return

    text = message.text.strip()
    if not text or text.startswith("/"):
        return

    normalized = " ".join(text.casefold().split())
    if _is_stop_text(normalized):
        import fantzo_reminders as reminders

        ibetin_leads.set_status(customer_id, "dnc")
        reminders.set_opt_out("business_dm", customer_id, True)
        reminders.set_opt_out("bot", customer_id, True)
        await _reply_with_retry(
            message,
            "✅ <b>Contact preference updated.</b>\n\n"
            "We will stop promotional follow-up to this Telegram lead. "
            "You can still use IBETIN and official support anytime.",
            None,
        )
        return

    # Test the exact production follow-up renderer in the same Business DM.
    if " ".join(text.lower().split()) in {"test followup", "followup test", "test reminder"}:
        import fantzo_reminders as reminders

        followup_text, followup_markup = reminders._copy_for("general", 1, "business_dm")
        await _reply_with_retry(
            message,
            "🧪 <b>IBETIN FOLLOW-UP TEST</b>\n\n" + followup_text,
            followup_markup,
        )
        logger.info(
            "IBETIN Business DM follow-up test sent: connection=%s customer=%s",
            connection_id,
            customer_id or None,
        )
        return

    category, reply, markup = classify_business_dm(text, customer_id)
    _touch_business_reminder(customer_id, connection_id, category)

    if _should_suppress_business_reply(connection_id, customer_id, category, text):
        logger.info(
            "IBETIN Business DM duplicate reply suppressed: connection=%s customer=%s category=%s",
            connection_id,
            customer_id or None,
            category,
        )
        return

    try:
        if customer_id:
            core.track(customer_id, f"business_dm:{category}")
    except Exception:
        logger.exception("Could not track IBETIN business DM")

    logger.info(
        "IBETIN business DM received: connection=%s customer=%s category=%s",
        connection_id,
        customer_id or None,
        category,
    )

    await _reply_with_retry(message, reply, markup)
    _mark_business_reply(connection_id, customer_id, category, text)
