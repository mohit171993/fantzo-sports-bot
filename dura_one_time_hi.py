"""Temporary, exactly-once outbound reachability probe for one Dura account."""

import logging


logger = logging.getLogger(__name__)
TARGET_USER_ID = 1456774567
MARKER = "dura_one_time_hi_1456774567_20260929"


async def send_once(application, db) -> None:
    """Claim the attempt durably before calling Telegram; never retry on restart."""
    try:
        conn = db()
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"
            )
            claimed = conn.execute(
                "INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",
                (MARKER, "attempted"),
            ).rowcount == 1
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logger.error("DURA one-time hi probe not sent: marker_error=%s", type(exc).__name__)
        return

    if not claimed:
        logger.info("DURA one-time hi probe skipped: already attempted")
        return

    try:
        sent = await application.bot.send_message(chat_id=TARGET_USER_ID, text="hi")
    except Exception as exc:
        detail = str(getattr(exc, "message", "") or "")[:160]
        token = str(getattr(application.bot, "token", "") or "")
        if token:
            detail = detail.replace(token, "[redacted]")
        logger.warning(
            "DURA one-time hi probe result=error type=%s detail=%s",
            type(exc).__name__, detail,
        )
        return

    logger.info(
        "DURA one-time hi probe result=sent target_id=%s message_id=%s",
        TARGET_USER_ID, int(sent.message_id),
    )
