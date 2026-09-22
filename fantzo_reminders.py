import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from telegram.error import BadRequest, Forbidden, RetryAfter

import bot as core

logger = logging.getLogger(__name__)
APP_TZ = ZoneInfo("Asia/Dubai")
CHECK_INTERVAL_SECONDS = 300
QUIET_START_HOUR = 22
QUIET_END_HOUR = 8
MAX_SENDS_PER_RUN = 20
MAX_ATTEMPTS_PER_RUN = 40


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

        cols = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(reminder_users)").fetchall()
        }
        if "delivery_disabled" not in cols:
            conn.execute(
                "ALTER TABLE reminder_users "
                "ADD COLUMN delivery_disabled INTEGER NOT NULL DEFAULT 0"
            )
        if "last_delivery_error" not in cols:
            conn.execute(
                "ALTER TABLE reminder_users "
                "ADD COLUMN last_delivery_error TEXT NOT NULL DEFAULT ''"
            )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reminder_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO reminder_settings(key,value) VALUES('paused','0')"
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



def is_paused() -> bool:
    ensure_tables()
    with core.db() as conn:
        row = conn.execute(
            "SELECT value FROM reminder_settings WHERE key='paused'"
        ).fetchone()
    return bool(row and str(row["value"]) == "1")


def set_paused(paused: bool) -> None:
    ensure_tables()
    with core.db() as conn:
        conn.execute(
            """
            INSERT INTO reminder_settings(key,value) VALUES('paused',?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            ("1" if paused else "0",),
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
                delivery_disabled = 0,
                last_delivery_error = '',
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


def repair_business_connections() -> dict:
    """Repair Business reminder rows from exact customer/connection history."""
    ensure_tables()
    repaired = 0
    disabled_missing = 0
    with core.db() as conn:
        has_welcomes = bool(conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='business_welcomes' LIMIT 1"
        ).fetchone())
        has_connections = bool(conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='business_connections' LIMIT 1"
        ).fetchone())

        if has_welcomes and has_connections:
            rows = conn.execute(
                """
                SELECT r.user_id,
                       (
                           SELECT w.connection_id
                           FROM business_welcomes w
                           JOIN business_connections b
                             ON b.connection_id=w.connection_id
                           WHERE w.customer_id=r.user_id
                             AND b.enabled=1
                           ORDER BY w.welcomed_at DESC
                           LIMIT 1
                       ) AS connection_id
                FROM reminder_users r
                WHERE r.source='business_dm'
                """
            ).fetchall()
            for row in rows:
                connection_id = str(row["connection_id"] or "")
                if connection_id:
                    cur = conn.execute(
                        """
                        UPDATE reminder_users
                        SET business_connection_id=?,
                            delivery_disabled=0,
                            last_delivery_error='',
                            updated_at=?
                        WHERE source='business_dm' AND user_id=?
                          AND COALESCE(business_connection_id,'')!=?
                        """,
                        (connection_id, _now_iso(), int(row["user_id"]), connection_id),
                    )
                    repaired += int(cur.rowcount or 0)

        cur = conn.execute(
            """
            UPDATE reminder_users
            SET delivery_disabled=1,
                last_delivery_error='missing_business_connection',
                updated_at=?
            WHERE source='business_dm'
              AND opted_out=0
              AND COALESCE(business_connection_id,'')=''
            """,
            (_now_iso(),),
        )
        disabled_missing = int(cur.rowcount or 0)

    logger.info(
        "Fantzo Business reminder mapping audit repaired=%s disabled_missing=%s",
        repaired,
        disabled_missing,
    )
    return {"repaired": repaired, "disabled_missing": disabled_missing}


def disable_business_connection(connection_id: str) -> int:
    if not connection_id:
        return 0
    ensure_tables()
    with core.db() as conn:
        cur = conn.execute(
            """
            UPDATE reminder_users
            SET delivery_disabled=1,
                last_delivery_error='business_connection_disabled',
                updated_at=?
            WHERE source='business_dm'
              AND business_connection_id=?
            """,
            (_now_iso(), str(connection_id)),
        )
    return int(cur.rowcount or 0)


def _disable_delivery(source: str, user_id: int, reason: str) -> None:
    ensure_tables()
    safe_reason = str(reason or "delivery_unavailable")[:240]
    with core.db() as conn:
        conn.execute(
            """
            UPDATE reminder_users
            SET delivery_disabled=1,
                last_delivery_error=?,
                updated_at=?
            WHERE source=? AND user_id=?
            """,
            (safe_reason, _now_iso(), str(source), int(user_id)),
        )


def _is_quiet_hours() -> bool:
    hour = datetime.now(APP_TZ).hour
    return hour >= QUIET_START_HOUR or hour < QUIET_END_HOUR


def _parse_dt(value: str):
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _is_mobile_verified(user_id: int) -> bool:
    """Shared verification state used by bot, Business DM and Live TV."""
    if not user_id:
        return False
    try:
        with core.db() as conn:
            table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='live_tv_mobile_users' LIMIT 1"
            ).fetchone()
            if not table:
                return False
            row = conn.execute(
                "SELECT 1 FROM live_tv_mobile_users "
                "WHERE user_id=? AND capture_method='telegram_contact' LIMIT 1",
                (int(user_id),),
            ).fetchone()
        return bool(row)
    except Exception:
        logger.exception("Could not check Fantzo mobile verification for reminder")
        return False


def _mark_business_verification_pending(user_id: int) -> None:
    """Keep Business reminder -> bot verification handoff robust."""
    if not user_id:
        return
    try:
        with core.db() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS business_verification_pending (
                    user_id INTEGER PRIMARY KEY,
                    requested_at TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'business_dm'
                )
                """
            )
            conn.execute(
                """
                INSERT INTO business_verification_pending(user_id, requested_at, source)
                VALUES(?, ?, 'business_dm')
                ON CONFLICT(user_id) DO UPDATE SET
                    requested_at=excluded.requested_at,
                    source='business_dm'
                """,
                (int(user_id), _now_iso()),
            )
    except Exception:
        logger.exception("Could not mark Business verification reminder pending")


def _verification_copy(stage: int, source: str):
    if stage == 1:
        intro = "🔐 <b>Complete your Fantzo verification</b>"
        detail = "You’re one step away. Verify your Telegram-linked mobile number to continue."
    elif stage == 2:
        intro = "📱 <b>Your Fantzo verification is still pending</b>"
        detail = "Complete the quick Telegram mobile verification to continue using Fantzo."
    else:
        intro = "👋 <b>Finish setting up Fantzo</b>"
        detail = "Your Telegram mobile verification is still incomplete. Verify once to continue."

    text = (
        f"{intro}\n\n"
        f"{detail}\n\n"
        "Telegram will only accept the mobile number linked to your own account."
    )

    if source == "business_dm":
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "📱 VERIFY MOBILE",
                url="https://t.me/fantzoofficialbot?start=verify_business_dm",
                api_kwargs={"style": "success"},
            )
        ]])
    else:
        markup = ReplyKeyboardMarkup(
            [[KeyboardButton("📱 VERIFY NOW", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True,
            input_field_placeholder="Tap VERIFY NOW",
        )

    return text, markup


def _due_stage(row, now_utc: datetime):
    last_activity = _parse_dt(str(row["last_activity"]))
    if not last_activity:
        return None
    elapsed = now_utc - last_activity
    stage = int(row["reminder_stage"] or 0)

    verified = _is_mobile_verified(int(row["user_id"]))

    if not verified and row["source"] == "business_dm":
        thresholds = [timedelta(hours=6), timedelta(hours=24), timedelta(hours=72)]
    elif not verified:
        # Paid-ad intent is freshest soon after the click. Follow up once after
        # one hour, then again at 24h and 72h if verification is still pending.
        thresholds = [timedelta(hours=1), timedelta(hours=24), timedelta(hours=72)]
    elif row["source"] == "business_dm":
        thresholds = [timedelta(hours=6), timedelta(hours=24), timedelta(hours=72)]
    else:
        thresholds = [timedelta(hours=24), timedelta(days=3), timedelta(days=7)]

    if stage >= len(thresholds):
        return None
    return stage + 1 if elapsed >= thresholds[stage] else None


def _copy_for(interest: str, stage: int, source: str):
    if interest == "cricket":
        subject = "🏏 Cricket action is waiting"
        detail = "Check live scores, today’s fixtures and the latest cricket updates."
    elif interest == "football":
        subject = "⚽ Football updates are ready"
        detail = "See live scores, upcoming fixtures and the latest football updates."
    else:
        subject = "🔥 Catch up with today’s sports"
        detail = "Follow live scores, fixtures, sports news and highlights in one place."

    if stage == 1:
        intro = subject
    elif stage == 2:
        intro = "📅 Don’t miss what’s happening today"
    else:
        intro = "👋 Your Fantzo sports updates are still here"

    text = (
        f"<b>{intro}</b>\n\n"
        f"{detail}\n\n"
        "Tap below whenever you want to catch up."
    )

    if source == "business_dm":
        markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔥 OPEN FANTZO", url="https://t.me/fantzoofficialbot?startapp=reminder_dm")],
             [InlineKeyboardButton("🏏 SPORTS BOT", url="https://t.me/fantzoofficialbot?start=reminder")]]
        )
    else:
        markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔴 LIVE NOW", callback_data="live_now"),
              InlineKeyboardButton("🗓 UPCOMING", callback_data="upcoming")],
             [InlineKeyboardButton("✨ OPEN FANTZO", url="https://t.me/fantzoofficialbot?startapp=reminder_bot")]]
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
    source = str(row["source"])
    user_id = int(row["user_id"])
    verified = _is_mobile_verified(user_id)

    if verified:
        text, markup = _copy_for(str(row["interest"]), stage, source)
    else:
        text, markup = _verification_copy(stage, source)

    kwargs = {
        "chat_id": int(row["user_id"]),
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": markup,
        "disable_web_page_preview": True,
    }
    if source == "business_dm" and row["business_connection_id"]:
        kwargs["business_connection_id"] = str(row["business_connection_id"])

    for attempt in range(3):
        try:
            await bot.send_message(**kwargs)
            if source == "business_dm" and not verified:
                _mark_business_verification_pending(user_id)
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
    if is_paused() or _is_quiet_hours():
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
              AND COALESCE(delivery_disabled,0) = 0
            ORDER BY last_activity ASC
            """
        ).fetchall()

    sent_count = 0
    attempt_count = 0
    for row in rows:
        if sent_count >= MAX_SENDS_PER_RUN or attempt_count >= MAX_ATTEMPTS_PER_RUN:
            break
        stage = _due_stage(row, now)
        if not stage:
            continue
        attempt_count += 1
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
        except Forbidden as exc:
            _disable_delivery(str(row["source"]), int(row["user_id"]), "blocked")
            _mark_send(str(row["source"]), int(row["user_id"]), stage, campaign_key, "blocked")
        except BadRequest as exc:
            logger.warning(
                "Fantzo reminder rejected for %s/%s: %s",
                row["source"],
                row["user_id"],
                exc,
            )
            if str(row["source"]) == "business_dm":
                _disable_delivery(
                    "business_dm",
                    int(row["user_id"]),
                    str(exc),
                )
                _mark_send(
                    "business_dm",
                    int(row["user_id"]),
                    stage,
                    campaign_key,
                    "undeliverable",
                )
            else:
                _mark_send(
                    str(row["source"]),
                    int(row["user_id"]),
                    stage,
                    campaign_key,
                    "bad_request",
                )
        except Exception:
            logger.exception("Fantzo reminder send failed for %s/%s", row["source"], row["user_id"])
            _mark_send(str(row["source"]), int(row["user_id"]), stage, campaign_key, "failed")


async def reminder_loop(application) -> None:
    ensure_tables()
    await asyncio.sleep(20)
    while True:
        try:
            await run_due_reminders(application)
        except Exception:
            logger.exception("Fantzo reminder loop error")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


async def _start_background_loop_when_running(application) -> None:
    while not application.running:
        await asyncio.sleep(0.2)
    application.create_task(reminder_loop(application))


def start_background_loop(application) -> None:
    try:
        repair_business_connections()
    except Exception:
        logger.exception("Fantzo Business reminder mapping repair failed")
    asyncio.create_task(
        _start_background_loop_when_running(application),
        name="fantzo-reminder-loop-starter",
    )


def stats() -> dict:
    ensure_tables()
    with core.db() as conn:
        users = conn.execute(
            "SELECT COUNT(DISTINCT user_id) AS c FROM reminder_users "
            "WHERE opted_out=0 AND COALESCE(delivery_disabled,0)=0"
        ).fetchone()["c"]
        dm = conn.execute(
            "SELECT COUNT(*) AS c FROM reminder_users "
            "WHERE source='business_dm' AND opted_out=0 "
            "AND COALESCE(delivery_disabled,0)=0"
        ).fetchone()["c"]
        bot = conn.execute(
            "SELECT COUNT(*) AS c FROM reminder_users "
            "WHERE source='bot' AND opted_out=0 "
            "AND COALESCE(delivery_disabled,0)=0"
        ).fetchone()["c"]
        sent = conn.execute(
            "SELECT COUNT(*) AS c FROM reminder_sends WHERE status='sent'"
        ).fetchone()["c"]
        undeliverable = conn.execute(
            "SELECT COUNT(*) AS c FROM reminder_users "
            "WHERE opted_out=0 AND COALESCE(delivery_disabled,0)=1"
        ).fetchone()["c"]
    return {
        "users": users,
        "dm": dm,
        "bot": bot,
        "sent": sent,
        "undeliverable": undeliverable,
    }
