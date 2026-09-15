import asyncio
import logging
import os
from datetime import datetime, timezone
from html import escape
from urllib.parse import quote
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.error import BadRequest, Forbidden, RetryAfter

import bot as core

logger = logging.getLogger(__name__)
APP_TZ = ZoneInfo("Asia/Dubai")
CHECK_INTERVAL_SECONDS = int(os.getenv("IBETIN_MATCH_ALERT_INTERVAL", "90"))
MAX_EVENT_SENDS_PER_RUN = int(os.getenv("IBETIN_MATCH_ALERT_MAX_SENDS", "120"))
ENABLED = os.getenv("IBETIN_MATCH_ALERTS_ENABLED", "1").strip().lower() not in {"0", "false", "off", "no"}

IBETIN_HOME_URL = os.getenv("IBETIN_HOME_URL", "https://ibetin.com").strip().rstrip("/")
IBETIN_LIVE_URL = os.getenv("IBETIN_LIVE_URL", f"{IBETIN_HOME_URL}/live").strip()
IBETIN_RESULTS_URL = os.getenv("IBETIN_RESULTS_URL", f"{IBETIN_HOME_URL}/results").strip()
TRACKING_BASE_URL = (
    os.getenv("TRACKING_BASE_URL", "").strip()
    or os.getenv("RAILWAY_STATIC_URL", "").strip()
    or os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
)

_missing_key_logged = False


def _web_base() -> str:
    value = TRACKING_BASE_URL
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    return value.rstrip("/")


def _hub_url(section: str) -> str:
    base = _web_base()
    if base:
        return f"{base}/hub?section={quote(section, safe='')}"
    return IBETIN_LIVE_URL if section == "live" else IBETIN_RESULTS_URL


def ensure_tables() -> None:
    with core.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS match_alert_sends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                sport TEXT NOT NULL,
                match_key TEXT NOT NULL,
                event_key TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                status TEXT NOT NULL,
                UNIQUE(user_id, sport, match_key, event_key)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_match_alert_sends_time ON match_alert_sends(sent_at)"
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_description(match: dict) -> str:
    state = (match or {}).get("state") or {}
    if isinstance(state, dict):
        return str(state.get("description") or "").strip()
    return str(state or "").strip()


def _report(match: dict) -> str:
    state = (match or {}).get("state") or {}
    if isinstance(state, dict):
        return str(state.get("report") or "").strip()
    return ""


def _team_name(match: dict, side: str) -> str:
    obj = (match or {}).get(f"{side}Team") or (match or {}).get(side) or {}
    if isinstance(obj, dict):
        return str(obj.get("name") or obj.get("displayName") or side.title()).strip()
    return str(obj or side.title()).strip()


def _league_name(match: dict) -> str:
    obj = (match or {}).get("league") or {}
    if isinstance(obj, dict):
        return str(obj.get("name") or "").strip()
    return str(obj or "").strip()


def _start_datetime(match: dict):
    raw = (match or {}).get("startDate") or (match or {}).get("startTime")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=APP_TZ)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _match_key(match: dict, sport: str) -> str:
    match_id = str((match or {}).get("id") or "").strip()
    if match_id:
        return match_id
    start = str((match or {}).get("startDate") or (match or {}).get("startTime") or "")
    return f"{sport}:{start}:{_team_name(match, 'home')}:{_team_name(match, 'away')}"[:220]


def _cricket_score(match: dict) -> str:
    state = (match or {}).get("state") or {}
    teams = state.get("teams") if isinstance(state, dict) else None
    if not isinstance(teams, dict):
        return ""
    parts = []
    for side in ("home", "away"):
        team = teams.get(side) or {}
        if not isinstance(team, dict):
            continue
        score = team.get("score")
        info = team.get("info")
        if score:
            suffix = f" ({info})" if info else ""
            parts.append(f"{_team_name(match, side)} {score}{suffix}")
    return " • ".join(parts)


def _football_score(match: dict) -> str:
    state = (match or {}).get("state") or {}
    score = state.get("score") if isinstance(state, dict) else None
    if isinstance(score, dict):
        current = score.get("current")
        if isinstance(current, dict):
            home = current.get("home")
            away = current.get("away")
            if home is not None or away is not None:
                return f"{_team_name(match, 'home')} {home if home is not None else '-'} - {away if away is not None else '-'} {_team_name(match, 'away')}"
        if current is not None:
            return str(current)
    return ""


def _score(match: dict, sport: str) -> str:
    return _cricket_score(match) if sport == "cricket" else _football_score(match)


def _toss_text(match: dict) -> str:
    toss = (match or {}).get("toss")
    if isinstance(toss, dict):
        winner = toss.get("winner") or toss.get("team") or toss.get("name")
        decision = toss.get("decision") or toss.get("choice")
        if isinstance(winner, dict):
            winner = winner.get("name") or winner.get("displayName")
        if winner:
            return f"{winner}{' · ' + str(decision) if decision else ''}"
    elif toss:
        return str(toss)

    report = _report(match)
    if "toss" in report.casefold():
        return report
    return ""


def _event_for(match: dict, sport: str, now_utc: datetime):
    state = _state_description(match).casefold()

    if state in core.FINISHED_STATES:
        return "final", {}

    if sport == "cricket" and state == "innings break":
        return "innings_break", {}

    if sport == "football" and state == "half time":
        return "halftime", {}

    if sport == "cricket" and state in core.UPCOMING_STATES:
        toss = _toss_text(match)
        if toss:
            return "toss", {"toss": toss}

    live_states = core.CRICKET_LIVE_STATES if sport == "cricket" else core.FOOTBALL_LIVE_STATES
    if state in live_states:
        return "started", {}

    if state in core.UPCOMING_STATES:
        start = _start_datetime(match)
        if start:
            minutes = (start - now_utc).total_seconds() / 60.0
            if 0 <= minutes <= 15:
                return "starting_soon", {"minutes": max(1, int(round(minutes)))}

    return None, {}


def _already_sent(user_id: int, sport: str, match_key: str, event_key: str) -> bool:
    ensure_tables()
    with core.db() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM match_alert_sends
            WHERE user_id = ? AND sport = ? AND match_key = ? AND event_key = ? AND status = 'sent'
            """,
            (user_id, sport, match_key, event_key),
        ).fetchone()
    return bool(row)


def _mark(user_id: int, sport: str, match_key: str, event_key: str, status: str) -> None:
    ensure_tables()
    with core.db() as conn:
        conn.execute(
            """
            INSERT INTO match_alert_sends(user_id, sport, match_key, event_key, sent_at, status)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, sport, match_key, event_key) DO UPDATE SET
                sent_at = excluded.sent_at,
                status = excluded.status
            """,
            (user_id, sport, match_key, event_key, _now_iso(), status),
        )


def _subscribers():
    with core.db() as conn:
        return conn.execute(
            "SELECT user_id, language FROM users WHERE subscribed = 1 ORDER BY last_seen DESC"
        ).fetchall()


def _event_text(match: dict, sport: str, event_key: str, extra: dict, language: str) -> str:
    home = escape(_team_name(match, "home"))
    away = escape(_team_name(match, "away"))
    league = escape(_league_name(match))
    score = escape(_score(match, sport))
    report = escape(_report(match))
    toss = escape(str(extra.get("toss") or ""))
    minutes = int(extra.get("minutes") or 0)

    hi = language == "hi"
    labels_en = {
        "starting_soon": "⏰ <b>MATCH STARTS SOON</b>",
        "toss": "🪙 <b>TOSS UPDATE</b>",
        "started": "🔴 <b>MATCH STARTED</b>",
        "innings_break": "🏏 <b>INNINGS BREAK</b>",
        "halftime": "⏸ <b>HALF-TIME</b>",
        "final": "✅ <b>FINAL RESULT</b>",
    }
    labels_hi = {
        "starting_soon": "⏰ <b>मैच जल्द शुरू होगा</b>",
        "toss": "🪙 <b>टॉस अपडेट</b>",
        "started": "🔴 <b>मैच शुरू</b>",
        "innings_break": "🏏 <b>इनिंग्स ब्रेक</b>",
        "halftime": "⏸ <b>हाफ-टाइम</b>",
        "final": "✅ <b>अंतिम परिणाम</b>",
    }
    label = (labels_hi if hi else labels_en)[event_key]

    lines = [label, "", f"<b>{home}</b>  vs  <b>{away}</b>"]
    if league:
        lines.append(f"🏆 {league}")
    if event_key == "starting_soon" and minutes:
        lines.append((f"⏱ लगभग {minutes} मिनट में" if hi else f"⏱ About {minutes} min to start"))
    if event_key == "toss" and toss:
        lines.append(f"🪙 {toss}")
    if score:
        lines.append(f"📊 {score}")
    if report and event_key not in {"toss"}:
        lines.append(f"📣 {report}")

    if hi:
        lines.extend(["", "IBETIN Mini App में लाइव अपडेट देखें।"])
    else:
        lines.extend(["", "Follow the latest update inside the IBETIN Mini App."])
    return "\n".join(lines)


def _markup(event_key: str) -> InlineKeyboardMarkup:
    if event_key == "final":
        return InlineKeyboardMarkup(
            [[InlineKeyboardButton("📊 VIEW RESULTS", web_app=WebAppInfo(url=_hub_url("results")))],
             [InlineKeyboardButton("⚡ OPEN IBETIN", web_app=WebAppInfo(url=_hub_url("home")))]]
        )
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔴 OPEN LIVE", web_app=WebAppInfo(url=_hub_url("live")))],
         [InlineKeyboardButton("🔔 MY ALERTS", web_app=WebAppInfo(url=_hub_url("alerts")))]]
    )


async def _send(bot, user_id: int, text: str, markup: InlineKeyboardMarkup) -> None:
    for attempt in range(3):
        try:
            await bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode="HTML",
                reply_markup=markup,
                disable_web_page_preview=True,
            )
            return
        except RetryAfter as exc:
            if attempt >= 2:
                raise
            delay = exc.retry_after.total_seconds() if hasattr(exc.retry_after, "total_seconds") else float(exc.retry_after)
            await asyncio.sleep(max(1.0, delay) + 1.0)


async def _today_matches(sport: str):
    today = datetime.now(APP_TZ).date().isoformat()
    return await core.get_sport_matches_for_date(sport, today)


async def run_due_match_alerts(application) -> int:
    global _missing_key_logged
    if not ENABLED:
        return 0
    if not getattr(core, "HIGHLIGHTLY_API_KEY", None):
        if not _missing_key_logged:
            logger.warning("IBETIN event alerts are ready but HIGHLIGHTLY_API_KEY is not configured")
            _missing_key_logged = True
        return 0

    ensure_tables()
    subscribers = _subscribers()
    if not subscribers:
        return 0

    results = await asyncio.gather(
        _today_matches("cricket"),
        _today_matches("football"),
        return_exceptions=True,
    )

    now_utc = datetime.now(timezone.utc)
    sent = 0

    for sport, matches in zip(("cricket", "football"), results):
        if isinstance(matches, Exception):
            logger.warning("IBETIN %s event-alert feed unavailable: %s", sport, matches)
            continue
        for match in matches or []:
            if not isinstance(match, dict):
                continue
            event_key, extra = _event_for(match, sport, now_utc)
            if not event_key:
                continue
            match_key = _match_key(match, sport)
            markup = _markup(event_key)

            for row in subscribers:
                if sent >= MAX_EVENT_SENDS_PER_RUN:
                    return sent
                user_id = int(row["user_id"])
                if _already_sent(user_id, sport, match_key, event_key):
                    continue
                language = str(row["language"] or "en")
                text = _event_text(match, sport, event_key, extra, language)
                try:
                    await _send(application.bot, user_id, text, markup)
                    _mark(user_id, sport, match_key, event_key, "sent")
                    sent += 1
                    await asyncio.sleep(0.08)
                except Forbidden:
                    core.set_subscription(user_id, False)
                    _mark(user_id, sport, match_key, event_key, "blocked")
                except BadRequest as exc:
                    logger.warning("IBETIN match alert rejected for %s: %s", user_id, exc)
                    _mark(user_id, sport, match_key, event_key, "bad_request")
                except Exception:
                    logger.exception("IBETIN match alert failed for %s", user_id)
                    _mark(user_id, sport, match_key, event_key, "failed")

    return sent


async def match_alert_loop(application) -> None:
    ensure_tables()
    await asyncio.sleep(15)
    while True:
        try:
            sent = await run_due_match_alerts(application)
            if sent:
                logger.info("IBETIN real-time match alerts sent: %s", sent)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("IBETIN match alert loop error")
        await asyncio.sleep(max(60, CHECK_INTERVAL_SECONDS))
