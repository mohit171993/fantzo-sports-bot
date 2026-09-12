import logging

from telegram import Update
from telegram.ext import ContextTypes

import bot as core
import fantzo_autoreply

logger = logging.getLogger(__name__)


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

    if not fantzo_autoreply.is_enabled():
        return

    # Never answer a message that was itself sent by a connected business bot.
    if message.sender_business_bot:
        return

    connection_id = message.business_connection_id or ""
    owner_id = _owner_user_id(connection_id)

    # Ignore messages sent manually by the business account owner to avoid loops.
    if owner_id and message.from_user and message.from_user.id == owner_id:
        return

    text = message.text.strip()
    if not text or text.startswith("/"):
        return

    customer_id = message.from_user.id if message.from_user else 0
    category, reply, markup = fantzo_autoreply.classify_and_reply(text)

    try:
        if customer_id:
            core.track(customer_id, f"business_dm:{category}")
    except Exception:
        logger.exception("Could not track Fantzo business DM auto reply")

    logger.info(
        "Fantzo business DM received: connection=%s customer=%s category=%s",
        connection_id,
        customer_id or None,
        category,
    )

    # Message.reply_text forwards business_connection_id automatically in PTB 21.x,
    # so this sends the reply on behalf of the connected Fantzo Business account.
    await message.reply_text(
        reply,
        parse_mode="HTML",
        reply_markup=markup,
        disable_web_page_preview=True,
    )
