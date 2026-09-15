import asyncio
import logging
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest, RetryAfter
from telegram.ext import ContextTypes

import bot as core
import fantzo_analytics as analytics
import fantzo_autoreply
import fantzo_live_tv

logger = logging.getLogger(__name__)

RESPONSIBLE_NOTE = "<i>🔞 18+ • Play responsibly • T&Cs apply</i>"
FANTZO_CHANNEL_URL = "https://t.me/fantzoupdates"

WELCOME_REPLY = (
    "👋 <b>Welcome to Fantzo</b>\n\n"
    "Live sports, updates and more — choose what you want to do below.\n\n"
    f"{RESPONSIBLE_NOTE}"
)


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
            CREATE TABLE IF NOT EXISTS business_welcomes (
                connection_id TEXT NOT NULL,
                customer_id INTEGER NOT NULL,
                welcomed_at TEXT NOT NULL,
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


def _has_been_welcomed(connection_id: str, customer_id: int) -> bool:
    if not connection_id or not customer_id:
        return False

    ensure_tables()
    with core.db() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM business_welcomes
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
            INSERT OR IGNORE INTO business_welcomes(
                connection_id, customer_id, welcomed_at
            ) VALUES (?, ?, ?)
            """,
            (connection_id, customer_id, core.now_iso()),
        )


def _contains(text: str, words) -> bool:
    return any(re.search(rf"\b{re.escape(word)}\b", text) for word in words)


def _funnel_buttons(source: str, destination: str = "home") -> InlineKeyboardMarkup:
    """Keep every Business reply focused on the same three user actions."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🎮 PLAY FANTZO",
                    url=analytics.tracking_url(f"{source}_play", destination),
                )
            ],
            [
                InlineKeyboardButton(
                    "📺 WATCH LIVE TV",
                    url=fantzo_live_tv.minitv_url(),
                )
            ],
            [
                InlineKeyboardButton(
                    "📢 SUBSCRIBE CHANNEL",
                    url=FANTZO_CHANNEL_URL,
                )
            ],
        ]
    )


def _welcome_buttons() -> InlineKeyboardMarkup:
    return _funnel_buttons("business_welcome")


def classify_business_dm(text: str):
    t = " ".join((text or "").lower().strip().split())

    if _contains(t, ["hi", "hello", "hey", "hii", "hola", "namaste"]):
        return (
            "greeting",
            WELCOME_REPLY,
            _funnel_buttons("business_greeting"),
        )

    if _contains(t, ["cricket", "football", "soccer", "ipl", "t20", "odi", "match", "score", "live", "sports"]):
        return (
            "sports",
            "🏏 <b>Sports & live action</b>\n\n"
            "You can play on Fantzo, open Live TV, or subscribe for updates below.\n\n"
            f"{RESPONSIBLE_NOTE}",
            _funnel_buttons("business_sports", "live"),
        )

    if _contains(t, ["join", "start", "get started", "new user", "create account", "signup", "sign up", "register", "registration"]):
        return (
            "join",
            "🚀 <b>Ready to get started?</b>\n\n"
            "Tap <b>PLAY FANTZO</b> below to continue.\n\n"
            f"{RESPONSIBLE_NOTE}",
            _funnel_buttons("business_join", "register"),
        )

    if _contains(t, ["login", "log in", "account", "password", "otp", "account help"]):
        return (
            "account",
            "👤 <b>Account help</b>\n\n"
            "For login or account options, open Fantzo below.\n\n"
            "🔐 Never share your password or OTP here.",
            _funnel_buttons("business_account"),
        )

    if _contains(t, ["deposit", "payment", "pay", "upi", "add money", "recharge"]):
        return (
            "deposit",
            "💳 <b>Payment / deposit</b>\n\n"
            "Payment options are shown inside Fantzo based on your account.\n\n"
            "🔐 Never send OTPs, passwords or full card/bank details in chat.\n\n"
            f"{RESPONSIBLE_NOTE}",
            _funnel_buttons("business_deposit"),
        )

    if _contains(t, ["withdraw", "withdrawal", "payout", "cashout", "cash out"]):
        return (
            "withdrawal",
            "💸 <b>Withdrawal</b>\n\n"
            "Open Fantzo to check your account and available support options.",
            _funnel_buttons("business_withdrawal"),
        )

    if _contains(t, ["bonus", "offer", "promo", "promotion", "cashback"]):
        return (
            "offers",
            "🎁 <b>Offers</b>\n\n"
            "Check Fantzo directly for currently available offers, eligibility and terms.\n\n"
            f"{RESPONSIBLE_NOTE}",
            _funnel_buttons("business_offers"),
        )

    if _contains(t, ["support", "help", "problem", "issue", "complaint", "failed", "pending", "stuck"]):
        return (
            "support",
            "🛟 <b>Tell me what happened.</b>\n\n"
            "Send a short description of the issue here. For anything requiring private account or transaction data, continue through Fantzo.",
            _funnel_buttons("business_support"),
        )

    if _contains(t, ["thanks", "thank", "thx", "ok", "okay"]):
        return (
            "thanks",
            "🙏 You’re welcome. Choose an option below whenever you’re ready.",
            _funnel_buttons("business_thanks"),
        )

    return (
        "general",
        "👋 <b>How can I help?</b>\n\n"
        "You can message me about sports, getting started, account access, payments or support.\n\n"
        f"{RESPONSIBLE_NOTE}",
        _funnel_buttons("business_general"),
    )


async def business_connection_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    connection = update.business_connection
    if not connection:
        return
    _save_connection(connection)
    logger.info(
        "Fantzo business connection update: id=%s owner=%s enabled=%s",
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
                logger.warning("Fantzo Business DM keyboard failed: %s", exc)
                kwargs["reply_markup"] = None
                continue
            raise
        except RetryAfter as exc:
            if attempt >= 2:
                logger.error("Fantzo Business DM still rate-limited after retries: %s", exc)
                raise
            delay = _retry_seconds(exc) + 1.0
            logger.warning(
                "Fantzo Business DM rate-limited; retrying in %.1f seconds (attempt %s/3)",
                delay,
                attempt + 2,
            )
            await asyncio.sleep(delay)


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

    # Welcome on the customer's first Business DM of any type: text, sticker,
    # photo, voice, video, document, etc. Mark only after a successful send so
    # transient Telegram failures can retry on the customer's next message.
    if customer_id and connection_id and not _has_been_welcomed(connection_id, customer_id):
        logger.info(
            "Fantzo first Business DM: connection=%s customer=%s sending welcome",
            connection_id,
            customer_id,
        )

        await _reply_with_retry(message, WELCOME_REPLY, _welcome_buttons())
        _mark_welcomed(connection_id, customer_id)

        try:
            core.track(customer_id, "business_dm:welcome")
        except Exception:
            logger.exception("Could not track Fantzo Business DM welcome")

        logger.info(
            "Fantzo Business DM welcome sent: connection=%s customer=%s",
            connection_id,
            customer_id,
        )
        return

    # After the one-time welcome, only text messages go through the smart
    # category reply engine. Non-text follow-ups are left untouched.
    if not message.text:
        return

    text = message.text.strip()
    if not text or text.startswith("/"):
        return

    category, reply, markup = classify_business_dm(text)

    try:
        if customer_id:
            core.track(customer_id, f"business_dm:{category}")
    except Exception:
        logger.exception("Could not track Fantzo business DM")

    logger.info(
        "Fantzo business DM received: connection=%s customer=%s category=%s",
        connection_id,
        customer_id or None,
        category,
    )

    await _reply_with_retry(message, reply, markup)
