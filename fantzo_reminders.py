import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardButton as TelegramInlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)
from telegram.error import BadRequest, Forbidden, RetryAfter

import bot as core
import fantzo_business as business
import ibetin_hub as hub
import ibetin_match_alerts as match_alerts
import ibetin_phone_verify as phone_verify

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
CHANNEL_AUTOPOST_ENABLED = os.getenv("IBETIN_CHANNEL_AUTOPOST_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
CHANNEL_AUTOPOST_HOUR = max(0, min(23, int(os.getenv("IBETIN_CHANNEL_AUTOPOST_HOUR", "10"))))
CHANNEL_AUTOPOST_MINUTE = max(0, min(59, int(os.getenv("IBETIN_CHANNEL_AUTOPOST_MINUTE", "0"))))
CHANNEL_RETRY_MINUTES = max(5, int(os.getenv("IBETIN_CHANNEL_RETRY_MINUTES", "15")))
CHANNEL_CATCHUP_HOURS = max(1, int(os.getenv("IBETIN_CHANNEL_CATCHUP_HOURS", "6")))
IBETIN_CHANNEL_CHAT_ID = "@ibetinoffcial"


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


def _runtime_setting_bool(key: str, default: bool) -> bool:
    ensure_tables()
    with core.db() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"
        )
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            (key,),
        ).fetchone()
    if not row:
        return bool(default)
    return str(row["value"] or "").strip().lower() in {"1", "true", "yes", "on"}


def set_automation_enabled(kind: str, enabled: bool) -> bool:
    key_map = {
        "reminders": "ibetin_reminders_enabled",
        "channel": "ibetin_channel_autopost_enabled",
    }
    key = key_map.get(str(kind or "").strip().lower())
    if not key:
        return False
    ensure_tables()
    with core.db() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"
        )
        conn.execute(
            """
            INSERT INTO settings(key, value) VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, "1" if enabled else "0"),
        )
    logger.info("IBETIN automation setting changed kind=%s enabled=%s", kind, enabled)
    return True


def reminders_enabled() -> bool:
    return _runtime_setting_bool("ibetin_reminders_enabled", True)


def channel_autopost_enabled() -> bool:
    return bool(CHANNEL_AUTOPOST_ENABLED) and _runtime_setting_bool(
        "ibetin_channel_autopost_enabled", True
    )


def automation_status() -> dict:
    ensure_tables()
    with core.db() as conn:
        last_channel = conn.execute(
            """
            SELECT campaign_key, sent_at, message_id, status
            FROM channel_campaigns
            ORDER BY sent_at DESC
            LIMIT 1
            """
        ).fetchone()
        reminder_sent_24h = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM reminder_sends
            WHERE status='sent' AND sent_at >= ?
            """,
            ((datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(),),
        ).fetchone()["c"]
    now = datetime.now(APP_TZ)
    target = now.replace(
        hour=CHANNEL_AUTOPOST_HOUR,
        minute=CHANNEL_AUTOPOST_MINUTE,
        second=0,
        microsecond=0,
    )
    today_key = _daily_channel_campaign_key(now)
    today_row = None
    with core.db() as conn:
        today_row = conn.execute(
            "SELECT sent_at, status FROM channel_campaigns WHERE campaign_key=?",
            (today_key,),
        ).fetchone()
    if target <= now:
        if (
            (not today_row or str(today_row["status"]) != "sent")
            and now <= target + timedelta(hours=CHANNEL_CATCHUP_HOURS)
        ):
            if today_row and today_row["sent_at"]:
                last_attempt = _parse_dt(str(today_row["sent_at"]))
                if last_attempt:
                    if last_attempt.tzinfo is None:
                        last_attempt = last_attempt.replace(tzinfo=timezone.utc)
                    target = max(
                        now,
                        last_attempt.astimezone(APP_TZ)
                        + timedelta(minutes=CHANNEL_RETRY_MINUTES),
                    )
                else:
                    target = now
            else:
                target = now
        else:
            target += timedelta(days=1)
    return {
        "reminders_enabled": reminders_enabled(),
        "channel_enabled": channel_autopost_enabled(),
        "channel_time": f"{CHANNEL_AUTOPOST_HOUR:02d}:{CHANNEL_AUTOPOST_MINUTE:02d}",
        "next_channel_at": target.isoformat(),
        "reminder_sent_24h": int(reminder_sent_24h or 0),
        "last_channel": dict(last_channel) if last_channel else None,
    }


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
    if not user_id:
        return
    ensure_tables()
    now = _now_iso()
    with core.db() as conn:
        conn.execute(
            """
            INSERT INTO reminder_users(
                source, user_id, business_connection_id, interest, last_activity,
                last_reminder, reminder_stage, opted_out, updated_at
            ) VALUES (?, ?, '', 'general', ?, NULL, 0, ?, ?)
            ON CONFLICT(source, user_id) DO UPDATE SET
                opted_out = excluded.opted_out,
                updated_at = excluded.updated_at
            """,
            (source, int(user_id), now, 1 if opted_out else 0, now),
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


def _verification_due_stage(row, now_utc: datetime):
    last_activity = _parse_dt(str(row["last_activity"]))
    if not last_activity:
        return None
    elapsed = now_utc - last_activity
    stage = int(row["reminder_stage"] or 0)
    thresholds = [
        timedelta(minutes=45),
        timedelta(hours=6),
        timedelta(hours=24),
    ]
    if stage >= len(thresholds):
        return None
    return stage + 1 if elapsed >= thresholds[stage] else None


def _copy_for(interest: str, stage: int, source: str, user_id: int = 0):
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
                        url=(
                            (
                                phone_verify.live_line_url(user_id, IBETIN_LIVE_LINE_URL)
                                if user_id and phone_verify.is_verified(user_id)
                                else phone_verify.verification_bot_url()
                            )
                        ),
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
        # Normal private-bot follow-ups stay in chat until mobile verification.
        # Only verified users receive a Live Line WebApp launcher.
        if user_id and phone_verify.is_verified(user_id):
            live_line_button = TelegramInlineKeyboardButton(
                "🏏 OPEN LIVE LINE",
                web_app=WebAppInfo(
                    url=phone_verify.live_line_url(user_id, IBETIN_LIVE_LINE_URL)
                ),
            )
        else:
            live_line_button = InlineKeyboardButton(
                "🏏 OPEN LIVE LINE",
                callback_data="liveline_access",
            )

        markup = InlineKeyboardMarkup(
            [
                [live_line_button],
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


def _verification_reminder_copy(stage: int):
    if stage == 1:
        intro = "📱 Complete your IBETIN verification"
    elif stage == 2:
        intro = "🔐 Your IBETIN verification is still pending"
    else:
        intro = "👋 Finish verification to continue with IBETIN"

    text = (
        f"<b>{intro}</b>\n\n"
        "Verify the mobile number linked to your Telegram account. "
        "You only need to do this once.\n\n"
        "Tap <b>📱 VERIFY & CONTINUE</b> below. By continuing, you agree that "
        "the IBETIN team may contact you about your request by phone call and WhatsApp. "
        "You can opt out anytime.\n\n"
        "🔞 <b>18+ only • Play responsibly</b>"
    )
    markup = ReplyKeyboardMarkup(
        [[KeyboardButton("📱 VERIFY & CONTINUE", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
        input_field_placeholder="Tap VERIFY & CONTINUE",
    )
    return text, markup


async def _send_verification_with_retry(bot, row, stage: int) -> bool:
    text, markup = _verification_reminder_copy(stage)
    kwargs = {
        "chat_id": int(row["user_id"]),
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": markup,
        "disable_web_page_preview": True,
    }

    for attempt in range(3):
        try:
            await bot.send_message(**kwargs)
            return True
        except RetryAfter as exc:
            delay = (
                exc.retry_after.total_seconds()
                if hasattr(exc.retry_after, "total_seconds")
                else float(exc.retry_after)
            )
            if attempt >= 2:
                raise
            await asyncio.sleep(max(1.0, delay) + 1.0)
        except (Forbidden, BadRequest):
            raise
    return False


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
    text, markup = _copy_for(
        str(row["interest"]),
        stage,
        str(row["source"]),
        int(row["user_id"]),
    )
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
    if not reminders_enabled() or _is_quiet_hours():
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

        # Unverified main-bot users receive verification-only reminders on
        # the verification cadence (45m, 6h, 24h). They never receive normal
        # sports/promotional reminders before completing verification.
        if not phone_verify.is_verified(int(row["user_id"])):
            if str(row["source"]) != "bot":
                continue

            stage = _verification_due_stage(row, now)
            if not stage:
                continue

            campaign_key = (
                f"verify:{row['source']}:{stage}:"
                + str(row["last_activity"]).replace(":", "").replace("+", "_")
            )
            with core.db() as conn:
                exists = conn.execute(
                    "SELECT 1 FROM reminder_sends "
                    "WHERE source = ? AND user_id = ? AND campaign_key = ? "
                    "AND status IN ('sent','bad_request','blocked')",
                    (row["source"], row["user_id"], campaign_key),
                ).fetchone()
            if exists:
                continue

            try:
                ok = await _send_verification_with_retry(application.bot, row, stage)
                _mark_send(
                    str(row["source"]),
                    int(row["user_id"]),
                    stage,
                    campaign_key,
                    "sent" if ok else "failed",
                )
                if ok:
                    sent_count += 1
                    await asyncio.sleep(1.2)
            except Forbidden:
                set_opt_out(str(row["source"]), int(row["user_id"]), True)
                _mark_send(
                    str(row["source"]),
                    int(row["user_id"]),
                    stage,
                    campaign_key,
                    "blocked",
                )
            except BadRequest as exc:
                logger.warning(
                    "IBETIN verification reminder rejected for %s/%s: %s",
                    row["source"],
                    row["user_id"],
                    exc,
                )
                _mark_send(
                    str(row["source"]),
                    int(row["user_id"]),
                    stage,
                    campaign_key,
                    "bad_request",
                )
            except Exception:
                logger.exception(
                    "IBETIN verification reminder send failed for %s/%s",
                    row["source"],
                    row["user_id"],
                )
                _mark_send(
                    str(row["source"]),
                    int(row["user_id"]),
                    stage,
                    campaign_key,
                    "failed",
                )
            continue

        stage = _due_stage(row, now)
        if not stage:
            continue
        campaign_key = _campaign_key(row, stage)
        with core.db() as conn:
            exists = conn.execute(
                "SELECT 1 FROM reminder_sends WHERE source = ? AND user_id = ? AND campaign_key = ? AND status IN ('sent','bad_request','blocked')",
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


def _daily_channel_campaign_key(local_now: datetime) -> str:
    return f"liveline-daily-{local_now.strftime('%Y%m%d')}"


def _channel_daily_creative(local_now: datetime):
    try:
        import ibetin_creatives as creatives
        creatives.ensure_tables()
        with core.db() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM creative_assets
                WHERE active = 1 AND pool = 'channel'
                ORDER BY id ASC
                """
            ).fetchall()
        if not rows:
            return None, creatives
        index = local_now.toordinal() % len(rows)
        return rows[index], creatives
    except Exception as exc:
        logger.warning("IBETIN channel creative lookup failed: %s", str(exc)[:180])
        return None, None


async def send_liveline_channel_daily(application, local_now: datetime | None = None) -> bool:
    """Send one scheduled Live Line channel post per Dubai calendar day."""
    if not channel_autopost_enabled():
        return False

    ensure_tables()
    local_now = local_now or datetime.now(APP_TZ)
    campaign_key = _daily_channel_campaign_key(local_now)

    with core.db() as conn:
        existing = conn.execute(
            "SELECT status FROM channel_campaigns WHERE campaign_key = ?",
            (campaign_key,),
        ).fetchone()
    if existing and str(existing["status"]) == "sent":
        logger.info("IBETIN daily channel post already sent campaign=%s", campaign_key)
        return True

    caption = (
        "🏏 <b>IBETIN LIVE LINE</b>\n\n"
        "Live cricket scores, Match Pulse, scorecards, fixtures and results — inside Telegram.\n\n"
        "⚡ Fast live updates\n"
        "📊 Match Pulse & scorecards\n"
        "🗓 Fixtures & results\n\n"
        "Tap below to open Live Line."
    )
    markup = InlineKeyboardMarkup(
        [[TelegramInlineKeyboardButton(
            "🏏 OPEN IBETIN LIVE LINE",
            url=IBETIN_LIVE_LINE_MINI_APP_URL,
        )]]
    )

    try:
        creative, creatives = _channel_daily_creative(local_now)
        if creative is not None and creatives is not None:
            msg = await creatives._send_creative_as_photo(
                application.bot,
                creative,
                {
                    "chat_id": IBETIN_CHANNEL_CHAT_ID,
                    "caption": caption,
                    "parse_mode": "HTML",
                    "reply_markup": markup,
                },
            )
            creative_id = int(creative["id"])
        else:
            msg = await application.bot.send_message(
                chat_id=IBETIN_CHANNEL_CHAT_ID,
                text=caption,
                parse_mode="HTML",
                reply_markup=markup,
                disable_web_page_preview=True,
            )
            creative_id = None

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
                (campaign_key, _now_iso(), int(msg.message_id)),
            )
        logger.info(
            "IBETIN daily channel post sent channel=%s message_id=%s campaign=%s creative_id=%s",
            IBETIN_CHANNEL_CHAT_ID,
            msg.message_id,
            campaign_key,
            creative_id,
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
                (campaign_key, _now_iso()),
            )
        logger.warning("IBETIN daily channel post failed: %s", str(exc)[:180])
        return False


async def channel_autopost_loop(application) -> None:
    if not CHANNEL_AUTOPOST_ENABLED:
        logger.info("IBETIN daily channel autopost feature disabled by environment")
        return

    last_logged_target = ""
    while True:
        if not channel_autopost_enabled():
            await asyncio.sleep(30)
            continue

        now = datetime.now(APP_TZ)
        today_target = now.replace(
            hour=CHANNEL_AUTOPOST_HOUR,
            minute=CHANNEL_AUTOPOST_MINUTE,
            second=0,
            microsecond=0,
        )
        campaign_key = _daily_channel_campaign_key(now)

        with core.db() as conn:
            row = conn.execute(
                "SELECT sent_at, status FROM channel_campaigns WHERE campaign_key=?",
                (campaign_key,),
            ).fetchone()

        already_sent = bool(row and str(row["status"]) == "sent")
        catchup_deadline = today_target + timedelta(hours=CHANNEL_CATCHUP_HOURS)

        # Before today's slot, simply wait for it.
        if now < today_target:
            target = today_target
        # After a successful send, next due is tomorrow.
        elif already_sent:
            target = today_target + timedelta(days=1)
        # If today's post is due and still inside the catch-up window, retry
        # failed attempts no more often than CHANNEL_RETRY_MINUTES.
        elif now <= catchup_deadline:
            last_attempt = _parse_dt(str(row["sent_at"])) if row and row["sent_at"] else None
            if last_attempt:
                if last_attempt.tzinfo is None:
                    last_attempt = last_attempt.replace(tzinfo=timezone.utc)
                retry_at = last_attempt.astimezone(APP_TZ) + timedelta(minutes=CHANNEL_RETRY_MINUTES)
            else:
                retry_at = today_target
            target = max(now, retry_at)
        else:
            target = today_target + timedelta(days=1)

        target_key = target.isoformat()
        if target_key != last_logged_target:
            logger.info(
                "IBETIN daily channel autopost scheduled next=%s channel=%s",
                target_key,
                IBETIN_CHANNEL_CHAT_ID,
            )
            last_logged_target = target_key

        wait_seconds = max(0.0, (target - now).total_seconds())
        if wait_seconds > 60:
            await asyncio.sleep(60)
            continue
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)

        current = datetime.now(APP_TZ)
        if (
            current.date() == today_target.date()
            and current >= today_target
            and current <= catchup_deadline
            and channel_autopost_enabled()
        ):
            try:
                await send_liveline_channel_daily(application, current)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("IBETIN daily channel autopost loop error")
            await asyncio.sleep(65)
        else:
            await asyncio.sleep(30)



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
    if CHANNEL_AUTOPOST_ENABLED:
        application.bot_data["ibetin_channel_autopost_task"] = asyncio.create_task(
            channel_autopost_loop(application),
            name="ibetin-channel-autopost",
        )
    logger.info(
        "IBETIN reminder and real-time match-alert workers started; channel_autopost=%s time=%02d:%02d Asia/Dubai",
        CHANNEL_AUTOPOST_ENABLED,
        CHANNEL_AUTOPOST_HOUR,
        CHANNEL_AUTOPOST_MINUTE,
    )


def stats() -> dict:
    ensure_tables()
    with core.db() as conn:
        users = conn.execute("SELECT COUNT(*) AS c FROM reminder_users WHERE opted_out = 0").fetchone()["c"]
        dm = conn.execute("SELECT COUNT(*) AS c FROM reminder_users WHERE source = 'business_dm' AND opted_out = 0").fetchone()["c"]
        bot = conn.execute("SELECT COUNT(*) AS c FROM reminder_users WHERE source = 'bot' AND opted_out = 0").fetchone()["c"]
        sent = conn.execute("SELECT COUNT(*) AS c FROM reminder_sends WHERE status = 'sent'").fetchone()["c"]
    return {"users": users, "dm": dm, "bot": bot, "sent": sent}
