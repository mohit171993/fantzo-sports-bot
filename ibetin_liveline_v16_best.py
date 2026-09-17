import logging
import os
from urllib.parse import urlencode

import ibetin_liveline_trial as liveline
import ibetin_liveline_v15_ui as v15

logger = logging.getLogger(__name__)

# Fresh private route for the V16 benchmark build.
liveline.LIVELINE_PATH = "/admin/liveline-ibetinv16"
liveline.LIVELINE_API_PATH = "/admin/liveline-ibetinv16/api"


def _v16_admin_url() -> str:
    root = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/") or "https://ibetin-app-production.up.railway.app"
    return f"{root}{liveline.LIVELINE_PATH}?{urlencode({'t': liveline._token(), 'v': '20260917-v16-best-market'})}"


def _v16_page() -> str:
    html = v15._v15_page()

    css = r'''
/* ============================================================
   IBETIN V16 — BEST-IN-MARKET UX LAYER
   Keeps the V14 API-saver backend and V15 Arena shell intact.
   ============================================================ */
.liveChip:after{content:'V16'!important}

/* Global polish */
.v16HeroTools{display:flex;align-items:center;gap:6px;position:relative;z-index:3}
.v16IconBtn{width:31px;height:31px;border-radius:9px;border:1px solid rgba(255,255,255,.18);background:rgba(255,255,255,.10);color:#fff;font-size:13px;font-weight:1000;display:grid;place-items:center;cursor:pointer}
.v16IconBtn:active{transform:scale(.96)}
.v15HeroPill{display:none!important}

/* True My Matches rail */
.v16MyMatches{display:none;margin:0 0 10px}
.v16MyMatches.show{display:block}
.v16SectionTop{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:0 2px 7px}
.v16SectionTop b{font-size:10px;color:#244b74;letter-spacing:.35px}.v16SectionTop span{font-size:7px;color:#8a9aab}
.v16PinnedRail{display:flex;gap:8px;overflow:auto;padding:1px 1px 3px;scroll-snap-type:x proximity}
.v16PinnedCard{min-width:196px;max-width:220px;scroll-snap-align:start;border:1px solid #dce5ee;border-radius:13px;background:#fff;padding:10px 11px;box-shadow:0 4px 14px rgba(8,38,78,.05);cursor:pointer}
.v16PinnedTop{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px}.v16PinnedTop span:first-child{font-size:6px;color:#7f91a4;font-weight:1000;letter-spacing:.55px;text-transform:uppercase}.v16PinnedLive{font-size:6px;color:#d92f45;background:#fff0f2;border:1px solid #ffd0d7;border-radius:999px;padding:3px 5px;font-weight:1000}
.v16PinnedTeams{display:grid;gap:6px}.v16PinnedTeam{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:center;font-size:9px;font-weight:950;color:#193c62}.v16PinnedTeam strong{font-size:12px;color:#08498e}.v16PinnedReport{margin-top:8px;padding-top:7px;border-top:1px solid #eef2f6;font-size:7px;color:#77899d;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

/* Match-detail utility actions */
.v16Actions{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin:0 0 9px}
.v16Action{height:36px;border:1px solid #dbe4ed;border-radius:10px;background:#fff;color:#416789;font-size:7px;font-weight:1000;display:flex;align-items:center;justify-content:center;gap:5px;cursor:pointer}
.v16Action.on{background:#fff6d6;border-color:#efd16f;color:#725600}.v16Action:active{transform:scale(.98)}

/* Recent activity summary */
.v16Activity{margin:0 0 10px;border:1px solid #dde6ee;border-radius:12px;background:#fff;overflow:hidden}
.v16ActivityHead{display:flex;align-items:center;justify-content:space-between;padding:9px 10px;background:#fafbfd;border-bottom:1px solid #edf1f5}.v16ActivityHead b{font-size:8px;color:#294f77}.v16ActivityHead span{font-size:6px;color:#8a9aab}
.v16ActivityBody{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;padding:8px}.v16ActivityStat{background:#f7f9fc;border:1px solid #e8edf2;border-radius:9px;padding:8px;text-align:center}.v16ActivityStat b{display:block;font-size:12px;color:#0b4e96}.v16ActivityStat span{display:block;font-size:5px;color:#8596a8;margin-top:3px;font-weight:900;letter-spacing:.45px}

/* Best-price odds summary */
.v16BestOdds{margin:10px 10px 0;border-radius:12px;background:linear-gradient(135deg,#f8fbff,#fff9e4);border:1px solid #dbe5ef;overflow:hidden}
.v16BestHead{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:8px 9px;border-bottom:1px solid #e9edf2}.v16BestHead b{font-size:8px;color:#234d79}.v16BestHead span{font-size:6px;color:#8797a8}.v16BestGrid{display:grid;grid-template-columns:1fr 1fr;gap:7px;padding:8px}.v16BestCell{border:1px solid #dbe8f5;background:#fff;border-radius:9px;padding:8px;text-align:center}.v16BestCell small{display:block;font-size:5px;color:#8698aa;font-weight:900;text-transform:uppercase}.v16BestCell strong{display:block;margin-top:4px;font-size:13px;color:#0b4e98}.v16Move{font-size:7px;margin-left:3px}.v16Move.up{color:#13845c}.v16Move.down{color:#d93a50}.v16BooksToggle{width:calc(100% - 20px);margin:7px 10px 10px;height:32px;border:1px solid #dce5ee;border-radius:9px;background:#f8fafc;color:#55718d;font-size:7px;font-weight:1000}.v12Book.v16HiddenBook{display:none!important}

/* Desk / Focus mode */
.v16FocusOverlay{position:fixed;inset:0;z-index:9999;background:radial-gradient(circle at 80% -10%,#125cb2 0,#071d3d 42%,#040f22 100%);color:#fff;padding:18px 16px 24px;display:none;overflow:auto}
.v16FocusOverlay.show{display:block}.v16FocusShell{max-width:680px;margin:0 auto;min-height:100%;display:flex;flex-direction:column;justify-content:center}.v16FocusTop{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:22px}.v16FocusBrand{font-size:10px;font-weight:1000;letter-spacing:1.2px;color:#b9d1ed}.v16FocusClose{height:34px;padding:0 11px;border-radius:9px;border:1px solid rgba(255,255,255,.18);background:rgba(255,255,255,.08);color:#fff;font-size:8px;font-weight:1000}.v16FocusLeague{text-align:center;color:#abc6e4;font-size:8px;letter-spacing:.6px;text-transform:uppercase}.v16FocusScore{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:12px;margin:22px 0}.v16FocusTeam{text-align:center;min-width:0}.v16FocusTeamName{font-size:12px;font-weight:950;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#dbeafa}.v16FocusRuns{font-size:34px;font-weight:1000;margin-top:8px;letter-spacing:-1px}.v16FocusVs{width:38px;height:38px;border-radius:50%;display:grid;place-items:center;background:#f6c844;color:#0b2b55;font-size:9px;font-weight:1000}.v16FocusReport{text-align:center;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.10);border-radius:13px;padding:12px;color:#d5e5f6;font-size:10px;line-height:1.45}.v16FocusBalls{display:flex;justify-content:center;gap:7px;margin-top:16px;overflow:auto}.v16FocusBall{min-width:34px;height:34px;border-radius:50%;display:grid;place-items:center;background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.14);font-size:9px;font-weight:1000}.v16FocusBall.boundary{background:#f6c844;color:#0c2d58}.v16FocusBall.wicket{background:#ef4357;color:#fff}.v16FocusMeta{text-align:center;margin-top:16px;font-size:7px;color:#93b2d2}.v16FocusRefresh{align-self:center;margin-top:16px;height:34px;border:1px solid rgba(255,255,255,.15);background:rgba(255,255,255,.08);color:#fff;border-radius:9px;padding:0 13px;font-size:7px;font-weight:1000}

/* Dark theme */
html[data-v16-theme="dark"],html[data-v16-theme="dark"] body{background:#07111f!important;color:#eaf2fb!important}
html[data-v16-theme="dark"] .content,html[data-v16-theme="dark"] .detailWrap{background:#07111f!important}
html[data-v16-theme="dark"] .navCard,html[data-v16-theme="dark"] .bottom{background:rgba(9,22,39,.96)!important;border-color:#1b2e44!important}
html[data-v16-theme="dark"] .tab,html[data-v16-theme="dark"] .v12Command,html[data-v16-theme="dark"] .leagueBlock,html[data-v16-theme="dark"] .leagueMatches .match,html[data-v16-theme="dark"] .leagueSectionHead,html[data-v16-theme="dark"] .v16PinnedCard,html[data-v16-theme="dark"] .v16Action,html[data-v16-theme="dark"] .panel,html[data-v16-theme="dark"] .scoreHero,html[data-v16-theme="dark"] .v16Activity{background:#0d1c2d!important;border-color:#203449!important;color:#dbe8f5!important}
html[data-v16-theme="dark"] .leagueMatches,html[data-v16-theme="dark"] .matchHead,html[data-v16-theme="dark"] .matchFoot,html[data-v16-theme="dark"] .panelTitle,html[data-v16-theme="dark"] .scoreTop,html[data-v16-theme="dark"] .liveSummary,html[data-v16-theme="dark"] .v16ActivityHead{background:#101f31!important;border-color:#213448!important}
html[data-v16-theme="dark"] .teamname,html[data-v16-theme="dark"] .leagueSectionName,html[data-v16-theme="dark"] .sectionTitle b,html[data-v16-theme="dark"] .v16SectionTop b,html[data-v16-theme="dark"] .v16PinnedTeam,html[data-v16-theme="dark"] .panelTitle b{color:#d9e8f7!important}
html[data-v16-theme="dark"] .score,html[data-v16-theme="dark"] .heroScore{color:#69aef2!important}
html[data-v16-theme="dark"] .v12SearchBox,html[data-v16-theme="dark"] .v12Clear,html[data-v16-theme="dark"] .v12Filter,html[data-v16-theme="dark"] .v12Sport,html[data-v16-theme="dark"] .mini,html[data-v16-theme="dark"] .v16ActivityStat{background:#122337!important;border-color:#25394f!important;color:#bcd0e4!important}
html[data-v16-theme="dark"] .detailTabs{background:#07111f!important}
html[data-v16-theme="dark"] .detailTab{background:#0d1c2d!important;border-color:#24394f!important;color:#9eb5cb!important}
html[data-v16-theme="dark"] .detailTab.active{background:#176fcf!important;color:#fff!important}
html[data-v16-theme="dark"] .v13CardBhav,html[data-v16-theme="dark"] .v12Book{background:#0d1c2d!important;border-color:#203449!important}
html[data-v16-theme="dark"] .v13BhavOdd,html[data-v16-theme="dark"] .v12Odd{background:#10263d!important;border-color:#24445f!important;color:#76b7f3!important}
html[data-v16-theme="dark"] .v16BestOdds{background:#101f31!important;border-color:#25394f!important}
html[data-v16-theme="dark"] .v16BestCell{background:#0d1c2d!important;border-color:#26405a!important}

@media(min-width:600px){.v16PinnedCard{min-width:230px}.v16Actions{max-width:520px}.v16FocusRuns{font-size:44px}}
'''
    html = html.replace("</style>", css + "\n</style>", 1)

    js = r'''
<script>
(function(){
  const THEME_KEY='ibetin-v16-theme';
  const PIN_KEY='ibetin-v13-pins';
  let v16Items=[];
  let v16Mode='live';
  let focusTimer=null;
  let wakeLock=null;
  let panelObserver=null;

  function setTheme(theme){
    const t=theme==='dark'?'dark':'light';
    document.documentElement.dataset.v16Theme=t;
    try{localStorage.setItem(THEME_KEY,t)}catch(e){}
    const btn=document.getElementById('v16ThemeBtn');if(btn)btn.textContent=t==='dark'?'☀':'☾';
    try{window.Telegram?.WebApp?.setHeaderColor(t==='dark'?'#061b3d':'#061b3d');window.Telegram?.WebApp?.setBackgroundColor(t==='dark'?'#07111f':'#f2f5f9')}catch(e){}
  }
  function currentTheme(){try{return localStorage.getItem(THEME_KEY)||'light'}catch(e){return'light'}}
  setTheme(currentTheme());

  function ensureHeroTools(){
    const top=document.querySelector('.v15HeroTop');if(!top||document.getElementById('v16ThemeBtn'))return;
    const old=top.querySelector('.v15HeroPill');if(old)old.remove();
    const tools=document.createElement('div');tools.className='v16HeroTools';tools.innerHTML='<button class="v16IconBtn" id="v16ThemeBtn" type="button" aria-label="Toggle theme">☾</button>';
    top.appendChild(tools);
    document.getElementById('v16ThemeBtn').addEventListener('click',()=>setTheme(currentTheme()==='dark'?'light':'dark'));
    setTheme(currentTheme());
  }

  function pins(){try{return new Set(JSON.parse(localStorage.getItem(PIN_KEY)||'[]'))}catch(e){return new Set()}}
  function writePins(set){try{localStorage.setItem(PIN_KEY,JSON.stringify([...set]))}catch(e){}}
  function isLive(m){return /in play|live|innings|stumps|lunch|tea|drinks|timeout/i.test(String(m?.state||''))}
  function safeScore(v){return v===null||v===undefined||v===''?'—':String(v)}

  function ensureMyMatches(){
    const home=document.getElementById('home'),command=document.getElementById('v12Command');
    if(!home||!command)return null;
    let box=document.getElementById('v16MyMatches');
    if(!box){box=document.createElement('section');box.id='v16MyMatches';box.className='v16MyMatches';box.innerHTML='<div class="v16SectionTop"><b>★ MY MATCHES</b><span>your pinned live board</span></div><div class="v16PinnedRail"></div>';command.insertAdjacentElement('afterend',box)}
    return box;
  }
  function renderMyMatches(){
    const box=ensureMyMatches();if(!box)return;
    const set=pins();const items=v16Items.filter(m=>set.has(String(m.id)));
    box.classList.toggle('show',items.length>0);
    const rail=box.querySelector('.v16PinnedRail');if(!rail)return;
    rail.innerHTML=items.map(m=>`<div class="v16PinnedCard" role="button" tabindex="0" data-id="${esc(m.id)}"><div class="v16PinnedTop"><span>${esc(m.league?.name||m.format||'Cricket')}</span>${isLive(m)?'<span class="v16PinnedLive">● LIVE</span>':''}</div><div class="v16PinnedTeams"><div class="v16PinnedTeam"><span>${esc(m.home?.abbr||m.home?.name||'Home')}</span><strong>${esc(safeScore(m.homeScore))}</strong></div><div class="v16PinnedTeam"><span>${esc(m.away?.abbr||m.away?.name||'Away')}</span><strong>${esc(safeScore(m.awayScore))}</strong></div></div><div class="v16PinnedReport">${esc(m.report||m.state||fmtTime(m.startTime)||'Open match')}</div></div>`).join('');
    rail.querySelectorAll('.v16PinnedCard').forEach(card=>{const go=()=>openMatch(card.dataset.id);card.addEventListener('click',go);card.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();go()}})});
  }

  const baseRenderMatches=window.renderMatches;
  window.renderMatches=function(items,mode){v16Items=Array.isArray(items)?items:[];v16Mode=mode||'live';baseRenderMatches(items,mode);ensureHeroTools();renderMyMatches()};
  document.addEventListener('click',e=>{if(e.target.closest('.v13Pin'))setTimeout(renderMyMatches,35)});

  function shareMatch(){
    const m=(window.currentDetail||{}).match||{};
    const text=`${m.home?.name||'Home'} ${safeScore(m.homeScore)} vs ${m.away?.name||'Away'} ${safeScore(m.awayScore)}\n${m.report||m.state||''}\nIBETIN Live Center`;
    if(navigator.share){navigator.share({title:'IBETIN Live Score',text}).catch(()=>{})}
    else if(navigator.clipboard){navigator.clipboard.writeText(text).then(()=>toast('Score copied')).catch(()=>{})}
    else toast('Share is not supported on this device');
  }
  function toast(text){
    let x=document.getElementById('v16Toast');if(!x){x=document.createElement('div');x.id='v16Toast';x.style='position:fixed;left:50%;bottom:86px;transform:translateX(-50%);z-index:10000;background:#071d3d;color:#fff;border-radius:999px;padding:9px 12px;font:800 8px Arial;box-shadow:0 8px 22px rgba(0,0,0,.2)';document.body.appendChild(x)}x.textContent=text;x.style.display='block';clearTimeout(x._t);x._t=setTimeout(()=>x.style.display='none',1600)
  }

  async function requestWake(){try{if('wakeLock'in navigator){wakeLock=await navigator.wakeLock.request('screen')}}catch(e){}}
  async function releaseWake(){try{await wakeLock?.release()}catch(e){}wakeLock=null}
  function ballObj(e){const c=String(e?.commentary||e?.description||e?.text||'');let val=String(e?.runs??e?.run??e?.event??'•');const wicket=!!e?.wicket||/wicket|\bout\b/i.test(c);const six=/\bsix\b/i.test(c)||val==='6',four=/\bfour\b/i.test(c)||val==='4';if(wicket)val='W';else if(six)val='6';else if(four)val='4';return{val:val.slice(0,3)||'•',wicket,boundary:six||four}}
  function ensureFocusOverlay(){
    let o=document.getElementById('v16FocusOverlay');if(o)return o;
    o=document.createElement('div');o.id='v16FocusOverlay';o.className='v16FocusOverlay';o.innerHTML='<div class="v16FocusShell"><div class="v16FocusTop"><div class="v16FocusBrand">IBETIN · DESK MODE</div><button class="v16FocusClose" type="button">EXIT</button></div><div id="v16FocusContent"></div><button class="v16FocusRefresh" type="button">REFRESH SCORE</button></div>';document.body.appendChild(o);
    o.querySelector('.v16FocusClose').addEventListener('click',exitFocus);o.querySelector('.v16FocusRefresh').addEventListener('click',refreshFocus);return o
  }
  function focusHtml(){
    const x=window.currentDetail||{},m=x.match||{},tl=x.timeline||[];const balls=tl.slice(-6).map(e=>{const b=ballObj(e);return`<span class="v16FocusBall ${b.wicket?'wicket':b.boundary?'boundary':''}">${esc(b.val)}</span>`}).join('');
    return `<div class="v16FocusLeague">${esc(m.league?.name||'Cricket')} · ${esc(m.format||'')}</div><div class="v16FocusScore"><div class="v16FocusTeam"><div class="v16FocusTeamName">${esc(m.home?.abbr||m.home?.name||'HOME')}</div><div class="v16FocusRuns">${esc(safeScore(m.homeScore))}</div></div><div class="v16FocusVs">VS</div><div class="v16FocusTeam"><div class="v16FocusTeamName">${esc(m.away?.abbr||m.away?.name||'AWAY')}</div><div class="v16FocusRuns">${esc(safeScore(m.awayScore))}</div></div></div><div class="v16FocusReport">${esc(m.report||m.state||'Live match')}</div>${balls?`<div class="v16FocusBalls">${balls}</div>`:''}<div class="v16FocusMeta">Auto-updates while Desk Mode is open · provider caching remains active</div>`
  }
  function renderFocus(){const o=ensureFocusOverlay(),c=document.getElementById('v16FocusContent');if(c)c.innerHTML=focusHtml();o.classList.add('show')}
  async function refreshFocus(){
    const m=(window.currentDetail||{}).match||{};if(!m.id||document.hidden)return;
    try{const j=await window.api({action:'match',id:m.id});if(j?.detail){window.currentDetail=j.detail;renderFocus()}}catch(e){}
  }
  function enterFocus(){renderFocus();requestWake();clearInterval(focusTimer);focusTimer=setInterval(refreshFocus,15000)}
  function exitFocus(){document.getElementById('v16FocusOverlay')?.classList.remove('show');clearInterval(focusTimer);focusTimer=null;releaseWake()}
  document.addEventListener('visibilitychange',()=>{if(document.hidden)releaseWake();else if(document.getElementById('v16FocusOverlay')?.classList.contains('show'))requestWake()});

  function detailPinButton(btn){
    const m=(window.currentDetail||{}).match||{},id=String(m.id||'');if(!id)return;const set=pins();const on=set.has(id);btn.classList.toggle('on',on);btn.innerHTML=(on?'★':'☆')+' PIN';
  }
  function ensureActions(){
    const d=document.getElementById('detail');if(!d||d.querySelector('.v16Actions'))return;
    const back=d.querySelector('.back');if(!back)return;
    const bar=document.createElement('div');bar.className='v16Actions';bar.innerHTML='<button class="v16Action" data-a="pin" type="button">☆ PIN</button><button class="v16Action" data-a="share" type="button">↗ SHARE</button><button class="v16Action" data-a="focus" type="button">▣ DESK</button><button class="v16Action" data-a="theme" type="button">◐ THEME</button>';back.insertAdjacentElement('afterend',bar);
    const pin=bar.querySelector('[data-a="pin"]');detailPinButton(pin);
    pin.addEventListener('click',()=>{const m=(window.currentDetail||{}).match||{},id=String(m.id||'');if(!id)return;const set=pins();set.has(id)?set.delete(id):set.add(id);writePins(set);detailPinButton(pin);renderMyMatches();toast(set.has(id)?'Match pinned':'Match unpinned')});
    bar.querySelector('[data-a="share"]').addEventListener('click',shareMatch);
    bar.querySelector('[data-a="focus"]').addEventListener('click',enterFocus);
    bar.querySelector('[data-a="theme"]').addEventListener('click',()=>setTheme(currentTheme()==='dark'?'light':'dark'));
  }

  function activityHtml(){
    const tl=(window.currentDetail||{}).timeline||[];if(!tl.length)return'';
    const recent=tl.slice(-30);let wickets=0,boundaries=0;recent.forEach(e=>{const b=ballObj(e);if(b.wicket)wickets++;if(b.boundary)boundaries++});
    return `<div class="v16Activity"><div class="v16ActivityHead"><b>RECENT ACTIVITY</b><span>last ${recent.length} events</span></div><div class="v16ActivityBody"><div class="v16ActivityStat"><b>${boundaries}</b><span>BOUNDARIES</span></div><div class="v16ActivityStat"><b>${wickets}</b><span>WICKETS</span></div><div class="v16ActivityStat"><b>${recent.length}</b><span>EVENTS</span></div></div></div>`
  }
  function decorateLivePanel(){const p=document.getElementById('panel');if(!p||currentTab!=='live'||p.querySelector('.v16Activity'))return;const h=activityHtml();if(h)p.insertAdjacentHTML('afterbegin',h)}

  function parseOdd(el){const span=el.querySelector('span');const txt=el.textContent.replace(span?.textContent||'','').trim();const m=txt.match(/[0-9]+(?:\.[0-9]+)?/);return m?Number(m[0]):null}
  function decorateBhav(){
    const p=document.getElementById('panel'),m=(window.currentDetail||{}).match||{};if(!p||currentTab!=='bhav'||p.querySelector('.v16BestOdds'))return;
    const rows=[...p.querySelectorAll('.v12Book')];if(!rows.length)return;
    let best=[null,null],labels=['HOME','AWAY'];
    rows.forEach((r,ri)=>{const odds=[...r.querySelectorAll('.v12Odd')];odds.slice(0,2).forEach((o,i)=>{const label=o.querySelector('span')?.textContent?.trim();if(label)labels[i]=label;const v=parseOdd(o);if(Number.isFinite(v)&&(!best[i]||v>best[i]))best[i]=v})});
    const key='ibetin-v16-odds-'+String(m.id||'');let prev=[];try{prev=JSON.parse(localStorage.getItem(key)||'[]')}catch(e){};
    function move(i){if(!Number.isFinite(best[i])||!Number.isFinite(Number(prev[i])))return'';if(best[i]>Number(prev[i]))return'<span class="v16Move up">▲</span>';if(best[i]<Number(prev[i]))return'<span class="v16Move down">▼</span>';return''}
    const box=document.createElement('div');box.className='v16BestOdds';box.innerHTML=`<div class="v16BestHead"><b>BEST AVAILABLE · MATCH WINNER</b><span>multi-bookmaker</span></div><div class="v16BestGrid"><div class="v16BestCell"><small>${esc(labels[0])}</small><strong>${best[0]??'—'}${move(0)}</strong></div><div class="v16BestCell"><small>${esc(labels[1])}</small><strong>${best[1]??'—'}${move(1)}</strong></div></div>`;
    const head=p.querySelector('.v12BhavHead');if(head)head.insertAdjacentElement('afterend',box);else p.prepend(box);
    try{localStorage.setItem(key,JSON.stringify(best))}catch(e){}
    if(rows.length>4){rows.slice(4).forEach(r=>r.classList.add('v16HiddenBook'));const btn=document.createElement('button');btn.className='v16BooksToggle';btn.type='button';btn.textContent=`SHOW ALL ${rows.length} BOOKMAKERS`;btn.addEventListener('click',()=>{const hidden=rows.some(r=>r.classList.contains('v16HiddenBook'));rows.slice(4).forEach(r=>r.classList.toggle('v16HiddenBook',!hidden));btn.textContent=hidden?'SHOW TOP 4 BOOKMAKERS':`SHOW ALL ${rows.length} BOOKMAKERS`});p.appendChild(btn)}
  }

  function watchPanel(){
    panelObserver?.disconnect();const p=document.getElementById('panel');if(!p)return;panelObserver=new MutationObserver(()=>{if(currentTab==='bhav')decorateBhav();if(currentTab==='live')decorateLivePanel()});panelObserver.observe(p,{childList:true,subtree:true});setTimeout(()=>{decorateBhav();decorateLivePanel()},0)
  }

  const baseRenderDetail=window.renderDetail;
  window.renderDetail=function(){baseRenderDetail();ensureActions();watchPanel();if(document.getElementById('v16FocusOverlay')?.classList.contains('show'))renderFocus()};
  const baseRenderPanel=window.renderPanel;
  window.renderPanel=function(){const out=baseRenderPanel();setTimeout(watchPanel,0);return out};

  setTimeout(()=>{ensureHeroTools();renderMyMatches();if(document.getElementById('detail')?.style.display!=='none'){ensureActions();watchPanel()}},120);
})();
</script>
'''
    html = html.replace("</body>", js + "\n</body>")
    html = html.replace("ARENA SPORTS COMMAND CENTER · PRIVATE TEST", "IBETIN SPORTS INTELLIGENCE · V16 PRIVATE TEST")
    return html


liveline.admin_url = _v16_admin_url
liveline._page = _v16_page

app = v15.app

logger.info("IBETIN Live Line V16 best-in-market UX installed on private test route")

if __name__ == "__main__":
    app.base.ibetin_start.main()
