"""One authorized, at-most-once outbound reachability probe."""

import logging
from datetime import datetime, timezone

import bot as core

logger = logging.getLogger(__name__)

PROBE_KEY = "mohit_97saxena_hi_20260929"
TARGET_USER_ID = 1456774567


async def send_once(bot) -> str:
    """Claim durably before sending; never retry after an ambiguous result."""
    try:
        with core.db() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS fantzo_one_time_outbound_probes (
                    probe_key TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    claimed_at TEXT NOT NULL
                )
                """
            )
            claimed = conn.execute(
                "INSERT OR IGNORE INTO fantzo_one_time_outbound_probes "
                "(probe_key, user_id, claimed_at) VALUES (?, ?, ?)",
                (PROBE_KEY, TARGET_USER_ID, datetime.now(timezone.utc).isoformat()),
            ).rowcount == 1
    except Exception:
        logger.exception("FANTZO_HI_PROBE claim_failed; no Telegram send attempted")
        return "claim_failed"

    if not claimed:
        logger.info("FANTZO_HI_PROBE already_claimed user_id=%s", TARGET_USER_ID)
        return "already_claimed"

    logger.info("FANTZO_HI_PROBE claimed user_id=%s; sending once", TARGET_USER_ID)
    try:
        message = await bot.send_message(chat_id=TARGET_USER_ID, text="hi")
    except Exception as exc:
        logger.warning(
            "FANTZO_HI_PROBE failed user_id=%s error_type=%s; no retry",
            TARGET_USER_ID,
            type(exc).__name__,
        )
        return "failed"

    response_chat_id = getattr(getattr(message, "chat", None), "id", None)
    logger.info(
        "FANTZO_HI_PROBE sent user_id=%s response_chat_id=%s message_id=%s",
        TARGET_USER_ID,
        response_chat_id,
        getattr(message, "message_id", None),
    )
    return "sent"
