import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode, urlparse

import bot as core
import ibetin_liveline_trial as liveline
import ibetin_liveline_v21_roanuz_clean_ui as v21
import ibetin_liveline_v20_roanuz_primary_ui as v20
import ibetin_ui_start as ui_start

logger = logging.getLogger(__name__)

liveline.LIVELINE_PATH = "/admin/liveline-ibetinv23"
liveline.LIVELINE_API_PATH = "/admin/liveline-ibetinv23/api"
_BASE_NORMALIZE = v20._normalize_roanuz_match


def _admin_url() -> str:
    root = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/") or "https://ibetin-app-production.up.railway.app"
    return f"{root}{liveline.LIVELINE_PATH}?{urlencode({'t': liveline._token(), 'v': '20260917-v23-stable-feed'})}"


def _overs_text(value) -> str:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return f"{value[0]}.{value[1]} ov"
    if value not in (None, ""):
        text = str(value)
        return text if "ov" in text.lower() else f"{text} ov"
    return ""


def _inning_text(row):
    if not isinstance(row, dict):
        return "", ""
    raw = str(row.get("score_str") or "").strip()
    if raw:
        score = raw.split(" in ", 1)[0].strip()
    else:
        score_obj = row.get("score") if isinstance(row.get("score"), dict) else {}
        runs = score_obj.get("runs")
        if runs is None:
            runs = row.get("runs")
        wickets = row.get("wickets")
        if wickets is None:
            wickets = score_obj.get("wickets")
        score = "" if runs is None else str(runs)
        if score and wickets is not None:
            score += f"/{wickets}"
    overs = row.get("overs")
    if overs in (None, "") and isinstance(row.get("score"), dict):
        overs = row["score"].get("overs")
    return score, _overs_text(overs)


def _apply_play_scores(normalized, node):
    out = dict(normalized or {})
    if not isinstance(node, dict):
        return out
    play = node.get("play") if isinstance(node.get("play"), dict) else {}
    innings = play.get("innings") if isinstance(play.get("innings"), dict) else {}
    order = play.get("innings_order") if isinstance(play.get("innings_order"), list) else []

    def side_score(side: str):
        indexes = [
            str(x)
            for x in order
            if str(x).startswith(side + "_") and isinstance(innings.get(str(x)), dict)
        ]
        if not indexes:
            for idx, row in innings.items():
                if not str(idx).startswith(side + "_") or not isinstance(row, dict):
                    continue
                sc = row.get("score") if isinstance(row.get("score"), dict) else {}
                runs = sc.get("runs")
                balls = sc.get("balls")
                if row.get("is_completed") or (runs not in (None, 0)) or (balls not in (None, 0)):
                    indexes.append(str(idx))
        texts = []
        last_info = ""
        for idx in indexes:
            text, info = _inning_text(innings.get(idx))
            if text:
                texts.append(text)
                last_info = info or last_info
        return " & ".join(texts), last_info

    a_score, a_info = side_score("a")
    b_score, b_info = side_score("b")
    if a_score:
        out["homeScore"] = a_score
        out["homeInfo"] = a_info
    if b_score:
        out["awayScore"] = b_score
        out["awayInfo"] = b_info

    live = play.get("live") if isinstance(play.get("live"), dict) else {}
    live_score = live.get("score") if isinstance(live.get("score"), dict) else {}
    title = str(live_score.get("title") or "").strip()
    batting = str(live.get("batting_team") or "").strip().lower()
    if title:
        side = out.get("home") if batting == "a" else out.get("away") if batting == "b" else {}
        team_name = side.get("name") if isinstance(side, dict) else ""
        out["report"] = f"{team_name} {title}".strip()
    return out


def _normalize_with_play(node):
    return _apply_play_scores(_BASE_NORMALIZE(node), node)


# V23 runtime patch: all Roanuz match-detail normalization understands play.innings.
v20._normalize_roanuz_match = _normalize_with_play


_LIVE_PLAYING_STATES = {
    "live", "in play", "inplay", "playing", "started", "play",
    "in progress", "ongoing", "innings break", "drinks", "lunch", "tea",
}
_LIVE_INTERRUPTION_STATES = {
    "match delayed", "delay", "delayed", "interrupted", "suspended",
    "rain delay", "rain stopped", "rain interruption", "wet outfield",
    "bad light", "weather delay",
}
_LIVE_END_STATES = {
    "stumps", "completed", "complete", "finished", "result", "ended", "closed",
    "abandoned", "cancelled", "canceled", "no result", "postponed",
}
_LIVE_INTERRUPT_WORDS = (
    "rain", "wet outfield", "bad light", "weather delay", "play suspended",
    "match delayed", "play stopped", "interrupted",
)
_TOSS_WORDS = ("won the toss", "toss won", "elected to bat", "elected to bowl", "opted to bat", "opted to bowl")

_ROANUZ_WEBHOOK_MATCHES = {}
_ROANUZ_WEBHOOK_LOCK = threading.RLock()
_ROANUZ_WEBHOOK_TTL = 6 * 60 * 60
_WEBHOOK_SUBSCRIBE_ATTEMPTS = {}
_WEBHOOK_UNSUBSCRIBE_ATTEMPTS = {}
_WEBHOOK_CONFIRMED_KEYS = set()
_WEBHOOK_SUBSCRIBE_LOCK = threading.RLock()
_WEBHOOK_ACCEPTED_COUNT = 0
_WEBHOOK_REST_FALLBACK_COUNT = 0
_WEBHOOK_SUBSCRIBE_OK_COUNT = 0
_WEBHOOK_UNSUBSCRIBE_OK_COUNT = 0
_WEBHOOK_LAST_DISCOVERY = 0.0
_WEBHOOK_DISCOVERY_BUSY = False


def _init_webhook_state_store():
    try:
        with core.db() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS roanuz_webhook_state (
                    match_key TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    terminal INTEGER NOT NULL DEFAULT 0
                )
                """
            )
    except Exception as exc:
        logger.warning("IBETIN webhook state store unavailable: %s", str(exc)[:140])


def _persist_webhook_state(key: str, node, terminal: bool = False):
    if not key or not isinstance(node, dict):
        return
    try:
        payload = json.dumps(node, separators=(",", ":"), ensure_ascii=False)
        with core.db() as conn:
            conn.execute(
                """
                INSERT INTO roanuz_webhook_state(match_key, payload_json, received_at, terminal)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(match_key) DO UPDATE SET
                    payload_json=excluded.payload_json,
                    received_at=excluded.received_at,
                    terminal=excluded.terminal
                """,
                (key, payload, datetime.now(timezone.utc).isoformat(), 1 if terminal else 0),
            )
    except Exception as exc:
        logger.warning("IBETIN webhook state persist failed key=%s: %s", key, str(exc)[:120])


def _restore_webhook_state():
    restored = 0
    try:
        with core.db() as conn:
            rows = conn.execute(
                "SELECT match_key, payload_json, received_at, terminal FROM roanuz_webhook_state WHERE terminal = 0"
            ).fetchall()
        now_wall = datetime.now(timezone.utc)
        for row in rows:
            try:
                received = datetime.fromisoformat(str(row["received_at"]).replace("Z", "+00:00"))
                if received.tzinfo is None:
                    received = received.replace(tzinfo=timezone.utc)
                age = (now_wall - received.astimezone(timezone.utc)).total_seconds()
                if age < 0 or age > _ROANUZ_WEBHOOK_TTL:
                    continue
                node = json.loads(row["payload_json"])
                if not isinstance(node, dict):
                    continue
                key = str(row["match_key"] or "")
                with _ROANUZ_WEBHOOK_LOCK:
                    _ROANUZ_WEBHOOK_MATCHES[key] = (time.monotonic() - age, node)
                restored += 1
            except Exception:
                continue
    except Exception as exc:
        logger.warning("IBETIN webhook state restore unavailable: %s", str(exc)[:140])
    logger.info("IBETIN webhook state restore rows=%s", restored)


def _is_terminal_webhook_match(node) -> bool:
    state = _live_state(node)
    text = _match_text(node)
    # Stumps is intentionally NOT terminal for subscription lifecycle.
    return (
        state in {"completed", "complete", "finished", "result", "ended", "closed", "abandoned", "cancelled", "canceled", "no result", "postponed"}
        or any(x in text for x in ("match completed", "match abandoned", "match cancelled", "match canceled", "no result"))
    )


def _webhook_health_snapshot():
    with _ROANUZ_WEBHOOK_LOCK:
        cache_count = len(_ROANUZ_WEBHOOK_MATCHES)
    return {
        "cachedMatches": cache_count,
        "acceptedPushes": _WEBHOOK_ACCEPTED_COUNT,
        "restFallbacks": _WEBHOOK_REST_FALLBACK_COUNT,
        "subscriptionsOk": _WEBHOOK_SUBSCRIBE_OK_COUNT,
        "confirmedSubscriptions": len(_WEBHOOK_CONFIRMED_KEYS),
        "unsubscriptionsOk": _WEBHOOK_UNSUBSCRIBE_OK_COUNT,
    }


def _roanuz_subscription_error_code(response) -> str:
    try:
        payload = response.json()
    except Exception:
        return ""

    found = ""

    def walk(value):
        nonlocal found
        if found:
            return
        if isinstance(value, dict):
            for k, v in value.items():
                lk = str(k).lower()
                if lk in {"code", "error_code", "errorcode"} and isinstance(v, str) and v.startswith("P-"):
                    found = v.strip()
                    return
                walk(v)
                if found:
                    return
        elif isinstance(value, list):
            for child in value:
                walk(child)
                if found:
                    return

    walk(payload)
    return found


def _unsubscribe_webhook_key(key: str):
    global _WEBHOOK_UNSUBSCRIBE_OK_COUNT
    key = str(key or "").strip()
    if not key:
        return
    try:
        project = os.getenv("ROANUZ_PROJECT_KEY", "").strip()
        if not project:
            return
        token = v20.admin._roanuz_auth()
        url = f"https://api.sports.roanuz.com/v5/cricket/{project}/match/{key}/unsubscribe/"
        with v20.admin.httpx.Client(timeout=12.0, follow_redirects=True) as client:
            response = client.post(
                url,
                headers={"rs-token": token, "Accept": "application/json"},
                json={"method": "web_hook"},
            )
        if 200 <= response.status_code < 300:
            _WEBHOOK_UNSUBSCRIBE_OK_COUNT += 1
            logger.info("IBETIN Roanuz webhook unsubscribe OK key=%s http=%s", key, response.status_code)
        else:
            logger.warning("IBETIN Roanuz webhook unsubscribe pending key=%s http=%s", key, response.status_code)
    except Exception as exc:
        logger.warning("IBETIN Roanuz webhook unsubscribe failed key=%s: %s", key, str(exc)[:140])


def _schedule_webhook_unsubscribe(key: str):
    key = str(key or "").strip()
    if not key:
        return
    now = time.monotonic()
    with _WEBHOOK_SUBSCRIBE_LOCK:
        last = _WEBHOOK_UNSUBSCRIBE_ATTEMPTS.get(key, 0)
        if now - last < 10 * 60:
            return
        _WEBHOOK_UNSUBSCRIBE_ATTEMPTS[key] = now
    threading.Thread(
        target=_unsubscribe_webhook_key,
        args=(key,),
        daemon=True,
        name=f"ibetin-roanuz-webhook-unsub-{key[-10:]}",
    ).start()


def _subscribe_webhook_key(key: str):
    global _WEBHOOK_SUBSCRIBE_OK_COUNT
    key = str(key or "").strip()
    if not key:
        return
    try:
        project = os.getenv("ROANUZ_PROJECT_KEY", "").strip()
        if not project:
            return
        token = v20.admin._roanuz_auth()
        url = f"https://api.sports.roanuz.com/v5/cricket/{project}/match/{key}/subscribe/"
        with v20.admin.httpx.Client(timeout=12.0, follow_redirects=True) as client:
            response = client.post(
                url,
                headers={"rs-token": token, "Accept": "application/json"},
                json={"method": "web_hook"},
            )
        error_code = _roanuz_subscription_error_code(response)
        if 200 <= response.status_code < 300 or (response.status_code == 400 and error_code == "P-400-4"):
            _WEBHOOK_SUBSCRIBE_OK_COUNT += 1
            with _WEBHOOK_SUBSCRIBE_LOCK:
                _WEBHOOK_CONFIRMED_KEYS.add(key)
            if error_code == "P-400-4":
                logger.info("IBETIN Roanuz webhook subscription already active key=%s code=%s", key, error_code)
            else:
                logger.info("IBETIN Roanuz webhook subscription OK key=%s http=%s", key, response.status_code)
        else:
            logger.warning(
                "IBETIN Roanuz webhook subscription pending key=%s http=%s code=%s",
                key,
                response.status_code,
                error_code or "unknown",
            )
    except Exception as exc:
        logger.warning("IBETIN Roanuz webhook subscription failed key=%s: %s", key, str(exc)[:140])


def _schedule_webhook_subscription(key: str):
    key = str(key or "").strip()
    if not key:
        return
    now = time.monotonic()
    with _WEBHOOK_SUBSCRIBE_LOCK:
        if key in _WEBHOOK_CONFIRMED_KEYS:
            return
        last = _WEBHOOK_SUBSCRIBE_ATTEMPTS.get(key, 0)
        if now - last < 10 * 60:
            return
        _WEBHOOK_SUBSCRIBE_ATTEMPTS[key] = now
    threading.Thread(
        target=_subscribe_webhook_key,
        args=(key,),
        daemon=True,
        name=f"ibetin-roanuz-webhook-sub-{key[-10:]}",
    ).start()


def _webhook_candidate(node):
    best = None
    best_score = -1

    def walk(value):
        nonlocal best, best_score
        if isinstance(value, dict):
            key = v20._match_key(value)
            if key:
                score = 0
                if isinstance(value.get("teams"), (dict, list)):
                    score += 3
                if isinstance(value.get("play"), dict):
                    score += 4
                if value.get("toss") not in (None, "", {}, []):
                    score += 2
                if v20._status(value):
                    score += 1
                if score > best_score:
                    best, best_score = value, score
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(node)
    return best if isinstance(best, dict) else None


def _accept_roanuz_webhook(payload):
    global _WEBHOOK_ACCEPTED_COUNT
    node = _webhook_candidate(payload)
    if not node:
        return ""
    key = v20._match_key(node)
    if not key:
        return ""
    terminal = _is_terminal_webhook_match(node)
    with _ROANUZ_WEBHOOK_LOCK:
        if terminal:
            _ROANUZ_WEBHOOK_MATCHES.pop(key, None)
        else:
            _ROANUZ_WEBHOOK_MATCHES[key] = (time.monotonic(), node)
    _WEBHOOK_ACCEPTED_COUNT += 1
    with _WEBHOOK_SUBSCRIBE_LOCK:
        if terminal:
            _WEBHOOK_CONFIRMED_KEYS.discard(key)
        else:
            _WEBHOOK_CONFIRMED_KEYS.add(key)
    _persist_webhook_state(key, node, terminal=terminal)
    if terminal:
        _schedule_webhook_unsubscribe(key)
    logger.info(
        "IBETIN Roanuz webhook cached key=%s state=%s toss=%s terminal=%s",
        key,
        _norm_live_state(v20._status(node)),
        _toss_done(node),
        terminal,
    )
    return key


def _webhook_raw(key: str):
    key = str(key or "").strip()
    if not key:
        return None
    with _ROANUZ_WEBHOOK_LOCK:
        item = _ROANUZ_WEBHOOK_MATCHES.get(key)
    if not item:
        return None
    ts, node = item
    if time.monotonic() - ts > _ROANUZ_WEBHOOK_TTL:
        with _ROANUZ_WEBHOOK_LOCK:
            _ROANUZ_WEBHOOK_MATCHES.pop(key, None)
        return None
    return node if isinstance(node, dict) else None


def _webhook_live_rows():
    now = time.monotonic()
    rows = []
    stale = []
    with _ROANUZ_WEBHOOK_LOCK:
        items = list(_ROANUZ_WEBHOOK_MATCHES.items())
    for key, (ts, node) in items:
        if now - ts > _ROANUZ_WEBHOOK_TTL:
            stale.append(key)
            continue
        if isinstance(node, dict) and _is_live_coverage_match(node):
            rows.append(node)
    if stale:
        with _ROANUZ_WEBHOOK_LOCK:
            for key in stale:
                _ROANUZ_WEBHOOK_MATCHES.pop(key, None)
    return rows


def _team_name_for_toss(match, winner):
    if isinstance(winner, dict):
        return str(winner.get("name") or winner.get("short_name") or winner.get("shortName") or "").strip()
    winner = str(winner or "").strip()
    if not winner or not isinstance(match, dict):
        return winner
    teams = match.get("teams")
    candidates = []
    if isinstance(teams, dict):
        candidates = list(teams.items())
    elif isinstance(teams, list):
        candidates = [(str(i), t) for i, t in enumerate(teams)]
    for slot, team in candidates:
        if not isinstance(team, dict):
            continue
        ids = {
            str(slot),
            str(team.get("key") or ""),
            str(team.get("id") or ""),
            str(team.get("code") or ""),
            str(team.get("short_name") or team.get("shortName") or ""),
        }
        if winner in ids:
            return str(team.get("name") or team.get("short_name") or team.get("shortName") or winner).strip()
    return winner


def _toss_display(match) -> str:
    if not isinstance(match, dict):
        return ""
    toss = match.get("toss")
    if isinstance(toss, dict):
        winner = (
            toss.get("winner")
            or toss.get("team")
            or toss.get("won_by")
            or toss.get("wonBy")
            or toss.get("winner_key")
            or toss.get("winnerKey")
        )
        decision = (
            toss.get("decision")
            or toss.get("choice")
            or toss.get("elected")
            or toss.get("opted")
        )
        winner_name = _team_name_for_toss(match, winner)
        decision_text = str(decision or "").strip().lower()
        if winner_name and decision_text:
            return f"{winner_name} won the toss · chose to {decision_text}"
        if winner_name:
            return f"{winner_name} won the toss · awaiting first ball"
        if decision_text:
            return f"Toss completed · chose to {decision_text} · awaiting first ball"
    if _toss_done(match):
        return "Toss completed · awaiting first ball"
    return ""


def _normalize_live_row(raw):
    match = v20._normalize_roanuz_match(raw)
    if not isinstance(match, dict):
        return {}
    if _toss_done(raw) and not _match_has_score(raw):
        match["liveStage"] = "toss"
        toss_text = _toss_display(raw)
        current = str(match.get("report") or "").strip().casefold().replace("_", " ")
        if toss_text and current in ("", "pre match", "pre-match", "pre_match", "scheduled", "upcoming"):
            match["report"] = toss_text
    return match


def _norm_live_state(value) -> str:
    value = str(value or "").strip().casefold().replace("_", " ").replace("-", " ")
    return " ".join(value.split())


def _deep_has_toss(node) -> bool:
    if isinstance(node, list):
        return any(_deep_has_toss(value) for value in node)
    if not isinstance(node, dict):
        return False
    for key in ("toss", "toss_winner", "tossWinner", "toss_result", "tossResult"):
        value = node.get(key)
        if value not in (None, "", {}, []):
            if isinstance(value, dict):
                winner = value.get("winner") or value.get("team") or value.get("won") or value.get("decision")
                if winner not in (None, "", {}, []):
                    return True
                if any(v not in (None, "", {}, []) for v in value.values()):
                    return True
            else:
                return True
    return any(_deep_has_toss(value) for value in node.values() if isinstance(value, (dict, list)))


def _match_text(match) -> str:
    if not isinstance(match, dict):
        return ""
    parts = []
    for key in ("report", "state", "status", "matchStatus", "match_status", "status_note", "statusNote", "note", "result"):
        value = match.get(key)
        if value not in (None, "", {}, []):
            parts.append(str(value))
    return " ".join(parts).casefold()


def _match_has_score(match) -> bool:
    if not isinstance(match, dict):
        return False
    for key in ("homeScore", "awayScore", "score", "runs", "overs", "over"):
        value = match.get(key)
        if value not in (None, "", {}, []):
            text = str(value).strip()
            if text and text not in {"0", "0/0", "0.0", "-"}:
                return True
    teams = match.get("teams")
    if isinstance(teams, dict):
        for team in teams.values():
            if isinstance(team, dict):
                for key in ("score", "runs", "overs", "over"):
                    value = team.get(key)
                    if value not in (None, "", {}, []):
                        text = str(value).strip()
                        if text and text not in {"0", "0/0", "0.0", "-"}:
                            return True
    return False


def _toss_done(match) -> bool:
    if _deep_has_toss(match):
        return True
    text = _match_text(match)
    return any(word in text for word in _TOSS_WORDS)


def _live_state(match) -> str:
    if not isinstance(match, dict):
        return ""
    raw = (
        match.get("state")
        or match.get("status")
        or match.get("matchStatus")
        or match.get("match_status")
        or ""
    )
    return _norm_live_state(raw)


def _is_live_coverage_match(match) -> bool:
    """LIVE starts at toss and survives temporary interruptions, but not stumps/end states."""
    if not isinstance(match, dict):
        return False
    state = _live_state(match)
    text = _match_text(match)

    if state in _LIVE_END_STATES or any(
        end in text for end in ("stumps", "match abandoned", "match cancelled", "match canceled", "no result", "match completed")
    ):
        return False

    toss = _toss_done(match)
    started = toss or _match_has_score(match) or state in _LIVE_PLAYING_STATES

    if state in _LIVE_PLAYING_STATES:
        return True
    if toss:
        return True

    interruption = state in _LIVE_INTERRUPTION_STATES or any(word in text for word in _LIVE_INTERRUPT_WORDS)
    if interruption and started:
        return True

    return False


def _parse_match_start_for_live(match):
    if not isinstance(match, dict):
        return None
    value = (
        match.get("startTime")
        or match.get("startDate")
        or match.get("start_at")
        or match.get("startAt")
        or match.get("start_time")
        or match.get("scheduled_at")
    )
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().isdigit()):
            num = float(value)
            if num < 1000000000000:
                return datetime.fromtimestamp(num, tz=timezone.utc).astimezone(liveline.DUBAI_TZ)
            return datetime.fromtimestamp(num / 1000.0, tz=timezone.utc).astimezone(liveline.DUBAI_TZ)
        text = str(value).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=liveline.DUBAI_TZ)
        return dt.astimezone(liveline.DUBAI_TZ)
    except Exception:
        return None


def _raw_fallback_detail(match_id: str):
    data = liveline._highlightly(f"/cricket/matches/{match_id}", ttl=30)
    raw = data[0] if isinstance(data, list) and data else data
    return raw if isinstance(raw, dict) else {}


def _fallback_live_candidates():
    """Use raw Highlightly records so toss/report fields are not lost in normalization."""
    today = datetime.now(liveline.DUBAI_TZ).date().isoformat()
    raw_today = liveline._matches_for_date(today)
    if not isinstance(raw_today, list):
        return []

    selected = [m for m in raw_today if isinstance(m, dict) and _is_live_coverage_match(m)]
    if selected:
        return selected

    # Some list responses omit toss details. Near the scheduled start, inspect a
    # small number of detail records; shared provider caching prevents duplicate calls.
    now = datetime.now(liveline.DUBAI_TZ)
    near = []
    for match in raw_today:
        if not isinstance(match, dict):
            continue
        state = _live_state(match)
        if state in _LIVE_END_STATES:
            continue
        start = _parse_match_start_for_live(match)
        if start is None:
            continue
        delta = (start - now).total_seconds()
        if -4 * 3600 <= delta <= 75 * 60:
            near.append((abs(delta), match))
    near.sort(key=lambda item: item[0])

    checked = []
    for _distance, match in near[:6]:
        match_id = str(match.get("id") or "")
        if not match_id.isdigit():
            continue
        try:
            detail_raw = _raw_fallback_detail(match_id)
            if detail_raw and _is_live_coverage_match(detail_raw):
                checked.append(detail_raw)
                logger.info(
                    "IBETIN V23 toss/detail live promotion id=%s %s vs %s state=%s",
                    match_id,
                    (detail_raw.get("homeTeam") or {}).get("name") if isinstance(detail_raw.get("homeTeam"), dict) else "",
                    (detail_raw.get("awayTeam") or {}).get("name") if isinstance(detail_raw.get("awayTeam"), dict) else "",
                    _live_state(detail_raw),
                )
        except Exception as exc:
            logger.warning("IBETIN V23 toss detail check failed id=%s: %s", match_id, str(exc)[:120])
    return checked


def _dedupe_matches(rows):
    out, seen = [], set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        key = str(row.get("roanuzMatchKey") or row.get("id") or row.get("key") or "")
        marker = key or repr((row.get("home"), row.get("away"), row.get("startTime")))
        if marker in seen:
            continue
        seen.add(marker)
        out.append(row)
    return out


def _roanuz_toss_promotions():
    """Promote near-start Roanuz fixture matches into LIVE once toss is confirmed."""
    try:
        fixtures = v20._roanuz_fixtures_raw()
    except Exception as exc:
        logger.warning("IBETIN V23 Roanuz fixture toss scan unavailable: %s", str(exc)[:140])
        return []

    now = datetime.now(liveline.DUBAI_TZ)
    near = []
    for raw in fixtures or []:
        if not isinstance(raw, dict):
            continue
        state = _norm_live_state(v20._status(raw))
        if state in _LIVE_END_STATES:
            continue
        start = _parse_match_start_for_live(raw)
        if start is None:
            # Raw Roanuz start field may use provider-specific names.
            try:
                raw_start = v20._start_time(raw)
                probe = {"startTime": raw_start}
                start = _parse_match_start_for_live(probe)
            except Exception:
                start = None
        if start is None:
            continue
        delta = (start - now).total_seconds()
        if -4 * 3600 <= delta <= 90 * 60:
            near.append((abs(delta), raw))

    near.sort(key=lambda item: item[0])
    promoted = []
    for _distance, raw in near[:8]:
        key = v20._match_key(raw)
        if not key:
            continue
        # Subscribe before toss so the webhook can deliver the toss transition.
        _schedule_webhook_subscription(key)

        # List-level toss/status may already be enough.
        if _is_live_coverage_match(raw):
            promoted.append(raw)
            logger.info(
                "IBETIN V23 Roanuz toss promotion from fixture key=%s %s vs %s state=%s",
                key,
                (v20._normalize_roanuz_match(raw).get("home") or {}).get("name"),
                (v20._normalize_roanuz_match(raw).get("away") or {}).get("name"),
                _norm_live_state(v20._status(raw)),
            )
            continue

        # Otherwise inspect match detail because fixtures can lag on toss.
        try:
            payload = v20.admin._roanuz_get(f"match/{key}/", ttl=20)
            detail = v20._find_match_dict(payload, key)
            if isinstance(detail, dict) and _is_live_coverage_match(detail):
                promoted.append(detail)
                nm = v20._normalize_roanuz_match(detail)
                logger.info(
                    "IBETIN V23 Roanuz toss/detail promotion key=%s %s vs %s state=%s",
                    key,
                    (nm.get("home") or {}).get("name"),
                    (nm.get("away") or {}).get("name"),
                    _norm_live_state(v20._status(detail)),
                )
        except Exception as exc:
            logger.warning("IBETIN V23 Roanuz toss detail check failed key=%s: %s", key, str(exc)[:120])

    return _dedupe_matches(promoted)


def _background_live_discovery():
    global _WEBHOOK_LAST_DISCOVERY, _WEBHOOK_DISCOVERY_BUSY
    try:
        raw = v20._roanuz_featured_raw()
        featured_live = [x for x in raw if isinstance(x, dict) and _is_live_coverage_match(x)]
        for item in featured_live:
            _schedule_webhook_subscription(v20._match_key(item))
        # Also scans near-start fixtures and subscribes them before toss.
        _roanuz_toss_promotions()
    except Exception as exc:
        logger.warning("IBETIN webhook discovery refresh failed: %s", str(exc)[:140])
    finally:
        _WEBHOOK_LAST_DISCOVERY = time.monotonic()
        _WEBHOOK_DISCOVERY_BUSY = False


def _schedule_live_discovery(force: bool = False):
    global _WEBHOOK_DISCOVERY_BUSY
    due = force or (time.monotonic() - _WEBHOOK_LAST_DISCOVERY > 45)
    if not due or _WEBHOOK_DISCOVERY_BUSY:
        return
    _WEBHOOK_DISCOVERY_BUSY = True
    threading.Thread(
        target=_background_live_discovery,
        daemon=True,
        name="ibetin-roanuz-live-discovery",
    ).start()


def _fast_matches(mode: str):
    source = "Roanuz V5 primary"

    if mode == "live":
        pushed = _webhook_live_rows()
        if pushed:
            _schedule_live_discovery()
            live = [
                m for m in (_normalize_live_row(x) for x in pushed)
                if v21._display_ok(m)
            ]
            if live:
                logger.info("IBETIN V23 live coverage feed source=Roanuz webhook matches=%s", len(live))
                return live[:40], "Roanuz webhook"
        global _WEBHOOK_REST_FALLBACK_COUNT
        _WEBHOOK_REST_FALLBACK_COUNT += 1
        try:
            raw = v20._roanuz_featured_raw()
            selected_raw = _webhook_live_rows()
            featured_live = [x for x in raw if isinstance(x, dict) and _is_live_coverage_match(x)]
            for item in featured_live:
                _schedule_webhook_subscription(v20._match_key(item))
            selected_raw.extend(featured_live)
            selected_raw.extend(_roanuz_toss_promotions())
            selected_raw = _dedupe_matches(selected_raw)
            live = [
                m for m in (_normalize_live_row(x) for x in selected_raw)
                if v21._display_ok(m)
            ]
            if live:
                logger.info(
                    "IBETIN V23 live coverage feed source=Roanuz matches=%s first=%s vs %s",
                    len(live),
                    live[0].get("home", {}).get("name"),
                    live[0].get("away", {}).get("name"),
                )
                return live[:40], source
        except Exception as exc:
            logger.warning("IBETIN V23 Roanuz live coverage list failed: %s", str(exc)[:160])

        try:
            raw_live = _fallback_live_candidates()
            live = [
                m for m in (liveline._normalize_match(x) for x in raw_live)
                if v21._display_ok(m)
            ]
            logger.warning(
                "IBETIN V23 live coverage fallback raw_active_or_tossed=%s display=%s",
                len(raw_live),
                len(live),
            )
            if live:
                return live[:40], "Highlightly display fallback"
            logger.info("IBETIN V23 live coverage fallback has no live/tossed matches")
        except Exception as exc:
            logger.warning("IBETIN V23 live coverage fallback failed: %s", str(exc)[:160])
        return [], source

    try:
        rows = v20._roanuz_matches_mode(mode)
    except Exception as exc:
        logger.warning("IBETIN V23 Roanuz %s list failed: %s", mode, str(exc)[:160])
        rows = []

    valid = [m for m in rows if v21._display_ok(m)]
    if valid:
        logger.info(
            "IBETIN V23 feed mode=%s source=Roanuz matches=%s first=%s vs %s",
            mode,
            len(valid),
            valid[0].get("home", {}).get("name"),
            valid[0].get("away", {}).get("name"),
        )
        return valid[:40], source

    try:
        fallback = v20._OLD_MATCHES_MODE(mode)
        if fallback:
            logger.warning("IBETIN V23 display fallback mode=%s matches=%s", mode, len(fallback))
            return fallback[:40], "Highlightly display fallback"
    except Exception as exc:
        logger.warning("IBETIN V23 fallback failed mode=%s: %s", mode, str(exc)[:160])
    return [], source


def _match_payload(key: str):
    if not v21._valid_key(key):
        raise ValueError("Invalid match key")
    pushed = _webhook_raw(key)
    if isinstance(pushed, dict):
        return {"source": "Roanuz webhook", "match": pushed}, pushed
    payload = v20.admin._roanuz_get(f"match/{key}/", ttl=15)
    node = v20._find_match_dict(payload, key)
    if not isinstance(node, dict):
        node = {}
    return payload, node


def _fallback_detail_v23(key: str):
    """Normalize the pre-Roanuz provider detail into the stable V23 contract."""
    result = v20._OLD_MATCH_DETAIL(str(key))
    if isinstance(result, tuple) and result:
        result = result[0]
    if not isinstance(result, dict):
        raise RuntimeError("Fallback match detail unavailable")
    detail = dict(result)
    match = detail.get("match")
    if not isinstance(match, dict):
        match = {"id": str(key)}
        detail["match"] = match
    else:
        match = dict(match)
        match.setdefault("id", str(key))
        # Do not label a numeric fallback id as a Roanuz key.
        if str(match.get("roanuzMatchKey") or "").isdigit():
            match.pop("roanuzMatchKey", None)
        detail["match"] = match
    for name in ("statistics", "squad", "bestBatsmen", "bestBowlers", "timeline"):
        if not isinstance(detail.get(name), list):
            detail[name] = []
    if not isinstance(detail.get("venue"), dict):
        detail["venue"] = {}
    if not isinstance(detail.get("inplayData"), dict):
        detail["inplayData"] = {}
    detail.setdefault("forecast", {})
    detail["fallback"] = {"provider": "Highlightly", "matchId": str(key)}
    return detail


def _score_summary(key: str):
    key = str(key or "").strip()
    if key.isdigit():
        detail = _fallback_detail_v23(key)
        match = detail.get("match") if isinstance(detail, dict) else None
        return match if isinstance(match, dict) else {"id": key}
    _payload, node = _match_payload(key)
    normalized = v20._normalize_roanuz_match(node)
    if not normalized.get("id"):
        normalized["id"] = key
        normalized["roanuzMatchKey"] = key
    return normalized


def _ordered_innings(node):
    play = node.get("play") if isinstance(node, dict) and isinstance(node.get("play"), dict) else {}
    innings = play.get("innings") if isinstance(play.get("innings"), dict) else {}
    order = play.get("innings_order") if isinstance(play.get("innings_order"), list) else []
    rows = []
    seen = set()
    for idx in order:
        idx = str(idx)
        row = innings.get(idx)
        if isinstance(row, dict):
            item = dict(row)
            item.setdefault("index", idx)
            rows.append(item)
            seen.add(idx)
    for idx, row in innings.items():
        idx = str(idx)
        if idx in seen or not isinstance(row, dict):
            continue
        item = dict(row)
        item.setdefault("index", idx)
        rows.append(item)
    return rows


_TAG_RE = re.compile(r"<[^>]+>")


def _embedded_timeline(node):
    play = node.get("play") if isinstance(node, dict) and isinstance(node.get("play"), dict) else {}
    related = play.get("related_balls")
    if not isinstance(related, (dict, list)):
        related = node.get("related_balls") if isinstance(node, dict) else None
    if isinstance(related, dict):
        values = list(related.values())
    elif isinstance(related, list):
        values = related
    else:
        values = []

    rows = []
    for ball in values:
        if not isinstance(ball, dict):
            continue
        overs = ball.get("overs")
        if isinstance(overs, (list, tuple)) and len(overs) >= 2:
            ball_label = f"{overs[0]}.{overs[1]}"
        else:
            ball_label = str(
                ball.get("over_str")
                or ball.get("overStr")
                or ball.get("ball")
                or ball.get("over")
                or ""
            )
        comment = str(
            ball.get("comment")
            or ball.get("commentary")
            or ball.get("description")
            or ball.get("text")
            or ""
        )
        comment = _TAG_RE.sub("", comment).strip()
        display_score = str(ball.get("display_score") or "").strip()
        if display_score and display_score not in comment:
            comment = f"{comment} · {display_score}".strip(" ·")
        try:
            sort_value = float(ball.get("updated_time") or ball.get("entry_time") or 0)
        except (TypeError, ValueError):
            sort_value = 0.0
        rows.append({"ball": ball_label, "commentary": comment, "_sort": sort_value})
    rows.sort(key=lambda x: x.get("_sort", 0))
    for row in rows:
        row.pop("_sort", None)
    return rows[-240:]


def _match_detail_v23(key: str):
    key = str(key or "").strip()
    if key.isdigit():
        return _fallback_detail_v23(key)
    _payload, node = _match_payload(key)
    normalized = v20._normalize_roanuz_match(node)
    if not normalized.get("id"):
        normalized["id"] = key
        normalized["roanuzMatchKey"] = key

    play = node.get("play") if isinstance(node.get("play"), dict) else {}
    live = play.get("live") if isinstance(play.get("live"), dict) else {}
    live_score = live.get("score") if isinstance(live.get("score"), dict) else {}
    venue = node.get("venue") if isinstance(node.get("venue"), dict) else {}

    return {
        "match": normalized,
        "venue": venue,
        "forecast": {},
        "statistics": _ordered_innings(node),
        "squad": [],
        "bestBatsmen": [],
        "bestBowlers": [],
        "inplayData": live,
        # Roanuz already includes recent delivery objects in match/{key}/.
        # Use them instead of the separate ball-by-ball endpoint, which returns
        # HTTP 400 for some currently live matches.
        "timeline": _embedded_timeline(node),
        "roanuz": {
            "matchKey": key,
            "source": "Roanuz V5 primary",
            "target": play.get("target"),
            "runRate": live_score.get("run_rate"),
            "toss": node.get("toss"),
            "winner": node.get("winner"),
        },
    }


v21._matches = _fast_matches
v21._match_detail = _match_detail_v23


def _api(handler):
    q = parse_qs(urlparse(handler.path).query)
    action = (q.get("action") or ["matches"])[0].strip().lower()
    key = (q.get("matchId") or q.get("id") or q.get("key") or [""])[0].strip()

    if action == "score":
        try:
            match = _score_summary(key)
            liveline._send_json(
                handler,
                200,
                {
                    "ok": True,
                    "source": "Roanuz V5 live score",
                    "generatedAt": datetime.now(timezone.utc).isoformat(),
                    "match": match,
                },
            )
        except ValueError as exc:
            liveline._send_json(handler, 400, {"ok": False, "error": str(exc)})
        except Exception as exc:
            logger.warning("IBETIN V23 score hydrate failed key=%s: %s", key, str(exc)[:160])
            liveline._send_json(
                handler,
                200,
                {"ok": True, "source": "score pending", "match": {"id": key}},
            )
        return

    return v21._api(handler)


def _page() -> str:
    html = v21._page()
    html = html.replace("/admin/liveline-ibetinv21/api", liveline.LIVELINE_API_PATH)
    html = html.replace("V21 · ROANUZ", "V23 · STABLE")
    html = html.replace("20260917-v21-clean-roanuz", "20260917-v23-stable-feed")

    # Home list: hydrate live scores only. BHAV stays on-demand in match detail.
    html = html.replace(
        "if(mode==='live')rows.slice(0,8).forEach(loadCardBhav)",
        "if(mode==='live')rows.slice(0,8).forEach(hydrateScore)",
    )

    # Readability and Telegram mobile safe-area polish.
    ui_css = r"""
.bhav{display:none!important}
body{padding-bottom:calc(84px + env(safe-area-inset-bottom))}
.brand span{font-size:9px}.v{font-size:9px}.tab{font-size:11px}
.hero small{font-size:8px}.hero p{font-size:10px;line-height:1.4}
.pill{font-size:8px}.status{font-size:9px}.league{font-size:10px}
.fmt{font-size:8px}.badge{font-size:8px}.ta,.si{font-size:8px}
.foot{font-size:9px;line-height:1.35}.bottom{bottom:max(8px,env(safe-area-inset-bottom))}
.bottom button{font-size:8px}.ptitle b{font-size:11px}.notice{font-size:10px}
.table{font-size:9px}.ball{font-size:9px}.graph{font-size:9px}
.scorecardRow strong{font-size:17px;color:#083f7f}
"""
    html = html.replace(
        "</style></head>",
        ui_css + '</style><link rel="icon" href="data:"></head>',
        1,
    )

    # Roanuz start_at is an epoch in seconds. Native JS Date expects ms.
    old_fmt = "function fmtTime(v){if(!v)return'';try{return new Date(v).toLocaleString([],{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})}catch(e){return String(v)}}"
    new_fmt = r"function fmtTime(v){if(!v)return'';try{let x=v;if(typeof v==='string'&&/^\d+(\.\d+)?$/.test(v))x=Number(v)*1000;else if(typeof v==='number'&&v<1000000000000)x=v*1000;const d=new Date(x);if(Number.isNaN(d.getTime()))return'';return d.toLocaleString([],{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})}catch(e){return''}}function prettyState(v){const s=String(v||'').toLowerCase().replace(/[_-]+/g,' ').trim();if(!s)return'';if(['in play','inplay','started','live','playing'].includes(s))return'LIVE';if(['not started','scheduled','upcoming','fixture','created','confirmed'].includes(s))return'UPCOMING';if(['completed','complete','finished','result','ended','closed'].includes(s))return'FINAL';return s.replace(/\b\w/g,c=>c.toUpperCase())}"
    html = html.replace(old_fmt, new_fmt, 1)
    html = html.replace(
        "esc(m.state||fmtTime(m.startTime)||mode.toUpperCase())",
        "esc(mode==='upcoming'?(fmtTime(m.startTime)||'UPCOMING'):mode==='results'?(prettyState(m.state)||'FINAL'):(prettyState(m.state)||mode.toUpperCase()))",
    )
    html = html.replace(
        "esc(m.report||m.state||fmtTime(m.startTime)||'Tap for details')",
        "esc(m.report||(mode==='upcoming'?fmtTime(m.startTime):prettyState(m.state))||'Tap for details')",
    )

    # Make the fixed bottom bar match what it actually does.
    html = html.replace(
        '<button data-nav="cricket"><b>🏏</b>CRICKET</button>',
        '<button data-nav="cricket"><b>◷</b>UPCOMING</button>',
    )
    html = html.replace(
        '<button data-nav="alerts"><b>🔔</b>ALERTS</button>',
        '<button data-nav="alerts"><b>✓</b>RESULTS</button>',
    )
    html = html.replace(
        '<button data-nav="more"><b>•••</b>MORE</button>',
        '<button data-nav="more"><b>⌕</b>SEARCH</button>',
    )
    html = html.replace(
        "if(x==='live'||x==='cricket'||x==='home'){backHome();load('live')}else if(x==='alerts'){alert('Smart match alerts are active in IBETIN.')}else document.getElementById('search').focus()",
        "if(x==='home'||x==='live'){backHome();load('live')}else if(x==='cricket'){backHome();load('upcoming')}else if(x==='alerts'){backHome();load('results')}else{backHome();document.getElementById('search').focus()}",
    )

    hydrate_js = r"""
const __scoreHydrateAt=new Map(),__scoreHydrateBusy=new Set();
async function hydrateScore(m){
  const key=matchKey(m); if(!key)return;
  if(m.homeScore&&m.awayScore)return;
  const now=Date.now(),last=__scoreHydrateAt.get(key)||0;
  if(__scoreHydrateBusy.has(key)||now-last<12000)return;
  __scoreHydrateBusy.add(key);__scoreHydrateAt.set(key,now);
  try{
    const j=await api({action:'score',matchId:key});
    const s=j.match||{};
    const box=Array.from(document.querySelectorAll('.match')).find(x=>x.dataset.key===key);
    if(!box)return;
    const scores=box.querySelectorAll('.sc');
    if(scores[0]&&s.homeScore) scores[0].textContent=s.homeScore;
    if(scores[1]&&s.awayScore) scores[1].textContent=s.awayScore;
    const infos=box.querySelectorAll('.si');
    if(infos[0]&&s.homeInfo) infos[0].textContent=s.homeInfo;
    if(infos[1]&&s.awayInfo) infos[1].textContent=s.awayInfo;
    const foot=box.querySelector('.foot span');
    if(foot&&(s.report||s.state)) foot.textContent=s.report||prettyState(s.state);
    const idx=allMatches.findIndex(x=>matchKey(x)===key);
    if(idx>=0) allMatches[idx]=Object.assign({},allMatches[idx],s);
  }catch(e){console.warn('score hydrate pending',key,e&&e.message)}
  finally{__scoreHydrateBusy.delete(key);__scoreHydrateAt.set(key,Date.now())}
}
function scorecardHtml(rows,m){
  return rows.map(r=>{
    const idx=String((r&&r.index)||'');
    const side=idx.startsWith('a_')?(m.home||{}):idx.startsWith('b_')?(m.away||{}):{};
    const name=side.name||idx.replace('_',' ').toUpperCase()||'Innings';
    const sc=(r&&r.score&&typeof r.score==='object')?r.score:{};
    let score=String((r&&r.score_str)||'').split(' in ')[0];
    if(!score){
      const runs=sc.runs;
      const wk=(r&&r.wickets!==undefined)?r.wickets:sc.wickets;
      score=(runs===undefined||runs===null)?'':String(runs)+(wk===undefined||wk===null?'':'/'+wk);
    }
    const ov=Array.isArray(r&&r.overs)?r.overs.join('.'):(r&&r.overs)||'';
    const rr=sc.run_rate;
    return `<div class="notice scorecardRow"><div style="display:flex;justify-content:space-between;gap:10px;align-items:center"><b>${esc(name)}</b><strong>${esc(score||'—')}</strong></div><div style="margin-top:5px">${ov?esc(ov)+' overs':''}${rr!==undefined&&rr!==null?(ov?' · ':'')+'RR '+esc(rr):''}</div></div>`;
  }).join('');
}
"""
    marker = "document.querySelectorAll('.tab').forEach(b=>b.onclick"
    html = html.replace(marker, hydrate_js + marker, 1)

    html = html.replace(
        "else if(tab==='scorecard'){const s=x.statistics||[];p.innerHTML=ptitle('SCORECARD')+(s.length?`<div class=\"graph\">${esc(JSON.stringify(s,null,2).slice(0,9000))}</div>`:'<div class=\"notice\">Scorecard data is not available yet.</div>')}",
        "else if(tab==='scorecard'){const s=x.statistics||[];p.innerHTML=ptitle('SCORECARD')+(s.length?scorecardHtml(s,m):'<div class=\"notice\">Scorecard data is not available yet.</div>')}",
        1,
    )

    # Use Telegram's native back control while match detail is open.
    html = html.replace(
        "async function openMatch(key){document.getElementById('home').style.display='none';",
        "async function openMatch(key){if(tg&&tg.BackButton)try{tg.BackButton.show()}catch(e){}document.getElementById('home').style.display='none';",
        1,
    )
    html = html.replace(
        "function backHome(){document.getElementById('detail').style.display='none';",
        "function backHome(){if(tg&&tg.BackButton)try{tg.BackButton.hide()}catch(e){}document.getElementById('detail').style.display='none';",
        1,
    )
    back_marker = "document.querySelectorAll('.tab').forEach(b=>b.onclick"
    back_js = "if(tg&&tg.BackButton){try{tg.BackButton.onClick(()=>{if(document.getElementById('detail').style.display==='block')backHome()})}catch(e){}}"
    html = html.replace(back_marker, back_js + back_marker, 1)

    html = html.replace("Refreshing '+mode+' cricket…", "Loading '+mode+' cricket…")
    html = html.replace(
        "setInterval(()=>{if(!document.hidden&&document.getElementById('home').style.display!=='none')load('live')},20000)",
        "setInterval(()=>{if(!document.hidden&&document.getElementById('home').style.display!=='none')load('live')},30000)",
    )
    return html


liveline.admin_url = _admin_url
liveline._page = _page
liveline._api = _api
app = v21.app

# Remove the obsolete one-time admin follow-up trial message. It was only a
# startup test and now targets a Telegram chat that no longer exists, producing
# a harmless but noisy Chat not found exception on every deploy. The real
# reminder worker remains enabled through the original background-loop function.
ui_start.reminders.start_background_loop = ui_start._original_start_background_loop
logger.info("IBETIN obsolete startup follow-up trial disabled; reminder worker remains active")


def _live_classifier_self_test() -> None:
    cases = {
        "before_toss": ({"state": "scheduled"}, False),
        "toss_done": ({"state": "pre_match", "toss": {"winner": "a", "decision": "bowl"}}, True),
        "normal_live": ({"state": "in_play"}, True),
        "rain_after_start": ({"state": "rain_delay", "score": "12/0"}, True),
        "stumps": ({"state": "stumps", "score": "250/6"}, False),
        "completed": ({"state": "completed", "score": "250/6"}, False),
    }
    failures = [name for name, (sample, expected) in cases.items() if _is_live_coverage_match(sample) is not expected]
    if failures:
        raise RuntimeError("live classifier cases failed: " + ", ".join(failures))
    logger.info("IBETIN V23 live-classifier self-test PASS cases=%s", ",".join(cases))


def _startup_self_test() -> None:
    try:
        page = _page()
        page_ok = (
            "/admin/liveline-ibetinv23/api" in page
            and "hydrateScore" in page
            and "__scoreHydrateBusy" in page
            and "forEach(loadCardBhav)" not in page
        )
        rows, source = _fast_matches("live")
        if not rows:
            logger.warning("IBETIN V23 self-test: page_ok=%s live feed empty source=%s", page_ok, source)
            return
        first = rows[0]
        key = str(first.get("roanuzMatchKey") or first.get("id") or "")
        score = _score_summary(key)
        detail = _match_detail_v23(key)
        score_ok = bool(score.get("homeScore") or score.get("awayScore"))
        toss_ok = bool((detail.get("roanuz") or {}).get("toss")) if isinstance(detail, dict) else False
        coverage_ok = score_ok or toss_ok
        detail_ok = isinstance(detail.get("statistics"), list) and isinstance(detail.get("timeline"), list)
        level = logger.info if page_ok and coverage_ok and detail_ok else logger.error
        level(
            "IBETIN V23 self-test %s page_ok=%s coverage_ok=%s score_ok=%s toss_ok=%s detail_ok=%s source=%s matches=%s key=%s score=%s/%s info=%s/%s innings=%s balls=%s state=%s report=%s",
            "PASS" if page_ok and coverage_ok and detail_ok else "FAILED",
            page_ok,
            coverage_ok,
            score_ok,
            toss_ok,
            detail_ok,
            source,
            len(rows),
            key,
            score.get("homeScore") or "-",
            score.get("awayScore") or "-",
            score.get("homeInfo") or "-",
            score.get("awayInfo") or "-",
            len(detail.get("statistics") or []),
            len(detail.get("timeline") or []),
            score.get("state") or "-",
            score.get("report") or "-",
        )
    except Exception as exc:
        logger.exception("IBETIN V23 self-test FAILED: %s", exc)


_init_webhook_state_store()
_restore_webhook_state()
_live_classifier_self_test()
_startup_self_test()
logger.info(
    "IBETIN V23 installed: stable Roanuz feed + webhook cache + toss-stage coverage + embedded scorecard/balls + numeric fallback detail + deduped hydration + mobile UI polish"
)

if __name__ == "__main__":
    app.base.ibetin_start.main()
