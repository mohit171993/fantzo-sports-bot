import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardButton as TelegramInlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)
from telegram.error import BadRequest, Forbidden, RetryAfter

import bot as core
import fantzo_business as business
import ibetin_hub as hub
import ibetin_match_alerts as match_alerts

logger = logging.getLogger(__name__)
APP_TZ = ZoneInfo("Asia/Dubai")
CHECK_INTERVAL_SECONDS = 300
QUIET_START_HOUR = 22
QUIET_END_HOUR = 8
MAX_SENDS_PER_RUN = 20

IBETIN_HOME_URL = os.getenv("IBETIN_HOME_URL", "https://ibetin.com").strip()
IBETIN_MINI_APP_DEEP_LINK = os.getenv("IBETIN_MINI_APP_DEEP_LINK", IBETIN_HOME_URL).strip()
IBETIN_CHANNEL_URL = "https://t.me/ibetinoffcial"
_IBETIN_APP_BASE_URL = (
    os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/")
    or "https://ibetin-app-production.up.railway.app"
)
IBETIN_LIVE_LINE_URL = os.getenv(
    "IBETIN_LIVE_LINE_URL", f"{_IBETIN_APP_BASE_URL}/liveline"
).strip()
IBETIN_LIVE_LINE_MINI_APP_URL = os.getenv(
    "IBETIN_LIVELINE_MINI_APP_DEEP_LINK",
    "https://t.me/Ibtnofficialbot/liveline?startapp=liveline",
).strip()
LIVELINE_CHANNEL_CAMPAIGN_KEY = "liveline-v40-launch-20260918"
SPORTS_BOT_URL = os.getenv("IBETIN_SPORTS_BOT_URL", IBETIN_HOME_URL).strip()


def ensure_tables() -> None:
    with core.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reminder_users (
                source TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                business_connection_id TEXT DEFAULT '',
                interest TEXT NOT NULL DEFAULT 'general',
                last_activity TEXT NOT NULL,
                last_reminder TEXT,
                reminder_stage INTEGER NOT NULL DEFAULT 0,
                opted_out INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(source, user_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS channel_campaigns (
                campaign_key TEXT PRIMARY KEY,
                sent_at TEXT,
                message_id INTEGER,
                status TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reminder_sends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                stage INTEGER NOT NULL,
                campaign_key TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                status TEXT NOT NULL,
                UNIQUE(source, user_id, campaign_key)
            )
            """
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _interest_from_category(category: str) -> str:
    if category == "cricket":
        return "cricket"
    if category == "football":
        return "football"
    if category in {"sports", "live_tv"}:
        return "sports"
    return "general"


def touch_user(source: str, user_id: int, category: str = "general", business_connection_id: str = "") -> None:
    if not user_id:
        return
    ensure_tables()
    now = _now_iso()
    interest = _interest_from_category(category)
    with core.db() as conn:
        existing = conn.execute(
            "SELECT interest, opted_out FROM reminder_users WHERE source = ? AND user_id = ?",
            (source, user_id),
        ).fetchone()
        current_interest = str(existing["interest"]) if existing else "general"
        opted_out = int(existing["opted_out"]) if existing else 0
        chosen_interest = interest if interest != "general" else current_interest
        conn.execute(
            """
            INSERT INTO reminder_users(
                source, user_id, business_connection_id, interest, last_activity,
                last_reminder, reminder_stage, opted_out, updated_at
            ) VALUES (?, ?, ?, ?, ?, NULL, 0, ?, ?)
            ON CONFLICT(source, user_id) DO UPDATE SET
                business_connection_id = CASE
                    WHEN excluded.business_connection_id != '' THEN excluded.business_connection_id
                    ELSE reminder_users.business_connection_id
                END,
                interest = excluded.interest,
                last_activity = excluded.last_activity,
                reminder_stage = 0,
                opted_out = reminder_users.opted_out,
                updated_at = excluded.updated_at
            """,
            (
                source,
                user_id,
                business_connection_id or "",
                chosen_interest,
                now,
                opted_out,
                now,
            ),
        )


def set_opt_out(source: str, user_id: int, opted_out: bool = True) -> None:
    ensure_tables()
    with core.db() as conn:
        conn.execute(
            "UPDATE reminder_users SET opted_out = ?, updated_at = ? WHERE source = ? AND user_id = ?",
            (1 if opted_out else 0, _now_iso(), source, user_id),
        )


def _is_quiet_hours() -> bool:
    hour = datetime.now(APP_TZ).hour
    return hour >= QUIET_START_HOUR or hour < QUIET_END_HOUR


def _parse_dt(value: str):
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _due_stage(row, now_utc: datetime):
    last_activity = _parse_dt(str(row["last_activity"]))
    if not last_activity:
        return None
    elapsed = now_utc - last_activity
    stage = int(row["reminder_stage"] or 0)

    if row["source"] == "business_dm":
        thresholds = [timedelta(hours=6), timedelta(hours=24), timedelta(hours=72)]
    else:
        thresholds = [timedelta(hours=24), timedelta(days=3), timedelta(days=7)]

    if stage >= len(thresholds):
        return None
    return stage + 1 if elapsed >= thresholds[stage] else None


def _copy_for(interest: str, stage: int, source: str):
    if interest == "cricket":
        subject = "🏏 IBETIN Live Line is ready"
        detail = "Open Live Line for live cricket scores, Match Pulse, scorecards, fixtures and results."
    elif interest == "football":
        subject = "⚽ Football updates are ready"
        detail = "See live scores, upcoming fixtures and the latest football updates."
    else:
        subject = "🔥 Catch up with today’s sports"
        detail = "Open IBETIN Live Line for live cricket scores, Match Pulse, scorecards, fixtures and results."

    if stage == 1:
        intro = subject
    elif stage == 2:
        intro = "📅 Don’t miss what’s happening today"
    else:
        intro = "👋 Your IBETIN sports updates are still here"

    text = (
        f"<b>{intro}</b>\n\n"
        f"{detail}\n\n"
        "Tap below whenever you want to catch up."
    )

    if source == "business_dm":
        # Telegram Business messages cannot use web_app buttons directly.
        # JOIN IBETIN therefore uses the Telegram Main Mini App deep link.
        markup = InlineKeyboardMarkup(
            [
                [
                    TelegramInlineKeyboardButton(
                        "🏏 OPEN LIVE LINE",
                        url=IBETIN_LIVE_LINE_MINI_APP_URL,
                    )
                ],
                [
                    TelegramInlineKeyboardButton(
                        "🚀 JOIN IBETIN",
                        url=business.telegram_mini_app_url("home"),
                    )
                ],
                [
                    TelegramInlineKeyboardButton(
                        "📢 JOIN CHANNEL",
                        url=IBETIN_CHANNEL_URL,
                    )
                ],
            ]
        )
    else:
        # Normal private-bot follow-ups can use a real WebApp button, so
        # JOIN IBETIN opens the Mini App directly without an external browser.
        markup = InlineKeyboardMarkup(
            [
                [
                    TelegramInlineKeyboardButton(
                        "🏏 OPEN LIVE LINE",
                        web_app=WebAppInfo(url=IBETIN_LIVE_LINE_URL),
                    )
                ],
                [
                    InlineKeyboardButton("🔴 LIVE NOW", callback_data="live_now"),
                    InlineKeyboardButton("🗓 UPCOMING", callback_data="upcoming"),
                ],
                [
                    TelegramInlineKeyboardButton(
                        "🚀 JOIN IBETIN",
                        web_app=WebAppInfo(url=hub.hub_url("home")),
                    )
                ],
                [
                    TelegramInlineKeyboardButton(
                        "📢 JOIN CHANNEL",
                        url=IBETIN_CHANNEL_URL,
                    )
                ],
            ]
        )
    return text, markup


def _campaign_key(row, stage: int) -> str:
    activity = str(row["last_activity"]).replace(":", "").replace("+", "_")
    return f"{row['source']}:{stage}:{activity}"


def _mark_send(source: str, user_id: int, stage: int, campaign_key: str, status: str) -> None:
    ensure_tables()
    now = _now_iso()
    with core.db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO reminder_sends(source, user_id, stage, campaign_key, sent_at, status) VALUES(?, ?, ?, ?, ?, ?)",
            (source, user_id, stage, campaign_key, now, status),
        )
        if status == "sent":
            conn.execute(
                "UPDATE reminder_users SET reminder_stage = ?, last_reminder = ?, updated_at = ? WHERE source = ? AND user_id = ?",
                (stage, now, now, source, user_id),
            )


async def _send_with_retry(bot, row, stage: int) -> bool:
    text, markup = _copy_for(str(row["interest"]), stage, str(row["source"]))
    kwargs = {
        "chat_id": int(row["user_id"]),
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": markup,
        "disable_web_page_preview": True,
    }
    if row["source"] == "business_dm" and row["business_connection_id"]:
        kwargs["business_connection_id"] = str(row["business_connection_id"])

    for attempt in range(3):
        try:
            await bot.send_message(**kwargs)
            return True
        except RetryAfter as exc:
            delay = exc.retry_after.total_seconds() if hasattr(exc.retry_after, "total_seconds") else float(exc.retry_after)
            if attempt >= 2:
                raise
            await asyncio.sleep(max(1.0, delay) + 1.0)
        except (Forbidden, BadRequest):
            raise
    return False


async def run_due_reminders(application) -> None:
    if _is_quiet_hours():
        return
    ensure_tables()
    now = datetime.now(timezone.utc)
    with core.db() as conn:
        rows = conn.execute(
            """
            SELECT source, user_id, business_connection_id, interest,
                   last_activity, last_reminder, reminder_stage, opted_out
            FROM reminder_users
            WHERE opted_out = 0
            ORDER BY last_activity ASC
            """
        ).fetchall()

    sent_count = 0
    for row in rows:
        if sent_count >= MAX_SENDS_PER_RUN:
            break
        stage = _due_stage(row, now)
        if not stage:
            continue
        campaign_key = _campaign_key(row, stage)
        with core.db() as conn:
            exists = conn.execute(
                "SELECT 1 FROM reminder_sends WHERE source = ? AND user_id = ? AND campaign_key = ? AND status = 'sent'",
                (row["source"], row["user_id"], campaign_key),
            ).fetchone()
        if exists:
            continue

        try:
            ok = await _send_with_retry(application.bot, row, stage)
            _mark_send(str(row["source"]), int(row["user_id"]), stage, campaign_key, "sent" if ok else "failed")
            if ok:
                sent_count += 1
                await asyncio.sleep(1.2)
        except Forbidden:
            set_opt_out(str(row["source"]), int(row["user_id"]), True)
            _mark_send(str(row["source"]), int(row["user_id"]), stage, campaign_key, "blocked")
        except BadRequest as exc:
            logger.warning("IBETIN reminder rejected for %s/%s: %s", row["source"], row["user_id"], exc)
            _mark_send(str(row["source"]), int(row["user_id"]), stage, campaign_key, "bad_request")
        except Exception:
            logger.exception("IBETIN reminder send failed for %s/%s", row["source"], row["user_id"])
            _mark_send(str(row["source"]), int(row["user_id"]), stage, campaign_key, "failed")


async def send_liveline_channel_launch(application) -> bool:
    """Send the V40 Live Line launch post once to the IBETIN channel."""
    ensure_tables()
    with core.db() as conn:
        existing = conn.execute(
            "SELECT status FROM channel_campaigns WHERE campaign_key = ?",
            (LIVELINE_CHANNEL_CAMPAIGN_KEY,),
        ).fetchone()
    if existing and str(existing["status"]) == "sent":
        logger.info("IBETIN Live Line channel launch already sent campaign=%s", LIVELINE_CHANNEL_CAMPAIGN_KEY)
        return True

    text = (
        "🏏 <b>IBETIN LIVE LINE IS LIVE</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Follow cricket live inside Telegram with IBETIN Live Line.\n\n"
        "⚡ Fast live score updates\n"
        "📊 Match Pulse & scorecards\n"
        "⭐ Save your favourite matches\n"
        "🗓 Upcoming fixtures & results\n\n"
        "Tap below to open Live Line."
    )
    markup = InlineKeyboardMarkup(
        [[
            TelegramInlineKeyboardButton(
                "🏏 OPEN IBETIN LIVE LINE",
                url=IBETIN_LIVE_LINE_MINI_APP_URL,
            )
        ]]
    )

    try:
        msg = await application.bot.send_message(
            chat_id="@ibetinoffcial",
            text=text,
            parse_mode="HTML",
            reply_markup=markup,
            disable_web_page_preview=True,
        )
        with core.db() as conn:
            conn.execute(
                """
                INSERT INTO channel_campaigns(campaign_key, sent_at, message_id, status)
                VALUES (?, ?, ?, 'sent')
                ON CONFLICT(campaign_key) DO UPDATE SET
                    sent_at = excluded.sent_at,
                    message_id = excluded.message_id,
                    status = 'sent'
                """,
                (LIVELINE_CHANNEL_CAMPAIGN_KEY, _now_iso(), int(msg.message_id)),
            )
        logger.info(
            "IBETIN Live Line channel launch sent channel=@ibetinoffcial message_id=%s campaign=%s",
            msg.message_id,
            LIVELINE_CHANNEL_CAMPAIGN_KEY,
        )
        return True
    except Exception as exc:
        with core.db() as conn:
            conn.execute(
                """
                INSERT INTO channel_campaigns(campaign_key, sent_at, message_id, status)
                VALUES (?, ?, NULL, 'failed')
                ON CONFLICT(campaign_key) DO UPDATE SET
                    sent_at = excluded.sent_at,
                    status = 'failed'
                """,
                (LIVELINE_CHANNEL_CAMPAIGN_KEY, _now_iso()),
            )
        logger.warning("IBETIN Live Line channel launch failed: %s", str(exc)[:180])
        return False


async def _send_liveline_channel_launch_after_start(application) -> None:
    await asyncio.sleep(8)
    await send_liveline_channel_launch(application)


async def reminder_loop(application) -> None:
    ensure_tables()
    await asyncio.sleep(20)
    while True:
        try:
            await run_due_reminders(application)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("IBETIN reminder loop error")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


def start_background_loop(application) -> None:
    if application.bot_data.get("ibetin_background_workers_started"):
        return
    application.bot_data["ibetin_background_workers_started"] = True
    match_alerts.ensure_tables()
    application.bot_data["ibetin_reminder_task"] = asyncio.create_task(
        reminder_loop(application), name="ibetin-reminders"
    )
    application.bot_data["ibetin_match_alert_task"] = asyncio.create_task(
        match_alerts.match_alert_loop(application), name="ibetin-match-alerts"
    )
    application.bot_data["ibetin_liveline_channel_launch_task"] = asyncio.create_task(
        _send_liveline_channel_launch_after_start(application),
        name="ibetin-liveline-channel-launch",
    )
    logger.info("IBETIN reminder and real-time match-alert workers started")


def stats() -> dict:
    ensure_tables()
    with core.db() as conn:
        users = conn.execute("SELECT COUNT(*) AS c FROM reminder_users WHERE opted_out = 0").fetchone()["c"]
        dm = conn.execute("SELECT COUNT(*) AS c FROM reminder_users WHERE source = 'business_dm' AND opted_out = 0").fetchone()["c"]
        bot = conn.execute("SELECT COUNT(*) AS c FROM reminder_users WHERE source = 'bot' AND opted_out = 0").fetchone()["c"]
        sent = conn.execute("SELECT COUNT(*) AS c FROM reminder_sends WHERE status = 'sent'").fetchone()["c"]
    return {"users": users, "dm": dm, "bot": bot, "sent": sent}
