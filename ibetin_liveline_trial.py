import hashlib
import hmac
import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import CommandHandler

import ibetin_ui_start as base

logger = logging.getLogger(__name__)

LIVELINE_PATH = "/admin/liveline"
LIVELINE_API_PATH = "/admin/liveline/api"
HIGHLIGHTLY_BASE = "https://sports.highlightly.net"
DUBAI_TZ = ZoneInfo("Asia/Dubai")
LIVE_STATES = {"in play", "stumps", "lunch", "innings break", "drinks", "timeout", "tea", "match delayed"}
UPCOMING_STATES = {"scheduled", "not started", "to be announced"}
FINISHED_STATES = {"finished", "finished after extra time", "finished after penalties"}

_cache = {}
_cache_lock = threading.Lock()


def _token() -> str:
    secret = os.getenv("BOT_TOKEN", "").strip()
    if not secret:
        return ""
    payload = f"ibetin-liveline-v1:{base.core.ADMIN_USER_ID}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def admin_url() -> str:
    root = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/") or "https://ibetin-app-production.up.railway.app"
    return f"{root}{LIVELINE_PATH}?{urlencode({'t': _token(), 'v': '20260916-v1'})}"


def _authorized(path: str) -> bool:
    expected = _token()
    supplied = (parse_qs(urlparse(path).query).get("t") or [""])[0]
    return bool(expected) and hmac.compare_digest(expected, supplied)


def _send_json(handler, status: int, payload) -> None:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Robots-Tag", "noindex, nofollow")
    handler.end_headers()
    handler.wfile.write(data)


def _send_html(handler, status: int, html: str) -> None:
    data = html.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
    handler.send_header("Pragma", "no-cache")
    handler.send_header("X-Robots-Tag", "noindex, nofollow")
    handler.end_headers()
    handler.wfile.write(data)


def _cache_get(key: str):
    with _cache_lock:
        item = _cache.get(key)
        if not item:
            return None
        expires, value = item
        if expires < time.time():
            _cache.pop(key, None)
            return None
        return value


def _cache_put(key: str, value, ttl: int):
    with _cache_lock:
        _cache[key] = (time.time() + ttl, value)


def _highlightly(path: str, params=None, ttl: int = 45):
    api_key = os.getenv("HIGHLIGHTLY_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("HIGHLIGHTLY_API_KEY is not configured")
    params = params or {}
    url = f"{HIGHLIGHTLY_BASE}{path}"
    if params:
        url += "?" + urlencode(params)
    cached = _cache_get(url)
    if cached is not None:
        return cached
    req = Request(url, headers={"x-rapidapi-key": api_key, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", "replace")[:500]
        except Exception:
            pass
        raise RuntimeError(f"Highlightly HTTP {exc.code}: {body or exc.reason}") from exc
    except URLError as exc:
        raise RuntimeError(f"Highlightly network error: {exc.reason}") from exc
    data = payload.get("data") if isinstance(payload, dict) and "data" in payload else payload
    _cache_put(url, data, ttl)
    return data


def _team(match, side: str):
    obj = (match or {}).get(f"{side}Team") or {}
    if not isinstance(obj, dict):
        obj = {}
    return {"id": str(obj.get("id") or ""), "name": str(obj.get("name") or obj.get("displayName") or side.title()), "abbr": str(obj.get("abbreviation") or ""), "logo": str(obj.get("logo") or "")}


def _state(match):
    obj = (match or {}).get("state") or {}
    return obj if isinstance(obj, dict) else {}


def _state_text(match):
    return str(_state(match).get("description") or "").strip()


def _side_score(match, side: str):
    teams = _state(match).get("teams") or {}
    obj = teams.get(side) if isinstance(teams, dict) else {}
    if not isinstance(obj, dict):
        obj = {}
    return {"score": str(obj.get("score") or ""), "info": str(obj.get("info") or "")}


def _league(match):
    obj = (match or {}).get("league") or {}
    if not isinstance(obj, dict):
        obj = {}
    return {"id": str(obj.get("id") or ""), "name": str(obj.get("name") or ""), "season": obj.get("season"), "logo": str(obj.get("logo") or "")}


def _normalize_match(match):
    if not isinstance(match, dict):
        return {}
    home_score = _side_score(match, "home")
    away_score = _side_score(match, "away")
    return {
        "id": str(match.get("id") or ""), "format": str(match.get("format") or ""), "dayType": str(match.get("dayType") or ""),
        "startDate": str(match.get("startDate") or ""), "startTime": str(match.get("startTime") or ""), "endDate": str(match.get("endDate") or ""),
        "country": match.get("country") if isinstance(match.get("country"), dict) else {}, "league": _league(match), "home": _team(match, "home"), "away": _team(match, "away"),
        "state": _state_text(match), "report": str(_state(match).get("report") or ""), "homeScore": home_score["score"], "homeInfo": home_score["info"], "awayScore": away_score["score"], "awayInfo": away_score["info"],
    }


def _matches_for_date(date_text: str):
    data = _highlightly("/cricket/matches", {"date": date_text, "timezone": "Asia/Dubai", "limit": 100, "offset": 0}, ttl=45)
    return data if isinstance(data, list) else []


def _matches_mode(mode: str):
    today = datetime.now(DUBAI_TZ).date()
    if mode == "live":
        dates = [today]
    elif mode == "upcoming":
        dates = [today + timedelta(days=i) for i in range(4)]
    elif mode == "results":
        dates = [today - timedelta(days=i) for i in range(3)]
    else:
        raise ValueError("Unknown matches mode")
    raw, seen = [], set()
    for date_obj in dates:
        for match in _matches_for_date(date_obj.isoformat()):
            if not isinstance(match, dict):
                continue
            key = str(match.get("id") or repr(match))
            if key in seen:
                continue
            seen.add(key)
            state = _state_text(match).casefold()
            if mode == "live" and state not in LIVE_STATES:
                continue
            if mode == "upcoming" and state not in UPCOMING_STATES:
                continue
            if mode == "results" and state not in FINISHED_STATES:
                continue
            raw.append(match)
    raw.sort(key=lambda x: str(x.get("startTime") or x.get("startDate") or ""), reverse=(mode == "results"))
    return [_normalize_match(x) for x in raw[:40]]


def _extract_timeline(match):
    state = match.get("state") if isinstance(match.get("state"), dict) else {}
    inplay = match.get("inplayData") if isinstance(match.get("inplayData"), dict) else {}
    candidates = [match.get("commentary"), match.get("events"), match.get("balls"), match.get("deliveries"), match.get("playByPlay"), state.get("events"), inplay.get("events"), inplay.get("commentary")]
    for value in candidates:
        if isinstance(value, list) and value:
            return value[-30:]
    return []


def _match_detail(match_id: str):
    if not match_id or not match_id.isdigit():
        raise ValueError("Invalid match id")
    data = _highlightly(f"/cricket/matches/{match_id}", ttl=45)
    match = data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else {})
    if not isinstance(match, dict):
        match = {}
    return {
        "match": _normalize_match(match), "venue": match.get("venue") if isinstance(match.get("venue"), dict) else {}, "forecast": match.get("forecast") if isinstance(match.get("forecast"), dict) else {},
        "statistics": match.get("statistics") if isinstance(match.get("statistics"), list) else [], "squad": match.get("squad") if isinstance(match.get("squad"), list) else [],
        "bestBatsmen": match.get("bestBatsmen") if isinstance(match.get("bestBatsmen"), list) else [], "bestBowlers": match.get("bestBowlers") if isinstance(match.get("bestBowlers"), list) else [],
        "inplayData": match.get("inplayData") if isinstance(match.get("inplayData"), dict) else {}, "timeline": _extract_timeline(match),
    }


def _api(handler):
    q = parse_qs(urlparse(handler.path).query)
    action = (q.get("action") or ["matches"])[0].strip().lower()
    try:
        if action == "matches":
            mode = (q.get("mode") or ["live"])[0].strip().lower()
            payload = {"ok": True, "mode": mode, "generatedAt": datetime.now(DUBAI_TZ).isoformat(), "matches": _matches_mode(mode)}
        elif action == "match":
            match_id = (q.get("id") or [""])[0].strip()
            payload = {"ok": True, "generatedAt": datetime.now(DUBAI_TZ).isoformat(), "detail": _match_detail(match_id)}
        else:
            _send_json(handler, 400, {"ok": False, "error": "Unknown action"})
            return
        _send_json(handler, 200, payload)
    except ValueError as exc:
        _send_json(handler, 400, {"ok": False, "error": str(exc)})
    except Exception as exc:
        logger.exception("IBETIN Live Line API failure")
        _send_json(handler, 502, {"ok": False, "error": str(exc)[:300]})


def _page() -> str:
    return r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no"><meta http-equiv="Cache-Control" content="no-store, no-cache, must-revalidate"><meta name="referrer" content="no-referrer"><title>IBETIN Live Line · Admin V1</title><script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
:root{--bg:#07101b;--card:#101d2d;--line:#26394f;--text:#f6f9fc;--muted:#93a7bc;--red:#ff4d5e}*{box-sizing:border-box}html,body{margin:0;min-height:100%;background:var(--bg);color:var(--text);font-family:Arial,Helvetica,sans-serif}body{padding:12px 12px 90px}.wrap{max-width:760px;margin:0 auto}.top{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:4px 2px 12px}.brand{font-weight:950;letter-spacing:.35px;font-size:17px}.badge{font-size:10px;font-weight:900;border:1px solid #37506a;border-radius:999px;padding:6px 9px;color:#c8d6e5}.hero{background:linear-gradient(145deg,#14263a,#0e1a29);border:1px solid var(--line);border-radius:20px;padding:16px;margin-bottom:12px}.hero h1{font-size:25px;margin:0 0 6px}.hero p{margin:0;color:var(--muted);font-size:12px;line-height:1.45}.tabs{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin:12px 0}.tab{border:1px solid var(--line);background:#0d1927;color:#b9c9d9;border-radius:12px;padding:11px 6px;font-size:12px;font-weight:900}.tab.active{background:#f7fafc;color:#0a1420}.status{font-size:11px;color:var(--muted);padding:2px 4px 8px}.list{display:grid;gap:10px}.match{border:1px solid var(--line);background:var(--card);border-radius:18px;padding:14px;cursor:pointer}.meta{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:10px}.league{font-size:11px;color:#a9bdd0;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.live{font-size:9px;font-weight:950;color:#fff;background:var(--red);border-radius:999px;padding:5px 8px}.state{font-size:9px;font-weight:950;color:#08111b;background:#dce8f4;border-radius:999px;padding:5px 8px}.team{display:grid;grid-template-columns:1fr auto;gap:10px;align-items:center;margin:8px 0}.teamname{font-size:15px;font-weight:900}.score{font-size:17px;font-weight:950;text-align:right}.info{font-size:10px;color:var(--muted);margin-top:2px}.report{font-size:11px;color:#d6e1eb;border-top:1px solid #22364b;padding-top:9px;margin-top:9px;line-height:1.4}.empty,.error{border:1px dashed #35506b;border-radius:18px;padding:28px 18px;text-align:center;color:var(--muted)}.detailHead{border:1px solid var(--line);background:var(--card);border-radius:18px;padding:15px;margin-bottom:10px}.back{border:0;background:#1a2b40;color:#fff;border-radius:10px;padding:9px 11px;font-weight:900;margin-bottom:11px}.vs{font-size:11px;color:var(--muted);margin-bottom:5px}.bigScore{font-size:22px;font-weight:950;line-height:1.35}.sub{font-size:11px;color:var(--muted);margin-top:5px}.detailTabs{display:flex;gap:6px;overflow:auto;padding-bottom:6px;margin-bottom:8px}.detailTab{white-space:nowrap;border:1px solid var(--line);background:#0d1927;color:#b9c9d9;border-radius:11px;padding:9px 11px;font-size:10px;font-weight:900}.detailTab.active{background:#f6f9fc;color:#08111b}.panel{border:1px solid var(--line);background:var(--card);border-radius:18px;padding:14px}.panel h3{margin:0 0 10px;font-size:14px}.livegrid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.mini{background:#0b1725;border:1px solid #22364b;border-radius:13px;padding:11px}.mini b{font-size:13px}.mini span{display:block;color:var(--muted);font-size:10px;margin-top:4px}.notice{background:#0b1725;border:1px dashed #35506b;border-radius:13px;padding:12px;color:#b6c7d7;font-size:11px;line-height:1.45;margin-top:10px}.innings{margin-top:10px;border-top:1px solid #26394f;padding-top:10px}.innTitle{display:flex;justify-content:space-between;gap:8px;font-weight:950;font-size:13px;margin-bottom:8px}.table{width:100%;border-collapse:collapse;font-size:10px}.table th,.table td{padding:7px 4px;border-bottom:1px solid #213449;text-align:right}.table th:first-child,.table td:first-child{text-align:left}.table th{color:#89a1b7;font-size:9px}.pillrow{display:flex;gap:6px;flex-wrap:wrap}.pill{border:1px solid #30475f;border-radius:999px;padding:6px 8px;font-size:10px;color:#c8d7e5}.loading{padding:34px;text-align:center;color:var(--muted)}.spin{width:24px;height:24px;border:3px solid #23384f;border-top-color:#fff;border-radius:50%;animation:s .7s linear infinite;margin:0 auto 10px}@keyframes s{to{transform:rotate(360deg)}}.footer{position:fixed;left:0;right:0;bottom:0;background:rgba(7,16,27,.94);backdrop-filter:blur(10px);border-top:1px solid #203348;padding:8px 12px}.footInner{max-width:760px;margin:0 auto;display:flex;justify-content:space-between;color:#7f96ac;font-size:10px}
</style></head><body><div class="wrap"><div class="top"><div class="brand">⚡ IBETIN LIVE LINE</div><div class="badge">ADMIN V1</div></div><section class="hero"><h1>Cricket Match Center</h1><p>Live score · scorecard · in-play data · upcoming · results. Public IBETIN menu is untouched.</p></section><div id="home"><div class="tabs"><button class="tab active" data-mode="live">🔴 LIVE</button><button class="tab" data-mode="upcoming">🗓 UPCOMING</button><button class="tab" data-mode="results">✅ RESULTS</button></div><div class="status" id="status">Loading cricket data…</div><div class="list" id="list"></div></div><div id="detail" style="display:none"></div></div><div class="footer"><div class="footInner"><span>IBETIN · private preview</span><span id="clock"></span></div></div>
<script>
const tg=window.Telegram&&window.Telegram.WebApp;if(tg){try{tg.ready();tg.expand();tg.setHeaderColor('#07101b');tg.setBackgroundColor('#07101b')}catch(e){}}const qs=new URLSearchParams(location.search);const TOKEN=qs.get('t')||'';let currentMode='live',currentDetail=null,currentTab='live';const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));const n=v=>v===null||v===undefined||v===''?'—':esc(v);function api(params){params.t=TOKEN;return fetch('/admin/liveline/api?'+new URLSearchParams(params),{cache:'no-store'}).then(async r=>{const j=await r.json();if(!r.ok||!j.ok)throw new Error(j.error||('HTTP '+r.status));return j})}function loading(el){el.innerHTML='<div class="loading"><div class="spin"></div>Loading…</div>'}function fmtTime(raw){if(!raw)return'';try{return new Intl.DateTimeFormat(undefined,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}).format(new Date(raw))}catch(e){return raw}}function teamLine(t,score,info){return `<div class="team"><div><div class="teamname">${esc(t.name||t.abbr||'Team')}</div><div class="info">${esc(t.abbr||'')}</div></div><div><div class="score">${n(score)}</div><div class="info">${esc(info||'')}</div></div></div>`}function renderMatches(items,mode){const list=document.getElementById('list');if(!items.length){list.innerHTML=`<div class="empty">${mode==='live'?'No live cricket matches right now.':mode==='upcoming'?'No upcoming matches found in the next few days.':'No recent results found.'}</div>`;return}list.innerHTML=items.map(m=>`<div class="match" data-id="${esc(m.id)}"><div class="meta"><div class="league">${esc(m.league?.name||m.format||'Cricket')}</div>${mode==='live'?'<div class="live">● LIVE</div>':`<div class="state">${esc(m.state||fmtTime(m.startTime))}</div>`}</div>${teamLine(m.home,m.homeScore,m.homeInfo)}${teamLine(m.away,m.awayScore,m.awayInfo)}<div class="report">${esc(m.report||fmtTime(m.startTime)||m.state||'')}</div></div>`).join('');list.querySelectorAll('.match').forEach(x=>x.addEventListener('click',()=>openMatch(x.dataset.id)))}async function loadMode(mode){currentMode=mode;document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('active',b.dataset.mode===mode));const list=document.getElementById('list');loading(list);document.getElementById('status').textContent='Refreshing '+mode+' cricket…';try{const j=await api({action:'matches',mode});renderMatches(j.matches||[],mode);document.getElementById('status').textContent=`${(j.matches||[]).length} match${(j.matches||[]).length===1?'':'es'} · updated ${new Date(j.generatedAt).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}`}catch(e){list.innerHTML=`<div class="error">Could not load cricket data.<br><br>${esc(e.message)}</div>`;document.getElementById('status').textContent='Feed error'}}document.querySelectorAll('.tab').forEach(b=>b.addEventListener('click',()=>loadMode(b.dataset.mode)));async function openMatch(id){document.getElementById('home').style.display='none';const d=document.getElementById('detail');d.style.display='block';loading(d);try{const j=await api({action:'match',id});currentDetail=j.detail;currentTab='live';renderDetail()}catch(e){d.innerHTML=`<button class="back" onclick="backHome()">← MATCH CENTER</button><div class="error">Could not load match detail.<br><br>${esc(e.message)}</div>`}}function backHome(){document.getElementById('detail').style.display='none';document.getElementById('home').style.display='block'}function tabs(){return ['live','scorecard','commentary','stats','info'].map(x=>`<button class="detailTab ${currentTab===x?'active':''}" data-tab="${x}">${x.toUpperCase()}</button>`).join('')}function renderDetail(){const d=document.getElementById('detail'),m=currentDetail.match||{};d.innerHTML=`<button class="back" onclick="backHome()">← MATCH CENTER</button><div class="detailHead"><div class="vs">${esc(m.league?.name||'Cricket')} · ${esc(m.format||'')}</div><div class="bigScore">${esc(m.home?.name||'Home')} ${n(m.homeScore)}<br>${esc(m.away?.name||'Away')} ${n(m.awayScore)}</div><div class="sub">${esc(m.report||m.state||'')} ${m.startTime?'· '+esc(fmtTime(m.startTime)):''}</div></div><div class="detailTabs">${tabs()}</div><div id="panel" class="panel"></div>`;d.querySelectorAll('.detailTab').forEach(b=>b.addEventListener('click',()=>{currentTab=b.dataset.tab;renderDetail()}));renderPanel()}function playerName(obj){return obj?.player?.name||obj?.name||'Player'}function renderPanel(){const p=document.getElementById('panel'),x=currentDetail||{},m=x.match||{};if(currentTab==='live'){const bats=x.inplayData?.batsmen||[],bowls=x.inplayData?.bowlers||[];const cards=[...bats.slice(0,2).map(v=>`<div class="mini"><b>🏏 ${esc(playerName(v))}</b><span>${n(v.player?.statistics?.runs)} runs · ${n(v.player?.statistics?.balls)} balls · SR ${n(v.player?.statistics?.strikeRate)}</span></div>`),...bowls.slice(0,1).map(v=>`<div class="mini"><b>🎯 ${esc(playerName(v))}</b><span>${n(v.player?.statistics?.overs)} ov · ${n(v.player?.statistics?.wickets)} wkts · Econ ${n(v.player?.statistics?.economy)}</span></div>`)].join('');p.innerHTML=`<h3>⚡ LIVE LINE</h3><div class="livegrid">${cards||'<div class="mini"><b>Live player data</b><span>Waiting for in-play player data.</span></div>'}</div><div class="notice"><b>${esc(m.state||'Match status')}</b><br>${esc(m.report||'Live score updates are coming from the connected cricket feed.')}</div>`}else if(currentTab==='scorecard'){p.innerHTML='<h3>📊 SCORECARD</h3>'+scorecardHtml(x.statistics||[])}else if(currentTab==='commentary'){const tl=x.timeline||[];p.innerHTML='<h3>💬 BALL-BY-BALL</h3>'+(tl.length?tl.slice().reverse().map((e,i)=>`<div class="notice"><b>${esc(e.over||e.ball||e.time||('#'+(i+1)))}</b><br>${esc(e.commentary||e.description||e.text||e.event||JSON.stringify(e).slice(0,220))}</div>`).join(''):'<div class="notice">The current source is not exposing a delivery-by-delivery timeline for this match. The IBETIN UI is ready for a dedicated ball-by-ball feed; live score and player data continue to work from the current source.</div>')}else if(currentTab==='stats'){p.innerHTML='<h3>📈 MATCH STATS</h3>'+statsHtml(x.statistics||[])}else{const v=x.venue||{},f=x.forecast||{};p.innerHTML=`<h3>ℹ️ MATCH INFO</h3><div class="pillrow"><span class="pill">${esc(m.format||'Cricket')}</span><span class="pill">${esc(m.state||'')}</span><span class="pill">${esc(m.league?.name||'')}</span></div><div class="notice"><b>Venue</b><br>${esc(v.name||'—')}${v.city?' · '+esc(v.city):''}${v.country?' · '+esc(v.country):''}</div><div class="notice"><b>Weather</b><br>${esc(f.status||'—')}${f.temperature?' · '+esc(f.temperature):''}</div>`}}function scorecardHtml(stats){if(!stats.length)return '<div class="notice">Scorecard data is not available for this match yet.</div>';return stats.map((inn,i)=>{const bats=inn.inningBatsmen||[],bowl=inn.inningBowlers||[];return `<div class="innings"><div class="innTitle"><span>${esc(inn.name||inn.abbreviation||('Innings '+(inn.inningNumber||i+1)))}</span><span>${n(inn.inningNumber?'#'+inn.inningNumber:'')}</span></div><table class="table"><thead><tr><th>BATTER</th><th>R</th><th>B</th><th>4</th><th>6</th><th>SR</th></tr></thead><tbody>${bats.map(b=>`<tr><td>${esc(playerName(b))}</td><td>${n(b.runs)}</td><td>${n(b.balls)}</td><td>${n(b.fours)}</td><td>${n(b.sixes)}</td><td>${n(b.battingStrikeRate)}</td></tr>`).join('')}</tbody></table><table class="table" style="margin-top:8px"><thead><tr><th>BOWLER</th><th>O</th><th>R</th><th>W</th><th>ECON</th></tr></thead><tbody>${bowl.map(b=>`<tr><td>${esc(playerName(b))}</td><td>${n(b.overs)}</td><td>${n(b.concededRuns??b.runsConceded)}</td><td>${n(b.wickets)}</td><td>${n(b.economy)}</td></tr>`).join('')}</tbody></table></div>`}).join('')}function statsHtml(stats){if(!stats.length)return '<div class="notice">Detailed innings statistics are not available for this match yet.</div>';return stats.map((inn,i)=>`<div class="innings"><div class="innTitle"><span>${esc(inn.name||inn.abbreviation||('Innings '+(inn.inningNumber||i+1)))}</span></div><div class="pillrow"><span class="pill">4s: ${n(inn.fours)}</span><span class="pill">6s: ${n(inn.sixes)}</span><span class="pill">Extras: ${n(inn.extras)}</span><span class="pill">Wides: ${n(inn.wides)}</span><span class="pill">No-balls: ${n(inn.noBalls)}</span></div>${(inn.inningPartnerships||[]).slice(-3).reverse().map(q=>`<div class="notice"><b>Partnership</b> · ${n(q.runs)} runs / ${n(q.balls)} balls<br>${esc(q.firstPlayer?.name||'')} + ${esc(q.secondPlayer?.name||'')}</div>`).join('')}</div>`).join('')}setInterval(()=>document.getElementById('clock').textContent=new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}),1000);loadMode('live');
</script></body></html>'''


def _install_route():
    handler_cls = base.ibetin_start.ibetin_entry.analytics.TrackingHandler
    if getattr(handler_cls, "_ibetin_liveline_v1_installed", False):
        return
    previous_get = handler_cls.do_GET
    def routed_get(self):
        parsed = urlparse(self.path)
        if parsed.path == LIVELINE_PATH:
            if not _authorized(self.path):
                _send_html(self, 403, "<h3>IBETIN Live Line preview link is invalid.</h3>")
                return
            _send_html(self, 200, _page())
            return
        if parsed.path == LIVELINE_API_PATH:
            if not _authorized(self.path):
                _send_json(self, 403, {"ok": False, "error": "Invalid preview token"})
                return
            _api(self)
            return
        previous_get(self)
    handler_cls.do_GET = routed_get
    handler_cls._ibetin_liveline_v1_installed = True
    logger.info("IBETIN admin Live Line V1 route installed at %s", LIVELINE_PATH)


async def liveline_command(update, context):
    user, message, chat = update.effective_user, update.effective_message, update.effective_chat
    if not user or not message or not chat:
        return
    if getattr(chat, "type", "") != "private":
        await message.reply_text("This preview is available only in a private chat with the bot.")
        return
    logger.info("IBETIN Live Line V1 preview accepted user_id=%s", user.id)
    await message.reply_text(
        "⚡ <b>IBETIN LIVE LINE · ADMIN V1</b>\n━━━━━━━━━━━━━━━━━━\n\nPrivate preview of Live Matches, Match Detail, Scorecard, In-Play data, Upcoming and Results.\n\nThe public IBETIN menu has not been changed.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚡ OPEN LIVE LINE V1", web_app=WebAppInfo(url=admin_url()))]]),
        disable_web_page_preview=True,
    )


def install():
    _install_route()
    runtime = base._runtime
    if getattr(runtime, "_ibetin_liveline_v1_configured", False):
        return
    previous_config = runtime.configure_telegram_ui
    async def configure_with_liveline(application):
        await previous_config(application)
        application.add_handler(CommandHandler("liveline", liveline_command))
        logger.info("IBETIN /liveline admin preview command registered")
    runtime.configure_telegram_ui = configure_with_liveline
    runtime.app.configure_telegram_ui = configure_with_liveline
    runtime._ibetin_liveline_v1_configured = True
    logger.info("IBETIN Live Line V1 installed as hidden private preview")
