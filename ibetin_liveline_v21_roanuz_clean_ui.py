import logging
import os
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode, urlparse

import ibetin_liveline_trial as liveline
import ibetin_liveline_v14_efficient as v14
import ibetin_liveline_v20_roanuz_primary_ui as v20

logger = logging.getLogger(__name__)
admin = v14.admin

liveline.LIVELINE_PATH = "/admin/liveline-ibetinv21"
liveline.LIVELINE_API_PATH = "/admin/liveline-ibetinv21/api"
_SAFE_KEY = re.compile(r"^[A-Za-z0-9_.:\-]{3,180}$")


def _admin_url() -> str:
    root = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/") or "https://ibetin-app-production.up.railway.app"
    return f"{root}{liveline.LIVELINE_PATH}?{urlencode({'t': liveline._token(), 'v': '20260917-v21-clean-roanuz'})}"


def _valid_key(value: str) -> bool:
    return bool(value and _SAFE_KEY.match(value))


def _clean_score(value):
    if value in (None, ""):
        return ""
    if isinstance(value, dict):
        runs = value.get("runs")
        if runs is None:
            runs = value.get("score")
        wickets = value.get("wickets")
        if wickets is None:
            wickets = value.get("wkts")
        if runs not in (None, ""):
            return f"{runs}/{wickets}" if wickets not in (None, "") else str(runs)
        return ""
    return str(value)


def _inning_score(inn):
    if not isinstance(inn, dict):
        return "", "", ""
    team = inn.get("team") or inn.get("batting_team") or inn.get("battingTeam") or inn.get("team_key") or inn.get("teamKey") or ""
    if isinstance(team, dict):
        team = team.get("key") or team.get("name") or team.get("short_name") or team.get("shortName") or ""
    score = inn.get("score")
    if score in (None, ""):
        score = inn.get("runs")
    wickets = inn.get("wickets")
    overs = inn.get("overs") or inn.get("over") or inn.get("overs_played") or inn.get("oversPlayed") or ""
    if isinstance(score, dict):
        runs = score.get("runs") or score.get("score")
        wickets = score.get("wickets") if wickets in (None, "") else wickets
        overs = score.get("overs") or overs
        score = runs
    score_text = ""
    if score not in (None, ""):
        score_text = str(score)
        if wickets not in (None, ""):
            score_text += f"/{wickets}"
    return str(team or ""), score_text, str(overs or "")


def _merge_detail_score(card, detail):
    if not isinstance(card, dict) or not isinstance(detail, dict):
        return card
    out = dict(card)
    match = detail.get("match") if isinstance(detail.get("match"), dict) else {}
    for field in ("homeScore", "homeInfo", "awayScore", "awayInfo", "report", "state", "format", "startTime", "startDate"):
        if match.get(field) not in (None, ""):
            out[field] = match.get(field)
    for side in ("home", "away"):
        if isinstance(match.get(side), dict) and match[side].get("name") not in (None, "", "Team A", "Team B"):
            out[side] = match[side]

    if out.get("homeScore") and out.get("awayScore"):
        return out

    stats = detail.get("statistics") if isinstance(detail.get("statistics"), list) else []
    innings = []
    for row in stats:
        team, score, overs = _inning_score(row)
        if score:
            innings.append((team.casefold(), score, overs))
    if not innings:
        return out

    home = out.get("home") if isinstance(out.get("home"), dict) else {}
    away = out.get("away") if isinstance(out.get("away"), dict) else {}
    home_tokens = [str(home.get(x) or "").casefold() for x in ("id", "name", "abbr")]
    away_tokens = [str(away.get(x) or "").casefold() for x in ("id", "name", "abbr")]

    home_hits, away_hits = [], []
    for team, score, overs in innings:
        if team and any(t and (t in team or team in t) for t in home_tokens):
            home_hits.append((score, overs))
        elif team and any(t and (t in team or team in t) for t in away_tokens):
            away_hits.append((score, overs))

    if home_hits and not out.get("homeScore"):
        out["homeScore"], out["homeInfo"] = home_hits[-1]
    if away_hits and not out.get("awayScore"):
        out["awayScore"], out["awayInfo"] = away_hits[-1]
    return out


def _display_ok(match):
    if not isinstance(match, dict) or not _valid_key(str(match.get("roanuzMatchKey") or match.get("id") or "")):
        return False
    home = match.get("home") if isinstance(match.get("home"), dict) else {}
    away = match.get("away") if isinstance(match.get("away"), dict) else {}
    hn = str(home.get("name") or "").strip()
    an = str(away.get("name") or "").strip()
    return bool(hn and an and hn not in {"Team A", "Home"} and an not in {"Team B", "Away"})


def _matches(mode: str):
    source = "Roanuz V5 primary"
    rows = []
    try:
        rows = v20._roanuz_matches_mode(mode)
    except Exception as exc:
        logger.warning("IBETIN V21 Roanuz %s list failed: %s", mode, str(exc)[:160])

    if mode == "live" and rows:
        enriched = []
        for card in rows[:12]:
            key = str(card.get("roanuzMatchKey") or card.get("id") or "")
            if not _valid_key(key):
                continue
            try:
                detail = v20._roanuz_match_detail(key)
                card = _merge_detail_score(card, detail)
            except Exception as exc:
                logger.warning("IBETIN V21 live detail enrichment failed key=%s: %s", key, str(exc)[:120])
            enriched.append(card)
        rows = enriched

    valid = [m for m in rows if _display_ok(m)]
    if valid:
        logger.info("IBETIN V21 feed mode=%s source=Roanuz matches=%s first=%s vs %s", mode, len(valid), valid[0].get("home", {}).get("name"), valid[0].get("away", {}).get("name"))
        return valid[:40], source

    # Display fallback only. Roanuz remains primary whenever it supplies a usable fixture.
    try:
        fallback = v20._OLD_MATCHES_MODE(mode)
        if fallback:
            logger.warning("IBETIN V21 display fallback active mode=%s matches=%s", mode, len(fallback))
            return fallback[:40], "Highlightly display fallback"
    except Exception as exc:
        logger.warning("IBETIN V21 display fallback failed mode=%s: %s", mode, str(exc)[:160])
    return [], source


def _match_detail(key: str):
    if _valid_key(key):
        return v20._roanuz_match_detail(key), "Roanuz V5 primary"
    if key.isdigit():
        return v20._OLD_MATCH_DETAIL(key), "Highlightly fallback"
    raise ValueError("Invalid match key")


def _api(handler):
    q = parse_qs(urlparse(handler.path).query)
    action = (q.get("action") or ["matches"])[0].strip().lower()
    key = (q.get("matchId") or q.get("id") or q.get("key") or [""])[0].strip()
    try:
        if action == "matches":
            mode = (q.get("mode") or ["live"])[0].strip().lower()
            if mode not in {"live", "upcoming", "results"}:
                raise ValueError("Unknown matches mode")
            rows, source = _matches(mode)
            liveline._send_json(handler, 200, {
                "ok": True,
                "mode": mode,
                "source": source,
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "matches": rows,
            })
            return

        if action == "match":
            detail, source = _match_detail(key)
            liveline._send_json(handler, 200, {
                "ok": True,
                "source": source,
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "detail": detail,
            })
            return

        if action == "bhav":
            if not _valid_key(key):
                liveline._send_json(handler, 200, {"ok": True, "matchId": key, "source": "No Roanuz live key", "entries": []})
                return
            liveline._send_json(handler, 200, v20._v20_bhav(key))
            return

        if action == "graphs":
            if not _valid_key(key):
                raise ValueError("Invalid Roanuz match key")
            liveline._send_json(handler, 200, v14._graphs_payload(key))
            return

        if action == "bhavhistory":
            if not _valid_key(key):
                liveline._send_json(handler, 200, {"ok": True, "matchId": key, "points": []})
                return
            liveline._send_json(handler, 200, v20.v19._history_payload(key))
            return

        if action == "trust":
            with v14._shared_lock:
                stats = dict(v14._stats)
            calls = int(stats.get("highlightly_provider_calls", 0)) + int(stats.get("roanuz_provider_calls", 0))
            hits = int(stats.get("highlightly_cache_hits", 0)) + int(stats.get("roanuz_cache_hits", 0))
            total = calls + hits
            liveline._send_json(handler, 200, {
                "ok": True,
                "roanuz": {"role": "primary fixtures + match + live odds", "directMatchKey": True},
                "highlightly": {"role": "display fallback only"},
                "apiSaver": {"providerCalls": calls, "cacheHits": hits, "cacheHitRate": round(hits * 100 / total, 1) if total else None},
            })
            return

        liveline._send_json(handler, 400, {"ok": False, "error": "Unknown action"})
    except ValueError as exc:
        liveline._send_json(handler, 400, {"ok": False, "error": str(exc)})
    except Exception as exc:
        logger.exception("IBETIN V21 API failure action=%s", action)
        liveline._send_json(handler, 502, {"ok": False, "error": str(exc)[:180]})


def _page() -> str:
    return r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no"><meta http-equiv="Cache-Control" content="no-store"><meta name="referrer" content="no-referrer"><title>IBETIN Live Cricket</title><script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
:root{--bg:#eef2f6;--navy:#06172f;--navy2:#0b315f;--blue:#0b5cb4;--gold:#f2c94c;--ink:#112b49;--muted:#74879a;--card:#fff;--line:#dce4ec;--live:#e83e55;--green:#0b9461}*{box-sizing:border-box}html,body{margin:0;min-height:100%;font-family:Inter,Arial,sans-serif;background:var(--bg);color:var(--ink)}body{padding-bottom:76px}.shell{max-width:760px;margin:auto}.top{position:sticky;top:0;z-index:30;background:linear-gradient(118deg,#041326,#092b55 72%,#0a3f78);color:#fff;padding:12px 12px 10px;box-shadow:0 5px 18px rgba(4,23,47,.18)}.toprow{display:flex;align-items:center;justify-content:space-between}.brand{display:flex;align-items:center;gap:9px}.mark{width:36px;height:36px;border-radius:11px;background:var(--gold);color:#17314e;display:grid;place-items:center;font-weight:1000}.brand b{display:block;font-size:17px;letter-spacing:.8px}.brand span{display:block;font-size:7px;color:#b9d0e8;margin-top:2px}.v{font-size:7px;font-weight:1000;padding:5px 7px;border-radius:999px;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.15)}.tabs{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:11px}.tab{height:36px;border:0;border-radius:10px;background:rgba(255,255,255,.08);color:#bcd0e5;font-size:9px;font-weight:1000}.tab.on{background:#fff;color:#0a315f}.main{padding:9px}.hero{border-radius:17px;background:linear-gradient(130deg,#06172f,#0b315f 65%,#0e579f);color:#fff;padding:14px;margin-bottom:9px;box-shadow:0 10px 24px rgba(6,35,72,.13)}.hero small{font-size:6px;font-weight:1000;letter-spacing:1.2px;color:#9fc0e5}.hero h1{font-size:18px;margin:4px 0}.hero p{font-size:7px;color:#c4d7eb;margin:0}.pills{display:flex;gap:5px;margin-top:10px;overflow:auto}.pill{white-space:nowrap;font-size:6px;font-weight:1000;padding:5px 7px;border-radius:999px;background:rgba(255,255,255,.09);border:1px solid rgba(255,255,255,.12)}.pill.gold{background:var(--gold);color:#18314e;border-color:var(--gold)}.tools{display:flex;gap:7px;margin-bottom:9px}.search{flex:1;height:40px;border:0;border-radius:11px;background:#fff;padding:0 12px;font-size:10px;outline:none}.refresh{width:42px;border:0;border-radius:11px;background:#fff;color:#0a4f98;font-size:16px}.status{font-size:7px;color:#8192a4;margin:0 2px 8px}.list{display:grid;gap:8px}.league{font-size:8px;font-weight:1000;color:#45627f;margin:4px 2px 0}.match{background:#fff;border-radius:14px;overflow:hidden;box-shadow:0 3px 11px rgba(7,36,68,.055);border-left:3px solid #d9e3ed;cursor:pointer}.match.live{border-left-color:var(--live)}.mh{display:flex;justify-content:space-between;gap:8px;align-items:center;padding:8px 10px 4px}.fmt{font-size:6px;color:#8496a8;font-weight:1000;letter-spacing:.5px}.badge{font-size:6px;font-weight:1000;padding:4px 6px;border-radius:999px;background:#eef4fb;color:#51718f}.badge.live{background:#fff0f2;color:#d72d45}.team{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:center;padding:7px 10px}.tn{font-size:12px;font-weight:1000}.ta{font-size:6px;color:#95a3b1;margin-top:2px}.sc{text-align:right;font-size:19px;font-weight:1000;color:#083f7f}.si{text-align:right;font-size:6px;color:#8b9bad;margin-top:2px}.foot{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:7px 10px;border-top:1px solid #f0f3f6;font-size:7px;color:#71869b}.bhav{display:grid;grid-template-columns:auto 1fr 1fr;gap:6px;align-items:center;background:#f8fafc;padding:6px 9px}.bhav small{font-size:6px;font-weight:1000;color:#8a9aac}.odd{background:#eaf3fc;border-radius:8px;padding:6px;text-align:center;color:#0a559f;font-size:9px;font-weight:1000}.empty,.err,.loading{background:#fff;border-radius:14px;padding:25px 14px;text-align:center;color:#73879a;font-size:9px}.spin{width:22px;height:22px;border:3px solid #dce5ed;border-top-color:#0b5cb4;border-radius:50%;animation:s .7s linear infinite;margin:0 auto 9px}@keyframes s{to{transform:rotate(360deg)}}.detail{display:none;padding:9px}.back{height:35px;border:0;border-radius:10px;background:#fff;color:#24578d;font-weight:1000;padding:0 11px}.scorehero{margin-top:8px;border-radius:15px;background:#fff;overflow:hidden}.scoretop{padding:9px 11px;border-bottom:1px solid #edf1f5;font-size:7px;color:#6f8397;display:flex;justify-content:space-between}.scoremain{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:8px;padding:17px 10px}.side.right{text-align:right}.sname{font-size:9px;font-weight:1000;color:#294662}.sval{font-size:23px;font-weight:1000;color:#083f7f;margin-top:4px}.vs{width:32px;height:32px;border-radius:50%;background:#fff5cf;color:#765700;display:grid;place-items:center;font-size:8px;font-weight:1000}.report{padding:9px 11px;background:#fbfcfd;border-top:1px solid #edf1f5;font-size:8px;color:#637b91}.dtabs{display:flex;gap:6px;overflow:auto;margin:8px 0}.dtab{height:34px;border:0;border-radius:9px;background:#fff;color:#687f96;padding:0 10px;font-size:7px;font-weight:1000;white-space:nowrap}.dtab.on{background:#0a315f;color:#fff}.panel{background:#fff;border-radius:13px;padding:10px}.ptitle{display:flex;justify-content:space-between;align-items:center;margin-bottom:9px}.ptitle b{font-size:9px}.source{font-size:5px;font-weight:1000;color:#0b9461;background:#eaf8f1;padding:4px 6px;border-radius:999px}.notice{background:#f7f9fb;border-radius:10px;padding:9px;font-size:8px;color:#647c92;line-height:1.5;margin-bottom:7px}.table{width:100%;border-collapse:collapse;font-size:7px}.table th,.table td{padding:7px 3px;border-bottom:1px solid #edf1f4;text-align:right}.table th:first-child,.table td:first-child{text-align:left}.balls{display:grid;gap:6px}.ball{background:#f8fafc;border-radius:9px;padding:8px;font-size:7px;line-height:1.45}.graphs{display:grid;gap:7px}.graph{background:#f8fafc;border-radius:10px;padding:9px;font-size:7px;color:#647c92;white-space:pre-wrap;word-break:break-word;max-height:190px;overflow:auto}.bottom{position:fixed;left:8px;right:8px;bottom:8px;z-index:40;max-width:720px;margin:auto;display:grid;grid-template-columns:repeat(5,1fr);gap:3px;background:rgba(5,22,45,.96);border-radius:15px;padding:6px;box-shadow:0 10px 28px rgba(4,23,48,.22)}.bottom button{border:0;background:transparent;color:#9fb2c8;height:42px;border-radius:10px;font-size:6px;font-weight:1000}.bottom b{display:block;font-size:14px}.bottom .on{background:rgba(255,255,255,.1);color:#fff}@media(min-width:620px){.list{grid-template-columns:1fr 1fr}.league{grid-column:1/-1}}
</style></head><body><div class="shell"><header class="top"><div class="toprow"><div class="brand"><div class="mark">I</div><div><b>IBETIN</b><span>LIVE CRICKET TERMINAL</span></div></div><div class="v">V21 · ROANUZ</div></div><div class="tabs"><button class="tab on" data-mode="live">● LIVE</button><button class="tab" data-mode="upcoming">UPCOMING</button><button class="tab" data-mode="results">RESULTS</button></div></header><main id="home" class="main"><section class="hero"><small>ROANUZ V5 · PRIMARY DATA</small><h1>Live Cricket Command Center</h1><p>Direct match keys · live scores · BHAV · ball-by-ball · graphs</p><div class="pills"><span class="pill gold">DIRECT MATCH KEY</span><span class="pill">API SAVER ON</span><span class="pill">HIGHLIGHTLY FALLBACK</span></div></section><div class="tools"><input id="search" class="search" placeholder="Search match, team or tournament"><button id="refresh" class="refresh">↻</button></div><div id="status" class="status">Loading live cricket…</div><div id="list" class="list"></div></main><section id="detail" class="detail"></section></div><nav class="bottom"><button class="on" data-nav="home"><b>⌂</b>HOME</button><button data-nav="live"><b style="color:#ff5b6f">●</b>LIVE</button><button data-nav="cricket"><b>🏏</b>CRICKET</button><button data-nav="alerts"><b>🔔</b>ALERTS</button><button data-nav="more"><b>•••</b>MORE</button></nav>
<script>
const tg=window.Telegram&&window.Telegram.WebApp;if(tg){try{tg.ready();tg.expand();tg.setHeaderColor('#06172f');tg.setBackgroundColor('#eef2f6')}catch(e){}}const qs=new URLSearchParams(location.search),TOKEN=qs.get('t')||'';let mode='live',allMatches=[],current=null,tab='match',refreshTimer=null;const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));const n=v=>v===null||v===undefined||v===''?'—':esc(v);function api(p){p.t=TOKEN;return fetch('/admin/liveline-ibetinv21/api?'+new URLSearchParams(p),{cache:'no-store'}).then(async r=>{const j=await r.json();if(!r.ok||!j.ok)throw new Error(j.error||('HTTP '+r.status));return j})}function loading(el){el.innerHTML='<div class="loading"><div class="spin"></div>Loading…</div>'}function fmtTime(v){if(!v)return'';try{return new Date(v).toLocaleString([],{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})}catch(e){return String(v)}}function matchKey(m){return String(m.roanuzMatchKey||m.id||'')}function league(m){return m?.league?.name||'Cricket'}function teamRow(t,s,i){return `<div class="team"><div><div class="tn">${esc(t?.name||t?.abbr||'Team')}</div><div class="ta">${esc(t?.abbr||'')}</div></div><div><div class="sc">${n(s)}</div><div class="si">${esc(i||'')}</div></div></div>`}function card(m){const live=mode==='live';return `<article class="match ${live?'live':''}" data-key="${esc(matchKey(m))}"><div class="mh"><div class="fmt">${esc(m.format||'CRICKET')} · ${esc(league(m))}</div><span class="badge ${live?'live':''}">${live?'● LIVE':esc(m.state||fmtTime(m.startTime)||mode.toUpperCase())}</span></div>${teamRow(m.home,m.homeScore,m.homeInfo)}${teamRow(m.away,m.awayScore,m.awayInfo)}<div class="bhav" data-bhav="${esc(matchKey(m))}"><small>BHAV</small><div class="odd">—</div><div class="odd">—</div></div><div class="foot"><span>${esc(m.report||m.state||fmtTime(m.startTime)||'Tap for details')}</span><b>›</b></div></article>`}function render(){const q=(document.getElementById('search').value||'').trim().toLowerCase();const rows=allMatches.filter(m=>!q||[m.home?.name,m.away?.name,league(m),m.format].join(' ').toLowerCase().includes(q));const list=document.getElementById('list');if(!rows.length){list.innerHTML='<div class="empty">No matching cricket feed found.</div>';return}let last='';list.innerHTML=rows.map(m=>{const l=league(m);const h=l!==last?`<div class="league">${esc(l)}</div>`:'';last=l;return h+card(m)}).join('');list.querySelectorAll('.match').forEach(x=>x.onclick=()=>openMatch(x.dataset.key));if(mode==='live')rows.slice(0,8).forEach(loadCardBhav)}async function loadCardBhav(m){const key=matchKey(m);if(!key||!key.includes('cricket'))return;try{const j=await api({action:'bhav',matchId:key});const vals=j?.entries?.[0]?.values||[];const box=document.querySelector(`[data-bhav="${CSS.escape(key)}"]`);if(!box)return;const odds=box.querySelectorAll('.odd');odds[0].textContent=vals[0]?`${vals[0].label} ${vals[0].odd}`:'—';odds[1].textContent=vals[1]?`${vals[1].label} ${vals[1].odd}`:'—'}catch(e){}}async function load(m=mode){mode=m;document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('on',b.dataset.mode===mode));loading(document.getElementById('list'));document.getElementById('status').textContent='Refreshing '+mode+' cricket…';try{const j=await api({action:'matches',mode});allMatches=j.matches||[];render();document.getElementById('status').textContent=`${allMatches.length} matches · ${j.source||'sports feed'} · ${new Date(j.generatedAt).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}`;}catch(e){document.getElementById('list').innerHTML=`<div class="err">Feed unavailable<br><br>${esc(e.message)}</div>`;document.getElementById('status').textContent='Feed error'}if(refreshTimer)clearInterval(refreshTimer);if(mode==='live')refreshTimer=setInterval(()=>{if(!document.hidden&&document.getElementById('home').style.display!=='none')load('live')},20000)}function tabs(){return [['match','MATCH'],['bhav','BHAV'],['scorecard','SCORECARD'],['balls','BALLS'],['graphs','GRAPHS'],['stats','STATS'],['info','INFO']].map(([k,l])=>`<button class="dtab ${tab===k?'on':''}" data-tab="${k}">${l}</button>`).join('')}async function openMatch(key){document.getElementById('home').style.display='none';const d=document.getElementById('detail');d.style.display='block';loading(d);try{const j=await api({action:'match',id:key});current=j.detail;tab='match';drawDetail()}catch(e){d.innerHTML=`<button class="back" onclick="backHome()">← BACK</button><div class="err">${esc(e.message)}</div>`}}function backHome(){document.getElementById('detail').style.display='none';document.getElementById('home').style.display='block';current=null;window.scrollTo({top:0,behavior:'smooth'})}function drawDetail(){const d=document.getElementById('detail'),m=current?.match||{};d.innerHTML=`<button class="back" onclick="backHome()">← MATCH CENTER</button><div class="scorehero"><div class="scoretop"><span>${esc(m.league?.name||'Cricket')} · ${esc(m.format||'')}</span><span>${esc(m.state||'')}</span></div><div class="scoremain"><div class="side"><div class="sname">${esc(m.home?.name||'Home')}</div><div class="sval">${n(m.homeScore)}</div><div class="ta">${esc(m.homeInfo||'')}</div></div><div class="vs">VS</div><div class="side right"><div class="sname">${esc(m.away?.name||'Away')}</div><div class="sval">${n(m.awayScore)}</div><div class="ta">${esc(m.awayInfo||'')}</div></div></div><div class="report">${esc(m.report||m.state||'')}</div></div><div class="dtabs">${tabs()}</div><div id="panel" class="panel"></div>`;d.querySelectorAll('.dtab').forEach(b=>b.onclick=()=>{tab=b.dataset.tab;drawDetail()});drawPanel()}function ptitle(t){return `<div class="ptitle"><b>${t}</b><span class="source">ROANUZ PRIMARY</span></div>`}function playerName(x){return x?.player?.name||x?.name||x?.short_name||x?.shortName||'Player'}function drawPanel(){const p=document.getElementById('panel'),x=current||{},m=x.match||{};if(tab==='match'){const rr=x.roanuz?.runRate;const target=x.roanuz?.target;p.innerHTML=ptitle('LIVE MATCH')+`<div class="notice"><b>${esc(m.report||m.state||'Match status')}</b><br>${target?`Target: ${esc(JSON.stringify(target).slice(0,120))}<br>`:''}${rr?`Run rate: ${esc(JSON.stringify(rr).slice(0,120))}`:''}</div>`}else if(tab==='bhav'){p.innerHTML=ptitle('LIVE BHAV')+'<div class="loading"><div class="spin"></div>Loading live prices…</div>';api({action:'bhav',matchId:matchKey(m)}).then(j=>{const es=j.entries||[];p.innerHTML=ptitle('LIVE BHAV')+(es.length?es.map(e=>`<div class="notice"><b>${esc(e.market||'Match Winner')}</b><br>${(e.values||[]).map(v=>`${esc(v.label)}: <b>${n(v.odd)}</b>`).join(' · ')}</div>`).join(''):'<div class="notice">Live BHAV is not available for this match at this moment.</div>')}).catch(e=>p.innerHTML=ptitle('LIVE BHAV')+`<div class="notice">${esc(e.message)}</div>`)}else if(tab==='scorecard'){const s=x.statistics||[];p.innerHTML=ptitle('SCORECARD')+(s.length?`<div class="graph">${esc(JSON.stringify(s,null,2).slice(0,9000))}</div>`:'<div class="notice">Scorecard data is not available yet.</div>')}else if(tab==='balls'){const a=x.timeline||[];p.innerHTML=ptitle('BALL-BY-BALL')+(a.length?`<div class="balls">${a.slice().reverse().map((e,i)=>`<div class="ball"><b>${esc(e.over||e.ball||('#'+(i+1)))}</b><br>${esc(e.commentary||e.comment||e.description||e.text||JSON.stringify(e).slice(0,220))}</div>`).join('')}</div>`:'<div class="notice">Ball-by-ball is waiting for the next available Roanuz update.</div>')}else if(tab==='graphs'){p.innerHTML=ptitle('MATCH GRAPHS')+'<div class="loading"><div class="spin"></div>Loading graphs…</div>';api({action:'graphs',key:matchKey(m)}).then(j=>{const g=j.graphs||{};p.innerHTML=ptitle('MATCH GRAPHS')+`<div class="graphs">${Object.entries(g).map(([k,v])=>`<div class="graph"><b>${esc(k.toUpperCase())}</b>\n${esc(JSON.stringify(v,null,2).slice(0,3000))}</div>`).join('')||'<div class="notice">No graph data yet.</div>'}</div>`}).catch(e=>p.innerHTML=ptitle('MATCH GRAPHS')+`<div class="notice">${esc(e.message)}</div>`)}else if(tab==='stats'){p.innerHTML=ptitle('MATCH STATS')+`<div class="graph">${esc(JSON.stringify(x.statistics||[],null,2).slice(0,9000))}</div>`}else{p.innerHTML=ptitle('MATCH INFO')+`<div class="notice"><b>Venue</b><br>${esc(x.venue?.name||'—')} ${x.venue?.city?'· '+esc(x.venue.city):''}</div><div class="notice"><b>Match key</b><br>${esc(matchKey(m))}</div>`}}document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>load(b.dataset.mode));document.getElementById('refresh').onclick=()=>load(mode);document.getElementById('search').oninput=render;document.querySelector('.bottom').onclick=e=>{const b=e.target.closest('button');if(!b)return;document.querySelectorAll('.bottom button').forEach(x=>x.classList.toggle('on',x===b));const x=b.dataset.nav;if(x==='live'||x==='cricket'||x==='home'){backHome();load('live')}else if(x==='alerts'){alert('Smart match alerts are active in IBETIN.')}else document.getElementById('search').focus()};document.addEventListener('visibilitychange',()=>{if(!document.hidden&&mode==='live'&&document.getElementById('home').style.display!=='none')load('live')});load('live');
</script></body></html>'''


liveline.admin_url = _admin_url
liveline._page = _page
liveline._api = _api
app = v20.app


def _startup_probe():
    try:
        rows, source = _matches("live")
        if rows:
            m = rows[0]
            logger.info("IBETIN V21 startup feed OK source=%s matches=%s first=%s vs %s score=%s/%s", source, len(rows), m.get("home", {}).get("name"), m.get("away", {}).get("name"), m.get("homeScore"), m.get("awayScore"))
        else:
            logger.warning("IBETIN V21 startup feed empty")
    except Exception as exc:
        logger.exception("IBETIN V21 startup feed probe failed: %s", exc)


_startup_probe()
logger.info("IBETIN V21 installed: clean frontend + Roanuz direct-key primary feed + safe display fallback")

if __name__ == "__main__":
    app.base.ibetin_start.main()
