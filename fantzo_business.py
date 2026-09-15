import asyncio
import hashlib
import hmac
import logging
import os
import time

from telegram import InlineKeyboardButton as TelegramInlineKeyboardButton
from telegram import InlineKeyboardMarkup, Update
from telegram.error import BadRequest, RetryAfter
from telegram.ext import ContextTypes

import bot as core
import fantzo_autoreply

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
BUSINESS_TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60


def _public_base_url() -> str:
    value = (
        os.getenv("TRACKING_BASE_URL", "").strip()
        or os.getenv("RAILWAY_STATIC_URL", "").strip()
        or os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
        or "https://ibetin-app-production.up.railway.app"
    )
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    return value.rstrip("/")


def _business_alert_token(user_id: int) -> str:
    if not BOT_TOKEN or user_id <= 0:
        return ""
    expires_at = int(time.time()) + BUSINESS_TOKEN_TTL_SECONDS
    payload = f"{int(user_id)}.{expires_at}"
    signature = hmac.new(
        BOT_TOKEN.encode("utf-8"),
        f"ibetin-business-alerts:{payload}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}.{signature}"


def _business_url(section: str = "home", customer_id: int = 0) -> str:
    """Build deterministic IBETIN URLs for Telegram Business buttons.

    Telegram Business messages cannot use web_app buttons, and startapp
    parameters have proven unreliable on some Telegram clients. Carrying the
    destination in our own URL makes each shortcut deterministic.
    """
    section = (section or "home").strip().lower()
    base = _public_base_url()
    if section == "news":
        return f"{base}/news?category=latest&source=business_dm"
    if section not in {"home", "live", "alerts", "support"}:
        section = "home"

    url = f"{base}/hub?section={section}&source=business_dm"
    if section == "alerts" and customer_id > 0:
        token = _business_alert_token(customer_id)
        if token:
            url += f"&bdm={token}"
    return url


def business_keyboard(customer_id: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [TelegramInlineKeyboardButton("⚡ OPEN IBETIN", url=_business_url("home", customer_id))],
            [
                TelegramInlineKeyboardButton("🔴 LIVE NOW", url=_business_url("live", customer_id)),
                TelegramInlineKeyboardButton("📰 NEWS", url=_business_url("news", customer_id)),
            ],
            [
                TelegramInlineKeyboardButton("🔔 MATCH ALERTS", url=_business_url("alerts", customer_id)),
                TelegramInlineKeyboardButton("🛟 SUPPORT", url=_business_url("support", customer_id)),
            ],
        ]
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


async def _reply_with_retry(message) -> None:
    customer_id = message.from_user.id if message.from_user else 0
    kwargs = {
        "parse_mode": "HTML",
        "reply_markup": business_keyboard(customer_id),
        "disable_web_page_preview": True,
    }

    for attempt in range(3):
        try:
            await message.reply_text(fantzo_autoreply.standard_reply(), **kwargs)
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

    text = (message.text or message.caption or "").strip()
    if text.startswith("/"):
        return

    customer_id = message.from_user.id if message.from_user else 0

    try:
        if customer_id:
            core.track(customer_id, "business_dm:message")
    except Exception:
        logger.exception("Could not track IBETIN incoming Business DM")

    logger.info(
        "IBETIN business DM received: connection=%s customer=%s",
        connection_id,
        customer_id or None,
    )

    await _reply_with_retry(message)

    try:
        if customer_id:
            core.track(customer_id, "business_dm:autoreply_sent")
    except Exception:
        logger.exception("Could not track IBETIN Business DM auto reply send")
