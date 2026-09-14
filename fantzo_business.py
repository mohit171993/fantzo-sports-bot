import asyncio
import logging
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest, RetryAfter
from telegram.ext import ContextTypes

import bot as core
import fantzo_analytics as analytics
import fantzo_autoreply

logger = logging.getLogger(__name__)

RESPONSIBLE_NOTE = "<i>🔞 18+ • Play responsibly • T&Cs apply</i>"
SPORTS_BOT_URL = "https://t.me/fantzoofficialbot?start=dm"
FANTZO_CHANNEL_URL = "https://t.me/fantzoupdates"
FANTZO_MINI_APP_DEEP_LINK = "https://t.me/fantzoofficialbot?startapp=business_dm"


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


def _contains(text: str, words) -> bool:
    return any(re.search(rf"\b{re.escape(word)}\b", text) for word in words)


def _fantzo_url_button(label: str = "🔥 EXPLORE FANTZO") -> InlineKeyboardButton:
    return InlineKeyboardButton(label, url=FANTZO_MINI_APP_DEEP_LINK)


def _fantzo_button(source: str, label: str = "🔥 EXPLORE FANTZO") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[_fantzo_url_button(label)]])


def _welcome_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_fantzo_url_button("🔥 EXPLORE FANTZO")],
            [InlineKeyboardButton("🏏 LIVE SCORES & FIXTURES", url=SPORTS_BOT_URL)],
            [InlineKeyboardButton("📢 SUBSCRIBE CHANNEL", url=FANTZO_CHANNEL_URL)],
        ]
    )


def classify_business_dm(text: str):
    t = " ".join((text or "").lower().strip().split())

    if _contains(t, ["hi", "hello", "hey", "hii", "hola", "namaste"]):
        return (
            "greeting",
            "👋 <b>Welcome to Fantzo</b>\n\n"
            "Follow the action, explore Fantzo, or simply message me what you need — I’ll point you in the right direction.\n\n"
            "🏏 Live scores & fixtures are available through our sports bot.\n"
            "📢 Subscribe to Fantzo Updates for the latest posts and announcements.\n\n"
            f"{RESPONSIBLE_NOTE}",
            _welcome_buttons(),
        )

    if _contains(t, ["cricket", "football", "soccer", "ipl", "t20", "odi", "match", "score", "live", "sports"]):
        return (
            "sports",
            "🏏 <b>Sports & live action</b>\n\n"
            "For live scores and fixtures, use our sports bot. If you want to continue to Fantzo, tap below.\n\n"
            f"{RESPONSIBLE_NOTE}",
            InlineKeyboardMarkup(
                [
                    [_fantzo_url_button("🔥 EXPLORE FANTZO")],
                    [InlineKeyboardButton("🏏 LIVE SCORES & FIXTURES", url=SPORTS_BOT_URL)],
                    [InlineKeyboardButton("📢 SUBSCRIBE CHANNEL", url=FANTZO_CHANNEL_URL)],
                ]
            ),
        )

    if _contains(t, ["join", "start", "get started", "new user", "create account", "signup", "sign up", "register", "registration"]):
        return (
            "join",
            "🚀 <b>Ready to get started?</b>\n\n"
            "Open Fantzo and continue from the options available there.\n\n"
            f"{RESPONSIBLE_NOTE}",
            _fantzo_button("business_dm_join", "🔥 OPEN FANTZO"),
        )

    if _contains(t, ["login", "log in", "account", "password", "otp", "account help"]):
        return (
            "account",
            "👤 <b>Account help</b>\n\n"
            "I can guide you, but I can’t see private Fantzo account data from Telegram. For login or account options, open Fantzo below.\n\n"
            "🔐 Never share your password or OTP here.",
            _fantzo_button("business_dm_account", "OPEN FANTZO"),
        )

    if _contains(t, ["deposit", "payment", "pay", "upi", "add money", "recharge"]):
        return (
            "deposit",
            "💳 <b>Payment / deposit</b>\n\n"
            "Payment options are shown inside Fantzo based on your account. Open Fantzo to continue.\n\n"
            "🔐 Never send OTPs, passwords or full card/bank details in chat.\n\n"
            f"{RESPONSIBLE_NOTE}",
            _fantzo_button("business_dm_deposit", "OPEN FANTZO"),
        )

    if _contains(t, ["withdraw", "withdrawal", "payout", "cashout", "cash out"]):
        return (
            "withdrawal",
            "💸 <b>Withdrawal</b>\n\n"
            "I can’t see your wallet or transaction status from Telegram. Please open Fantzo to check your account and available support options.",
            _fantzo_button("business_dm_withdrawal", "OPEN FANTZO"),
        )

    if _contains(t, ["bonus", "offer", "promo", "promotion", "cashback"]):
        return (
            "offers",
            "🎁 <b>Offers</b>\n\n"
            "Please check Fantzo directly for any currently available offer, eligibility and terms.\n\n"
            f"{RESPONSIBLE_NOTE}",
            _fantzo_button("business_dm_offers", "🔥 CHECK FANTZO"),
        )

    if _contains(t, ["support", "help", "problem", "issue", "complaint", "failed", "pending", "stuck"]):
        return (
            "support",
            "🛟 <b>Tell me what happened.</b>\n\n"
            "Send a short description of the issue here. I’ll guide you as far as possible from Telegram.\n\n"
            "For anything requiring private account or transaction data, you’ll need to continue through Fantzo.",
            _fantzo_button("business_dm_support", "OPEN FANTZO"),
        )

    if _contains(t, ["thanks", "thank", "thx", "ok", "okay"]):
        return ("thanks", "🙏 You’re welcome. If you need anything else, just message me here.", None)

    return (
        "general",
        "👋 <b>How can I help?</b>\n\n"
        "You can ask about sports, getting started, account access, payments or support.\n\n"
        "Or explore Fantzo directly below.\n\n"
        f"{RESPONSIBLE_NOTE}",
        _fantzo_button("business_dm_general"),
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
    if not message or not message.text:
        return

    if not fantzo_autoreply.is_enabled():
        return

    if message.sender_business_bot:
        return

    connection_id = message.business_connection_id or ""
    owner_id = _owner_user_id(connection_id)

    if owner_id and message.from_user and message.from_user.id == owner_id:
        return

    text = message.text.strip()
    if not text or text.startswith("/"):
        return

    customer_id = message.from_user.id if message.from_user else 0
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
