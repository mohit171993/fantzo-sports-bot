"""Explicitly allowlisted score data for a separate score-only page/API.

The current `/liveline` payload contains BHAV, odds, and session markets; it
must not be reused as the Live Line mode's public endpoint.
"""

from __future__ import annotations

from html import escape
import json
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


def _score_text(value) -> str:
    raw = _plain(value, 60).strip()
    return raw if re.fullmatch(r"[0-9/().& +:-]+", raw) else ""


def _overs_text(value) -> str:
    raw = _plain(value, 40).strip()
    return raw if re.fullmatch(r"[0-9. ]+\s*(?:ov|overs)?", raw, re.IGNORECASE) else ""


def _state(value) -> str:
    raw = _plain(value, 40).strip().lower().replace("_", " ")
    allowed = {"live", "in progress", "upcoming", "scheduled", "not started",
               "toss", "completed", "complete", "finished", "ended", "result",
               "abandoned", "cancelled", "canceled", "delayed", "stumps", "innings break"}
    return raw.title() if raw in allowed else ""


def score_match(value) -> dict:
    """Build a new object; never pass through provider or existing API dicts."""
    value = value if isinstance(value, dict) else {}
    league = value.get("league")
    league = league if isinstance(league, dict) else {}
    return {
        "id": _plain(value.get("roanuzMatchKey") or value.get("id"), 100),
        "state": _state(value.get("state")),
        "start_time": _plain(value.get("startTime") or value.get("start_time"), 60),
        "format": _plain(value.get("format"), 40),
        "league": _plain(league.get("name") if league else value.get("league")),
        "home": _team(value.get("home")),
        "away": _team(value.get("away")),
        "home_score": _score_text(value.get("homeScore") or value.get("home_score")),
        "home_info": _overs_text(value.get("homeInfo") or value.get("home_info")),
        "away_score": _score_text(value.get("awayScore") or value.get("away_score")),
        "away_info": _overs_text(value.get("awayInfo") or value.get("away_info")),
    }


def score_matches(rows) -> list[dict]:
    return [score_match(row) for row in rows if isinstance(row, dict)][:40]


def merge_score_match(list_match: dict, detail_match: dict) -> dict:
    """Fill missing list scores from the matching cached detail record."""
    list_match = score_match(list_match)
    detail_match = score_match(detail_match)
    if not list_match["id"] or list_match["id"] != detail_match["id"]:
        return list_match
    for field in ("home_score", "away_score", "home_info", "away_info",
                  "state", "start_time", "format", "league"):
        if not list_match[field] and detail_match[field]:
            list_match[field] = detail_match[field]
    for side in ("home", "away"):
        for field in ("name", "abbr"):
            if not list_match[side][field] and detail_match[side][field]:
                list_match[side][field] = detail_match[side][field]
    return list_match


def _stat_number(value) -> str:
    raw = _plain(value, 18)
    return raw if re.fullmatch(r"[0-9.]+", raw) else ""


def _items(value) -> list:
    return value if isinstance(value, list) else []


def _player(value, fields) -> dict:
    value = value if isinstance(value, dict) else {}
    person = value.get("player") if isinstance(value.get("player"), dict) else value
    result = {"name": _plain(person.get("name") or value.get("name"), 80)}
    stats = person.get("statistics") if isinstance(person.get("statistics"), dict) else value
    for public, provider in fields.items():
        result[public] = _stat_number(value.get(provider, stats.get(provider)))
    return result


def score_detail(value, list_match=None) -> dict:
    """Project only match scores and scorecard statistics from provider detail."""
    value = value if isinstance(value, dict) else {}
    match = value.get("match") if isinstance(value.get("match"), dict) else {}
    safe_match = score_match(match)
    if isinstance(list_match, dict):
        if not safe_match["id"]:
            safe_match["id"] = score_match(list_match)["id"]
        safe_match = merge_score_match(list_match, {
            **match, "id": safe_match["id"],
        })
    innings = []
    for row in _items(value.get("statistics"))[:8]:
        if not isinstance(row, dict):
            continue
        score = row.get("score") if isinstance(row.get("score"), dict) else {}
        runs = _stat_number(row.get("runs", score.get("runs")))
        wickets = _stat_number(row.get("wickets", score.get("wickets")))
        score_text = f"{runs}/{wickets}" if runs and wickets else runs
        innings.append({
            "name": _plain(row.get("name") or row.get("abbreviation") or row.get("index"), 80),
            "score": score_text,
            "overs": _stat_number(row.get("overs", score.get("overs"))),
            "batters": [_player(x, {"runs": "runs", "balls": "balls", "fours": "fours",
                                    "sixes": "sixes", "strike_rate": "strikeRate"})
                        for x in _items(row.get("inningBatsmen") or row.get("batsmen"))[:20]
                        if isinstance(x, dict)],
            "bowlers": [_player(x, {"overs": "overs", "runs": "concededRuns",
                                    "wickets": "wickets", "economy": "economy"})
                        for x in _items(row.get("inningBowlers") or row.get("bowlers"))[:20]
                        if isinstance(x, dict)],
        })
    return {"match": safe_match, "innings": innings}


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


def _crest(value: dict) -> str:
    text = _plain(value.get("abbr"), 24) or _plain(value.get("name"))
    return escape(re.sub(r"[^0-9A-Za-z]", "", text)[:3].upper())


def _score_card_html(row: dict, mode: str) -> str:
    home, away = row.get("home") or {}, row.get("away") or {}
    label = "LIVE" if mode == "live" else _plain(row.get("state")) or mode.title()
    badge = ('<em class="badge live"><i></i>' if mode == "live" else '<em class="badge">')
    def team(value, score, info, side):
        return ('<div class="team ' + side + '"><span class="crest">' + _crest(value)
                + '</span><div class="tname"><strong>' + escape(_plain(value.get("name")))
                + '</strong><small>' + escape(_plain(value.get("abbr"), 24))
                + '</small></div><div class="number"><b>' + escape(_plain(score))
                + '</b><small>' + escape(_plain(info)) + '</small></div></div>')
    return (
        '<button type="button" class="match' + (' is-live' if mode == "live" else '')
        + '" data-id="' + escape(_plain(row.get("id")), quote=True)
        + '"><div class="match-top"><span><i class="fmt">' + escape(_plain(row.get("format")))
        + '</i><span class="lg">' + escape(_plain(row.get("league"))) + '</span></span>'
        + badge + escape(label) + '</em></div>'
        + team(home, row.get("home_score"), row.get("home_info"), "home")
        + team(away, row.get("away_score"), row.get("away_info"), "away")
        + '<div class="match-foot"><span>'
        + escape(_plain(row.get("state")))
        + '</span><span class="go">›</span></div></button>'
    )


def score_page(rows: list[dict], brand: str, mode: str = "live", *, feed_error=False) -> str:
    """A score-only Mini App with a server-rendered first response."""
    if mode not in {"live", "upcoming", "results"}:
        mode = "live"
    safe_rows = score_matches(rows)
    cards = ''.join(_score_card_html(row, mode) for row in safe_rows)
    if not cards:
        cards = ('<div class="empty">Match scores are temporarily unavailable. '
                 'Please try again.</div>' if feed_error else
                 '<div class="empty">No matches in this view right now.</div>')
    title = escape(_plain(brand, 32))
    tabs = ''.join(
        '<a href="/scores?mode=' + name + '" data-mode="' + name + '"'
        + (' class="active"' if mode == name else '') + '>' + name.title() + '</a>'
        for name in ("live", "upcoming", "results")
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Cache-Control" content="no-store">'
        '<title>' + title + ' Match Scores</title>'
        '<script src="https://telegram.org/js/telegram-web-app.js"></script>'
        '<style>' + _SCORE_CSS + '</style></head><body>'
        '<div class="shell"><header class="top"><div class="brand"><span class="mark">🏏</span>'
        '<div><h1><span class="wm">' + title + '</span> Live Line</h1><p>MATCH SCORES</p></div></div>'
        '<nav aria-label="Match views">' + tabs + '</nav></header>'
        '<main id="home"><div class="tools"><div id="status" role="status">'
        + ('Feed temporarily unavailable' if feed_error else 'Live scores')
        + '</div><button id="refresh" type="button" aria-label="Refresh scores">↻</button></div>'
        '<div id="list" class="list">' + cards + '</div></main>'
        '<section id="detail" class="detail" hidden></section></div>'
        '<script>const START_MODE=' + json.dumps(mode) + ';' + _SCORE_JS + '</script>'
        '</body></html>'
    )


_SCORE_CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700;8..60,900&display=swap');
:root{--cream:#f4ecdc;--paper:#fffaf1;--paper2:#f8efdf;--ink:#1a1612;--ink2:#4d4439;--mute:#8a7d6c;--red:#c8231b;--red2:#8f150f;--carbon:#14110e;--carbon2:#211c17;--gold:#d8b25a;--gold2:#f3dc98;--gold3:#9c7428;--rule:#e4d6bd}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}html,body{margin:0;min-height:100%;font-family:'Source Serif 4',Georgia,'Times New Roman',serif;-webkit-font-smoothing:antialiased}
.brand h1,.brand p,nav a,.match-top,.number b,.number small,.match-foot,.crest,.back,.scorehero h2,.scorehero p,.detail-team b,.innings h3,.innings p,.stat-table th,.stat-table td:not(:first-child),#status{font-family:'Oswald','Arial Narrow',Arial,sans-serif}
body{background:radial-gradient(120% 60% at 50% 0,#fbf4e6 0,var(--cream) 46%,#eee2cc 100%) fixed;color:var(--ink)}
button,a{font:inherit}.shell{max-width:760px;margin:auto;min-height:100vh}
.top{position:sticky;top:0;z-index:5;padding:16px 16px 14px;color:#f6eedd;background:repeating-linear-gradient(45deg,rgba(255,255,255,.022) 0 2px,transparent 2px 6px),repeating-linear-gradient(-45deg,rgba(0,0,0,.25) 0 2px,transparent 2px 6px),radial-gradient(130% 120% at 0 0,#2c241d 0,var(--carbon) 58%,#0c0a08 100%);box-shadow:0 14px 30px rgba(20,14,8,.28)}
.top:after{content:"";position:absolute;left:0;right:0;bottom:-2px;height:2px;background:linear-gradient(90deg,var(--gold3),var(--gold2) 30%,var(--gold) 55%,var(--red) 80%,var(--red2))}
.brand{display:flex;align-items:center;gap:12px}
.mark{display:grid;place-items:center;flex:0 0 46px;width:46px;height:46px;border-radius:14px;font-size:22px;background:radial-gradient(circle at 30% 25%,#d8392f,var(--red) 45%,var(--red2));box-shadow:inset 0 0 0 1.5px var(--gold),inset 0 1px 0 2px rgba(255,236,190,.35),0 6px 16px rgba(200,35,27,.35)}
.brand h1{margin:0;font-size:23px;line-height:1.05;font-weight:600;letter-spacing:.3px;color:#f6eedd}
.brand h1 .wm{font-weight:700;letter-spacing:1.6px;color:#e2382d;-webkit-text-stroke:.6px var(--gold);text-shadow:0 0 1px rgba(243,220,152,.6),0 2px 10px rgba(226,56,45,.35);margin-right:2px}
.brand p{margin:5px 0 0;color:var(--gold);font-size:10px;font-weight:500;letter-spacing:3.2px}
nav{display:grid;grid-template-columns:repeat(3,1fr);gap:4px;margin-top:15px;padding:4px;border-radius:15px;background:rgba(255,255,255,.045);box-shadow:inset 0 0 0 1px rgba(216,178,90,.22)}
nav a{padding:10px 6px;border-radius:11px;color:#bfb2a0;text-align:center;text-decoration:none;font-size:13px;font-weight:500;letter-spacing:1.4px;text-transform:uppercase;transition:background .2s,color .2s}
nav a.active{color:#fff;background:linear-gradient(180deg,#dc3127,var(--red) 55%,#a5180f);box-shadow:inset 0 1px 0 rgba(255,214,160,.45),inset 0 0 0 1px rgba(243,220,152,.35),0 6px 16px rgba(200,35,27,.4)}
main,.detail{padding:16px 14px calc(56px + env(safe-area-inset-bottom))}
.tools{display:flex;justify-content:space-between;align-items:center;gap:10px;margin:2px 2px 14px}
#status{display:flex;align-items:center;gap:8px;color:var(--ink2);font-size:12px;font-weight:400;letter-spacing:.9px;text-transform:uppercase}
#status:before{content:"";width:7px;height:7px;border-radius:50%;background:var(--red);box-shadow:0 0 0 3px rgba(200,35,27,.16);animation:pulse 1.6s ease-in-out infinite}
#refresh{display:grid;place-items:center;width:40px;height:40px;border:0;border-radius:50%;background:linear-gradient(180deg,var(--paper),#efe3cc);color:var(--red);font-size:21px;line-height:1;cursor:pointer;box-shadow:inset 0 0 0 1px rgba(156,116,40,.45),0 4px 12px rgba(80,52,18,.12)}
#refresh:active{transform:rotate(-30deg) scale(.96)}
.list{display:grid;gap:13px}
.match{position:relative;display:block;width:100%;padding:0;text-align:left;color:var(--ink);background:linear-gradient(180deg,var(--paper),var(--paper2));border:0;border-radius:20px;overflow:hidden;cursor:pointer;box-shadow:inset 0 0 0 1px rgba(110,80,40,.14),0 1px 0 rgba(255,255,255,.9),0 12px 26px -10px rgba(70,44,14,.28);transition:transform .15s}
.match:active{transform:scale(.988)}
.match:before{content:"";position:absolute;inset:0 0 auto 0;height:3px;background:linear-gradient(90deg,var(--gold3),var(--gold2) 40%,var(--gold3))}
.match.is-live:before{background:linear-gradient(90deg,var(--red2),var(--red) 35%,var(--gold) 75%,var(--gold2))}
.match-top{display:flex;justify-content:space-between;gap:10px;align-items:center;padding:14px 14px 6px;font-size:11px;color:var(--ink2)}
.match-top>span{display:flex;align-items:center;gap:8px;min-width:0}
.fmt{flex:none;padding:3px 7px 2px;border-radius:6px;background:var(--carbon);color:var(--gold2);font-style:normal;font-size:10px;font-weight:600;letter-spacing:1.2px;box-shadow:inset 0 0 0 1px rgba(216,178,90,.45)}
.lg{overflow:hidden;white-space:nowrap;text-overflow:ellipsis;font-weight:500;letter-spacing:.5px;text-transform:uppercase;color:var(--ink2)}
.badge{flex:none;display:inline-flex;align-items:center;gap:6px;padding:4px 9px 3px;border-radius:999px;font-style:normal;font-size:10px;font-weight:600;letter-spacing:1.4px;text-transform:uppercase;color:var(--ink2);background:#efe4cf;box-shadow:inset 0 0 0 1px rgba(110,80,40,.18)}
.badge.live{color:#fff;background:linear-gradient(180deg,#de3529,var(--red));box-shadow:inset 0 0 0 1px rgba(243,220,152,.55),0 4px 10px rgba(200,35,27,.3)}
.badge.live i{width:6px;height:6px;border-radius:50%;background:#fff;animation:pulse 1.3s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.35;transform:scale(.7)}}
.team{display:flex;align-items:center;gap:12px;padding:9px 14px}
.team+.team{border-top:1px dashed var(--rule)}
.crest{flex:0 0 40px;display:grid;place-items:center;width:40px;height:40px;border-radius:50%;font-size:12px;font-weight:600;letter-spacing:.6px;color:#f6eedd;background:radial-gradient(circle at 32% 26%,#3a3129,var(--carbon) 70%);box-shadow:inset 0 0 0 1.5px var(--gold),inset 0 0 0 3px var(--carbon),inset 0 0 0 4px rgba(216,178,90,.35),0 4px 10px rgba(20,14,8,.22)}
.team.home .crest{background:radial-gradient(circle at 32% 26%,#e04a3e,var(--red) 55%,var(--red2));box-shadow:inset 0 0 0 1.5px var(--gold),inset 0 0 0 3px var(--red2),inset 0 0 0 4px rgba(243,220,152,.4),0 4px 10px rgba(200,35,27,.25)}
.tname{flex:1;min-width:0}.team strong{display:block;font-size:17px;font-weight:700;line-height:1.15;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.team .tname small{display:block;margin-top:2px;color:var(--mute);font-size:11px;letter-spacing:.6px}
.number{flex:none;text-align:right}.number b{display:block;font-size:27px;font-weight:600;line-height:1;color:var(--ink);letter-spacing:-.2px}.number small{display:block;margin-top:3px;color:var(--mute);font-size:11px;letter-spacing:.6px}
.match-foot{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:4px;padding:9px 14px 10px;font-size:11px;letter-spacing:1.2px;text-transform:uppercase;color:var(--ink2);background:linear-gradient(180deg,rgba(228,214,189,.25),rgba(228,214,189,.5));border-top:1px solid var(--rule)}
.match.is-live .match-foot span:first-child{color:var(--red)}
.go{display:grid;place-items:center;width:22px;height:22px;border-radius:50%;background:var(--carbon);color:var(--gold2);font-size:15px;line-height:1;padding-bottom:2px}
.empty{padding:30px 18px;border-radius:20px;background:linear-gradient(180deg,var(--paper),var(--paper2));color:var(--ink2);text-align:center;font-size:15px;box-shadow:inset 0 0 0 1px rgba(110,80,40,.16),0 10px 24px -12px rgba(70,44,14,.25)}
.detail[hidden]{display:none}
.back{display:inline-flex;align-items:center;gap:6px;padding:9px 15px 8px;border-radius:999px;border:0;background:var(--carbon);color:var(--gold2);font-size:12px;font-weight:500;letter-spacing:1.6px;cursor:pointer;box-shadow:inset 0 0 0 1px rgba(216,178,90,.5),0 6px 14px rgba(20,14,8,.22)}
.scorehero{position:relative;margin-top:14px;padding:16px 16px 6px;border-radius:22px;overflow:hidden;color:#f6eedd;background:repeating-linear-gradient(45deg,rgba(255,255,255,.02) 0 2px,transparent 2px 6px),radial-gradient(120% 90% at 100% 0,rgba(200,35,27,.32),transparent 55%),linear-gradient(160deg,#2a231c,var(--carbon) 60%,#0c0a08);box-shadow:inset 0 0 0 1px rgba(216,178,90,.45),0 18px 34px -14px rgba(20,14,8,.55)}
.scorehero:before{content:"";position:absolute;inset:0 0 auto;height:3px;background:linear-gradient(90deg,var(--red2),var(--red) 35%,var(--gold) 75%,var(--gold2))}
.scorehero h2{margin:2px 0 4px;font-size:16px;font-weight:600;letter-spacing:.8px;text-transform:uppercase;color:#f6eedd}
.scorehero p{display:inline-block;margin:0 0 10px;padding:3px 9px 2px;border-radius:999px;font-size:10px;letter-spacing:1.4px;text-transform:uppercase;color:#fff;background:linear-gradient(180deg,#de3529,var(--red));box-shadow:inset 0 0 0 1px rgba(243,220,152,.5)}
.detail-team{display:flex;align-items:center;gap:12px;padding:12px 0;border-top:1px solid rgba(216,178,90,.2)}
.detail-team .crest{font-style:normal;flex-basis:44px;width:44px;height:44px}
.detail-team.home .crest{background:radial-gradient(circle at 32% 26%,#e04a3e,var(--red) 55%,var(--red2));box-shadow:inset 0 0 0 1.5px var(--gold),inset 0 0 0 3px var(--red2),inset 0 0 0 4px rgba(243,220,152,.4)}
.detail-team span{flex:1;min-width:0;font-size:17px;font-weight:700}.detail-team span small{display:block;margin-top:3px;font-family:'Oswald',Arial,sans-serif;font-size:11px;font-weight:400;letter-spacing:.8px;color:#bfb2a0}
.detail-team b{font-size:30px;font-weight:600;color:#fff;letter-spacing:-.2px}
.innings{position:relative;margin-top:13px;padding:15px 14px 10px;border-radius:20px;background:linear-gradient(180deg,var(--paper),var(--paper2));box-shadow:inset 0 0 0 1px rgba(110,80,40,.14),0 12px 26px -12px rgba(70,44,14,.26)}
.innings h3{margin:0;font-size:15px;font-weight:600;letter-spacing:.6px;text-transform:uppercase;color:var(--ink)}.innings h3 b{color:var(--red);font-weight:600}
.innings p{margin:3px 0 0;color:var(--mute);font-size:11px;letter-spacing:1px;text-transform:uppercase}
.stat-table{width:100%;border-collapse:separate;border-spacing:0;margin-top:12px;font-size:13px}
.stat-table th,.stat-table td{padding:8px 5px;text-align:right}
.stat-table th:first-child,.stat-table td:first-child{text-align:left;padding-left:9px}.stat-table th:last-child,.stat-table td:last-child{padding-right:9px}
.stat-table th{font-size:10px;font-weight:500;letter-spacing:1.3px;color:var(--gold2);background:var(--carbon)}
.stat-table th:first-child{border-radius:9px 0 0 9px}.stat-table th:last-child{border-radius:0 9px 9px 0}
.stat-table td{border-bottom:1px solid var(--rule);color:var(--ink2)}.stat-table td:first-child{font-weight:600;color:var(--ink)}
.stat-table td:nth-child(2){color:var(--ink);font-weight:600}
.stat-table tr:last-child td{border-bottom:0}
.na{font-style:normal;font-weight:400;color:#c4b393}.scorehero .na{color:#6f6253}
"""


_SCORE_JS = r"""
const tg=window.Telegram&&window.Telegram.WebApp;if(tg){try{tg.ready();tg.expand();tg.setHeaderColor('#14110e');tg.setBackgroundColor('#f4ecdc')}catch(e){}}
let mode=START_MODE,matches=[],selected='';const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const shown=s=>s===null||s===undefined||s===''?'<i class="na">—</i>':esc(s);
async function api(p){const r=await fetch('/scores/api?'+new URLSearchParams(p),{cache:'no-store',credentials:'same-origin'});const j=await r.json();if(!r.ok||!j.ok)throw Error(j.error||'Feed temporarily unavailable');return j}
const crest=t=>esc(String(t?.abbr||t?.name||'').replace(/[^0-9A-Za-z]/g,'').slice(0,3).toUpperCase());
function card(m){const live=mode==='live';const team=(t,score,info,side)=>`<div class="team ${side}"><span class="crest">${crest(t)}</span><div class="tname"><strong>${esc(t?.name||'Team')}</strong><small>${esc(t?.abbr||'')}</small></div><div class="number"><b>${shown(score)}</b><small>${esc(info||'')}</small></div></div>`;return `<button type="button" class="match${live?' is-live':''}" data-id="${esc(m.id)}"><div class="match-top"><span><i class="fmt">${esc(m.format||'CRICKET')}</i><span class="lg">${esc(m.league||'Cricket')}</span></span>${live?'<em class="badge live"><i></i>LIVE</em>':`<em class="badge">${esc(m.state||mode.toUpperCase())}</em>`}</div>${team(m.home,m.home_score,m.home_info,'home')}${team(m.away,m.away_score,m.away_info,'away')}<div class="match-foot"><span>${esc(m.state||'')}</span><span class="go">›</span></div></button>`}
function render(){const list=document.getElementById('list');list.innerHTML=matches.length?matches.map(card).join(''):'<div class="empty">No matches in this view right now.</div>'}
async function hydrateScores(view){const pending=matches.filter(m=>m.id&&(!m.home_score||!m.away_score)).slice(0,8);let next=0;async function worker(){while(next<pending.length&&mode===view){const item=pending[next++];try{const j=await api({action:'score',id:item.id,mode:view});if(mode!==view)return;const current=matches.find(m=>m.id===item.id);if(!current)continue;const s=j.match||{};for(const k of ['home_score','away_score','home_info','away_info','state'])if(!current[k]&&s[k])current[k]=s[k];render()}catch(e){}}}await Promise.all([worker(),worker()])}
async function load(next=mode){mode=next;document.querySelectorAll('nav a').forEach(a=>a.classList.toggle('active',a.dataset.mode===mode));const status=document.getElementById('status');status.textContent='Refreshing '+mode+' scores…';try{const j=await api({action:'matches',mode});matches=j.matches||[];render();status.textContent=`${matches.length} match${matches.length===1?'':'es'} · updated ${new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}`;history.replaceState(null,'','/scores?mode='+encodeURIComponent(mode));if(mode==='live')hydrateScores(mode)}catch(e){status.textContent='Feed temporarily unavailable';if(!matches.length)document.getElementById('list').innerHTML='<div class="empty">Match scores are temporarily unavailable. Please try again.</div>'}}
function table(items,labels,keys){if(!items?.length)return '';return `<table class="stat-table"><thead><tr>${labels.map(x=>`<th>${x}</th>`).join('')}</tr></thead><tbody>${items.map(x=>`<tr>${keys.map(k=>`<td>${shown(x[k])}</td>`).join('')}</tr>`).join('')}</tbody></table>`}
function detailHtml(d){const m=d.match||{};const team=(t,score,info,side)=>`<div class="detail-team ${side}"><i class="crest">${crest(t)}</i><span>${esc(t?.name||'Team')}<small>${esc(info||'')}</small></span><b>${shown(score)}</b></div>`;return `<button type="button" class="back">← MATCH CENTER</button><div class="scorehero"><h2>${esc(m.league||'Cricket')} · ${esc(m.format||'')}</h2><p>${esc(m.state||'Match score')}</p>${team(m.home,m.home_score,m.home_info,'home')}${team(m.away,m.away_score,m.away_info,'away')}</div>${(d.innings||[]).map(x=>`<section class="innings"><h3><span>${esc(x.name||'Innings')}</span> · <b>${shown(x.score)}</b></h3><p>${x.overs?esc(x.overs)+' overs':''}</p>${table(x.batters,['BATTER','R','B','4','6'],['name','runs','balls','fours','sixes'])}${table(x.bowlers,['BOWLER','O','R','W'],['name','overs','runs','wickets'])}</section>`).join('')}`}
function back(){selected='';document.getElementById('detail').hidden=true;document.getElementById('home').hidden=false;if(tg?.BackButton)try{tg.BackButton.hide()}catch(e){}}
async function openMatch(id){if(!id)return;selected=id;document.getElementById('home').hidden=true;const detail=document.getElementById('detail');detail.hidden=false;detail.innerHTML='<button type="button" class="back">← MATCH CENTER</button><div class="empty">Loading match score…</div>';if(tg?.BackButton)try{tg.BackButton.show()}catch(e){}await refreshDetail()}
async function refreshDetail(){if(!selected)return;const id=selected;try{const j=await api({action:'match',id,mode});if(selected===id)document.getElementById('detail').innerHTML=detailHtml(j.detail||{})}catch(e){if(selected===id)document.getElementById('detail').innerHTML='<button type="button" class="back">← MATCH CENTER</button><div class="empty">Match score is temporarily unavailable. Please try again.</div>'}}
document.querySelector('nav').onclick=e=>{const a=e.target.closest('a[data-mode]');if(!a)return;e.preventDefault();back();load(a.dataset.mode)};
document.getElementById('refresh').onclick=()=>selected?refreshDetail():load(mode);
document.getElementById('list').onclick=e=>{const b=e.target.closest('.match');if(b)openMatch(b.dataset.id)};
document.getElementById('detail').onclick=e=>{if(e.target.closest('.back'))back()};
if(tg?.BackButton)try{tg.BackButton.onClick(back)}catch(e){}
document.addEventListener('visibilitychange',()=>{if(!document.hidden){if(selected)refreshDetail();else load(mode)}});
setInterval(()=>{if(!document.hidden){if(selected)refreshDetail();else if(mode==='live')load(mode)}},30000);
load(mode);
"""
