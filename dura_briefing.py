"""An on-demand DURA match briefing from the existing Live Line providers."""

from datetime import datetime, timezone
from html import escape
import time
from zoneinfo import ZoneInfo

INDIA = ZoneInfo("Asia/Kolkata")
_LIVE_STATES = {"live", "in play", "inplay", "playing", "started"}
_FINAL_STATES = {"completed", "complete", "finished", "result", "ended"}


def _start_in_india(row: dict):
    value = row.get("startTime") or row.get("start_time")
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)) or str(value).replace(".", "", 1).isdigit():
            seconds = float(value)
            if seconds > 10**12:
                seconds /= 1000
            dt = datetime.fromtimestamp(seconds, timezone.utc)
        else:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.astimezone(INDIA) if dt.tzinfo else None
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _name(row: dict, side: str) -> str:
    value = row.get(side) or {}
    if isinstance(value, dict):
        return str(value.get("name") or value.get("abbr") or "").strip()
    return ""


def select_rows(feed_by_mode: dict, today=None) -> list[dict]:
    """Use only provider rows: live-list items, then today's fixtures/results."""
    today = today or datetime.now(INDIA).date()
    selected, seen = [], set()
    for mode in ("live", "upcoming", "results"):
        for row in feed_by_mode.get(mode, []):
            if not isinstance(row, dict):
                continue
            home, away = _name(row, "home"), _name(row, "away")
            key = str(row.get("roanuzMatchKey") or row.get("id") or "")
            if not home or not away or not key or key in seen:
                continue
            started = _start_in_india(row)
            if mode != "live":
                if not started or started.date() != today:
                    continue
            seen.add(key)
            selected.append({"mode": mode, "match": row})
            if len(selected) == 3:
                return selected
    return selected


def fetch_today_rows() -> list[dict]:
    """Keep the established Roanuz-first, Highlightly-second feed selection."""
    import ibetin_liveline_v25_fast_cache as feed

    modes = {}
    for mode in ("live", "upcoming", "results"):
        try:
            with feed._lock:
                cached = feed._list_cache.get(mode)
            if cached and time.monotonic() - cached[0] <= 30:
                rows = cached[1]
            else:
                rows, _source = feed._refresh_matches(mode)
            modes[mode] = rows if isinstance(rows, list) else []
        except Exception:
            modes[mode] = []
        if len(select_rows(modes)) >= 3:
            break
    return select_rows(modes)


def format_briefing(rows: list[dict]) -> str:
    if not rows:
        return (
            "⚡ <b>TODAY ON DURA</b>\n\n"
            "The match feed has no current briefing details. Open Live Line for the full board."
        )
    lines = ["⚡ <b>TODAY ON DURA</b>", "", "From the current match feed:"]
    for item in rows[:3]:
        row = item["match"]
        home, away = escape(_name(row, "home")), escape(_name(row, "away"))
        state = str(row.get("state") or "").replace("_", " ").lower().strip()
        mode = item["mode"]
        if mode == "live" and state in _LIVE_STATES:
            label = "LIVE"
        elif mode == "results" or state in _FINAL_STATES:
            label = "RESULT"
        elif mode == "upcoming":
            label = "TODAY'S FIXTURE"
        else:
            label = "MATCH UPDATE"
        raw_h, raw_a = row.get("homeScore"), row.get("awayScore")
        score_h = escape(str(raw_h).strip()) if isinstance(raw_h, (str, int, float)) else ""
        score_a = escape(str(raw_a).strip()) if isinstance(raw_a, (str, int, float)) else ""
        scores = f" · {score_h} / {score_a}" if score_h or score_a else ""
        lines.append(f"• <b>{home} vs {away}</b> — {label}{scores}")
    lines.extend(["", "Feed details can change. Open Live Line for the latest available view."])
    return "\n".join(lines)
