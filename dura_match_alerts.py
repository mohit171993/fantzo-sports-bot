"""Follow-a-team score alerts for the DURA cricket bot.

Events are derived from match payloads the liveline feed has already fetched
(Roanuz webhooks, restored webhook cache, live lists, and match detail).
This module does not call a sports API. Sends are queued in SQLite so a
restart cannot deliver the same event twice, and a drain loop spaces them
out for Telegram.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import threading
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden, RetryAfter
from telegram.ext import CommandHandler

import bot as core

logger = logging.getLogger(__name__)

APP_TZ = ZoneInfo("Asia/Kolkata")
ENABLED = os.getenv("DURA_TEAM_ALERTS_ENABLED", "1").strip().lower() not in {
    "0",
    "false",
    "off",
    "no",
}
MAX_SENDS_PER_DRAIN = int(os.getenv("DURA_TEAM_ALERT_MAX_SENDS", "20"))
SEND_GAP_SECONDS = float(os.getenv("DURA_TEAM_ALERT_SEND_GAP", "0.05"))
STARTING_SOON_MINUTES = 20
PAGE_SIZE = 6

# Close finishes stay off until a user turns them on.
ALERT_TYPES = (
    ("prestart", "Toss / starting soon", True),
    ("wicket", "Wickets", True),
    ("milestone", "Fifties and hundreds", True),
    ("innings_break", "Innings break", True),
    ("close_finish", "Close finish", False),
    ("final", "Final result", True),
)
_TYPE_DEFAULTS = {key: enabled for key, _label, enabled in ALERT_TYPES}
_SILENT_ON_FIRST_SIGHT = {"wicket", "milestone"}

_FINISHED = {
    "completed",
    "complete",
    "finished",
    "result",
    "ended",
    "closed",
    "abandoned",
    "cancelled",
    "canceled",
    "no result",
}
_UPCOMING = {
    "not_started",
    "not started",
    "scheduled",
    "upcoming",
    "fixture",
    "created",
    "confirmed",
    "to be announced",
    "tba",
    "pre_match",
    "prematch",
    "notstarted",
}
_INNINGS_BREAK = {"innings break", "innings_break", "inningsbreak"}

_BANNED = re.compile(
    r"(?i)(?:https?://\S+|t\.me/\S+|durabet|ibetin|"
    r"\b(?:odds|bhav|betting|bets?|casino|payments?|gambl\w*|"
    r"wagers?|wagering|bookmakers?|bookies?)\b)"
)
_DB_LOCK = threading.Lock()


@dataclass
class Batter:
    name: str
    name_key: str
    runs: int
    dismissed: bool


@dataclass
class Innings:
    index: str
    team_name: str
    runs: int | None = None
    wickets: int | None = None
    overs: str = ""
    completed: bool = False
    batters: list[Batter] = field(default_factory=list)


@dataclass
class Snapshot:
    match_key: str
    home: str
    away: str
    aliases: set[str]
    phase: str
    toss: str = ""
    start_at: datetime | None = None
    target: int | None = None
    innings: list[Innings] = field(default_factory=list)
    players: set[str] = field(default_factory=set)
    result: str = ""
    label: str = ""


@dataclass
class AlertEvent:
    match_key: str
    event_key: str
    alert_type: str
    body: str
    player_keys: tuple[str, ...] = ()


def name_key(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return re.sub(r"\s+", " ", text)


def scrub(value) -> str:
    text = _BANNED.sub(" ", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip(" -·|")
    return text


def safe(value) -> str:
    return escape(scrub(value))


def ensure_tables() -> None:
    with _DB_LOCK:
        with core.db() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS dura_team_follows (
                    user_id INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    name_key TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, kind, name_key)
                );
                CREATE TABLE IF NOT EXISTS dura_alert_catalog (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    name_key TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    UNIQUE(kind, name_key)
                );
                CREATE TABLE IF NOT EXISTS dura_alert_matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_key TEXT NOT NULL UNIQUE,
                    label TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dura_alert_seen (
                    match_key TEXT NOT NULL,
                    event_key TEXT NOT NULL,
                    seen_at TEXT NOT NULL,
                    PRIMARY KEY (match_key, event_key)
                );
                CREATE TABLE IF NOT EXISTS dura_alert_match_init (
                    match_key TEXT PRIMARY KEY,
                    initialized_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dura_alert_outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    match_key TEXT NOT NULL,
                    event_key TEXT NOT NULL,
                    body TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    sent_at TEXT,
                    UNIQUE(user_id, match_key, event_key)
                );
                CREATE INDEX IF NOT EXISTS idx_dura_alert_outbox_status
                    ON dura_alert_outbox(status, id);
                CREATE TABLE IF NOT EXISTS dura_alert_prefs (
                    user_id INTEGER NOT NULL,
                    pref_key TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, pref_key)
                );
                """
            )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_int(value) -> int | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, dict):
        for key in ("runs", "score", "wickets", "target"):
            if key in value:
                found = _as_int(value.get(key))
                if found is not None:
                    return found
        return None
    text = str(value).strip()
    match = re.search(r"-?\d+", text)
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def _score_pair(value) -> tuple[int | None, int | None]:
    if isinstance(value, dict):
        runs = _as_int(value.get("runs"))
        if runs is None:
            runs = _as_int(value.get("score"))
        wickets = _as_int(value.get("wickets"))
        return runs, wickets
    text = str(value or "").strip()
    match = re.search(r"(\d+)\s*/\s*(\d+)", text)
    if match:
        return int(match.group(1)), int(match.group(2))
    return _as_int(text), None


def _overs_text(value) -> str:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return f"{value[0]}.{value[1]}"
    text = str(value or "").strip()
    text = text.replace(" ov", "").replace(" overs", "").strip()
    return text


def _parse_start(value) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        stamp = float(value)
        if stamp > 10_000_000_000:
            stamp /= 1000.0
        try:
            return datetime.fromtimestamp(stamp, timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if re.fullmatch(r"\d+(\.\d+)?", text):
        return _parse_start(float(text))
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=APP_TZ)
    return parsed.astimezone(timezone.utc)


def _person_name(node) -> str:
    if isinstance(node, str):
        return scrub(node)
    if not isinstance(node, dict):
        return ""
    player = node.get("player") if isinstance(node.get("player"), dict) else {}
    for source in (node, player):
        for key in ("name", "full_name", "fullName", "display_name", "displayName", "short_name", "shortName"):
            value = source.get(key)
            if value not in (None, ""):
                return scrub(value)
    return ""


def _person_runs(node) -> int | None:
    if not isinstance(node, dict):
        return None
    for key in ("runs", "score", "batting"):
        found = _as_int(node.get(key)) if not isinstance(node.get(key), dict) else None
        if isinstance(node.get(key), dict):
            runs, _wickets = _score_pair(node.get(key))
            found = runs
        if found is not None:
            return found
    stats = node.get("statistics") if isinstance(node.get("statistics"), dict) else {}
    return _as_int(stats.get("runs"))


def _person_out(node) -> bool:
    if not isinstance(node, dict):
        return False
    for key in ("is_out", "out", "dismissed", "is_dismissed"):
        value = node.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, str)) and str(value).strip().lower() in {"1", "true", "yes", "out"}:
            return True
    status = str(node.get("status") or node.get("dismissal") or "").strip().casefold()
    if status in {"out", "dismissed", "bowled", "caught", "lbw", "run out", "stumped"}:
        return True
    return bool(node.get("how_out") or node.get("howOut") or node.get("wicket"))


def _batters(rows) -> list[Batter]:
    found = []
    if isinstance(rows, dict):
        rows = list(rows.values())
    if not isinstance(rows, list):
        return found
    for row in rows:
        name = _person_name(row)
        runs = _person_runs(row)
        if not name or runs is None:
            continue
        key = name_key(name)
        if not key:
            continue
        found.append(Batter(name=name, name_key=key, runs=runs, dismissed=_person_out(row)))
    return found


def _team_label(node, fallback: str = "") -> tuple[str, set[str]]:
    aliases = set()
    if isinstance(node, dict):
        name = scrub(
            node.get("name")
            or node.get("displayName")
            or node.get("short_name")
            or node.get("shortName")
            or node.get("code")
            or fallback
        )
        for key in ("name", "displayName", "short_name", "shortName", "code", "abbr"):
            alias = name_key(node.get(key) or "")
            if alias:
                aliases.add(alias)
    else:
        name = scrub(node or fallback)
    key = name_key(name)
    if key:
        aliases.add(key)
    return name, aliases


def _phase(status: str) -> str:
    text = re.sub(r"[_-]+", " ", str(status or "").casefold()).strip()
    if text in _FINISHED or "won by" in text:
        return "finished"
    if text in _INNINGS_BREAK:
        return "innings_break"
    if text in _UPCOMING:
        return "upcoming"
    if not text:
        return "unknown"
    return "live"


def _dict_get(node, names):
    if not isinstance(node, dict):
        return None
    for name in names:
        if node.get(name) not in (None, "", {}, []):
            return node.get(name)
    return None


def _toss_text(node, home: str, away: str) -> str:
    toss = None
    if isinstance(node, dict):
        toss = node.get("toss")
        roanuz = node.get("roanuz") if isinstance(node.get("roanuz"), dict) else {}
        if toss in (None, "", {}, []):
            toss = roanuz.get("toss")
        play = node.get("play") if isinstance(node.get("play"), dict) else {}
        if toss in (None, "", {}, []):
            toss = play.get("toss")
    if isinstance(toss, str):
        return scrub(toss)
    if not isinstance(toss, dict):
        return ""
    winner = (
        toss.get("winner")
        or toss.get("team")
        or toss.get("won_by")
        or toss.get("wonBy")
        or toss.get("winner_key")
        or toss.get("name")
    )
    decision = toss.get("decision") or toss.get("choice") or toss.get("elected") or toss.get("opted")
    winner_name = ""
    if isinstance(winner, dict):
        winner_name, _aliases = _team_label(winner)
    else:
        token = str(winner or "").strip().casefold()
        if token in {"a", "home", "team_a"}:
            winner_name = home
        elif token in {"b", "away", "team_b"}:
            winner_name = away
        else:
            winner_name = scrub(winner)
    decision_text = scrub(decision).casefold()
    if winner_name and decision_text:
        return scrub(f"{winner_name} won the toss and chose to {decision_text}")
    if winner_name:
        return scrub(f"{winner_name} won the toss")
    return ""


def _target_runs(node) -> int | None:
    if not isinstance(node, dict):
        return None
    play = node.get("play") if isinstance(node.get("play"), dict) else {}
    roanuz = node.get("roanuz") if isinstance(node.get("roanuz"), dict) else {}
    for source in (node, play, roanuz):
        raw = source.get("target") if isinstance(source, dict) else None
        found = _as_int(raw)
        if found and found > 0:
            return found
    return None


def _result_text(node, home: str, away: str) -> str:
    if not isinstance(node, dict):
        return ""
    winner = node.get("winner")
    roanuz = node.get("roanuz") if isinstance(node.get("roanuz"), dict) else {}
    if winner in (None, "", {}, []):
        winner = roanuz.get("winner")
    if isinstance(winner, dict):
        name, _aliases = _team_label(winner)
        return scrub(f"{name} won") if name else ""
    token = str(winner or "").strip()
    if not token:
        return ""
    folded = token.casefold()
    if folded in {"a", "home"}:
        return scrub(f"{home} won")
    if folded in {"b", "away"}:
        return scrub(f"{away} won")
    return scrub(token if "won" in folded else f"{token} won")


def _innings_from_rows(rows, home: str, away: str) -> list[Innings]:
    if isinstance(rows, dict):
        items = []
        order = []
        play = rows.get("play") if isinstance(rows.get("play"), dict) else {}
        if isinstance(play.get("innings_order"), list):
            order = [str(item) for item in play.get("innings_order")]
        source = play.get("innings") if isinstance(play.get("innings"), dict) else rows
        if isinstance(source, dict):
            keys = order + [str(key) for key in source.keys() if str(key) not in order]
            for key in keys:
                row = source.get(key)
                if isinstance(row, dict):
                    item = dict(row)
                    item.setdefault("index", key)
                    items.append(item)
            rows = items
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        return []
    innings = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        index = str(row.get("index") or row.get("innings") or len(innings) + 1)
        side = str(row.get("batting_team") or row.get("team") or index).casefold()
        if side.startswith("a") or side in {"home", "team_a"}:
            team = home
        elif side.startswith("b") or side in {"away", "team_b"}:
            team = away
        else:
            team_node = row.get("team") if isinstance(row.get("team"), dict) else {}
            team, _aliases = _team_label(team_node, home if len(innings) % 2 == 0 else away)
        score_obj = row.get("score") if isinstance(row.get("score"), dict) else {}
        runs, wickets = _score_pair(score_obj or row.get("score_str") or row.get("score"))
        if wickets is None:
            wickets = _as_int(row.get("wickets"))
        if runs is None:
            runs = _as_int(row.get("runs"))
        overs = _overs_text(row.get("overs") if row.get("overs") not in (None, "") else score_obj.get("overs"))
        completed = bool(row.get("is_completed") or row.get("completed"))
        batter_rows = (
            row.get("batsmen")
            or row.get("batsman")
            or row.get("batters")
            or row.get("batting")
        )
        innings.append(
            Innings(
                index=index,
                team_name=team or home,
                runs=runs,
                wickets=wickets,
                overs=overs,
                completed=completed,
                batters=_batters(batter_rows),
            )
        )
    return [item for item in innings if item.runs is not None or item.wickets is not None or item.batters]


def _simple_innings(name: str, score, info: str, index: str) -> Innings | None:
    runs, wickets = _score_pair(score)
    if runs is None and wickets is None:
        return None
    return Innings(
        index=index,
        team_name=name,
        runs=runs,
        wickets=wickets,
        overs=_overs_text(info),
    )


def snapshot_from(node) -> Snapshot | None:
    if not isinstance(node, dict):
        return None
    match = node.get("match") if isinstance(node.get("match"), dict) else node
    home_node = (
        _dict_get(match, ("home", "homeTeam"))
        or _dict_get((match.get("teams") if isinstance(match.get("teams"), dict) else {}), ("a", "home", "team_a", "teamA"))
    )
    away_node = (
        _dict_get(match, ("away", "awayTeam"))
        or _dict_get((match.get("teams") if isinstance(match.get("teams"), dict) else {}), ("b", "away", "team_b", "teamB"))
    )
    if home_node is None and isinstance(match.get("teams"), list) and len(match.get("teams")) >= 2:
        home_node, away_node = match["teams"][0], match["teams"][1]
    home, home_aliases = _team_label(home_node, "")
    away, away_aliases = _team_label(away_node, "")
    if not home or not away or home.casefold() in {"team a", "team b"} or away.casefold() in {"team a", "team b"}:
        return None

    status = ""
    state = match.get("state")
    if isinstance(state, dict):
        status = str(state.get("description") or state.get("status") or state.get("name") or "")
    elif state not in (None, ""):
        status = str(state)
    if not status:
        status = str(
            match.get("play_status")
            or match.get("playStatus")
            or match.get("status")
            or match.get("match_status")
            or ""
        )
    phase = _phase(status)

    innings = _innings_from_rows(node.get("statistics"), home, away)
    if not innings:
        innings = _innings_from_rows(match, home, away)
    if not innings:
        state_teams = state.get("teams") if isinstance(state, dict) else {}
        if isinstance(state_teams, dict):
            for side, label, index in (("home", home, "home"), ("away", away, "away")):
                team_state = state_teams.get(side) if isinstance(state_teams.get(side), dict) else {}
                item = _simple_innings(label, team_state.get("score"), str(team_state.get("info") or ""), index)
                if item:
                    innings.append(item)
        for side, label, score_key, info_key, index in (
            ("home", home, "homeScore", "homeInfo", "home"),
            ("away", away, "awayScore", "awayInfo", "away"),
        ):
            if any(item.index == index for item in innings):
                continue
            item = _simple_innings(label, match.get(score_key), str(match.get(info_key) or ""), index)
            if item:
                innings.append(item)

    live = node.get("inplayData") if isinstance(node.get("inplayData"), dict) else {}
    if not live and isinstance(match.get("play"), dict):
        live = match["play"].get("live") if isinstance(match["play"].get("live"), dict) else {}
    extra_batters = _batters(
        [
            live.get("striker"),
            live.get("non_striker"),
            live.get("nonStriker"),
            live.get("current_batsman"),
            live.get("currentBatsman"),
        ]
    )
    players = {batter.name_key for batter in extra_batters}
    for item in innings:
        for batter in item.batters:
            players.add(batter.name_key)
    if extra_batters and innings:
        current = innings[-1]
        known = {batter.name_key for batter in current.batters}
        for batter in extra_batters:
            if batter.name_key not in known:
                current.batters.append(batter)
                known.add(batter.name_key)

    match_key = str(
        match.get("roanuzMatchKey")
        or match.get("key")
        or match.get("match_key")
        or match.get("id")
        or ""
    ).strip()
    if not match_key:
        match_key = f"{name_key(home)}-{name_key(away)}"[:180]

    start_at = _parse_start(match.get("startDate") or match.get("startTime") or match.get("start_at") or match.get("startAt"))
    toss = _toss_text(node if node.get("toss") or (isinstance(node.get("roanuz"), dict) and node["roanuz"].get("toss")) else match, home, away)
    if not toss:
        toss = _toss_text(match, home, away)
    target = _target_runs(node) or _target_runs(match)
    result = _result_text(node, home, away) or _result_text(match, home, away)
    if phase == "unknown" and result:
        phase = "finished"
    return Snapshot(
        match_key=match_key[:180],
        home=home,
        away=away,
        aliases=home_aliases | away_aliases,
        phase=phase,
        toss=toss,
        start_at=start_at,
        target=target,
        innings=innings,
        players=players,
        result=result,
        label=f"{home} vs {away}",
    )


def _score_line(item: Innings) -> str:
    if item.runs is None:
        return item.team_name
    wickets = "" if item.wickets is None else f"/{item.wickets}"
    overs = f" ({item.overs} ov)" if item.overs else ""
    return f"{item.team_name} {item.runs}{wickets}{overs}"


def _lines(title: str, snap: Snapshot, extra: list[str]) -> str:
    rows = [f"{title}", "", f"<b>{safe(snap.home)}</b> vs <b>{safe(snap.away)}</b>"]
    for item in extra:
        cleaned = safe(item)
        if cleaned:
            rows.append(cleaned)
    for item in snap.innings:
        line = safe(_score_line(item))
        if line:
            rows.append(line)
    rows.append("")
    rows.append("DURA score alert")
    return "\n".join(rows)


def _early(snap: Snapshot, now: datetime) -> bool:
    if snap.phase == "upcoming":
        return True
    if snap.phase != "live":
        return False
    runs = sum(item.runs or 0 for item in snap.innings)
    wickets = sum(item.wickets or 0 for item in snap.innings)
    return wickets == 0 and runs < 15


def events_from_snapshot(snap: Snapshot, now: datetime | None = None) -> list[AlertEvent]:
    now = now or datetime.now(timezone.utc)
    events: list[AlertEvent] = []
    if snap.phase != "finished" and _early(snap, now):
        if snap.toss:
            events.append(
                AlertEvent(
                    snap.match_key,
                    "toss",
                    "prestart",
                    _lines("🪙 <b>TOSS</b>", snap, [snap.toss]),
                )
            )
        elif snap.phase == "upcoming" and snap.start_at is not None:
            minutes = (snap.start_at - now).total_seconds() / 60.0
            if 0 <= minutes <= STARTING_SOON_MINUTES:
                events.append(
                    AlertEvent(
                        snap.match_key,
                        "prestart",
                        "prestart",
                        _lines(
                            "⏰ <b>STARTING SOON</b>",
                            snap,
                            [f"About {max(1, int(round(minutes)))} min to the first ball"],
                        ),
                    )
                )

    for item in snap.innings:
        dismissed = [batter for batter in item.batters if batter.dismissed]
        wickets = item.wickets if item.wickets is not None else len(dismissed)
        for number in range(1, wickets + 1):
            batter = dismissed[number - 1] if number <= len(dismissed) else None
            detail = f"Wicket {number}"
            if batter:
                detail = f"Wicket {number}: {batter.name} is out"
            events.append(
                AlertEvent(
                    snap.match_key,
                    f"wicket:{item.index}:{number}",
                    "wicket",
                    _lines("🏏 <b>WICKET</b>", snap, [detail]),
                    (batter.name_key,) if batter else (),
                )
            )
        for batter in item.batters:
            if batter.runs >= 100:
                events.append(
                    AlertEvent(
                        snap.match_key,
                        f"hundred:{item.index}:{batter.name_key}",
                        "milestone",
                        _lines("💯 <b>HUNDRED</b>", snap, [f"{batter.name} {batter.runs}"]),
                        (batter.name_key,),
                    )
                )
            elif batter.runs >= 50:
                events.append(
                    AlertEvent(
                        snap.match_key,
                        f"fifty:{item.index}:{batter.name_key}",
                        "milestone",
                        _lines("🏏 <b>FIFTY</b>", snap, [f"{batter.name} {batter.runs}"]),
                        (batter.name_key,),
                    )
                )

    if snap.phase == "innings_break" and snap.target:
        events.append(
            AlertEvent(
                snap.match_key,
                "innings_break",
                "innings_break",
                _lines("🏏 <b>INNINGS BREAK</b>", snap, [f"Target {snap.target}"]),
            )
        )

    if snap.phase == "live" and snap.target and len(snap.innings) >= 2:
        chase = snap.innings[-1]
        if chase.runs is not None and not chase.completed:
            needed = snap.target - chase.runs
            left = None if chase.wickets is None else 10 - chase.wickets
            close = 0 < needed <= 15 or (left is not None and left <= 2 and 0 < needed <= 30)
            if close:
                events.append(
                    AlertEvent(
                        snap.match_key,
                        "close_finish",
                        "close_finish",
                        _lines(
                            "🔥 <b>CLOSE FINISH</b>",
                            snap,
                            [f"{needed} needed", _score_line(chase)],
                        ),
                    )
                )

    if snap.phase == "finished":
        extra = [snap.result] if snap.result else ["Match completed"]
        events.append(
            AlertEvent(
                snap.match_key,
                "final",
                "final",
                _lines("✅ <b>FINAL</b>", snap, extra),
            )
        )
    return events


def follow(user_id: int, display_name: str, kind: str = "team") -> dict:
    ensure_tables()
    kind = "player" if str(kind).strip().casefold() == "player" else "team"
    display_name = scrub(display_name)[:80]
    key = name_key(display_name)
    if not key:
        return {"ok": False, "error": "Name is empty"}
    now = _now()
    with _DB_LOCK:
        with core.db() as conn:
            conn.execute(
                """
                INSERT INTO dura_team_follows(user_id, kind, name_key, display_name, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, kind, name_key) DO UPDATE SET
                    display_name=excluded.display_name
                """,
                (int(user_id), kind, key, display_name, now),
            )
            conn.execute(
                """
                INSERT INTO dura_alert_catalog(kind, name_key, display_name, last_seen)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(kind, name_key) DO UPDATE SET
                    display_name=excluded.display_name,
                    last_seen=excluded.last_seen
                """,
                (kind, key, display_name, now),
            )
    return {"ok": True, "kind": kind, "name": display_name, "name_key": key}


def unfollow(user_id: int, display_name: str, kind: str | None = None) -> int:
    ensure_tables()
    key = name_key(display_name)
    if not key:
        return 0
    with _DB_LOCK:
        with core.db() as conn:
            if kind:
                kind_name = "player" if kind == "player" else "team"
                cursor = conn.execute(
                    "DELETE FROM dura_team_follows WHERE user_id=? AND kind=? AND name_key=?",
                    (int(user_id), kind_name, key),
                )
            else:
                cursor = conn.execute(
                    "DELETE FROM dura_team_follows WHERE user_id=? AND name_key=?",
                    (int(user_id), key),
                )
            return int(cursor.rowcount or 0)


def list_follows(user_id: int) -> list[dict]:
    ensure_tables()
    with core.db() as conn:
        rows = conn.execute(
            """
            SELECT kind, name_key, display_name
            FROM dura_team_follows
            WHERE user_id=?
            ORDER BY kind, display_name
            """,
            (int(user_id),),
        ).fetchall()
    return [
        {"kind": row["kind"], "name_key": row["name_key"], "display_name": row["display_name"]}
        for row in rows
    ]


def set_pref(user_id: int, pref_key: str, enabled: bool) -> None:
    ensure_tables()
    with _DB_LOCK:
        with core.db() as conn:
            conn.execute(
                """
                INSERT INTO dura_alert_prefs(user_id, pref_key, enabled, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, pref_key) DO UPDATE SET
                    enabled=excluded.enabled,
                    updated_at=excluded.updated_at
                """,
                (int(user_id), pref_key, 1 if enabled else 0, _now()),
            )


def prefs_for(user_id: int) -> dict[str, bool]:
    ensure_tables()
    with core.db() as conn:
        rows = conn.execute(
            "SELECT pref_key, enabled FROM dura_alert_prefs WHERE user_id=?",
            (int(user_id),),
        ).fetchall()
    return {row["pref_key"]: bool(row["enabled"]) for row in rows}


def alert_enabled(user_id: int, alert_type: str, match_key: str, prefs: dict[str, bool] | None = None) -> bool:
    current = prefs if prefs is not None else prefs_for(user_id)
    if current.get(f"match:{match_key}") is False:
        return False
    type_key = f"type:{alert_type}"
    if type_key in current:
        return bool(current[type_key])
    return bool(_TYPE_DEFAULTS.get(alert_type, True))


def mute_match(user_id: int, match_key: str) -> None:
    set_pref(user_id, f"match:{match_key}", False)


def _remember_names(conn, pairs: list[tuple[str, str]]) -> None:
    now = _now()
    for kind, display_name in pairs:
        key = name_key(display_name)
        if not key:
            continue
        conn.execute(
            """
            INSERT INTO dura_alert_catalog(kind, name_key, display_name, last_seen)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(kind, name_key) DO UPDATE SET
                display_name=excluded.display_name,
                last_seen=excluded.last_seen
            """,
            (kind, key, scrub(display_name)[:80], now),
        )


def _remember_match(conn, snap: Snapshot) -> int:
    now = _now()
    conn.execute(
        """
        INSERT INTO dura_alert_matches(match_key, label, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(match_key) DO UPDATE SET
            label=excluded.label,
            updated_at=excluded.updated_at
        """,
        (snap.match_key, scrub(snap.label)[:120], now),
    )
    row = conn.execute(
        "SELECT id FROM dura_alert_matches WHERE match_key=?",
        (snap.match_key,),
    ).fetchone()
    return int(row["id"])


def _followers(conn) -> list:
    return conn.execute(
        "SELECT user_id, kind, name_key FROM dura_team_follows"
    ).fetchall()


def _interested(rows, snap: Snapshot, event: AlertEvent) -> list[int]:
    users = []
    seen = set()
    for row in rows:
        user_id = int(row["user_id"])
        key = str(row["name_key"])
        kind = str(row["kind"])
        matched = False
        if kind == "team" and key in snap.aliases:
            matched = True
        elif kind == "player":
            if event.player_keys:
                matched = key in event.player_keys
            else:
                matched = key in snap.players
        if matched and user_id not in seen:
            seen.add(user_id)
            users.append(user_id)
    return users


def observe_nodes(nodes) -> int:
    """Record new score events from payloads the live feed already has.

    Returns the number of outbox rows created. The first time a match is
    seen, wickets and milestones already on the board are remembered without
    sending, so a restart or a late discovery does not replay the innings.
    """
    if not ENABLED:
        return 0
    ensure_tables()
    queued = 0
    with _DB_LOCK:
        with core.db() as conn:
            follows = _followers(conn)
            pref_rows = conn.execute(
                "SELECT user_id, pref_key, enabled FROM dura_alert_prefs"
            ).fetchall()
            pref_map: dict[int, dict[str, bool]] = {}
            for row in pref_rows:
                pref_map.setdefault(int(row["user_id"]), {})[row["pref_key"]] = bool(row["enabled"])
            now = _now()
            for node in nodes or []:
                snap = snapshot_from(node)
                if snap is None:
                    continue
                names = [("team", snap.home), ("team", snap.away)]
                for item in snap.innings:
                    for batter in item.batters:
                        names.append(("player", batter.name))
                _remember_names(conn, names)
                _remember_match(conn, snap)
                initialized = conn.execute(
                    "SELECT 1 FROM dura_alert_match_init WHERE match_key=?",
                    (snap.match_key,),
                ).fetchone()
                known = {
                    row["event_key"]
                    for row in conn.execute(
                        "SELECT event_key FROM dura_alert_seen WHERE match_key=?",
                        (snap.match_key,),
                    ).fetchall()
                }
                for event in events_from_snapshot(snap):
                    if event.event_key in known:
                        continue
                    conn.execute(
                        """
                        INSERT INTO dura_alert_seen(match_key, event_key, seen_at)
                        VALUES (?, ?, ?)
                        """,
                        (snap.match_key, event.event_key, now),
                    )
                    known.add(event.event_key)
                    if not initialized and event.alert_type in _SILENT_ON_FIRST_SIGHT:
                        continue
                    if _BANNED.search(event.body):
                        logger.warning(
                            "DURA team alert dropped unsafe copy match=%s event=%s",
                            snap.match_key,
                            event.event_key,
                        )
                        continue
                    for user_id in _interested(follows, snap, event):
                        if not alert_enabled(user_id, event.alert_type, snap.match_key, pref_map.get(user_id, {})):
                            continue
                        cursor = conn.execute(
                            """
                            INSERT INTO dura_alert_outbox(
                                user_id, match_key, event_key, body, status, attempts, created_at
                            )
                            VALUES (?, ?, ?, ?, 'queued', 0, ?)
                            ON CONFLICT(user_id, match_key, event_key) DO NOTHING
                            """,
                            (user_id, snap.match_key, event.event_key, event.body, now),
                        )
                        queued += int(cursor.rowcount or 0)
                if not initialized:
                    conn.execute(
                        "INSERT INTO dura_alert_match_init(match_key, initialized_at) VALUES (?, ?)",
                        (snap.match_key, now),
                    )
    return queued


def note_observed(nodes) -> int:
    try:
        return observe_nodes(nodes)
    except Exception:
        logger.exception("DURA team-alert observe failed")
        return 0


def queued_count() -> int:
    ensure_tables()
    with core.db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM dura_alert_outbox WHERE status='queued'"
        ).fetchone()
    return int(row["c"] or 0)


def _mark(conn, row_id: int, status: str) -> None:
    conn.execute(
        """
        UPDATE dura_alert_outbox
        SET status=?, attempts=attempts+1, sent_at=?
        WHERE id=?
        """,
        (status, _now(), int(row_id)),
    )


def _mute_keyboard(match_ids: list[int]) -> InlineKeyboardMarkup | None:
    rows = []
    for match_id in match_ids[:3]:
        rows.append(
            [InlineKeyboardButton("🔕 Mute this match", callback_data=f"durafollow:mm:{int(match_id)}")]
        )
    if not rows:
        return None
    return InlineKeyboardMarkup(rows)


async def _send(bot, user_id: int, text: str, markup) -> None:
    await bot.send_message(
        chat_id=user_id,
        text=text[:4000],
        parse_mode="HTML",
        reply_markup=markup,
        disable_web_page_preview=True,
    )


async def drain_outbox(bot, limit: int | None = None) -> int:
    """Send a batch from the persistent queue. One Telegram call per user."""
    if not ENABLED:
        return 0
    ensure_tables()
    limit = MAX_SENDS_PER_DRAIN if limit is None else int(limit)
    with _DB_LOCK:
        with core.db() as conn:
            rows = conn.execute(
                """
                SELECT id, user_id, match_key, body
                FROM dura_alert_outbox
                WHERE status='queued'
                ORDER BY id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            match_ids = {}
            if rows:
                keys = sorted({row["match_key"] for row in rows})
                found = conn.execute(
                    f"SELECT id, match_key FROM dura_alert_matches WHERE match_key IN ({','.join('?' for _ in keys)})",
                    keys,
                ).fetchall()
                match_ids = {row["match_key"]: int(row["id"]) for row in found}
    if not rows:
        return 0

    grouped: dict[int, list] = {}
    for row in rows:
        grouped.setdefault(int(row["user_id"]), []).append(row)

    sent_users = 0
    for user_id, items in grouped.items():
        bodies = []
        ids = []
        matches = []
        for item in items:
            body = str(item["body"] or "")
            if _BANNED.search(body):
                with _DB_LOCK:
                    with core.db() as conn:
                        _mark(conn, int(item["id"]), "dropped")
                continue
            bodies.append(body)
            ids.append(int(item["id"]))
            match_id = match_ids.get(item["match_key"])
            if match_id and match_id not in matches:
                matches.append(match_id)
        if not bodies:
            continue
        text = "\n\n".join(bodies)[:4000]
        try:
            await _send(bot, user_id, text, _mute_keyboard(matches))
        except RetryAfter as exc:
            delay = exc.retry_after
            seconds = delay.total_seconds() if isinstance(delay, timedelta) else float(delay or 1)
            logger.warning("DURA team alerts paused for Telegram retry_after=%s", seconds)
            await asyncio.sleep(max(1.0, seconds))
            break
        except Forbidden:
            with _DB_LOCK:
                with core.db() as conn:
                    for row_id in ids:
                        _mark(conn, row_id, "blocked")
            continue
        except Exception:
            logger.exception("DURA team alert send failed user=%s", user_id)
            with _DB_LOCK:
                with core.db() as conn:
                    for row_id in ids:
                        conn.execute(
                            "UPDATE dura_alert_outbox SET attempts=attempts+1 WHERE id=?",
                            (row_id,),
                        )
                        row = conn.execute(
                            "SELECT attempts FROM dura_alert_outbox WHERE id=?",
                            (row_id,),
                        ).fetchone()
                        if row and int(row["attempts"] or 0) >= 3:
                            _mark(conn, row_id, "failed")
            continue
        with _DB_LOCK:
            with core.db() as conn:
                for row_id in ids:
                    _mark(conn, row_id, "sent")
        sent_users += 1
        await asyncio.sleep(SEND_GAP_SECONDS)
    return sent_users


async def alert_loop(application) -> None:
    ensure_tables()
    await asyncio.sleep(5)
    while True:
        try:
            sent = await drain_outbox(application.bot)
            if sent:
                logger.info("DURA team alerts delivered users=%s", sent)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("DURA team alert loop failed")
        await asyncio.sleep(2)


def catalog_page(kind: str, page: int) -> tuple[list[dict], int]:
    ensure_tables()
    kind = "player" if kind == "player" else "team"
    page = max(0, int(page))
    with core.db() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS c FROM dura_alert_catalog WHERE kind=?",
            (kind,),
        ).fetchone()["c"]
        rows = conn.execute(
            """
            SELECT id, display_name, name_key
            FROM dura_alert_catalog
            WHERE kind=?
            ORDER BY last_seen DESC, display_name
            LIMIT ? OFFSET ?
            """,
            (kind, PAGE_SIZE, page * PAGE_SIZE),
        ).fetchall()
    return (
        [{"id": int(row["id"]), "display_name": row["display_name"], "name_key": row["name_key"]} for row in rows],
        int(total or 0),
    )


def catalog_row(catalog_id: int) -> dict | None:
    ensure_tables()
    with core.db() as conn:
        row = conn.execute(
            "SELECT id, kind, name_key, display_name FROM dura_alert_catalog WHERE id=?",
            (int(catalog_id),),
        ).fetchone()
    if not row:
        return None
    return {
        "id": int(row["id"]),
        "kind": row["kind"],
        "name_key": row["name_key"],
        "display_name": row["display_name"],
    }


def match_key_for_id(match_id: int) -> str:
    ensure_tables()
    with core.db() as conn:
        row = conn.execute(
            "SELECT match_key FROM dura_alert_matches WHERE id=?",
            (int(match_id),),
        ).fetchone()
    return str(row["match_key"]) if row else ""


def _menu_text(user_id: int) -> str:
    follows = list_follows(user_id)
    if not follows:
        body = "You are not following any team yet.\n\nTap a team below, or send /follow Team Name."
    else:
        lines = ["<b>Your follows</b>"]
        for item in follows:
            prefix = "🏏" if item["kind"] == "team" else "👤"
            lines.append(f"{prefix} {safe(item['display_name'])}")
        body = "\n".join(lines)
    return (
        "⭐ <b>FOLLOW TEAMS</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"{body}\n\n"
        "Alerts are score updates only: toss, wickets, fifties, hundreds, "
        "innings breaks, and the final result."
    )


def menu_markup(user_id: int, kind: str = "team", page: int = 0) -> InlineKeyboardMarkup:
    rows_data, total = catalog_page(kind, page)
    followed = {(item["kind"], item["name_key"]) for item in list_follows(user_id)}
    rows = []
    for item in rows_data:
        marked = (kind, item["name_key"]) in followed
        label = f"{'✓ ' if marked else ''}{item['display_name']}"[:40]
        action = "off" if marked else "on"
        rows.append(
            [InlineKeyboardButton(label, callback_data=f"durafollow:{action}:{int(item['id'])}")]
        )
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"durafollow:{kind}:{page - 1}"))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"durafollow:{kind}:{page + 1}"))
    if nav:
        rows.append(nav)
    other = "player" if kind == "team" else "team"
    other_label = "Players" if other == "player" else "Teams"
    rows.append([InlineKeyboardButton(other_label, callback_data=f"durafollow:{other}:0")])
    rows.append([InlineKeyboardButton("🔔 Alert settings", callback_data="durafollow:settings")])
    return InlineKeyboardMarkup(rows)


def settings_text(user_id: int) -> str:
    current = prefs_for(user_id)
    lines = ["🔔 <b>ALERT SETTINGS</b>", ""]
    for key, label, default in ALERT_TYPES:
        enabled = current.get(f"type:{key}", default)
        lines.append(f"{'✅' if enabled else '🔕'} {label}")
    lines.append("")
    lines.append("Tap a row to turn that alert on or off. Mute a single match from the alert itself.")
    return "\n".join(lines)


def settings_markup(user_id: int) -> InlineKeyboardMarkup:
    current = prefs_for(user_id)
    rows = []
    for key, label, default in ALERT_TYPES:
        enabled = current.get(f"type:{key}", default)
        verb = "Mute" if enabled else "Enable"
        rows.append(
            [InlineKeyboardButton(f"{verb} {label}", callback_data=f"durafollow:pref:{key}")]
        )
    rows.append([InlineKeyboardButton("⬅️ Teams", callback_data="durafollow:team:0")])
    return InlineKeyboardMarkup(rows)


def parse_follow_args(args: list[str]) -> tuple[str, str]:
    parts = [str(part).strip() for part in args if str(part).strip()]
    if parts and parts[0].casefold() in {"player", "players"}:
        return "player", " ".join(parts[1:])
    return "team", " ".join(parts)


async def _guard(update, context) -> bool:
    from bot_tracked import _require_verified

    return await _require_verified(update, context, "follow")


async def follow_command(update, context) -> None:
    if not await _guard(update, context):
        return
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return
    args = list(getattr(context, "args", []) or [])
    kind, name = parse_follow_args(args)
    if not name:
        await message.reply_text(
            _menu_text(user.id),
            parse_mode="HTML",
            reply_markup=menu_markup(user.id, kind),
            disable_web_page_preview=True,
        )
        return
    result = follow(user.id, name, kind)
    if not result.get("ok"):
        await message.reply_text("Send /follow Team Name or /follow player Player Name.")
        return
    noun = "player" if result["kind"] == "player" else "team"
    await message.reply_text(
        f"⭐ Following {noun} <b>{safe(result['name'])}</b>.\n\n"
        "You will get score alerts for their matches. Use /myteams to review or unfollow.",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


async def unfollow_command(update, context) -> None:
    if not await _guard(update, context):
        return
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return
    args = list(getattr(context, "args", []) or [])
    kind, name = parse_follow_args(args)
    if not name:
        await message.reply_text("Send /unfollow Team Name or /unfollow player Player Name.")
        return
    explicit_player = bool(args) and args[0].casefold() in {"player", "players"}
    removed = unfollow(user.id, name, "player" if explicit_player else None)
    if removed:
        await message.reply_text(f"Removed <b>{safe(name)}</b> from your follows.", parse_mode="HTML")
    else:
        await message.reply_text("That follow was not on your list. Use /myteams to see it.")


async def myteams_command(update, context) -> None:
    if not await _guard(update, context):
        return
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return
    await message.reply_text(
        _menu_text(user.id),
        parse_mode="HTML",
        reply_markup=menu_markup(user.id),
        disable_web_page_preview=True,
    )


async def _present(query, text: str, markup=None) -> None:
    try:
        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=markup,
            disable_web_page_preview=True,
        )
    except Exception:
        message = getattr(query, "message", None)
        if message is not None:
            await message.reply_text(
                text,
                parse_mode="HTML",
                reply_markup=markup,
                disable_web_page_preview=True,
            )


async def handle_callback(update, context) -> None:
    query = update.callback_query
    user = update.effective_user
    if not query or not user:
        return
    data = str(query.data or "")
    if not data.startswith("durafollow:"):
        return
    try:
        await query.answer()
    except Exception:
        pass
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else "menu"
    if action in {"team", "player"}:
        page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
        await _present(query, _menu_text(user.id), menu_markup(user.id, action, page))
        return
    if action == "menu":
        await _present(query, _menu_text(user.id), menu_markup(user.id))
        return
    if action in {"on", "off"} and len(parts) > 2 and parts[2].isdigit():
        row = catalog_row(int(parts[2]))
        if row:
            if action == "on":
                follow(user.id, row["display_name"], row["kind"])
            else:
                unfollow(user.id, row["display_name"], row["kind"])
        await _present(
            query,
            _menu_text(user.id),
            menu_markup(user.id, row["kind"] if row else "team"),
        )
        return
    if action == "settings":
        await _present(query, settings_text(user.id), settings_markup(user.id))
        return
    if action == "pref" and len(parts) > 2 and parts[2] in _TYPE_DEFAULTS:
        alert_type = parts[2]
        current = prefs_for(user.id)
        enabled = current.get(f"type:{alert_type}", _TYPE_DEFAULTS[alert_type])
        set_pref(user.id, f"type:{alert_type}", not enabled)
        await _present(query, settings_text(user.id), settings_markup(user.id))
        return
    if action == "mm" and len(parts) > 2 and parts[2].isdigit():
        match_key = match_key_for_id(int(parts[2]))
        if match_key:
            mute_match(user.id, match_key)
            await _present(query, "🔕 This match is muted. Your other follows stay active.")
        return


def install(application) -> None:
    if application.bot_data.get("dura_team_alerts_installed"):
        return
    application.bot_data["dura_team_alerts_installed"] = True
    ensure_tables()
    application.add_handler(CommandHandler("follow", follow_command))
    application.add_handler(CommandHandler("unfollow", unfollow_command))
    application.add_handler(CommandHandler("myteams", myteams_command))
    application.bot_data["dura_team_alert_task"] = asyncio.create_task(
        alert_loop(application),
        name="dura-team-alerts",
    )
    logger.info("DURA follow-a-team alerts installed")
