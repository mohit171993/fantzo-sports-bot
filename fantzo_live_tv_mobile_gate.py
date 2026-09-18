"""Mandatory Indian mobile capture before public Fantzo Live TV access.

The gate is intentionally isolated from the Live TV engine. It intercepts only
public Live TV entry points, stores a normalized Indian mobile number, and then
hands control back to the existing tested Live TV flow.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import ContextTypes, MessageHandler, filters

import bot_tracked as tracked
import fantzo_autoreply

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

    if len(digits) != 10:
        return None

    if digits[0] not in {"6", "7", "8", "9"}:
        return None

    return f"+91{digits}", digits


def is_registered(user_id: int) -> bool:
    ensure_tables()
    with core.db() as conn:
        row = conn.execute(
            "SELECT 1 FROM live_tv_mobile_users WHERE user_id=? LIMIT 1",
            (int(user_id),),
        ).fetchone()
    return bool(row)


def save_mobile(
    user_id: int,
    value: str,
    source: str,
    capture_method: str,
) -> tuple[str, str]:
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
                capture_method=excluded.capture_method,
                source=excluded.source,
                updated_at=excluded.updated_at,
                last_live_tv_at=excluded.last_live_tv_at
            """,
            (
                int(user_id),
                e164,
                national,
                str(capture_method or "manual")[:32],
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
            "UPDATE live_tv_mobile_users SET last_live_tv_at=?, updated_at=? WHERE user_id=?",
            (_now_iso(), _now_iso(), int(user_id)),
        )


def _share_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📱 SHARE INDIAN MOBILE", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Share or type your Indian mobile number",
    )


def _continue_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("📺 CONTINUE TO LIVE TV", callback_data="live_tv_status")]]
    )


async def _prompt_mobile(update: Update, context: ContextTypes.DEFAULT_TYPE, source: str) -> None:
    user = update.effective_user
    if not user:
        return

    context.user_data[_PENDING_KEY] = True
    context.user_data[_PENDING_SOURCE_KEY] = str(source or "live_tv")[:64]

    query = update.callback_query
    message = update.effective_message

    if query:
        try:
            await query.answer("Indian mobile number required")
        except Exception:
            pass

    if message:
        await message.reply_text(
            "📱 <b>INDIAN MOBILE REQUIRED</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "To access <b>Fantzo Live TV</b>, please provide a valid Indian mobile number.\n\n"
            "Tap <b>SHARE INDIAN MOBILE</b> below, or type your 10-digit Indian mobile number in this chat.\n\n"
            "Accepted: <code>9876543210</code> or <code>+919876543210</code>.\n"
            "Your number is stored for Live TV access and admin reporting.",
            parse_mode="HTML",
            reply_markup=_share_keyboard(),
        )


async def _finish_capture(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    phone_value: str,
    capture_method: str,
) -> bool:
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return False

    normalized = normalize_indian_mobile(phone_value)
    if not normalized:
        await message.reply_text(
            "⚠️ <b>Please enter a valid Indian mobile number.</b>\n\n"
            "It must be a 10-digit mobile number starting with 6, 7, 8 or 9.\n"
            "Example: <code>9876543210</code>",
            parse_mode="HTML",
            reply_markup=_share_keyboard(),
        )
        return True

    source = str(context.user_data.get(_PENDING_SOURCE_KEY) or "live_tv")
    e164, _ = save_mobile(user.id, phone_value, source, capture_method)

    context.user_data.pop(_PENDING_KEY, None)
    context.user_data.pop(_PENDING_SOURCE_KEY, None)

    masked = e164[:3] + "••••••" + e164[-4:]
    await message.reply_text(
        f"✅ <b>Mobile number saved</b>\n\n"
        f"Registered number: <code>{masked}</code>\n"
        "You can now access Fantzo Live TV.",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.reply_text(
        "📺 Tap below to continue.",
        reply_markup=_continue_keyboard(),
    )
    return True


async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message or not message.contact:
        return

    if not context.user_data.get(_PENDING_KEY):
        return

    contact = message.contact
    if contact.user_id and int(contact.user_id) != int(user.id):
        await message.reply_text(
            "⚠️ Please share <b>your own</b> Telegram contact using the button below.",
            parse_mode="HTML",
            reply_markup=_share_keyboard(),
        )
        return

    await _finish_capture(
        update,
        context,
        contact.phone_number or "",
        "telegram_contact",
    )


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
    original_auto_reply = fantzo_autoreply.auto_reply

    async def gated_start(update, context):
        user = update.effective_user
        arg = context.args[0].lower() if context.args else ""

        if user and user.id != core.ADMIN_USER_ID and arg in LIVE_TV_START_ARGS:
            if not is_registered(user.id):
                await _prompt_mobile(update, context, _source_from_start_arg(arg))
                return
            touch_live_tv_access(user.id)

        await original_start(update, context)

    async def gated_router(update, context):
        query = update.callback_query
        user = update.effective_user
        action = str(query.data or "") if query else ""

        if user and user.id != core.ADMIN_USER_ID and action == "live_tv_status":
            if not is_registered(user.id):
                await _prompt_mobile(update, context, "bot_live_tv")
                return
            touch_live_tv_access(user.id)

        await original_router(update, context)

    async def auto_reply_with_mobile_capture(update, context):
        user = update.effective_user
        message = update.effective_message

        if (
            user
            and message
            and message.text
            and context.user_data.get(_PENDING_KEY)
        ):
            text = message.text.strip()
            if text.lower() in {"cancel", "stop"}:
                context.user_data.pop(_PENDING_KEY, None)
                context.user_data.pop(_PENDING_SOURCE_KEY, None)
                await message.reply_text(
                    "Mobile registration cancelled.",
                    reply_markup=ReplyKeyboardRemove(),
                )
                return

            await _finish_capture(update, context, text, "manual")
            return

        await original_auto_reply(update, context)

    tracked.app.start = gated_start
    tracked.app.core.callback_router = gated_router
    fantzo_autoreply.auto_reply = auto_reply_with_mobile_capture

    logger.info("Fantzo Live TV mobile gate installed: Indian mobile required")


def register_handlers(application) -> None:
    global _handlers_registered
    if _handlers_registered:
        return
    _handlers_registered = True

    # Negative group runs before the normal direct-message handlers.
    application.add_handler(
        MessageHandler(filters.CONTACT, contact_handler),
        group=-10,
    )
    logger.info("Fantzo Live TV mobile contact handler registered")
