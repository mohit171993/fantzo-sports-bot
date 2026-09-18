"""Telegram-contact verification gate for public Fantzo Live TV.

A user is considered verified only when Telegram supplies a Contact whose
contact.user_id exactly matches the requesting Telegram user and whose phone
number is a valid Indian +91 mobile number. Typed numbers never unlock Live TV.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from telegram import (
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import ApplicationHandlerStop, MessageHandler, filters

import bot_tracked as tracked

logger = logging.getLogger(__name__)
core = tracked.app.core

_installed = False
_handlers_registered = False
_PENDING_KEY = "fantzo_live_tv_mobile_pending"
_PENDING_SOURCE_KEY = "fantzo_live_tv_mobile_source"
LIVE_TV_START_ARGS = {"livetv_business", "livetv_banner"}


def ensure_tables() -> None:
    with core.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS live_tv_mobile_users (
                user_id INTEGER PRIMARY KEY,
                mobile_e164 TEXT NOT NULL,
                mobile_national TEXT NOT NULL,
                capture_method TEXT NOT NULL DEFAULT 'manual',
                source TEXT NOT NULL DEFAULT 'live_tv',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_live_tv_at TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_live_tv_mobile_number "
            "ON live_tv_mobile_users(mobile_e164)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_live_tv_mobile_created "
            "ON live_tv_mobile_users(created_at)"
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_indian_mobile(value: str) -> tuple[str, str] | None:
    digits = re.sub(r"\D", "", str(value or ""))

    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]

    if len(digits) != 10 or digits[0] not in {"6", "7", "8", "9"}:
        return None

    return f"+91{digits}", digits


def is_registered(user_id: int) -> bool:
    """Only a Telegram self-contact share counts as verified."""
    ensure_tables()
    with core.db() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM live_tv_mobile_users
            WHERE user_id=? AND capture_method='telegram_contact'
            LIMIT 1
            """,
            (int(user_id),),
        ).fetchone()
    return bool(row)


def save_verified_contact(user_id: int, value: str, source: str) -> tuple[str, str]:
    normalized = normalize_indian_mobile(value)
    if not normalized:
        raise ValueError("A valid Indian mobile number is required")

    e164, national = normalized
    now = _now_iso()

    ensure_tables()
    with core.db() as conn:
        existing = conn.execute(
            "SELECT created_at FROM live_tv_mobile_users WHERE user_id=?",
            (int(user_id),),
        ).fetchone()
        created_at = str(existing["created_at"]) if existing else now

        conn.execute(
            """
            INSERT INTO live_tv_mobile_users(
                user_id, mobile_e164, mobile_national, capture_method,
                source, created_at, updated_at, last_live_tv_at
            ) VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET
                mobile_e164=excluded.mobile_e164,
                mobile_national=excluded.mobile_national,
                capture_method='telegram_contact',
                source=excluded.source,
                updated_at=excluded.updated_at,
                last_live_tv_at=excluded.last_live_tv_at
            """,
            (
                int(user_id),
                e164,
                national,
                "telegram_contact",
                str(source or "live_tv")[:64],
                created_at,
                now,
                now,
            ),
        )

    return e164, national


def touch_live_tv_access(user_id: int) -> None:
    ensure_tables()
    with core.db() as conn:
        conn.execute(
            """
            UPDATE live_tv_mobile_users
            SET last_live_tv_at=?, updated_at=?
            WHERE user_id=? AND capture_method='telegram_contact'
            """,
            (_now_iso(), _now_iso(), int(user_id)),
        )


def _verify_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📱 VERIFY & CONTINUE", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Tap VERIFY & CONTINUE",
    )


async def _prompt_mobile(update: Update, context, source: str) -> None:
    user = update.effective_user
    if not user:
        return

    context.user_data[_PENDING_KEY] = True
    context.user_data[_PENDING_SOURCE_KEY] = str(source or "live_tv")[:64]

    query = update.callback_query
    message = update.effective_message

    if query:
        try:
            await query.answer("Telegram mobile verification required")
        except Exception:
            pass

    if message:
        await message.reply_text(
            "📱 <b>VERIFY MOBILE TO WATCH LIVE TV</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Fantzo Live TV requires a verified Indian mobile number.\n\n"
            "Tap <b>📱 VERIFY & CONTINUE</b> below. Telegram will share the "
            "mobile number linked to your own Telegram account.\n\n"
            "Only an Indian <b>+91</b> mobile number is accepted. "
            "Typed numbers are not accepted.",
            parse_mode="HTML",
            reply_markup=_verify_keyboard(),
        )


async def contact_handler(update: Update, context) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message or not message.contact:
        return

    if not context.user_data.get(_PENDING_KEY):
        return

    contact = message.contact

    # Telegram self-contact verification: user_id must be present and must
    # exactly match the Telegram account requesting Live TV.
    if contact.user_id is None or int(contact.user_id) != int(user.id):
        await message.reply_text(
            "⚠️ <b>Verification failed.</b>\n\n"
            "Please use the <b>📱 VERIFY & CONTINUE</b> button and share "
            "the mobile number linked to your own Telegram account.",
            parse_mode="HTML",
            reply_markup=_verify_keyboard(),
        )
        return

    normalized = normalize_indian_mobile(contact.phone_number or "")
    if not normalized:
        await message.reply_text(
            "⚠️ <b>An Indian mobile number is required.</b>\n\n"
            "The mobile number linked to this Telegram account is not a valid "
            "Indian +91 mobile number, so Live TV cannot be unlocked.",
            parse_mode="HTML",
            reply_markup=_verify_keyboard(),
        )
        return

    source = str(context.user_data.get(_PENDING_SOURCE_KEY) or "live_tv")
    e164, _ = save_verified_contact(
        user.id,
        contact.phone_number or "",
        source,
    )

    context.user_data.pop(_PENDING_KEY, None)
    context.user_data.pop(_PENDING_SOURCE_KEY, None)

    masked = e164[:3] + "••••••" + e164[-4:]
    await message.reply_text(
        "✅ <b>Telegram mobile verified</b>\n\n"
        f"Verified number: <code>{masked}</code>\n"
        "Opening Fantzo Live TV…",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )

    # Continue immediately into the already-tested Live TV status screen.
    import fantzo_business_flow_fix as live_flow

    await live_flow.send_live_tv_status_from_start(update, context)


async def pending_text_handler(update: Update, context) -> None:
    """Do not let typed numbers substitute for Telegram contact verification."""
    user = update.effective_user
    message = update.effective_message
    if not user or not message or not message.text:
        return
    if not context.user_data.get(_PENDING_KEY):
        return

    await message.reply_text(
        "🔐 <b>Telegram verification is required.</b>\n\n"
        "Typed mobile numbers cannot unlock Live TV. "
        "Please tap <b>📱 VERIFY & CONTINUE</b> below.",
        parse_mode="HTML",
        reply_markup=_verify_keyboard(),
    )
    raise ApplicationHandlerStop


def _source_from_start_arg(arg: str) -> str:
    if arg == "livetv_business":
        return "business_dm"
    if arg == "livetv_banner":
        return "banner"
    return "live_tv"


def install() -> None:
    global _installed
    if _installed:
        return
    _installed = True
    ensure_tables()

    original_start = tracked.app.start
    original_router = tracked.app.core.callback_router

    async def gated_start(update, context):
        user = update.effective_user
        arg = context.args[0].lower() if context.args else ""

        if user and arg in LIVE_TV_START_ARGS:
            if not is_registered(user.id):
                await _prompt_mobile(update, context, _source_from_start_arg(arg))
                return
            touch_live_tv_access(user.id)

        await original_start(update, context)

    async def gated_router(update, context):
        query = update.callback_query
        user = update.effective_user
        action = str(query.data or "") if query else ""

        if user and action == "live_tv_status":
            if not is_registered(user.id):
                await _prompt_mobile(update, context, "bot_live_tv")
                return
            touch_live_tv_access(user.id)

        await original_router(update, context)

    tracked.app.start = gated_start
    tracked.app.core.callback_router = gated_router

    logger.info(
        "Fantzo Live TV mobile gate installed: Telegram self-contact + Indian +91 required"
    )


def register_handlers(application) -> None:
    global _handlers_registered
    if _handlers_registered:
        return
    _handlers_registered = True

    # Negative group runs before the normal direct-message auto-reply handlers.
    application.add_handler(
        MessageHandler(filters.CONTACT, contact_handler),
        group=-10,
    )
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, pending_text_handler),
        group=-10,
    )
    logger.info("Fantzo Telegram-only mobile verification handlers registered")
