import logging
import os
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode, urlparse

import bot as core
import ibetin_liveline_trial as liveline
import ibetin_liveline_v14_efficient as v14
import ibetin_liveline_v18_roanuz_bhav as v18

logger = logging.getLogger(__name__)

liveline.LIVELINE_PATH = "/admin/liveline-ibetinv19"
liveline.LIVELINE_API_PATH = "/admin/liveline-ibetinv19/api"


def _v19_admin_url() -> str:
    root = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/") or "https://ibetin-app-production.up.railway.app"
    return f"{root}{liveline.LIVELINE_PATH}?{urlencode({'t': liveline._token(), 'v': '20260917-v19-trust-intel'})}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_history() -> None:
    with core.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS liveline_bhav_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id TEXT NOT NULL,
                source TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                team_a TEXT NOT NULL,
                odd_a REAL NOT NULL,
                team_b TEXT NOT NULL,
                odd_b REAL NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_liveline_bhav_history_match_time "
            "ON liveline_bhav_history(match_id, observed_at)"
        )


def _record_bhav(payload) -> None:
    if not isinstance(payload, dict):
        return
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries or not isinstance(entries[0], dict):
        return
    values = entries[0].get("values")
    if not isinstance(values, list) or len(values) < 2:
        return
    a, b = values[0], values[1]
    if not isinstance(a, dict) or not isinstance(b, dict):
        return
    try:
        odd_a = float(a.get("odd"))
        odd_b = float(b.get("odd"))
    except (TypeError, ValueError):
        return
    match_id = str(payload.get("matchId") or "")
    if not match_id:
        return
    source = str(payload.get("source") or entries[0].get("bookmaker") or "Unknown")
    observed = _now_iso()
    _ensure_history()
    with core.db() as conn:
        last = conn.execute(
            "SELECT observed_at, source, odd_a, odd_b FROM liveline_bhav_history WHERE match_id=? ORDER BY id DESC LIMIT 1",
            (match_id,),
        ).fetchone()
        if last:
            same = str(last["source"]) == source and abs(float(last["odd_a"]) - odd_a) < 0.000001 and abs(float(last["odd_b"]) - odd_b) < 0.000001
            try:
                age = time.time() - datetime.fromisoformat(str(last["observed_at"])).timestamp()
            except Exception:
                age = 9999
            if same and age < 300:
                return
        conn.execute(
            "INSERT INTO liveline_bhav_history(match_id,source,observed_at,team_a,odd_a,team_b,odd_b) VALUES(?,?,?,?,?,?,?)",
            (match_id, source, observed, str(a.get("label") or "Team A"), odd_a, str(b.get("label") or "Team B"), odd_b),
        )


def _history_payload(match_id: str):
    _ensure_history()
    with core.db() as conn:
        rows = conn.execute(
            "SELECT source,observed_at,team_a,odd_a,team_b,odd_b FROM liveline_bhav_history WHERE match_id=? ORDER BY id DESC LIMIT 60",
            (match_id,),
        ).fetchall()
    return {
        "ok": True,
        "matchId": match_id,
        "points": [
            {
                "source": str(r["source"]),
                "observedAt": str(r["observed_at"]),
                "a": {"label": str(r["team_a"]), "odd": float(r["odd_a"])},
                "b": {"label": str(r["team_b"]), "odd": float(r["odd_b"])},
            }
            for r in reversed(rows)
        ],
    }


def _latest_bhav(match_id: str):
    if not match_id:
        return None
    _ensure_history()
    with core.db() as conn:
        row = conn.execute(
            "SELECT source,observed_at FROM liveline_bhav_history WHERE match_id=? ORDER BY id DESC LIMIT 1",
            (match_id,),
        ).fetchone()
    if not row:
        return None
    try:
        age = max(0, int(time.time() - datetime.fromisoformat(str(row["observed_at"])).timestamp()))
    except Exception:
        age = None
    return {"source": str(row["source"]), "observedAt": str(row["observed_at"]), "ageSeconds": age}


def _highlightly_payload(match_id: str, odds_type: str, requested: str):
    rows = liveline._highlightly(
        "/cricket/odds",
        {"matchId": match_id, "oddsType": odds_type, "limit": 5, "offset": 0},
        ttl=30 if odds_type == "live" else 120,
    )
    if isinstance(rows, dict):
        rows = [rows]
    rows = rows if isinstance(rows, list) else []
    record = next((r for r in rows if isinstance(r, dict) and str(r.get("matchId") or "") == match_id), None)
    if record is None and rows and isinstance(rows[0], dict):
        record = rows[0]
    entries = v14._normalize_record(record, odds_type) if record else []
    return {
        "ok": True,
        "matchId": match_id,
        "oddsType": odds_type,
        "requestedType": requested,
        "market": "Match Winner",
        "source": "Highlightly PRO · fallback" if requested == "live" else "Highlightly PRO · prematch",
        "observedAt": _now_iso(),
        "entries": entries,
    }


_previous_api = liveline._api


def _v19_api(handler):
    q = parse_qs(urlparse(handler.path).query)
    action = (q.get("action") or [""])[0].strip().lower()

    if action == "bhavhistory":
        match_id = (q.get("matchId") or q.get("id") or [""])[0].strip()
        if not match_id.isdigit():
            liveline._send_json(handler, 400, {"ok": False, "error": "Invalid match id"})
            return
        liveline._send_json(handler, 200, _history_payload(match_id))
        return

    if action == "trust":
        match_id = (q.get("matchId") or q.get("id") or [""])[0].strip()
        with v14._shared_lock:
            stats = dict(v14._stats)
            cache_entries = len(v14._shared_cache)
        calls = int(stats.get("highlightly_provider_calls", 0)) + int(stats.get("roanuz_provider_calls", 0))
        hits = int(stats.get("highlightly_cache_hits", 0)) + int(stats.get("roanuz_cache_hits", 0))
        total = calls + hits
        liveline._send_json(
            handler,
            200,
            {
                "ok": True,
                "generatedAt": _now_iso(),
                "latestBhav": _latest_bhav(match_id),
                "roanuz": {"liveOdds": "enabled", "role": "primary"},
                "highlightly": {"role": "fallback"},
                "apiSaver": {
                    "providerCalls": calls,
                    "cacheHits": hits,
                    "cacheHitRate": round((hits / total) * 100, 1) if total else None,
                    "sharedCacheEntries": cache_entries,
                },
            },
        )
        return

    if action == "bhav":
        match_id = (q.get("matchId") or q.get("id") or [""])[0].strip()
        requested = (q.get("oddsType") or ["live"])[0].strip().lower()
        requested = requested if requested in {"live", "prematch"} else "live"
        if not match_id.isdigit():
            liveline._send_json(handler, 400, {"ok": False, "error": "Invalid match id"})
            return
        payload = None
        if requested == "live":
            try:
                payload = v18._roanuz_primary_for_match(match_id)
            except Exception as exc:
                logger.warning("IBETIN V19 Roanuz primary unavailable: %s", str(exc)[:160])
        if not payload:
            try:
                payload = _highlightly_payload(match_id, requested, requested)
                if requested == "live" and not payload.get("entries"):
                    prematch = _highlightly_payload(match_id, "prematch", "live")
                    if prematch.get("entries"):
                        payload = prematch
            except Exception as exc:
                logger.warning("IBETIN V19 Highlightly fallback unavailable: %s", str(exc)[:160])
                payload = {"ok": True, "matchId": match_id, "oddsType": requested, "requestedType": requested, "market": "Match Winner", "source": "No live price available", "observedAt": _now_iso(), "entries": []}
        payload = dict(payload)
        payload.setdefault("observedAt", _now_iso())
        _record_bhav(payload)
        liveline._send_json(handler, 200, payload)
        return

    return _previous_api(handler)


liveline._api = _v19_api


def _v19_page() -> str:
    html = v18._v18_page()
    css = r'''
.liveChip:after{content:'V19'!important}
.v19Trust{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin:0 0 9px}.v19Trust>div{border:1px solid #dce5ee;background:#fff;border-radius:10px;padding:8px 9px;min-width:0}.v19Trust small{display:block;font-size:5px;font-weight:1000;color:#8a9bab;text-transform:uppercase;letter-spacing:.45px}.v19Trust b{display:block;margin-top:4px;font-size:8px;color:#244d76;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.v19Trust span{display:block;margin-top:2px;font-size:5px;color:#8495a6;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.v19Fresh{color:#14845d!important}.v19Stale{color:#d23b50!important}.v19Wait{color:#b27600!important}
.v19Drawer{display:none;position:fixed;z-index:10020;left:10px;right:10px;bottom:12px;max-width:620px;margin:auto;border:1px solid #d6e2ed;background:#fff;border-radius:16px;box-shadow:0 18px 55px rgba(4,25,54,.24);padding:12px}.v19Drawer.show{display:block}.v19DrawerTop{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:8px}.v19DrawerTop b{font-size:10px;color:#244d76}.v19Close{width:30px;height:30px;border:1px solid #dce5ed;border-radius:9px;background:#f7f9fb;color:#56708b;font-weight:1000}.v19AlertNote{font-size:6px;color:#7f91a3;line-height:1.5;margin-bottom:9px}.v19AlertGrid{display:grid;grid-template-columns:1fr 1fr;gap:7px}.v19Alert{display:flex;justify-content:space-between;align-items:center;gap:8px;border:1px solid #e1e8ef;border-radius:10px;padding:9px;background:#fafbfd}.v19Alert span{font-size:7px;color:#3b5f80;font-weight:900}.v19Switch{width:34px;height:20px;border:0;border-radius:999px;background:#dfe7ef;position:relative}.v19Switch:after{content:'';position:absolute;top:3px;left:3px;width:14px;height:14px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.18)}.v19Switch.on{background:#0b67c9}.v19Switch.on:after{left:17px}.v19Toast{display:none;position:fixed;z-index:10030;left:50%;transform:translateX(-50%);bottom:78px;max-width:88vw;background:#071d3d;color:#fff;border-radius:12px;padding:10px 12px;font-size:8px;font-weight:900;box-shadow:0 12px 40px rgba(3,20,45,.28)}.v19Toast.show{display:block}
.v19Lab,.v19History{border:1px solid #dce5ee;border-radius:12px;background:#fff;margin-top:9px;overflow:hidden}.v19History{margin:10px}.v19Head{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:9px 10px;background:#fafbfd;border-bottom:1px solid #edf1f5}.v19Head b{font-size:8px;color:#244c75}.v19Head span{font-size:6px;color:#8798a9}.v19Search{margin:9px 10px 4px;width:calc(100% - 20px);height:34px;border:1px solid #dce5ee;border-radius:9px;padding:0 10px;font-size:8px}.v19Players{display:grid;gap:6px;padding:6px 10px 10px}.v19Player{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:center;border:1px solid #e3e9ef;border-radius:9px;padding:8px;background:#fafbfd}.v19Player b{display:block;font-size:8px;color:#244b72}.v19Player span{display:block;font-size:5px;color:#8797a7;margin-top:2px}.v19Compare{height:26px;border:1px solid #d8e3ec;border-radius:8px;background:#fff;color:#56728d;font-size:6px;font-weight:1000}.v19Compare.on{background:#fff5cf;border-color:#efd06b;color:#765900}.v19CompareBar{display:none;margin:0 10px 10px;padding:9px;border:1px solid #dbe4ed;border-radius:10px;background:#f7faff}.v19CompareBar.show{display:grid;grid-template-columns:1fr 1fr;gap:7px}.v19CompareBar b{display:block;font-size:8px;color:#174d81}.v19CompareBar span{display:block;font-size:6px;color:#73889c;margin-top:3px}.v19HistoryBody{padding:8px}.v19Chart{display:block;width:100%;height:120px}.v19HistoryMeta{display:flex;justify-content:space-between;gap:8px;margin-top:5px;font-size:6px;color:#7d90a3}.v19Empty{padding:12px;text-align:center;font-size:7px;color:#8192a3;border:1px dashed #dce5ee;border-radius:9px}
html[data-v16-theme="dark"] .v19Trust>div,html[data-v16-theme="dark"] .v19Drawer,html[data-v16-theme="dark"] .v19Lab,html[data-v16-theme="dark"] .v19History{background:#0d1c2d!important;border-color:#203449!important}html[data-v16-theme="dark"] .v19Head,html[data-v16-theme="dark"] .v19Alert,html[data-v16-theme="dark"] .v19Player,html[data-v16-theme="dark"] .v19CompareBar{background:#122337!important;border-color:#25394f!important}html[data-v16-theme="dark"] .v19Head b,html[data-v16-theme="dark"] .v19Trust b,html[data-v16-theme="dark"] .v19Player b,html[data-v16-theme="dark"] .v19DrawerTop b{color:#d9e8f7!important}
@media(min-width:600px){.v19AlertGrid{grid-template-columns:repeat(3,1fr)}.v19Players{grid-template-columns:1fr 1fr}}
'''
    html = html.replace("</style>", css + "\n</style>", 1)
    js = r'''
<script>
(function(){
 const KEY='ibetin-v19-alerts';let lastId='',seen=new Set(),lastReport='',busy=false,compare=new Set();
 function det(){try{return (typeof currentDetail!=='undefined'&&currentDetail)||window.currentDetail||{}}catch(e){return window.currentDetail||{}}}
 function id(){return String(det()?.match?.id||'')}
 function visible(){const x=document.getElementById('detail');return x&&x.style.display!=='none'}
 function tab(){return String(document.querySelector('.detailTab.active')?.textContent||'').trim().toUpperCase()}
 function e(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
 function pref(){try{return Object.assign({wicket:true,boundary:true,milestone:true,innings:true,close:true,result:true},JSON.parse(localStorage.getItem(KEY)||'{}'))}catch(x){return{wicket:true,boundary:true,milestone:true,innings:true,close:true,result:true}}}
 function save(x){try{localStorage.setItem(KEY,JSON.stringify(x))}catch(z){}}
 function toast(t){let x=document.getElementById('v19Toast');if(!x){x=document.createElement('div');x.id='v19Toast';x.className='v19Toast';document.body.appendChild(x)}x.textContent=t;x.classList.add('show');clearTimeout(x._t);x._t=setTimeout(()=>x.classList.remove('show'),4200);try{Telegram.WebApp.HapticFeedback.notificationOccurred('success')}catch(z){}}
 function actions(){const a=document.querySelector('.v16Actions');if(!a)return;if(!document.getElementById('v19Alerts')){a.style.gridTemplateColumns='repeat(3,1fr)';a.insertAdjacentHTML('beforeend','<button class="v16Action" id="v19Alerts" type="button">🔔 ALERTS</button><button class="v16Action" id="v19TrustBtn" type="button">✓ TRUST</button>');document.getElementById('v19Alerts').onclick=()=>drawer().classList.toggle('show');document.getElementById('v19TrustBtn').onclick=()=>trust(true)}if(!document.getElementById('v19Trust')){const b=document.createElement('div');b.id='v19Trust';b.className='v19Trust';b.innerHTML='<div><small>Live BHAV</small><b>Checking…</b><span>source & freshness</span></div><div><small>Roanuz</small><b class="v19Fresh">PRIMARY</b><span>live odds enabled</span></div><div><small>API Saver</small><b>ON</b><span>shared cache</span></div>';a.insertAdjacentElement('afterend',b)}}
 function drawer(){let b=document.getElementById('v19Drawer');if(b)return b;b=document.createElement('div');b.id='v19Drawer';b.className='v19Drawer';b.innerHTML='<div class="v19DrawerTop"><b>SMART LIVE ALERTS</b><button class="v19Close" type="button">×</button></div><div class="v19AlertNote">These in-app alerts run while this live match is open. Existing Telegram match alerts continue separately.</div><div class="v19AlertGrid"></div>';document.body.appendChild(b);b.querySelector('.v19Close').onclick=()=>b.classList.remove('show');toggles();return b}
 const names={wicket:'🏏 Wicket',boundary:'💥 4 / 6',milestone:'⭐ 50 / 100',innings:'↔ Innings',close:'🔥 Close match',result:'✅ Result'};
 function toggles(){const g=document.querySelector('#v19Drawer .v19AlertGrid');if(!g)return;const p=pref();g.innerHTML=Object.keys(names).map(k=>`<div class="v19Alert"><span>${names[k]}</span><button type="button" class="v19Switch ${p[k]?'on':''}" data-k="${k}"></button></div>`).join('');g.querySelectorAll('[data-k]').forEach(b=>b.onclick=()=>{const p=pref(),k=b.dataset.k;p[k]=!p[k];save(p);toggles()})}
 async function trust(pop){actions();if(!id())return;try{const j=await api({action:'trust',matchId:id()}),c=document.querySelectorAll('#v19Trust>div'),h=j?.latestBhav,age=h?.ageSeconds,st=age==null?'WAITING':age<=45?'FRESH':age<=90?'AGING':'STALE';c[0].querySelector('b').textContent=h?.source||'Waiting for BHAV';c[0].querySelector('b').className=st==='FRESH'?'v19Fresh':st==='STALE'?'v19Stale':'v19Wait';c[0].querySelector('span').textContent=age==null?'first price not captured yet':`${st.toLowerCase()} · ${age}s ago`;const rate=j?.apiSaver?.cacheHitRate;c[2].querySelector('b').textContent=rate==null?'ON':`${rate}% HIT`;c[2].querySelector('span').textContent=`${j?.apiSaver?.sharedCacheEntries||0} cached responses`;if(pop)toast(`Trust: ${st} · ${h?.source||'waiting'}`)}catch(x){if(pop)toast('Trust check temporarily unavailable')}}
 function pname(o){return o?.player?.name||o?.name||o?.fullName||o?.displayName||''}
 function squad(){const out=[],raw=det().squad||[];raw.forEach((x,i)=>{if(Array.isArray(x?.players))x.players.forEach((p,j)=>out.push({...p,_team:x?.team?.name||x?.name||'',_key:String(p?.id||`${i}-${j}`)}));else if(x&&typeof x==='object')out.push({...x,_team:x?.team?.name||'',_key:String(x?.id||i)})});const s=new Set();return out.filter(x=>{const n=pname(x);if(!n||s.has(n))return false;s.add(n);return true}).slice(0,30)}
 function perf(n){const x=det(),q=String(n).toLowerCase(),a=[];for(const p of (x.bestBatsmen||[])){if(pname(p).toLowerCase()===q){const s=p?.player?.statistics||p?.statistics||p;a.push(`${s.runs??s.score??'—'} runs${s.balls!=null?' · '+s.balls+' balls':''}`);break}}for(const p of (x.bestBowlers||[])){if(pname(p).toLowerCase()===q){const s=p?.player?.statistics||p?.statistics||p;a.push(`${s.wickets??'—'} wkts${s.overs!=null?' · '+s.overs+' ov':''}`);break}}return a.join(' · ')||'Current-match squad data'}
 function lab(){if(tab()!=='INTEL')return;const p=document.getElementById('panel');if(!p||document.getElementById('v19Lab'))return;const rows=squad(),b=document.createElement('section');b.id='v19Lab';b.className='v19Lab';b.innerHTML='<div class="v19Head"><b>PLAYER LAB</b><span>current match · verified data only</span></div><input class="v19Search" placeholder="Search player…"><div class="v19CompareBar"></div><div class="v19Players"></div>';p.appendChild(b);const render=q=>{const g=b.querySelector('.v19Players'),list=rows.filter(x=>pname(x).toLowerCase().includes(String(q||'').toLowerCase())).slice(0,16);g.innerHTML=list.length?list.map(x=>{const n=pname(x),r=x.role||x?.player?.role||x.position||x._team||'Squad';return `<div class="v19Player"><div><b>${e(n)}</b><span>${e(r)} · ${e(perf(n))}</span></div><button class="v19Compare ${compare.has(n)?'on':''}" data-p="${e(n)}">${compare.has(n)?'✓ COMPARE':'COMPARE'}</button></div>`}).join(''):'<div class="v19Empty">No matching player.</div>';g.querySelectorAll('[data-p]').forEach(z=>z.onclick=()=>{const n=z.dataset.p;if(compare.has(n))compare.delete(n);else{if(compare.size>=2)compare=new Set();compare.add(n)}render(b.querySelector('.v19Search').value);cmp()})};const cmp=()=>{const c=b.querySelector('.v19CompareBar'),n=[...compare];c.classList.toggle('show',n.length>0);c.innerHTML=n.map(x=>`<div><b>${e(x)}</b><span>${e(perf(x))}</span></div>`).join('')};b.querySelector('.v19Search').oninput=z=>render(z.target.value);render('');cmp()}
 function svg(pts){if(pts.length<2)return'';const v=[];pts.forEach(p=>{v.push(+p.a.odd,+p.b.odd)});let mn=Math.min(...v),mx=Math.max(...v);if(mx-mn<.05){mx+=.05;mn-=.05}const W=320,H=105,P=12,X=i=>P+i/(pts.length-1)*(W-2*P),Y=n=>H-P-(n-mn)/(mx-mn)*(H-2*P),a=pts.map((p,i)=>`${X(i)},${Y(+p.a.odd)}`).join(' '),b=pts.map((p,i)=>`${X(i)},${Y(+p.b.odd)}`).join(' ');return `<svg class="v19Chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><polyline points="${a}" fill="none" stroke="#0b67c9" stroke-width="2.2" vector-effect="non-scaling-stroke"/><polyline points="${b}" fill="none" stroke="#e09c18" stroke-width="2.2" vector-effect="non-scaling-stroke"/></svg>`}
 async function history(){if(tab()!=='BHAV')return;const p=document.getElementById('panel');if(!p||!id()||document.getElementById('v19History'))return;const b=document.createElement('section');b.id='v19History';b.className='v19History';b.innerHTML='<div class="v19Head"><b>BHAV MOVEMENT</b><span>persistent observed prices</span></div><div class="v19HistoryBody"><div class="v19Empty">Loading history…</div></div>';p.appendChild(b);try{const j=await api({action:'bhavhistory',matchId:id()}),pts=j?.points||[],x=b.querySelector('.v19HistoryBody');if(!pts.length){x.innerHTML='<div class="v19Empty">History starts after the first live price is observed.</div>';return}const z=pts[pts.length-1];x.innerHTML=(pts.length>1?svg(pts):'<div class="v19Empty">First price captured. The movement chart appears after another observation.</div>')+`<div class="v19HistoryMeta"><span>🔵 ${e(z.a.label)} ${e(z.a.odd)}</span><span>🟠 ${e(z.b.label)} ${e(z.b.odd)}</span></div><div class="v19HistoryMeta"><span>${pts.length} observations</span><span>${e(z.source)}</span></div>`}catch(x){b.querySelector('.v19HistoryBody').innerHTML='<div class="v19Empty">History temporarily unavailable.</div>'}}
 function events(x){const t=x?.timeline||[];return Array.isArray(t)?t.slice(-20).map((o,i)=>{const z=typeof o==='string'?o:(o?.comment||o?.commentary||o?.text||o?.description||JSON.stringify(o));return{f:String(o?.id||o?.key||o?.ball||i)+'|'+String(z),t:String(z)}}):[]}
 function inspect(x){const m=String(x?.match?.id||'');if(!m)return;const ev=events(x),p=pref(),fp=new Set(ev.map(x=>x.f));if(lastId!==m){lastId=m;seen=fp;lastReport=String(x?.match?.report||'');return}ev.forEach(x=>{if(seen.has(x.f))return;const t=x.t;if(p.wicket&&/\bwicket\b|\bout\b/i.test(t))toast('🏏 WICKET · '+t.slice(0,100));else if(p.boundary&&/\bsix\b|\b6 runs?\b|\bfour\b|\b4 runs?\b/i.test(t))toast('💥 BOUNDARY · '+t.slice(0,100));else if(p.milestone&&/\b50\b|\b100\b|fifty|century/i.test(t))toast('⭐ MILESTONE · '+t.slice(0,100))});seen=fp;const r=String(x?.match?.report||''),s=String(x?.match?.state||'');if(r&&r!==lastReport){if(p.innings&&/innings break|end of innings/i.test(r+' '+s))toast('↔ INNINGS · '+r.slice(0,110));const q=r.match(/need\s+(\d+)\s+(?:runs?\s+)?(?:from|off)\s+(\d+)/i);if(p.close&&q&&+q[1]<=30&&+q[2]<=18)toast('🔥 CLOSE MATCH · '+r.slice(0,110));if(p.result&&/won by|match tied|no result|abandoned/i.test(r+' '+s))toast('✅ RESULT · '+r.slice(0,110))}lastReport=r}
 async function poll(){if(busy||document.hidden||!visible()||!id())return;busy=true;try{const j=await api({action:'match',id:id()});if(j?.detail){try{currentDetail=j.detail}catch(x){window.currentDetail=j.detail}inspect(j.detail)}}catch(x){}finally{busy=false}}
 function decorate(){if(!visible())return;actions();trust(false);lab();history()}
 new MutationObserver(()=>setTimeout(decorate,40)).observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['class','style']});
 setInterval(()=>{if(visible())trust(false)},30000);setInterval(poll,30000);document.addEventListener('visibilitychange',()=>{if(!document.hidden){decorate();poll()}});setTimeout(()=>{drawer();decorate()},700);
})();
</script>
'''
    html = html.replace("</body>", js + "\n</body>")
    return html


liveline.admin_url = _v19_admin_url
liveline._page = _v19_page
app = v18.app

_ensure_history()
logger.info("IBETIN V19 installed: trust layer + smart in-app alerts + player lab + persistent BHAV history")

if __name__ == "__main__":
    app.base.ibetin_start.main()
