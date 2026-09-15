import asyncio
import logging
import os
from urllib.parse import parse_qs, parse_qsl, quote, urlencode, urlparse, urlunparse

from telegram import InlineKeyboardButton as TelegramInlineKeyboardButton
from telegram import InlineKeyboardMarkup, Update
from telegram.error import BadRequest, RetryAfter
from telegram.ext import ContextTypes

import bot as core
import fantzo_autoreply

logger = logging.getLogger(__name__)

IBETIN_BOT_USERNAME = os.getenv("IBETIN_BOT_USERNAME", "ibtnofficialbot").strip().lstrip("@")
IBETIN_MINI_APP_DEEP_LINK = os.getenv("IBETIN_MINI_APP_DEEP_LINK", "").strip()
BUSINESS_SECTIONS = {"home", "live", "news", "alerts", "support"}


def _is_telegram_mini_app_base(url: str) -> bool:
    if not url:
        return False
    try:
        parsed = urlparse(url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        has_startapp = "startapp" in query
        if parsed.scheme in {"http", "https"}:
            return (
                parsed.netloc.lower()
                in {"t.me", "www.t.me", "telegram.me", "www.telegram.me"}
                and has_startapp
            )
        return parsed.scheme == "tg" and parsed.netloc.lower() == "resolve" and has_startapp
    except Exception:
        return False


def telegram_mini_app_url(section: str = "home") -> str:
    """Return a Telegram Main Mini App deep link for one IBETIN section.

    Telegram Business messages cannot contain ``web_app`` buttons, but they can
    contain Telegram URL buttons. Since @ibtnofficialbot now has a Main Mini App,
    ``startapp=<section>`` launches that app and passes the section to our router.
    """
    section = (section or "home").strip().lower()
    if section not in BUSINESS_SECTIONS:
        section = "home"

    configured = IBETIN_MINI_APP_DEEP_LINK
    if configured and _is_telegram_mini_app_base(configured):
        try:
            parsed = urlparse(configured)
            items = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != "startapp"]
            items.append(("startapp", section))
            return urlunparse(parsed._replace(query=urlencode(items)))
        except Exception:
            logger.warning("Could not apply IBETIN section to configured Mini App deep link")

    return f"https://t.me/{IBETIN_BOT_USERNAME}?startapp={quote(section, safe='')}"


def business_reply_text() -> str:
    return (
        "👋 <b>Welcome to IBETIN</b>\n\n"
        "Choose where you want to go. Each button opens the matching IBETIN "
        "section inside Telegram.\n\n"
        "⚡ One Mini App • direct section access"
    )


def business_keyboard(customer_id: int = 0) -> InlineKeyboardMarkup:
    # customer_id is retained for backward compatibility with the existing caller.
    # Telegram Business cannot send web_app buttons, therefore these are Telegram
    # Main Mini App deep-link URL buttons carrying section-specific startapp values.
    return InlineKeyboardMarkup(
        [
            [
                TelegramInlineKeyboardButton(
                    "⚡ OPEN IBETIN", url=telegram_mini_app_url("home")
                )
            ],
            [
                TelegramInlineKeyboardButton(
                    "🔴 LIVE NOW", url=telegram_mini_app_url("live")
                ),
                TelegramInlineKeyboardButton(
                    "📰 NEWS", url=telegram_mini_app_url("news")
                ),
            ],
            [
                TelegramInlineKeyboardButton(
                    "🔔 MATCH ALERTS", url=telegram_mini_app_url("alerts")
                ),
                TelegramInlineKeyboardButton(
                    "🛟 SUPPORT", url=telegram_mini_app_url("support")
                ),
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
            await message.reply_text(business_reply_text(), **kwargs)
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
