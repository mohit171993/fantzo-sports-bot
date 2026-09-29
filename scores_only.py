"""Explicitly allowlisted score data for a separate score-only page/API.

The current `/liveline` payload contains BHAV, odds, and session markets; it
must not be reused as the Live Line mode's public endpoint.
"""

from __future__ import annotations

from html import escape
import re


_BLOCKED_COPY = re.compile(
    r"\b(?:odds?|bhav|sessions?|betting|bets?|gambling|casinos?|wagers?|"
    r"sportsbooks?|bookmakers?|slots?|stakes?|cashout|jackpots?|bonuses?|promos?|"
    r"deposits?|withdrawals?|payments?)\b", re.IGNORECASE,
)


def _plain(value, limit: int = 120) -> str:
    if isinstance(value, (str, int, float)):
        text = str(value)[:limit]
        return "" if _BLOCKED_COPY.search(text) else text
    return ""


def _team(value) -> dict:
    value = value if isinstance(value, dict) else {}
    return {"name": _plain(value.get("name")), "abbr": _plain(value.get("abbr"), 24)}


def score_match(value) -> dict:
    """Build a new object; never pass through provider or existing API dicts."""
    value = value if isinstance(value, dict) else {}
    league = value.get("league")
    league = league if isinstance(league, dict) else {}
    return {
        "id": _plain(value.get("roanuzMatchKey") or value.get("id"), 100),
        "state": _plain(value.get("state"), 40),
        "start_time": _plain(value.get("startTime"), 60),
        "format": _plain(value.get("format"), 40),
        "league": _plain(league.get("name")),
        "home": _team(value.get("home")),
        "away": _team(value.get("away")),
        "home_score": _plain(value.get("homeScore"), 60),
        "away_score": _plain(value.get("awayScore"), 60),
    }


def score_matches(rows) -> list[dict]:
    return [score_match(row) for row in rows if isinstance(row, dict)][:40]


def alert_score_match(match, sport: str) -> dict:
    """Project the separate alert provider shape without its report or markets."""
    match = match if isinstance(match, dict) else {}
    state = match.get("state")
    state = state if isinstance(state, dict) else {}
    if sport == "cricket":
        teams = state.get("teams")
        teams = teams if isinstance(teams, dict) else {}
        home = teams.get("home") if isinstance(teams.get("home"), dict) else {}
        away = teams.get("away") if isinstance(teams.get("away"), dict) else {}
        home_score, away_score = home.get("score"), away.get("score")
    else:
        score = state.get("score")
        score = score if isinstance(score, dict) else {}
        current = score.get("current")
        current = current if isinstance(current, dict) else {}
        home_score, away_score = current.get("home"), current.get("away")

    def clean_score(value):
        raw = _plain(value, 24)
        return raw if re.fullmatch(r"[0-9/().& :+-]*", raw) else ""

    return score_match({
        "id": match.get("id"),
        "home": match.get("homeTeam") or match.get("home"),
        "away": match.get("awayTeam") or match.get("away"),
        "homeScore": clean_score(home_score),
        "awayScore": clean_score(away_score),
    })


def score_page(rows: list[dict], brand: str, mode: str = "live") -> str:
    """Server-rendered first response: scores are visible before JS runs."""
    if mode not in {"live", "upcoming", "results"}:
        mode = "live"
    cards = []
    for row in rows:
        home = row.get("home") or {}
        away = row.get("away") or {}
        cards.append(
            '<article class="match"><p class="league">'
            + escape(_plain(row.get("league")))
            + '</p><div><strong>' + escape(_plain(home.get("name")))
            + '</strong><span>' + escape(_plain(row.get("home_score")))
            + '</span></div><div><strong>' + escape(_plain(away.get("name")))
            + '</strong><span>' + escape(_plain(row.get("away_score")))
            + '</span></div><p class="state">'
            + escape(_plain(row.get("state"))) + '</p></article>'
        )
    if not cards:
        cards.append('<p>No match scores are available right now.</p>')
    title = escape(_plain(brand, 32))
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="refresh" content="30">'
        '<meta http-equiv="Cache-Control" content="no-store">'
        '<title>' + title + ' Match Scores</title>'
        '<style>body{font-family:system-ui;margin:0;background:#f4f7fa;color:#172536}'
        'main{max-width:700px;margin:auto;padding:20px}nav{display:flex;gap:14px}'
        'nav a{color:#145a85;padding:8px 0}.match{background:white;'
        'border:1px solid #dce5ed;border-radius:14px;padding:16px;margin:10px 0}'
        '.match div{display:flex;justify-content:space-between;padding:7px 0}'
        '.league,.state{color:#65788a;font-size:13px}</style></head><body>'
        '<main><h1>' + title + ' Match Scores</h1>'
        '<nav aria-label="Match views"><a href="/scores?mode=live">Live</a>'
        '<a href="/scores?mode=upcoming">Upcoming</a>'
        '<a href="/scores?mode=results">Results</a></nav>'
        '<h2>' + escape(mode.title()) + '</h2>' + ''.join(cards)
        + '</main></body></html>'
    )
