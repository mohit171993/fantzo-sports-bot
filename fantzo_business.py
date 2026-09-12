import logging
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import bot as core
import fantzo_analytics as analytics
import fantzo_autoreply

logger = logging.getLogger(__name__)

RESPONSIBLE_NOTE = "🔞 18+ • Play responsibly • T&Cs apply"


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


def _fantzo_button(source: str, label: str = "🔥 OPEN FANTZO") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, url=analytics.tracking_url(source))]]
    )


def _guided_prompt() -> str:
    return (
        "What are you looking for?\n\n"
        "1️⃣ <b>Live sports</b>\n"
        "2️⃣ <b>Join / get started</b>\n"
        "3️⃣ <b>Account help</b>\n"
        "4️⃣ <b>Support</b>\n\n"
        "Reply with <b>1, 2, 3 or 4</b> — or simply type your question."
    )


def classify_business_dm(text: str):
    """Business-DM conversion flow, intentionally separate from the sports bot menu."""
    t = " ".join((text or "").lower().strip().split())

    if t in {"1", "1️⃣"}:
        t = "live sports"
    elif t in {"2", "2️⃣"}:
        t = "join"
    elif t in {"3", "3️⃣"}:
        t = "account help"
    elif t in {"4", "4️⃣"}:
        t = "support"

    if _contains(t, ["hi", "hello", "hey", "hii", "hola", "namaste"]):
        return (
            "greeting",
            "👋 <b>Hi! Welcome to Fantzo.</b>\n\n"
            "I’ll help you get to the right place quickly.\n\n"
            f"{_guided_prompt()}\n\n"
            f"{RESPONSIBLE_NOTE}",
            _fantzo_button("business_dm_greeting"),
        )

    if _contains(
        t,
        [
            "cricket",
            "football",
            "soccer",
            "ipl",
            "t20",
            "odi",
            "match",
            "score",
            "live",
            "sports",
        ],
    ):
        return (
            "sports",
            "🏟 <b>Live sports</b>\n\n"
            "Fantzo is where you can continue from here. This Telegram assistant can guide you, "
            "but it does not control Fantzo.com or its internal pages.\n\n"
            "Tap below to open Fantzo.\n\n"
            f"{RESPONSIBLE_NOTE}",
            _fantzo_button("business_dm_sports", "🔥 EXPLORE FANTZO"),
        )

    if _contains(t, ["join", "start", "get started", "new user", "create account", "signup", "sign up", "register", "registration"]):
        return (
            "join",
            "🚀 <b>Ready to get started?</b>\n\n"
            "Open Fantzo below and continue from the options available on the site. "
            "This Telegram chat cannot see or confirm what happens after you open Fantzo.\n\n"
            f"{RESPONSIBLE_NOTE}",
            _fantzo_button("business_dm_join", "🔥 JOIN FANTZO"),
        )

    if _contains(
        t,
        [
            "login",
            "log in",
            "account",
            "password",
            "otp",
            "account help",
        ],
    ):
        return (
            "account",
            "👤 <b>Account help</b>\n\n"
            "Please open Fantzo and use the account options available there. "
            "This Telegram chat is not connected to Fantzo's internal account system, so I can't see registrations, passwords, OTPs or account status.\n\n"
            "🔐 Never share your password or OTP in Telegram.\n\n"
            f"{RESPONSIBLE_NOTE}",
            _fantzo_button("business_dm_account"),
        )

    if _contains(t, ["deposit", "payment", "pay", "upi", "add money", "recharge"]):
        return (
            "deposit",
            "💳 <b>Payment / Deposit</b>\n\n"
            "Available payment options are shown inside Fantzo after you open your account. "
            "I can't view, process or confirm deposits from this Telegram chat.\n\n"
            "For your security, don't send OTPs, passwords or full card/bank details here.\n\n"
            f"{RESPONSIBLE_NOTE}",
            _fantzo_button("business_dm_deposit"),
        )

    if _contains(t, ["withdraw", "withdrawal", "payout", "cashout", "cash out"]):
        return (
            "withdrawal",
            "💸 <b>Withdrawal</b>\n\n"
            "Please check your Fantzo account for the latest withdrawal options and status. "
            "This Telegram assistant cannot access your wallet, balance or transaction history.\n\n"
            "If you need account-specific help, use the official support option available inside Fantzo.\n\n"
            f"{RESPONSIBLE_NOTE}",
            _fantzo_button("business_dm_withdrawal"),
        )

    if _contains(t, ["bonus", "offer", "promo", "promotion", "cashback"]):
        return (
            "offers",
            "🎁 <b>Offers & promotions</b>\n\n"
            "Any currently available Fantzo offer should be checked directly on Fantzo together with its eligibility and terms. "
            "I won't promise an offer that isn't shown there.\n\n"
            f"{RESPONSIBLE_NOTE}",
            _fantzo_button("business_dm_offers"),
        )

    if _contains(
        t,
        [
            "support",
            "help",
            "problem",
            "issue",
            "complaint",
            "failed",
            "pending",
            "stuck",
        ],
    ):
        return (
            "support",
            "🛟 <b>Support</b>\n\n"
            "Tell me briefly what went wrong and I’ll guide you as far as I can from Telegram. "
            "For anything that needs private account data or transaction verification, you’ll need to continue through Fantzo's own support options.\n\n"
            "You can open Fantzo below.\n\n"
            f"{RESPONSIBLE_NOTE}",
            _fantzo_button("business_dm_support"),
        )

    if _contains(t, ["thanks", "thank", "thx", "ok", "okay"]):
        return (
            "thanks",
            "🙏 You're welcome.\n\n"
            "If you want to continue, Fantzo is one tap away.\n\n"
            f"{RESPONSIBLE_NOTE}",
            _fantzo_button("business_dm_thanks"),
        )

    return (
        "general",
        "👋 <b>Thanks for messaging Fantzo.</b>\n\n"
        "I didn't fully understand that yet.\n\n"
        f"{_guided_prompt()}\n\n"
        f"{RESPONSIBLE_NOTE}",
        _fantzo_button("business_dm_general"),
    )


async def business_connection_update(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
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


async def business_auto_reply(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.business_message
    if not message or not message.text:
        return

    # Keep the existing admin on/off switch, but Business DMs now use separate logic.
    if not fantzo_autoreply.is_enabled():
        return

    # Never answer a message that was itself sent by a connected business bot.
    if message.sender_business_bot:
        return

    connection_id = message.business_connection_id or ""
    owner_id = _owner_user_id(connection_id)

    # Ignore messages sent manually by the business owner to avoid loops.
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

    # PTB carries business_connection_id through Message.reply_text(), so the
    # response is sent on behalf of the connected Fantzo Business account.
    await message.reply_text(
        reply,
        parse_mode="HTML",
        reply_markup=markup,
        disable_web_page_preview=True,
    )
