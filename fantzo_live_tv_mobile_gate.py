"""One-time Telegram-contact verification for Fantzo users.

A user is considered verified only when Telegram supplies a Contact whose
contact.user_id exactly matches the requesting Telegram user. Any country's
Telegram-linked phone number is accepted. Typed numbers never verify an account.
The same verification is reused by the bot, Business DM handoff and Live TV.
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
_PENDING_KEY = "fantzo_mobile_verification_pending"
_PENDING_SOURCE_KEY = "fantzo_mobile_verification_source"
LIVE_TV_START_ARGS = {"livetv_business", "livetv_banner"}
BUSINESS_VERIFY_START_ARG = "verify_business_dm"


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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mobile_verification_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                source TEXT NOT NULL,
                event TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mobile_verify_events_user "
            "ON mobile_verification_events(user_id, created_at)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS business_verification_pending (
                user_id INTEGER PRIMARY KEY,
                requested_at TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'business_dm'
            )
            """
        )
        # The temporary Railway maintenance command used reset_pending for a
        # one-time test. Ignore any future repeat of that maintenance update.
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS block_repeat_reset_pending
            BEFORE UPDATE OF capture_method ON live_tv_mobile_users
            WHEN NEW.capture_method='reset_pending'
                 AND OLD.capture_method='telegram_contact'
            BEGIN
                SELECT RAISE(IGNORE);
            END
            """
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def track_verification_event(user_id: int, source: str, event: str) -> None:
    ensure_tables()
    with core.db() as conn:
        conn.execute(
            "INSERT INTO mobile_verification_events(user_id,source,event,created_at) "
            "VALUES(?,?,?,?)",
            (
                int(user_id),
                str(source or "unknown")[:64],
                str(event or "unknown")[:64],
                _now_iso(),
            ),
        )


def business_verification_pending(user_id: int, max_age_hours: int = 24) -> bool:
    ensure_tables()
    with core.db() as conn:
        row = conn.execute(
            "SELECT requested_at FROM business_verification_pending WHERE user_id=?",
            (int(user_id),),
        ).fetchone()

        # Compatibility fallback for Business DMs that happened before the
        # persistent-pending table was introduced.
        if not row:
            clicks_table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='clicks' LIMIT 1"
            ).fetchone()
            if clicks_table:
                row = conn.execute(
                    "SELECT created_at AS requested_at FROM clicks "
                    "WHERE user_id=? AND action='business_dm:verify_required' "
                    "ORDER BY created_at DESC LIMIT 1",
                    (int(user_id),),
                ).fetchone()

    if not row or not row["requested_at"]:
        return False
    try:
        requested = datetime.fromisoformat(str(row["requested_at"]).replace("Z", "+00:00"))
        if requested.tzinfo is None:
            requested = requested.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - requested.astimezone(timezone.utc)
        return age.total_seconds() <= max_age_hours * 3600
    except Exception:
        logger.exception("Could not parse Business verification pending timestamp")
        return False


def clear_business_verification_pending(user_id: int) -> None:
    ensure_tables()
    with core.db() as conn:
        conn.execute(
            "DELETE FROM business_verification_pending WHERE user_id=?",
            (int(user_id),),
        )


def normalize_telegram_mobile(value: str) -> tuple[str, str] | None:
    """Normalize a Telegram-provided phone number without country restriction."""
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) < 7 or len(digits) > 15:
        return None
    return f"+{digits}", digits


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
    normalized = normalize_telegram_mobile(value)
    if not normalized:
        raise ValueError("A valid Telegram-linked mobile number is required")

    e164, digits = normalized
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
                digits,
                "telegram_contact",
                str(source or "live_tv")[:64],
                created_at,
                now,
                now,
            ),
        )

    return e164, digits


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

    source = str(source or "live_tv")[:64]
    context.user_data[_PENDING_KEY] = True
    context.user_data[_PENDING_SOURCE_KEY] = source
    track_verification_event(user.id, source, "prompt")

    query = update.callback_query
    message = update.effective_message

    if query:
        try:
            await query.answer("Telegram mobile verification required")
        except Exception:
            pass

    if not message:
        return

    if source == "business_dm":
        title = "📱 <b>VERIFY MOBILE TO CONTINUE</b>"
        detail = (
            "Before continuing from Fantzo Business DM, verify the mobile number "
            "linked to your Telegram account."
        )
    elif source == "bot_start":
        title = "📱 <b>VERIFY MOBILE TO CONTINUE</b>"
        detail = (
            "Before using Fantzo Bot, verify the mobile number linked to your "
            "Telegram account. You only need to do this once."
        )
    else:
        title = "📱 <b>VERIFY MOBILE TO CONTINUE</b>"
        detail = (
            "Verify the mobile number linked to your Telegram account. "
            "Once verified, Fantzo and Live TV will use the same verification."
        )

    await message.reply_text(
        f"{title}\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"{detail}\n\n"
        "Tap <b>📱 VERIFY & CONTINUE</b> below. Telegram will share the "
        "mobile number linked to your own Telegram account.\n\n"
        "Numbers from <b>any country</b> are accepted. "
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
    # exactly match the Telegram account being verified.
    if contact.user_id is None or int(contact.user_id) != int(user.id):
        await message.reply_text(
            "⚠️ <b>Verification failed.</b>\n\n"
            "Please use the <b>📱 VERIFY & CONTINUE</b> button and share "
            "the mobile number linked to your own Telegram account.",
            parse_mode="HTML",
            reply_markup=_verify_keyboard(),
        )
        return

    normalized = normalize_telegram_mobile(contact.phone_number or "")
    if not normalized:
        await message.reply_text(
            "⚠️ <b>A valid Telegram-linked mobile number is required.</b>\n\n"
            "Telegram did not provide a usable phone number for this account, "
            "so verification cannot be completed.",
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
    track_verification_event(user.id, source, "verified")

    try:
        if source == "business_dm":
            core.track(user.id, "business_dm:verified")
        else:
            core.track(user.id, f"mobile_verified:{source}")
    except Exception:
        logger.exception("Could not track Fantzo mobile verification")

    context.user_data.pop(_PENDING_KEY, None)
    context.user_data.pop(_PENDING_SOURCE_KEY, None)

    if len(e164) > 7:
        masked = e164[:4] + "••••" + e164[-4:]
    else:
        masked = e164

    import fantzo_business_flow_fix as live_flow

    if source == "business_dm":
        clear_business_verification_pending(user.id)
        await message.reply_text(
            "✅ <b>Telegram mobile verified</b>\n\n"
            f"Verified number: <code>{masked}</code>\n"
            "Verification complete.",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove(),
        )
        await message.reply_text(
            "Choose what you want to do next 👇",
            reply_markup=live_flow.business_funnel_buttons("business_verified"),
        )
        return

    if source == "bot_start":
        await message.reply_text(
            "✅ <b>Telegram mobile verified</b>\n\n"
            f"Verified number: <code>{masked}</code>\n"
            "Opening Fantzo…",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove(),
        )
        # The account is now verified, so the global /start gate falls through
        # immediately to the normal existing Fantzo home flow.
        await tracked.app.start(update, context)
        return

    await message.reply_text(
        "✅ <b>Telegram mobile verified</b>\n\n"
        f"Verified number: <code>{masked}</code>\n"
        "Opening Fantzo Live TV…",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )

    # Deep links/callbacks that specifically requested Live TV continue there.
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
        "Typed mobile numbers cannot verify your account. "
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

        business_handoff = bool(
            user
            and (
                arg == BUSINESS_VERIFY_START_ARG
                or business_verification_pending(user.id)
            )
        )

        if business_handoff:
            try:
                core.touch_user(update)
                core.track(user.id, "business_dm:verify_open")
            except Exception:
                logger.exception("Could not track Business verification handoff")

            track_verification_event(
                user.id,
                "business_dm",
                "verify_open_payload" if arg == BUSINESS_VERIFY_START_ARG else "verify_open_fallback",
            )

            if is_registered(user.id):
                clear_business_verification_pending(user.id)
                track_verification_event(user.id, "business_dm", "already_verified")
                import fantzo_business_flow_fix as live_flow

                await update.effective_message.reply_text(
                    "✅ <b>Your Telegram mobile is already verified.</b>\n\n"
                    "Continue with Fantzo below.",
                    parse_mode="HTML",
                    reply_markup=ReplyKeyboardRemove(),
                )
                await update.effective_message.reply_text(
                    "Choose what you want to do next 👇",
                    reply_markup=live_flow.business_funnel_buttons("business_verified"),
                )
                return

            logger.info(
                "Fantzo Business verification start: user=%s arg=%s fallback=%s",
                user.id,
                arg or "(none)",
                arg != BUSINESS_VERIFY_START_ARG,
            )
            await _prompt_mobile(update, context, "business_dm")
            return

        if user and arg in LIVE_TV_START_ARGS:
            if not is_registered(user.id):
                await _prompt_mobile(update, context, _source_from_start_arg(arg))
                return
            touch_live_tv_access(user.id)
            await original_start(update, context)
            return

        # Global Fantzo onboarding gate: every normal /start from an unverified
        # account must complete Telegram self-contact verification first.
        if user and not is_registered(user.id):
            try:
                core.touch_user(update)
                core.track(user.id, "mobile_verify:bot_start")
            except Exception:
                logger.exception("Could not track bot-start verification requirement")
            track_verification_event(user.id, "bot_start", "prompt_from_start")
            await _prompt_mobile(update, context, "bot_start")
            return

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
        "Fantzo mobile verification installed: global bot gate + Business DM handoff + shared Live TV verification; all countries accepted"
    )


def register_handlers(application) -> None:
    global _handlers_registered
    if _handlers_registered:
        return
    _handlers_registered = True

    # Negative group runs before the normal direct-message auto-reply handlers.
    application.add_handler(
        MessageHandler(
            filters.UpdateType.MESSAGE & filters.CONTACT,
            contact_handler,
        ),
        group=-10,
    )
    application.add_handler(
        MessageHandler(
            filters.UpdateType.MESSAGE & filters.TEXT & ~filters.COMMAND,
            pending_text_handler,
        ),
        group=-10,
    )
    logger.info("Fantzo global Telegram-only mobile verification handlers registered")
