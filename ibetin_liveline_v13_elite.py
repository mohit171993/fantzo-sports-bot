import logging
import os
import re
from urllib.parse import parse_qs, urlencode, urlparse

import ibetin_liveline_trial as liveline
import ibetin_liveline_v12_command_center as v12

logger = logging.getLogger(__name__)

# Fresh private route for Telegram cache isolation.
liveline.LIVELINE_PATH = "/admin/liveline-ibetinv13"
liveline.LIVELINE_API_PATH = "/admin/liveline-ibetinv13/api"


def _v13_admin_url() -> str:
    root = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/") or "https://ibetin-app-production.up.railway.app"
    return f"{root}{liveline.LIVELINE_PATH}?{urlencode({'t': liveline._token(), 'v': '20260917-v13-elite'})}"


# Extend V12 API with Roanuz graph data. BHAV remains handled by V12/Highlightly.
_previous_api = liveline._api
_SAFE_MATCH_KEY = re.compile(r"^[A-Za-z0-9_.:\-]{3,180}$")


def _v13_api(handler):
    query = parse_qs(urlparse(handler.path).query)
    action = (query.get("action") or [""])[0].strip().lower()
    if action != "graphs":
        return _previous_api(handler)

    try:
        match_key = (query.get("key") or [""])[0].strip()
        if not match_key or not _SAFE_MATCH_KEY.match(match_key):
            liveline._send_json(handler, 400, {"ok": False, "error": "Invalid Roanuz match key"})
            return

        admin = v12.app
        graphs = {}
        failures = {}
        for name, endpoint in (
            ("worm", f"match/{match_key}/worm/"),
            ("manhattan", f"match/{match_key}/manhattan/"),
            ("runRate", f"match/{match_key}/run-rate/"),
        ):
            try:
                graphs[name] = admin._roanuz_get(endpoint, ttl=20)
            except Exception as exc:
                failures[name] = str(exc)[:120]

        liveline._send_json(
            handler,
            200,
            {
                "ok": True,
                "source": "Roanuz",
                "matchKey": match_key,
                "graphs": graphs,
                "failures": failures,
            },
        )
    except Exception as exc:
        logger.exception("IBETIN V13 graphs API failed")
        liveline._send_json(handler, 502, {"ok": False, "error": str(exc)[:180]})


liveline._api = _v13_api


def _v13_page() -> str:
    html = v12._v12_page()

    css = r'''
/* V13 — elite cricket UX */
.liveChip:after{content:'V13 TEST'!important}
.brandText span{letter-spacing:.85px!important}

/* Skeleton loading */
.v13Skeleton{display:grid;gap:10px}.v13SkelCard{height:142px;border-radius:14px;background:linear-gradient(90deg,#e6eef7 25%,#f6f9fd 37%,#e6eef7 63%);background-size:400% 100%;animation:v13sh 1.25s ease infinite;border:1px solid #d6e2ee}@keyframes v13sh{0%{background-position:100% 0}100%{background-position:0 0}}

/* Freshness */
.v13Fresh{display:inline-flex;align-items:center;gap:5px;margin-top:4px;font-size:8px;color:#70869d;font-weight:850}.v13Fresh i{width:6px;height:6px;border-radius:50%;background:#1b9d6b;display:inline-block}.v13Fresh.stale i{background:#e7a51b}

/* Match card controls */
.matchHead{position:relative!important}.v13Pin{position:absolute;right:8px;top:7px;z-index:4;width:27px;height:27px;border-radius:8px;border:1px solid #d2dfec;background:#fff;color:#8193a7;display:grid;place-items:center;font-size:13px;font-weight:1000;box-shadow:0 2px 6px rgba(11,55,103,.06)}.v13Pin.on{background:#fff6cf;border-color:#f2ca4b;color:#9a6a00}.leagueMatches .badgeLive,.leagueMatches .badgeState{margin-right:32px!important}
.v13CardBhav{display:grid;grid-template-columns:auto 1fr 1fr;align-items:center;gap:6px;padding:7px 10px 8px 12px;background:#fff;border-top:1px solid #edf1f6}.v13BhavLabel{font-size:7px;font-weight:1000;color:#7b8ea4;letter-spacing:.35px}.v13BhavOdd{border:1px solid #d3e1ef;background:#eef6ff;border-radius:8px;padding:6px 7px;color:#0a4d99;font-size:9px;font-weight:1000;text-align:center;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.v13BhavOdd span{color:#7c90a6;font-size:6px;font-weight:900;margin-right:4px}.v13BhavLoading{color:#9aabba;font-size:7px;font-weight:850}
.match.v13Pinned{outline:2px solid rgba(255,201,40,.55);outline-offset:-2px}.match.v13Pinned:after{content:'PINNED';position:absolute;right:39px;top:10px;color:#8c6900;font-size:6px;font-weight:1000;letter-spacing:.4px}

/* Collapsible tournament sections */
.leagueSectionHead{cursor:pointer}.v13Collapse{border:0;background:#edf4fb;color:#315e8b;width:26px;height:26px;border-radius:8px;font-size:13px;font-weight:1000;display:grid;place-items:center}.leagueSectionHead>.leagueCount{margin-left:auto}.leagueBlock.v13Collapsed .leagueMatches{display:none!important}.leagueBlock.v13Collapsed .v13Collapse{transform:rotate(-90deg)}

/* Compact sticky scoreboard */
.v13MiniScore{position:sticky;top:0;z-index:15;display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:8px;background:linear-gradient(110deg,#061f46,#08488f);color:#fff;border:1px solid #174f8f;border-radius:12px;padding:9px 10px;margin:0 0 9px;box-shadow:0 8px 20px rgba(6,41,87,.18)}.v13MiniSide{min-width:0}.v13MiniSide.right{text-align:right}.v13MiniTeam{font-size:8px;color:#bcd2ea;font-weight:900;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.v13MiniVal{font-size:12px;font-weight:1000;margin-top:2px}.v13MiniLive{font-size:7px;font-weight:1000;background:#e6384f;border-radius:999px;padding:4px 6px}.detailTabs{top:49px!important}

/* Stronger pulse */
.v12Pulse{border-radius:15px!important}.v13PulseBalls{display:flex;gap:5px;margin-top:10px;overflow:auto}.v13Ball{min-width:28px;height:28px;border-radius:50%;display:grid;place-items:center;background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.15);font-size:8px;font-weight:1000}.v13Ball.boundary{background:#ffcc39;color:#17345a;border-color:#ffdc73}.v13Ball.wicket{background:#e6384f;color:#fff;border-color:#ef7182}.v13PlayerLine{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:9px}.v13Player{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12);border-radius:9px;padding:8px;min-width:0}.v13Player b{display:block;font-size:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.v13Player span{display:block;color:#bed3eb;font-size:7px;margin-top:4px}

/* Commentary filters */
.v13BallFilters{display:flex;gap:6px;overflow:auto;padding:9px 10px;background:#f7fbff;border-bottom:1px solid #dce7f1;scrollbar-width:none}.v13BallFilters::-webkit-scrollbar{display:none}.v13BallFilter{border:1px solid #d1dfec;background:#fff;color:#647d96;border-radius:999px;padding:6px 9px;font-size:7px;font-weight:1000;white-space:nowrap}.v13BallFilter.active{background:#073b83;color:#fff;border-color:#073b83}.ballRow.v13Filtered{display:none!important}

/* Graphs */
.v13GraphWrap{padding:10px}.v13GraphCard{background:#fff;border:1px solid #d4e1ed;border-radius:12px;margin-bottom:9px;overflow:hidden}.v13GraphTitle{display:flex;align-items:center;justify-content:space-between;padding:9px 10px;background:#f4f8fd;border-bottom:1px solid #dce7f1}.v13GraphTitle b{font-size:9px;color:#174a7f}.v13GraphTitle span{font-size:7px;color:#8094a9}.v13Chart{padding:8px 8px 4px}.v13Chart svg{display:block;width:100%;height:150px}.v13GraphEmpty{padding:18px 12px;color:#7a8ea3;font-size:9px;line-height:1.5}.v13Bar{fill:#0b5fc5}.v13Line{fill:none;stroke:#0b5fc5;stroke-width:3;stroke-linecap:round;stroke-linejoin:round}.v13Grid{stroke:#e4ebf3;stroke-width:1}

@media(min-width:600px){.v13MiniScore{max-width:620px;margin-left:auto;margin-right:auto}.v13CardBhav{padding-left:14px;padding-right:14px}}
'''
    html = html.replace("</style>", css + "\n</style>", 1)

    js = r'''
<script>
(function(){
  const PIN_KEY='ibetin-v13-pins';
  const COLLAPSE_KEY='ibetin-v13-collapsed';
  let lastRefresh=Date.now();
  const graphCache=new Map();
  const cardBhavCache=new Map();

  function readSet(key){try{return new Set(JSON.parse(localStorage.getItem(key)||'[]'))}catch(e){return new Set()}}
  function saveSet(key,set){try{localStorage.setItem(key,JSON.stringify([...set]))}catch(e){}}
  let pins=readSet(PIN_KEY),collapsed=readSet(COLLAPSE_KEY);

  /* Premium skeletons */
  window.loading=function(el){el.innerHTML='<div class="v13Skeleton"><div class="v13SkelCard"></div><div class="v13SkelCard"></div><div class="v13SkelCard"></div></div>'};

  function formatAge(){const sec=Math.max(0,Math.floor((Date.now()-lastRefresh)/1000));if(sec<5)return'updated now';if(sec<60)return`updated ${sec}s ago`;return`updated ${Math.floor(sec/60)}m ago`}
  function ensureFresh(){const status=document.getElementById('status');if(!status)return;let el=document.getElementById('v13Fresh');if(!el){el=document.createElement('div');el.id='v13Fresh';el.className='v13Fresh';el.innerHTML='<i></i><span></span>';status.insertAdjacentElement('afterend',el)}const age=(Date.now()-lastRefresh)/1000;el.classList.toggle('stale',age>70);el.querySelector('span').textContent=formatAge()}
  setInterval(ensureFresh,1000);ensureFresh();

  const prevLoadMode=window.loadMode;
  window.loadMode=async function(mode){const out=await prevLoadMode(mode);lastRefresh=Date.now();ensureFresh();return out};

  function addPin(card){const id=String(card.dataset.id||'');if(!id||card.querySelector('.v13Pin'))return;const btn=document.createElement('button');btn.className='v13Pin';btn.type='button';btn.textContent='★';const sync=()=>{const on=pins.has(id);btn.classList.toggle('on',on);card.classList.toggle('v13Pinned',on)};sync();btn.addEventListener('click',e=>{e.stopPropagation();e.preventDefault();pins.has(id)?pins.delete(id):pins.add(id);saveSet(PIN_KEY,pins);sync();sortPins()});card.querySelector('.matchHead')?.appendChild(btn)}
  function sortPins(){document.querySelectorAll('#list .leagueMatches').forEach(box=>{const cards=[...box.querySelectorAll(':scope > .match')];cards.sort((a,b)=>(pins.has(String(b.dataset.id))-pins.has(String(a.dataset.id))));cards.forEach(c=>box.appendChild(c))})}

  function addCollapse(block){const head=block.querySelector('.leagueSectionHead');if(!head||head.querySelector('.v13Collapse'))return;const name=(block.querySelector('.leagueSectionName')?.textContent||'').trim();const btn=document.createElement('button');btn.className='v13Collapse';btn.type='button';btn.textContent='▾';head.appendChild(btn);const sync=()=>block.classList.toggle('v13Collapsed',collapsed.has(name));sync();head.addEventListener('click',e=>{if(e.target.closest('.match'))return;e.preventDefault();collapsed.has(name)?collapsed.delete(name):collapsed.add(name);saveSet(COLLAPSE_KEY,collapsed);sync()})}

  function teamLabel(label,m){const x=String(label||'').toLowerCase();if(x==='home')return m?.home?.abbr||m?.home?.name||'Home';if(x==='away')return m?.away?.abbr||m?.away?.name||'Away';return label||'—'}
  function bestTwo(entries,m){let a=null,b=null;for(const e of entries||[]){const vals=e.values||[];for(const v of vals){const label=String(v.label||'').toLowerCase();const odd=Number(v.odd);if(!Number.isFinite(odd))continue;if(label==='home'&&(!a||odd>a.odd))a={label:teamLabel(v.label,m),odd};else if(label==='away'&&(!b||odd>b.odd))b={label:teamLabel(v.label,m),odd}}}return[a,b]}
  function addCardBhav(card,m,mode,index){if(!card||card.querySelector('.v13CardBhav')||index>7||mode==='results')return;const strip=document.createElement('div');strip.className='v13CardBhav';strip.innerHTML='<div class="v13BhavLabel">BEST BHAV</div><div class="v13BhavLoading">loading…</div><div></div>';card.querySelector('.matchFoot')?.insertAdjacentElement('beforebegin',strip);const type=mode==='live'?'live':'prematch',key=String(m.id)+':'+type;const render=j=>{const [a,b]=bestTwo(j?.entries||[],m);if(!a&&!b){strip.innerHTML='<div class="v13BhavLabel">BHAV</div><div class="v13BhavLoading">not available</div><div></div>';return}strip.innerHTML=`<div class="v13BhavLabel">BEST BHAV</div><div class="v13BhavOdd"><span>${esc(a?.label||'HOME')}</span>${n(a?.odd)}</div><div class="v13BhavOdd"><span>${esc(b?.label||'AWAY')}</span>${n(b?.odd)}</div>`};if(cardBhavCache.has(key)){render(cardBhavCache.get(key));return}api({action:'bhav',matchId:m.id,oddsType:type}).then(j=>{cardBhavCache.set(key,j);render(j)}).catch(()=>{strip.innerHTML='<div class="v13BhavLabel">BHAV</div><div class="v13BhavLoading">unavailable</div><div></div>'})}

  const prevRenderMatches=window.renderMatches;
  window.renderMatches=function(items,mode){prevRenderMatches(items,mode);const map=new Map((items||[]).map(m=>[String(m.id),m]));document.querySelectorAll('#list .match').forEach((card,i)=>{addPin(card);const m=map.get(String(card.dataset.id));if(m)addCardBhav(card,m,mode,i)});document.querySelectorAll('#list .leagueBlock').forEach(addCollapse);sortPins()};

  function getStat(obj,names){for(const name of names){if(obj&&obj[name]!==undefined&&obj[name]!==null&&obj[name]!=='')return obj[name]}return '—'}
  function ballText(e){const t=String(e?.runs??e?.run??e?.event??'•');const c=String(e?.commentary||e?.description||'');const w=!!e?.wicket||/wicket|\bout\b/i.test(c);const boundary=t==='4'||t==='6'||/\bfour\b|\bsix\b/i.test(c);return{txt:w?'W':t.slice(0,3)||'•',w,boundary}}
  function upgradePulse(){const pulse=document.querySelector('#detail .v12Pulse');if(!pulse)return;const x=currentDetail||{},m=x.match||{},inp=x.inplayData||{},bats=inp.batsmen||[],bowls=inp.bowlers||[],striker=bats[0]||{},bowler=bowls[0]||{},timeline=x.timeline||[];const s=getStat(striker?.player?.statistics||striker,['runs']),sb=getStat(striker?.player?.statistics||striker,['balls']),w=getStat(bowler?.player?.statistics||bowler,['wickets']),ov=getStat(bowler?.player?.statistics||bowler,['overs']);const balls=timeline.slice(-6).map(e=>{const z=ballText(e);return`<span class="v13Ball ${z.w?'wicket':z.boundary?'boundary':''}">${esc(z.txt)}</span>`}).join('');pulse.innerHTML=`<div class="v12PulseTop"><b>⚡ LIVE PULSE</b><span class="v12PulseBadge">${/live|in play|innings|stumps|lunch|tea|drinks/i.test(String(m.state||''))?'LIVE':'MATCH'}</span></div><div class="v12PulseBody"><div class="v12PulseMain">${esc(m.report||m.state||'Match Center')}</div><div class="v12PulseSub">${esc(m.home?.abbr||m.home?.name||'Home')} ${n(m.homeScore)} · ${esc(m.away?.abbr||m.away?.name||'Away')} ${n(m.awayScore)}</div><div class="v13PlayerLine"><div class="v13Player"><b>🏏 ${esc(striker?.player?.name||striker?.name||'Striker')}</b><span>${n(s)} runs · ${n(sb)} balls</span></div><div class="v13Player"><b>🎯 ${esc(bowler?.player?.name||bowler?.name||'Bowler')}</b><span>${n(w)} wkts · ${n(ov)} ov</span></div></div>${balls?`<div class="v13PulseBalls">${balls}</div>`:''}</div>`}

  function installMiniScore(){const d=document.getElementById('detail'),hero=d?.querySelector('.scoreHero');if(!d||!hero||d.querySelector('.v13MiniScore'))return;const m=(currentDetail||{}).match||{};const bar=document.createElement('div');bar.className='v13MiniScore';bar.innerHTML=`<div class="v13MiniSide"><div class="v13MiniTeam">${esc(m.home?.abbr||m.home?.name||'HOME')}</div><div class="v13MiniVal">${n(m.homeScore)}</div></div><div class="v13MiniLive">${/live|in play|innings/i.test(String(m.state||''))?'LIVE':'MATCH'}</div><div class="v13MiniSide right"><div class="v13MiniTeam">${esc(m.away?.abbr||m.away?.name||'AWAY')}</div><div class="v13MiniVal">${n(m.awayScore)}</div></div>`;hero.insertAdjacentElement('beforebegin',bar)}

  const prevRenderDetail=window.renderDetail;
  window.renderDetail=function(){prevRenderDetail();installMiniScore();upgradePulse()};
  window.tabs=function(){return [['live','MATCH'],['bhav','BHAV'],['scorecard','SCORECARD'],['commentary','BALLS'],['graphs','GRAPHS'],['stats','STATS'],['info','INFO']].map(([x,label])=>`<button class="detailTab ${currentTab===x?'active':''}" data-tab="${x}">${label}</button>`).join('')};

  function installBallFilters(){const p=document.getElementById('panel');if(!p||p.querySelector('.v13BallFilters'))return;const rows=[...p.querySelectorAll('.ballRow')];if(!rows.length)return;const bar=document.createElement('div');bar.className='v13BallFilters';bar.innerHTML=['ALL','WICKETS','4s','6s'].map((x,i)=>`<button class="v13BallFilter ${i===0?'active':''}" data-f="${x}">${x}</button>`).join('');p.insertBefore(bar,p.firstChild.nextSibling||p.firstChild);bar.querySelectorAll('button').forEach(btn=>btn.addEventListener('click',()=>{bar.querySelectorAll('button').forEach(x=>x.classList.toggle('active',x===btn));const f=btn.dataset.f;rows.forEach(r=>{const t=(r.textContent||'').toLowerCase();let show=true;if(f==='WICKETS')show=/wicket|\bout\b/.test(t);else if(f==='4s')show=/\bfour\b|\b4\b/.test(t);else if(f==='6s')show=/\bsix\b|\b6\b/.test(t);r.classList.toggle('v13Filtered',!show)})}))}

  function findSeries(root){const found=[];const seen=new Set();function walk(node,path){if(!node||seen.has(node))return;if(typeof node==='object')seen.add(node);if(Array.isArray(node)){if(node.length>=2&&node.every(x=>x&&typeof x==='object'&&!Array.isArray(x))){const rows=[];for(let i=0;i<node.length;i++){const o=node[i];const xKeys=['over','overs','overNumber','over_number','x','index','ball'];const yKeys=['runs','score','value','runRate','run_rate','rate','y'];let xv=null,yv=null;for(const k of xKeys){const q=Number(o[k]);if(Number.isFinite(q)){xv=q;break}}for(const k of yKeys){const q=Number(o[k]);if(Number.isFinite(q)){yv=q;break}}if(yv!==null)rows.push({x:xv===null?i:xv,y:yv})}if(rows.length>=2)found.push({path,rows})}node.forEach((x,i)=>walk(x,path+'['+i+']'))}else if(typeof node==='object'){Object.entries(node).forEach(([k,v])=>walk(v,path?path+'.'+k:k))}}walk(root,'');found.sort((a,b)=>b.rows.length-a.rows.length);return found[0]||null}
  function chartSvg(series,type){const pts=series.rows.slice(0,60);const W=340,H=150,P=18;const xs=pts.map(p=>p.x),ys=pts.map(p=>p.y);const minX=Math.min(...xs),maxX=Math.max(...xs),maxY=Math.max(1,...ys);const sx=x=>P+((x-minX)/(maxX-minX||1))*(W-P*2),sy=y=>H-P-(y/maxY)*(H-P*2);const grid=[.25,.5,.75].map(q=>`<line class="v13Grid" x1="${P}" x2="${W-P}" y1="${sy(maxY*q)}" y2="${sy(maxY*q)}"/>`).join('');if(type==='bar'){const bw=Math.max(3,(W-P*2)/pts.length*.65);const bars=pts.map(p=>`<rect class="v13Bar" x="${sx(p.x)-bw/2}" y="${sy(p.y)}" width="${bw}" height="${H-P-sy(p.y)}" rx="2"/>`).join('');return`<svg viewBox="0 0 ${W} ${H}" role="img">${grid}${bars}</svg>`}const line=pts.map(p=>`${sx(p.x)},${sy(p.y)}`).join(' ');return`<svg viewBox="0 0 ${W} ${H}" role="img">${grid}<polyline class="v13Line" points="${line}"/></svg>`}
  function graphCard(title,payload,type){const s=findSeries(payload);if(!s)return`<div class="v13GraphCard"><div class="v13GraphTitle"><b>${title}</b><span>ROANUZ</span></div><div class="v13GraphEmpty">Graph data was returned, but this match does not expose a plottable numeric series in the current response.</div></div>`;return`<div class="v13GraphCard"><div class="v13GraphTitle"><b>${title}</b><span>${s.rows.length} points</span></div><div class="v13Chart">${chartSvg(s,type)}</div></div>`}
  function renderGraphs(){const p=document.getElementById('panel'),x=currentDetail||{},key=x.roanuzMatchKey||'';if(!key){p.innerHTML='<div class="panelTitle"><b>MATCH GRAPHS</b><span class="sourceTag">ROANUZ</span></div><div class="notice">Graphs will appear when this match is mapped to a Roanuz match key.</div>';return}p.innerHTML='<div class="loading"><div class="spin"></div>Loading match graphs…</div>';const render=j=>{const g=j?.graphs||{};let out='<div class="panelTitle"><b>MATCH GRAPHS</b><span class="sourceTag">ROANUZ</span></div><div class="v13GraphWrap">';if(g.worm)out+=graphCard('WORM · SCORE PROGRESSION',g.worm,'line');if(g.manhattan)out+=graphCard('MANHATTAN · RUNS PER OVER',g.manhattan,'bar');if(g.runRate)out+=graphCard('RUN RATE',g.runRate,'line');if(!g.worm&&!g.manhattan&&!g.runRate)out+='<div class="notice">Roanuz graph endpoints are not returning chart data for this match.</div>';out+='</div>';p.innerHTML=out};if(graphCache.has(key)){render(graphCache.get(key));return}api({action:'graphs',key}).then(j=>{graphCache.set(key,j);if(currentTab==='graphs')render(j)}).catch(e=>{if(currentTab==='graphs')p.innerHTML=`<div class="notice"><b>Graphs unavailable</b><br>${esc(e.message)}</div>`})}

  const prevRenderPanel=window.renderPanel;
  window.renderPanel=function(){if(currentTab==='graphs')return renderGraphs();const out=prevRenderPanel();if(currentTab==='commentary')setTimeout(installBallFilters,0);return out};

  // Repaint current list through V13 decorators and then auto-refresh live every 30s.
  setTimeout(()=>{if(window.currentMode)loadMode(currentMode)},60);
  setInterval(()=>{const home=document.getElementById('home');if(home&&home.style.display!=='none'&&window.currentMode==='live')loadMode('live')},30000);
})();
</script>
'''
    html = html.replace("</body>", js + "\n</body>")
    html = html.replace("SPORTS COMMAND CENTER · TEST MODE", "ELITE SPORTS COMMAND CENTER · TEST MODE")
    return html


liveline.admin_url = _v13_admin_url
liveline._page = _v13_page

app = v12.app

logger.info("IBETIN Live Line V13 elite command center installed on private test route")

if __name__ == "__main__":
    app.base.ibetin_start.main()
