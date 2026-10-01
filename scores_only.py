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


def _score_card_html(row: dict, mode: str) -> str:
    home, away = row.get("home") or {}, row.get("away") or {}
    label = "● LIVE" if mode == "live" else _plain(row.get("state")) or mode.title()
    def team(value, score, info):
        return ('<div class="team"><div><strong>' + escape(_plain(value.get("name")))
                + '</strong><small>' + escape(_plain(value.get("abbr"), 24))
                + '</small></div><div class="number"><b>' + escape(_plain(score))
                + '</b><small>' + escape(_plain(info)) + '</small></div></div>')
    return (
        '<button type="button" class="match" data-id="' + escape(_plain(row.get("id")), quote=True)
        + '"><div class="match-top"><span>' + escape(_plain(row.get("format")))
        + ' · ' + escape(_plain(row.get("league"))) + '</span><em>'
        + escape(label) + '</em></div>'
        + team(home, row.get("home_score"), row.get("home_info"))
        + team(away, row.get("away_score"), row.get("away_info"))
        + '<div class="match-foot"><span>'
        + escape(_plain(row.get("state")))
        + '</span><span>›</span></div></button>'
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
        '<div><h1>' + title + ' Live Line</h1><p>MATCH SCORES</p></div></div>'
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
@import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700;800&family=Manrope:wght@400;500;600;700;800&display=swap');
*{box-sizing:border-box}html,body{margin:0;min-height:100%;font-family:'Manrope','Inter',Arial,Helvetica,sans-serif}
.brand h1,.scorehero h2,.innings h3{font-family:'Cinzel','Times New Roman',serif}
body{background:radial-gradient(circle at 50% -8%,#2a1f0c 0,#0f0b07 38%,#0a0806 78%);color:#f6ecd6}
button,a{font:inherit}.shell{max-width:760px;margin:auto;min-height:100vh}
.top{position:sticky;top:0;z-index:2;background:linear-gradient(125deg,#0a0806,#14100a 72%,#1c150b);padding:17px 16px 13px;border-bottom:1px solid #c9962b;box-shadow:0 12px 32px #00000088}
.brand{display:flex;align-items:center;gap:11px}.mark{display:grid;place-items:center;width:44px;height:44px;border-radius:13px;background:linear-gradient(135deg,#f5d27a,#c9962b 55%,#8a6414);font-size:23px}.brand h1{margin:0;font-size:20px;line-height:1.2;color:#f5d27a}.brand p{margin:4px 0 0;color:#c9962b;font-size:10px;font-weight:800;letter-spacing:1.5px}
nav{display:grid;grid-template-columns:repeat(3,1fr);gap:9px;margin-top:16px}nav a{padding:12px 7px;border-radius:13px;background:#14100a;border:1px solid #3a2c12;color:#cbbd9f;text-align:center;text-decoration:none;font-size:14px;font-weight:800}nav a.active{background:linear-gradient(135deg,#f5d27a,#c9962b 55%,#8a6414);border-color:#c9962b;color:#1a1206;box-shadow:0 8px 24px #c9962b33}
main,.detail{padding:16px 16px calc(55px + env(safe-area-inset-bottom))}.tools{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:12px}#status{color:#cbbd9f;font-size:12px}#refresh{width:44px;height:44px;border:1px solid #c9962b;border-radius:13px;background:#14100a;color:#f5d27a;font-size:26px;cursor:pointer}.list{display:grid;gap:12px}
.match{display:block;width:100%;padding:0;text-align:left;color:#f6ecd6;background:linear-gradient(180deg,#14100a,#0f0c08);border:1px solid #3a2c12;border-left:4px solid #c9962b;border-radius:18px;overflow:hidden;box-shadow:0 15px 34px #00000066;cursor:pointer}.match-top,.match-foot{display:flex;justify-content:space-between;gap:8px;align-items:center;padding:11px 14px;font-size:11px;color:#cbbd9f}.match-top span{font-weight:700}.match-top em{font-size:10px;font-style:normal;font-weight:800;color:#f5d27a}.match-foot{border-top:1px solid #2a2010}.team{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:9px 14px}.team strong{font-size:17px}.team small{display:block;color:#cbbd9f;font-size:11px;margin-top:2px}.number{text-align:right}.number b{font-size:26px;color:#f5d27a;letter-spacing:-.5px}
.empty{padding:28px 16px;border:1px solid #3a2c12;border-radius:18px;background:#14100a;color:#cbbd9f;text-align:center;font-size:14px}.detail[hidden]{display:none}.back{padding:10px 14px;border-radius:12px;border:1px solid #c9962b;background:#14100a;color:#f5d27a;font-weight:800;cursor:pointer}.scorehero,.innings{margin-top:12px;padding:16px;border:1px solid #3a2c12;border-radius:18px;background:linear-gradient(180deg,#14100a,#0f0c08)}.scorehero h2{margin:0 0 8px;font-size:17px;color:#f5d27a}.scorehero p{color:#cbbd9f;font-size:12px}.detail-team{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:10px 0;border-top:1px solid #2a2010}.detail-team b{font-size:22px;color:#f5d27a}.innings h3{margin:0 0 12px;font-size:15px;color:#f5d27a}.innings p{margin:0;color:#cbbd9f;font-size:13px}.stat-table{width:100%;border-collapse:collapse;margin-top:13px;font-size:12px}.stat-table th,.stat-table td{padding:8px 4px;border-top:1px solid #2a2010;text-align:right}.stat-table th:first-child,.stat-table td:first-child{text-align:left}.stat-table th{color:#cbbd9f}
"""


_SCORE_JS = r"""
const tg=window.Telegram&&window.Telegram.WebApp;if(tg){try{tg.ready();tg.expand();tg.setHeaderColor('#0a0806');tg.setBackgroundColor('#0a0806')}catch(e){}}
let mode=START_MODE,matches=[],selected='';const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const shown=s=>s===null||s===undefined||s===''?'—':esc(s);
async function api(p){const r=await fetch('/scores/api?'+new URLSearchParams(p),{cache:'no-store',credentials:'same-origin'});const j=await r.json();if(!r.ok||!j.ok)throw Error(j.error||'Feed temporarily unavailable');return j}
function card(m){const team=(t,score,info)=>`<div class="team"><div><strong>${esc(t?.name||'Team')}</strong><small>${esc(t?.abbr||'')}</small></div><div class="number"><b>${shown(score)}</b><small>${esc(info||'')}</small></div></div>`;return `<button type="button" class="match" data-id="${esc(m.id)}"><div class="match-top"><span>${esc(m.format||'CRICKET')} · ${esc(m.league||'Cricket')}</span><em>${mode==='live'?'● LIVE':esc(m.state||mode.toUpperCase())}</em></div>${team(m.home,m.home_score,m.home_info)}${team(m.away,m.away_score,m.away_info)}<div class="match-foot"><span>${esc(m.state||'')}</span><span>›</span></div></button>`}
function render(){const list=document.getElementById('list');list.innerHTML=matches.length?matches.map(card).join(''):'<div class="empty">No matches in this view right now.</div>'}
async function hydrateScores(view){const pending=matches.filter(m=>m.id&&(!m.home_score||!m.away_score)).slice(0,8);let next=0;async function worker(){while(next<pending.length&&mode===view){const item=pending[next++];try{const j=await api({action:'score',id:item.id,mode:view});if(mode!==view)return;const current=matches.find(m=>m.id===item.id);if(!current)continue;const s=j.match||{};for(const k of ['home_score','away_score','home_info','away_info','state'])if(!current[k]&&s[k])current[k]=s[k];render()}catch(e){}}}await Promise.all([worker(),worker()])}
async function load(next=mode){mode=next;document.querySelectorAll('nav a').forEach(a=>a.classList.toggle('active',a.dataset.mode===mode));const status=document.getElementById('status');status.textContent='Refreshing '+mode+' scores…';try{const j=await api({action:'matches',mode});matches=j.matches||[];render();status.textContent=`${matches.length} match${matches.length===1?'':'es'} · updated ${new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}`;history.replaceState(null,'','/scores?mode='+encodeURIComponent(mode));if(mode==='live')hydrateScores(mode)}catch(e){status.textContent='Feed temporarily unavailable';if(!matches.length)document.getElementById('list').innerHTML='<div class="empty">Match scores are temporarily unavailable. Please try again.</div>'}}
function table(items,labels,keys){if(!items?.length)return '';return `<table class="stat-table"><thead><tr>${labels.map(x=>`<th>${x}</th>`).join('')}</tr></thead><tbody>${items.map(x=>`<tr>${keys.map(k=>`<td>${shown(x[k])}</td>`).join('')}</tr>`).join('')}</tbody></table>`}
function detailHtml(d){const m=d.match||{};const team=(t,score,info)=>`<div class="detail-team"><span>${esc(t?.name||'Team')}<small>${esc(info||'')}</small></span><b>${shown(score)}</b></div>`;return `<button type="button" class="back">← MATCH CENTER</button><div class="scorehero"><h2>${esc(m.league||'Cricket')} · ${esc(m.format||'')}</h2><p>${esc(m.state||'Match score')}</p>${team(m.home,m.home_score,m.home_info)}${team(m.away,m.away_score,m.away_info)}</div>${(d.innings||[]).map(x=>`<section class="innings"><h3>${esc(x.name||'Innings')} · ${shown(x.score)}</h3><p>${x.overs?esc(x.overs)+' overs':''}</p>${table(x.batters,['BATTER','R','B','4','6'],['name','runs','balls','fours','sixes'])}${table(x.bowlers,['BOWLER','O','R','W'],['name','overs','runs','wickets'])}</section>`).join('')}`}
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
