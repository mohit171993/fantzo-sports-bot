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
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@500;600;700;800&family=Space+Grotesk:wght@400;500;600;700&display=swap');
:root{--bg:#030607;--bg2:#061014;--panel:#0a1216;--panel2:#070d10;--ink:#eef9fb;--ink2:#b4cbd0;--mute:#7f9aa1;--cy:#19e3ff;--cy2:#8af3ff;--cy3:#0a8fa6;--blue:#2f7dff;--rule:rgba(25,227,255,.13);--edge:rgba(25,227,255,.28)}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}html,body{margin:0;min-height:100%;font-family:'Space Grotesk','Sora',Arial,sans-serif;-webkit-font-smoothing:antialiased}
.brand h1,.brand p,nav a,.match-top,.number b,.match-foot,.crest,.back,.scorehero h2,.scorehero p,.detail-team b,.innings h3,.innings p,.stat-table th,#status{font-family:'Sora','Space Grotesk',Arial,sans-serif}
body{color:var(--ink);background:radial-gradient(90% 40% at 50% -6%,rgba(25,227,255,.16),transparent 70%),url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='28' height='48' viewBox='0 0 28 48'%3E%3Cpath d='M14 0l14 8v16L14 32 0 24V8zM14 32l14 8v16M14 32L0 40' fill='none' stroke='%2319e3ff' stroke-opacity='.05'/%3E%3C/svg%3E"),linear-gradient(180deg,var(--bg2),var(--bg) 40%) fixed}
button,a{font:inherit}.shell{max-width:760px;margin:auto;min-height:100vh}
.top{position:sticky;top:0;z-index:5;padding:16px 16px 14px;color:var(--ink);background:radial-gradient(120% 140% at 0 0,rgba(25,227,255,.14),transparent 55%),linear-gradient(180deg,rgba(6,13,16,.97),rgba(3,7,8,.95));-webkit-backdrop-filter:blur(10px);backdrop-filter:blur(10px);box-shadow:0 14px 30px rgba(0,0,0,.55)}
.top:after{content:"";position:absolute;left:0;right:0;bottom:-1px;height:1px;background:linear-gradient(90deg,transparent,var(--cy) 30%,var(--cy2) 50%,var(--blue) 75%,transparent);box-shadow:0 0 12px rgba(25,227,255,.7)}
.brand{display:flex;align-items:center;gap:12px}
.mark{position:relative;display:grid;place-items:center;flex:0 0 46px;width:46px;height:50px;font-size:0;color:transparent;clip-path:polygon(50% 0,100% 25%,100% 75%,50% 100%,0 75%,0 25%);background:linear-gradient(160deg,var(--cy2),var(--cy) 40%,var(--blue));filter:drop-shadow(0 0 10px rgba(25,227,255,.55))}
.mark:before{content:"";position:absolute;inset:2px;clip-path:polygon(50% 0,100% 25%,100% 75%,50% 100%,0 75%,0 25%);background:radial-gradient(circle at 50% 30%,#0e2a31,#04090b 70%)}
.mark:after{content:"";position:relative;width:20px;height:26px;background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 20 26'%3E%3Cdefs%3E%3ClinearGradient id='g' x1='0' y1='0' x2='0' y2='1'%3E%3Cstop offset='0' stop-color='%23ffffff'/%3E%3Cstop offset='1' stop-color='%2319e3ff'/%3E%3C/linearGradient%3E%3C/defs%3E%3Cpath d='M12.5 0L1 15h7l-2 11L19 9.5h-7.2z' fill='url(%23g)'/%3E%3C/svg%3E") center/contain no-repeat;filter:drop-shadow(0 0 5px rgba(25,227,255,.9))}
.brand h1{margin:0;font-size:22px;line-height:1.05;font-weight:600;letter-spacing:.2px;color:var(--ink)}
.brand h1 .wm{font-weight:800;letter-spacing:.6px;color:var(--cy);text-shadow:0 0 14px rgba(25,227,255,.55);margin-right:2px}
.brand p{margin:6px 0 0;color:var(--cy2);opacity:.85;font-size:9.5px;font-weight:600;letter-spacing:3.4px}
nav{display:grid;grid-template-columns:repeat(3,1fr);gap:4px;margin-top:15px;padding:4px;border-radius:15px;background:rgba(255,255,255,.03);box-shadow:inset 0 0 0 1px var(--rule)}
nav a{padding:10px 6px;border-radius:11px;color:var(--mute);text-align:center;text-decoration:none;font-size:12px;font-weight:600;letter-spacing:1.4px;text-transform:uppercase;transition:background .2s,color .2s}
nav a.active{color:#021014;background:linear-gradient(180deg,var(--cy2),var(--cy) 55%,#08b9d6);box-shadow:inset 0 1px 0 rgba(255,255,255,.55),0 0 18px rgba(25,227,255,.45)}
main,.detail{padding:16px 14px calc(56px + env(safe-area-inset-bottom))}
.tools{display:flex;justify-content:space-between;align-items:center;gap:10px;margin:2px 2px 14px}
#status{display:flex;align-items:center;gap:8px;color:var(--ink2);font-size:11px;font-weight:500;letter-spacing:1px;text-transform:uppercase}
#status:before{content:"";width:7px;height:7px;border-radius:50%;background:var(--cy);box-shadow:0 0 0 3px rgba(25,227,255,.16),0 0 10px var(--cy);animation:pulse 1.6s ease-in-out infinite}
#refresh{display:grid;place-items:center;width:40px;height:40px;border:0;border-radius:50%;background:linear-gradient(180deg,#0e1a1e,#071013);color:var(--cy);font-size:20px;line-height:1;cursor:pointer;box-shadow:inset 0 0 0 1px var(--edge),0 0 14px rgba(25,227,255,.18)}
#refresh:active{transform:rotate(-30deg) scale(.96)}
.list{display:grid;gap:13px}
.match{position:relative;display:block;width:100%;padding:0;text-align:left;color:var(--ink);background:linear-gradient(180deg,var(--panel),var(--panel2));border:0;border-radius:20px;overflow:hidden;cursor:pointer;box-shadow:inset 0 0 0 1px var(--rule),inset 0 1px 0 rgba(255,255,255,.04),0 16px 30px -12px rgba(0,0,0,.8);transition:transform .15s}
.match:active{transform:scale(.988)}
.match:before{content:"";position:absolute;inset:0 0 auto 0;height:2px;background:linear-gradient(90deg,transparent,rgba(25,227,255,.55),transparent)}
.match.is-live{box-shadow:inset 0 0 0 1px var(--edge),inset 0 1px 0 rgba(255,255,255,.05),0 16px 30px -12px rgba(0,0,0,.8),0 0 22px -8px rgba(25,227,255,.35)}
.match.is-live:before{height:2px;background:linear-gradient(90deg,var(--blue),var(--cy) 45%,var(--cy2) 70%,transparent);box-shadow:0 0 10px var(--cy)}
.match-top{display:flex;justify-content:space-between;gap:10px;align-items:center;padding:14px 14px 6px;font-size:10.5px;color:var(--ink2)}
.match-top>span{display:flex;align-items:center;gap:8px;min-width:0}
.fmt{flex:none;padding:3px 7px;border-radius:6px;background:rgba(25,227,255,.1);color:var(--cy2);font-style:normal;font-size:9.5px;font-weight:700;letter-spacing:1.2px;box-shadow:inset 0 0 0 1px rgba(25,227,255,.35)}
.lg{overflow:hidden;white-space:nowrap;text-overflow:ellipsis;font-weight:600;letter-spacing:.8px;text-transform:uppercase;color:var(--ink2)}
.badge{flex:none;display:inline-flex;align-items:center;gap:6px;padding:4px 9px;border-radius:999px;font-style:normal;font-size:9.5px;font-weight:700;letter-spacing:1.4px;text-transform:uppercase;color:var(--ink2);background:rgba(255,255,255,.04);box-shadow:inset 0 0 0 1px rgba(180,203,208,.22)}
.badge.live{color:#021014;background:linear-gradient(180deg,var(--cy2),var(--cy));box-shadow:0 0 12px rgba(25,227,255,.55);animation:glow 1.6s ease-in-out infinite}
.badge.live i{width:6px;height:6px;border-radius:50%;background:#021014;animation:pulse 1.3s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.3;transform:scale(.65)}}
@keyframes glow{0%,100%{box-shadow:0 0 6px rgba(25,227,255,.4)}50%{box-shadow:0 0 16px rgba(25,227,255,.85)}}
.team{display:flex;align-items:center;gap:12px;padding:9px 14px}
.team+.team{border-top:1px solid var(--rule)}
.crest{position:relative;isolation:isolate;flex:0 0 40px;display:grid;place-items:center;width:40px;height:44px;font-size:11px;font-weight:700;letter-spacing:.5px;color:var(--cy2);clip-path:polygon(50% 0,100% 25%,100% 75%,50% 100%,0 75%,0 25%);background:linear-gradient(160deg,rgba(138,243,255,.75),rgba(25,227,255,.35) 50%,rgba(47,125,255,.6))}
.crest:before{content:"";position:absolute;inset:1.5px;z-index:-1;clip-path:polygon(50% 0,100% 25%,100% 75%,50% 100%,0 75%,0 25%);background:radial-gradient(circle at 50% 28%,#123038,#060c0e 72%)}
.team.home .crest{color:#021014;background:linear-gradient(160deg,var(--cy2),var(--cy) 50%,var(--blue))}
.team.home .crest:before{background:radial-gradient(circle at 50% 25%,#bff8ff,var(--cy) 60%,#10a9c4)}
.tname{flex:1;min-width:0}.team strong{display:block;font-family:'Sora','Space Grotesk',Arial,sans-serif;font-size:16px;font-weight:700;line-height:1.15;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;color:var(--ink)}
.team .tname small{display:block;margin-top:3px;color:var(--mute);font-size:10.5px;font-weight:500;letter-spacing:1px}
.number{flex:none;text-align:right}.number b{display:block;font-size:26px;font-weight:700;line-height:1;color:#fff;letter-spacing:-.4px;font-variant-numeric:tabular-nums}.number small{display:block;margin-top:4px;color:var(--mute);font-size:10.5px;letter-spacing:.6px}
.match.is-live .team.home .number b{text-shadow:0 0 14px rgba(25,227,255,.45)}
.match-foot{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:4px;padding:9px 14px 10px;font-size:10.5px;font-weight:600;letter-spacing:1.3px;text-transform:uppercase;color:var(--mute);background:rgba(0,0,0,.25);border-top:1px solid var(--rule)}
.match.is-live .match-foot span:first-child{color:var(--cy)}
.go{display:grid;place-items:center;width:22px;height:22px;border-radius:50%;background:rgba(25,227,255,.1);color:var(--cy);font-size:15px;line-height:1;padding-bottom:2px;box-shadow:inset 0 0 0 1px rgba(25,227,255,.35)}
.empty{padding:30px 18px;border-radius:20px;background:linear-gradient(180deg,var(--panel),var(--panel2));color:var(--ink2);text-align:center;font-size:14px;box-shadow:inset 0 0 0 1px var(--rule)}
.detail[hidden]{display:none}
.back{display:inline-flex;align-items:center;gap:6px;padding:9px 15px;border-radius:999px;border:0;background:rgba(25,227,255,.08);color:var(--cy2);font-size:11px;font-weight:600;letter-spacing:1.6px;cursor:pointer;box-shadow:inset 0 0 0 1px rgba(25,227,255,.45),0 0 14px rgba(25,227,255,.15)}
.scorehero{position:relative;margin-top:14px;padding:16px 16px 6px;border-radius:22px;overflow:hidden;color:var(--ink);background:radial-gradient(110% 90% at 100% 0,rgba(25,227,255,.2),transparent 55%),radial-gradient(90% 80% at 0 100%,rgba(47,125,255,.14),transparent 60%),linear-gradient(160deg,#0c1a1f,#060c0f 60%,#030607);box-shadow:inset 0 0 0 1px rgba(25,227,255,.4),0 0 26px -6px rgba(25,227,255,.35),0 18px 34px -14px rgba(0,0,0,.8)}
.scorehero:before{content:"";position:absolute;inset:0 0 auto;height:2px;background:linear-gradient(90deg,var(--blue),var(--cy) 45%,var(--cy2));box-shadow:0 0 10px var(--cy)}
.scorehero h2{margin:2px 0 6px;font-size:15px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;color:var(--ink)}
.scorehero p{display:inline-block;margin:0 0 10px;padding:3px 9px;border-radius:999px;font-size:9.5px;font-weight:700;letter-spacing:1.4px;text-transform:uppercase;color:#021014;background:linear-gradient(180deg,var(--cy2),var(--cy));box-shadow:0 0 12px rgba(25,227,255,.5)}
.detail-team{display:flex;align-items:center;gap:12px;padding:12px 0;border-top:1px solid var(--rule)}
.detail-team .crest{font-style:normal;flex-basis:44px;width:44px;height:48px}
.detail-team.home .crest{color:#021014;background:linear-gradient(160deg,var(--cy2),var(--cy) 50%,var(--blue))}
.detail-team.home .crest:before{background:radial-gradient(circle at 50% 25%,#bff8ff,var(--cy) 60%,#10a9c4)}
.detail-team span{flex:1;min-width:0;font-family:'Sora','Space Grotesk',Arial,sans-serif;font-size:16px;font-weight:700}.detail-team span small{display:block;margin-top:3px;font-family:'Space Grotesk',Arial,sans-serif;font-size:11px;font-weight:500;letter-spacing:.8px;color:var(--mute)}
.detail-team b{font-size:30px;font-weight:700;color:#fff;letter-spacing:-.4px;font-variant-numeric:tabular-nums}
.detail-team.home b{text-shadow:0 0 16px rgba(25,227,255,.5)}
.innings{position:relative;margin-top:13px;padding:15px 14px 10px;border-radius:20px;background:linear-gradient(180deg,var(--panel),var(--panel2));box-shadow:inset 0 0 0 1px var(--rule),0 16px 30px -14px rgba(0,0,0,.8)}
.innings h3{margin:0;font-size:14px;font-weight:700;letter-spacing:.6px;text-transform:uppercase;color:var(--ink)}.innings h3 b{color:var(--cy);font-weight:700;text-shadow:0 0 10px rgba(25,227,255,.45)}
.innings p{margin:4px 0 0;color:var(--mute);font-size:10.5px;letter-spacing:1px;text-transform:uppercase}
.stat-table{width:100%;border-collapse:separate;border-spacing:0;margin-top:12px;font-size:13px;font-variant-numeric:tabular-nums}
.stat-table th,.stat-table td{padding:8px 5px;text-align:right}
.stat-table th:first-child,.stat-table td:first-child{text-align:left;padding-left:9px}.stat-table th:last-child,.stat-table td:last-child{padding-right:9px}
.stat-table th{font-size:9.5px;font-weight:700;letter-spacing:1.3px;color:var(--cy2);background:rgba(25,227,255,.08)}
.stat-table th:first-child{border-radius:9px 0 0 9px}.stat-table th:last-child{border-radius:0 9px 9px 0}
.stat-table td{border-bottom:1px solid var(--rule);color:var(--ink2)}.stat-table td:first-child{font-weight:600;color:var(--ink)}
.stat-table td:nth-child(2){color:#fff;font-weight:700}
.stat-table tr:last-child td{border-bottom:0}
"""


_SCORE_JS = r"""
const tg=window.Telegram&&window.Telegram.WebApp;if(tg){try{tg.ready();tg.expand();tg.setHeaderColor('#070a0b');tg.setBackgroundColor('#040607')}catch(e){}}
let mode=START_MODE,matches=[],selected='';const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const shown=s=>s===null||s===undefined||s===''?'—':esc(s);
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
