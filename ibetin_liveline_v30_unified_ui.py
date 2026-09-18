import logging

import ibetin_liveline_v25_fast_cache as v25

logger = logging.getLogger(__name__)
v23 = v25.v23
API_PATH = v23.liveline.LIVELINE_API_PATH


def _page_v30() -> str:
    html = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta http-equiv="Cache-Control" content="no-store">
<meta name="referrer" content="no-referrer">
<title>IBETIN Live Cricket</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
:root{--bg:#eef3f8;--navy:#071a34;--blue:#0b5cb4;--gold:#f6c84b;--ink:#102c4b;--muted:#7b8ea2;--card:#fff;--live:#ef4763;--green:#0c9a68;--shadow:0 8px 24px rgba(5,34,69,.08)}
*{box-sizing:border-box}html,body{margin:0;min-height:100%;font-family:Inter,Arial,sans-serif;background:var(--bg);color:var(--ink);-webkit-tap-highlight-color:transparent}body{padding-bottom:calc(145px + env(safe-area-inset-bottom));scroll-padding-bottom:calc(145px + env(safe-area-inset-bottom))}
.shell{max-width:760px;margin:auto}.top{position:sticky;top:0;z-index:30;background:linear-gradient(118deg,#041326,#0a315f 74%,#0b4d8e);color:#fff;padding:14px 16px 12px;box-shadow:0 5px 18px rgba(4,23,47,.18)}
.toprow{display:flex;align-items:center;justify-content:space-between}.brand{display:flex;align-items:center;gap:11px}.mark{width:46px;height:46px;border-radius:14px;background:var(--gold);color:#17314e;display:grid;place-items:center;font-weight:1000;font-size:23px}.brand b{display:block;font-size:22px;letter-spacing:1px}.brand span{display:block;font-size:11px;color:#c7d8eb;margin-top:2px}.liveDot{font-size:11px;font-weight:900;padding:7px 10px;border-radius:999px;background:rgba(14,160,105,.19);border:1px solid rgba(81,220,162,.3);color:#fff}
.tabs{display:grid;grid-template-columns:repeat(3,1fr);gap:9px;margin-top:14px}.tab{height:48px;border:0;border-radius:13px;background:rgba(255,255,255,.08);color:#c5d6e9;font-size:14px;font-weight:900}.tab.on{background:#fff;color:#0a315f}
.main{padding:16px 16px calc(145px + env(safe-area-inset-bottom))}.tools{display:flex;gap:10px;margin-bottom:8px}.search{flex:1;height:52px;border:1px solid #e7edf3;border-radius:15px;background:#fff;padding:0 16px;font-size:15px;outline:none;box-shadow:var(--shadow)}.refresh{width:52px;border:1px solid #e7edf3;border-radius:15px;background:#fff;color:#0a4f98;font-size:23px;box-shadow:var(--shadow)}.status{font-size:12px;color:#8293a5;margin:10px 3px 12px}.list{display:grid;gap:12px}.league{font-size:14px;font-weight:900;color:#46627f;margin:8px 3px 1px}
.match{background:#fff;border-radius:18px;overflow:hidden;box-shadow:var(--shadow);border-left:4px solid #dbe5ef;cursor:pointer}.match.live{border-left-color:var(--live)}.mh{display:flex;justify-content:space-between;gap:10px;align-items:center;padding:13px 14px 5px}.fmt{font-size:11px;color:#8697a8;font-weight:800}.badge{font-size:10px;font-weight:1000;padding:6px 8px;border-radius:999px;background:#eef4fb;color:#51718f}.badge.live{background:#fff0f2;color:#d72d45}
.team{display:grid;grid-template-columns:auto 1fr auto;gap:10px;align-items:center;padding:10px 14px}.miniMark,.teamMark{border-radius:50%;display:grid;place-items:center;background:#edf4fb;color:#0b4f94;font-weight:1000;border:1px solid #dbe7f2;overflow:hidden}.miniMark{width:34px;height:34px;font-size:10px}.teamMark{width:40px;height:40px;font-size:11px}.miniMark img,.teamMark img{width:100%;height:100%;object-fit:cover}.tn{font-size:17px;font-weight:1000}.ta{font-size:10px;color:#96a5b4;margin-top:2px}.sc{text-align:right;font-size:27px;font-weight:1000;color:#083f7f;letter-spacing:-.5px}.si{text-align:right;font-size:11px;color:#8b9bad;margin-top:2px}
.oddsRow{display:grid;grid-template-columns:auto 1fr 1fr;gap:7px;align-items:center;padding:9px 14px;border-top:1px solid #f0f3f6;background:#fbfdff}.oddsTitle{font-size:9px;font-weight:1000;color:#7d91a5;letter-spacing:.35px;white-space:nowrap}.oddBox{min-width:0;background:#edf5fd;border:1px solid #dbe9f6;border-radius:10px;padding:8px 9px;display:flex;align-items:center;justify-content:space-between;gap:6px}.oddLabel{font-size:9px;font-weight:800;color:#5e7891;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.oddValue{font-size:13px;font-weight:1000;color:#0a579e;white-space:nowrap}.foot{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:11px 14px;border-top:1px solid #f0f3f6;font-size:12px;color:#6f8499}
.empty,.err,.loading{background:#fff;border-radius:16px;padding:30px 16px;text-align:center;color:#73879a;font-size:13px;box-shadow:var(--shadow)}.spin{width:24px;height:24px;border:3px solid #dce5ed;border-top-color:#0b5cb4;border-radius:50%;animation:s .7s linear infinite;margin:0 auto 10px}@keyframes s{to{transform:rotate(360deg)}}
.detail{display:none;padding:16px 16px calc(175px + env(safe-area-inset-bottom))}.back{height:44px;border:0;border-radius:13px;background:#fff;color:#24578d;font-size:14px;font-weight:1000;padding:0 14px;box-shadow:0 2px 10px rgba(6,37,70,.04)}.scorehero{margin-top:10px;border-radius:20px;background:#fff;overflow:hidden;border:1px solid #e6edf4;box-shadow:var(--shadow)}.scoretop{padding:12px 14px;border-bottom:1px solid #edf1f5;font-size:11px;color:#6f8397;display:flex;justify-content:space-between;gap:10px}.scoremain{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:10px;padding:20px 14px}.side.right{text-align:right}.teamIdentity{display:flex;align-items:center;gap:8px;margin-bottom:6px}.side.right .teamIdentity{justify-content:flex-end}.sname{font-size:13px;font-weight:1000;color:#294662}.sval{font-size:31px;font-weight:1000;color:#083f7f;margin-top:4px;letter-spacing:-.6px}.vs{width:38px;height:38px;border-radius:50%;background:#fff5cf;color:#765700;display:grid;place-items:center;font-size:10px;font-weight:1000}.report{padding:12px 14px;background:#fbfdff;border-top:1px solid #edf1f5;font-size:11px;color:#637b91}
.quickMarket{margin-top:11px;background:#fff;border-radius:16px;padding:13px;box-shadow:var(--shadow);border:1px solid #e6edf4}.quickHead{display:flex;align-items:center;justify-content:space-between;margin-bottom:9px}.quickHead b{font-size:13px}.quickHead span{font-size:9px;color:#6c8297;font-weight:900}.quickOdds{display:grid;grid-template-columns:1fr 1fr;gap:8px}.quickOdd{background:#edf5fd;border:1px solid #dbe9f6;border-radius:12px;padding:10px}.quickOdd small{display:block;color:#6d8297;font-size:9px;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.quickOdd strong{display:block;color:#084f94;font-size:20px;margin-top:3px}.sessionTitle{font-size:10px;font-weight:1000;color:#73889c;margin:12px 0 6px}.sessionGrid{display:grid;gap:7px}.sessionCard{background:#f8fafc;border:1px solid #e7edf3;border-radius:11px;padding:9px}.sessionCard b{font-size:10px;color:#284d70}.sessionVals{display:flex;gap:8px;flex-wrap:wrap;margin-top:5px;font-size:10px;color:#637b92}.sessionVals strong{color:#0a579e}.quickLoading{font-size:11px;color:#758a9f;padding:4px 0}
.chaseBox{margin-top:9px;background:linear-gradient(135deg,#edf6ff,#f8fbff);border:1px solid #d8e9f8;border-radius:12px;padding:11px 12px}.chaseBox b{display:block;font-size:14px;color:#164a79}.chaseBox span{font-size:10px;color:#6f8498}.lastSix{display:flex;align-items:center;gap:6px;overflow:auto;margin-top:10px;scrollbar-width:none}.lastSix::-webkit-scrollbar{display:none}.lastSixTitle{font-size:9px;font-weight:1000;color:#8194a7;letter-spacing:.4px;margin-right:2px;white-space:nowrap}.ballChip{width:30px;height:30px;border-radius:50%;display:grid;place-items:center;background:#eaf1f8;color:#294d70;font-size:10px;font-weight:1000;flex:none}.ballChip.boundary{background:#e6f4ff;color:#0968b7}.ballChip.six{background:#efe9ff;color:#6943b5}.ballChip.wicket{background:#fff0f2;color:#d02f47}.ballChip.extra{background:#fff6db;color:#856200}
.dtabs{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:6px;margin:11px 0}.dtab{height:43px;border:1px solid #e4ebf2;border-radius:12px;background:#fff;color:#687f96;font-size:9px;font-weight:1000;padding:0 3px}.dtab.on{background:#0a315f;color:#fff;border-color:#0a315f}.panel{background:#fff;border-radius:16px;padding:13px;box-shadow:var(--shadow);margin-bottom:14px}.ptitle{margin-bottom:10px}.ptitle b{font-size:13px}.notice{background:#f7f9fb;border-radius:12px;padding:11px;font-size:11px;color:#647c92;line-height:1.5;margin-bottom:8px}.metricRow{display:flex;gap:7px;flex-wrap:wrap}.metric{display:inline-flex;gap:4px;align-items:center;background:#edf4fb;border-radius:999px;padding:7px 9px;color:#58728b;font-size:10px}.playerStrip{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}.playerCard{background:#f7f9fc;border:1px solid #e8edf3;border-radius:12px;padding:10px;min-width:0}.playerRole{font-size:8px;font-weight:1000;color:#8b9caf;letter-spacing:.6px;margin-bottom:4px}.playerName{font-size:11px;font-weight:900;color:#173a5e;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.playerStat{font-size:10px;color:#617b93;margin-top:3px}
.innings{display:grid;gap:8px}.inning{border:1px solid #e7edf3;background:#f9fbfd;border-radius:12px;padding:11px}.inningTop{display:flex;align-items:center;justify-content:space-between;gap:8px}.inningTeam{font-size:12px;font-weight:900}.inningScore{font-size:18px;font-weight:1000;color:#083f7f}.inningMeta{font-size:10px;color:#8091a2;margin-top:4px}.balls{display:grid;gap:7px}.ball{background:#f8fafc;border-radius:10px;padding:9px;font-size:10px;line-height:1.45}.moreGrid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.moreItem{border:1px solid #e5ebf2;background:#f8fafc;border-radius:13px;padding:14px 11px;text-align:left;color:#234766;font-size:11px;font-weight:900}.moreItem span{display:block;font-size:9px;font-weight:600;color:#7d90a3;margin-top:4px}.kv{display:grid;grid-template-columns:1fr auto;gap:8px;padding:9px 0;border-bottom:1px solid #edf1f4;font-size:10px}.kv b{color:#244867}
.bottom{position:fixed;left:14px;right:14px;bottom:calc(10px + env(safe-area-inset-bottom));z-index:40;max-width:732px;margin:auto;display:grid;grid-template-columns:repeat(4,1fr);gap:4px;background:rgba(5,22,45,.98);border-radius:20px;padding:8px;box-shadow:0 12px 30px rgba(4,23,48,.25)}.bottom button{border:0;background:transparent;color:#9fb2c8;height:54px;border-radius:13px;font-size:9px;font-weight:1000}.bottom b{display:block;font-size:18px;margin-bottom:2px}.bottom .on{background:rgba(255,255,255,.1);color:#fff}
@media(min-width:620px){.list{grid-template-columns:1fr 1fr}.league{grid-column:1/-1}}@media(max-width:390px){.brand b{font-size:20px}.mark{width:42px;height:42px}.tab{font-size:12px}.tn{font-size:15px}.sc{font-size:24px}.sval{font-size:27px}.playerStrip{grid-template-columns:1fr}.oddsRow{grid-template-columns:1fr 1fr}.oddsTitle{grid-column:1/-1}.dtab{font-size:8px}.quickOdds{grid-template-columns:1fr 1fr}}
</style><link rel="icon" href="data:">
</head>
<body>
<div class="shell">
<header class="top"><div class="toprow"><div class="brand"><div class="mark">I</div><div><b>IBETIN</b><span>LIVE CRICKET</span></div></div><div class="liveDot">● LIVE</div></div><div class="tabs"><button class="tab on" data-mode="live">● LIVE</button><button class="tab" data-mode="upcoming">UPCOMING</button><button class="tab" data-mode="results">RESULTS</button></div></header>
<main id="home" class="main"><div class="tools"><input id="search" class="search" placeholder="Search match, team or tournament"><button id="refresh" class="refresh">↻</button></div><div id="status" class="status">Loading live cricket…</div><div id="list" class="list"></div></main>
<section id="detail" class="detail"></section>
</div>
<nav class="bottom"><button class="on" data-nav="home"><b>⌂</b>HOME</button><button data-nav="live"><b style="color:#ff5b6f">●</b>LIVE</button><button data-nav="fixtures"><b>◷</b>FIXTURES</button><button data-nav="search"><b>⌕</b>SEARCH</button></nav>
<script>
'use strict';
const tg=window.Telegram&&window.Telegram.WebApp;
if(tg){try{tg.ready();tg.expand();tg.setHeaderColor('#071a34');tg.setBackgroundColor('#eef3f8')}catch(e){}}
const qs=new URLSearchParams(location.search),TOKEN=qs.get('t')||'',API_PATH='__API_PATH__';
let mode='live',allMatches=[],detailData=null,detailTab='match',refreshTimer=null,loadGeneration=0,lastHomeLoad=0;
const bhavCache=new Map(),bhavBusy=new Set();
const BHAV_TTL=10000;
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot',"'":'&#39;'}[m]));
const display=v=>v===null||v===undefined||v===''?'—':esc(v);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function api(params,retry=true){params.t=TOKEN;const ctrl=new AbortController(),timer=setTimeout(()=>ctrl.abort(),7000);try{const r=await fetch(API_PATH+'?'+new URLSearchParams(params),{cache:'no-store',signal:ctrl.signal});const j=await r.json();if(!r.ok||!j.ok)throw new Error(j.error||('HTTP '+r.status));return j}catch(e){if(retry&&e.name!=='AbortError'){await sleep(250);return api(params,false)}throw e}finally{clearTimeout(timer)}}
function loading(el){el.innerHTML='<div class="loading"><div class="spin"></div>Loading…</div>'}
function fmtTime(v){if(!v)return'';try{let x=v;if(typeof v==='string'&&/^\d+(\.\d+)?$/.test(v))x=Number(v)*1000;else if(typeof v==='number'&&v<1000000000000)x=v*1000;const d=new Date(x);if(Number.isNaN(d.getTime()))return'';return d.toLocaleString([],{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})}catch(e){return''}}
function prettyState(v){const s=String(v||'').toLowerCase().replace(/[_-]+/g,' ').trim();if(!s)return'';if(['in play','inplay','started','live','playing'].includes(s))return'LIVE';if(['not started','scheduled','upcoming','fixture','created','confirmed'].includes(s))return'UPCOMING';if(['completed','complete','finished','result','ended','closed'].includes(s))return'FINAL';return s.replace(/\b\w/g,c=>c.toUpperCase())}
function matchKey(m){return String(m?.roanuzMatchKey||m?.id||'')}
function league(m){return m?.league?.name||'Cricket'}
function initials(t){const n=String(t?.name||t?.abbr||'TM').trim(),p=n.split(/\s+/).filter(Boolean);return (p.length>1?(p[0][0]+p[1][0]):n.slice(0,2)).toUpperCase()}
function imageUrl(t){return t?.logo||t?.logoUrl||t?.image||t?.imageUrl||t?.flag||t?.flagUrl||''}
function miniMark(t){const u=imageUrl(t),i=esc(initials(t));return u?`<span class="miniMark"><img src="${esc(u)}" alt="" onerror="this.parentElement.textContent='${i}'"></span>`:`<span class="miniMark">${i}</span>`}
function teamMark(t){const u=imageUrl(t),i=esc(initials(t));return u?`<span class="teamMark"><img src="${esc(u)}" alt="" onerror="this.parentElement.textContent='${i}'"></span>`:`<span class="teamMark">${i}</span>`}
function teamRow(t,s,i){return `<div class="team">${miniMark(t)}<div><div class="tn">${esc(t?.name||t?.abbr||'Team')}</div><div class="ta">${esc(t?.abbr||'')}</div></div><div><div class="sc">${display(s)}</div><div class="si">${esc(i||'')}</div></div></div>`}
function entries(j){return Array.isArray(j?.entries)?j.entries:[]}
function values(e){return Array.isArray(e?.values)?e.values.filter(v=>v&&v.odd!==undefined&&v.odd!==null):[]}
function findMatchMarket(j){const es=entries(j);return es.find(e=>/match|winner|moneyline/i.test(String(e?.market||''))&&values(e).length>=2)||es.find(e=>values(e).length>=2)||null}
function sessionMarkets(j,main){return entries(j).filter(e=>e!==main&&values(e).length>=2&&/over|session|runs|line|total|fancy|innings/i.test(String(e?.market||''))).slice(0,3)}
function homeOddsHtml(m){if(mode!=='live')return'';const c=bhavCache.get(matchKey(m));if(!c?.data)return'';const market=findMatchMarket(c.data);if(!market)return'';const vs=values(market).slice(0,2);return `<div class="oddsRow"><span class="oddsTitle">MATCH ODDS</span>${vs.map(x=>`<div class="oddBox"><span class="oddLabel">${esc(x.label||'Selection')}</span><span class="oddValue">${esc(x.odd)}</span></div>`).join('')}</div>`}
function card(m){const live=mode==='live',label=live?'● LIVE':mode==='upcoming'?(fmtTime(m.startTime)||'UPCOMING'):(prettyState(m.state)||'FINAL');return `<article class="match ${live?'live':''}" data-key="${esc(matchKey(m))}"><div class="mh"><div class="fmt">${esc(m.format||'CRICKET')} · ${esc(league(m))}</div><span class="badge ${live?'live':''}">${esc(label)}</span></div>${teamRow(m.home,m.homeScore,m.homeInfo)}${teamRow(m.away,m.awayScore,m.awayInfo)}${homeOddsHtml(m)}<div class="foot"><span>${esc(m.report||prettyState(m.state)||fmtTime(m.startTime)||'Tap for details')}</span><b>›</b></div></article>`}
function render(){const q=(document.getElementById('search').value||'').trim().toLowerCase(),rows=allMatches.filter(m=>!q||[m.home?.name,m.away?.name,league(m),m.format].join(' ').toLowerCase().includes(q)),list=document.getElementById('list');if(!rows.length){list.innerHTML='<div class="empty">No matching cricket matches found.</div>';return}let last='';list.innerHTML=rows.map(m=>{const l=league(m),h=l!==last?`<div class="league">${esc(l)}</div>`:'';last=l;return h+card(m)}).join('');list.querySelectorAll('.match').forEach(el=>el.onclick=()=>openMatch(el.dataset.key));if(mode==='live')setTimeout(()=>rows.slice(0,6).forEach(m=>getBhav(matchKey(m))),120)}
function mergeScore(base,fresh){if(!base||!fresh)return base;return {...base,home:fresh.home||base.home,away:fresh.away||base.away,homeScore:fresh.homeScore||base.homeScore,homeInfo:fresh.homeInfo||base.homeInfo,awayScore:fresh.awayScore||base.awayScore,awayInfo:fresh.awayInfo||base.awayInfo,report:fresh.report||base.report,state:fresh.state||base.state}}
async function hydrateScore(m){const key=matchKey(m);if(!key)return;try{const j=await api({action:'score',key});const i=allMatches.findIndex(x=>matchKey(x)===key);if(i>=0){allMatches[i]=mergeScore(allMatches[i],j.match||{});render()}}catch(e){}}
async function getBhav(key,force=false){if(!key)return null;const c=bhavCache.get(key);if(!force&&c&&Date.now()-c.ts<BHAV_TTL)return c.data;if(bhavBusy.has(key))return c?.data||null;bhavBusy.add(key);try{const j=await api({action:'bhav',matchId:key},false);bhavCache.set(key,{ts:Date.now(),data:j});if(mode==='live'&&document.getElementById('home').style.display!=='none')render();return j}catch(e){bhavCache.set(key,{ts:Date.now(),data:null});return null}finally{bhavBusy.delete(key)}}
async function load(nextMode=mode,force=false){mode=nextMode;document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('on',b.dataset.mode===mode));const gen=++loadGeneration,list=document.getElementById('list');if(force||!allMatches.length)loading(list);document.getElementById('status').textContent='Updating '+mode+' matches…';try{const j=await api({action:'matches',mode});if(gen!==loadGeneration)return;allMatches=j.matches||[];render();lastHomeLoad=Date.now();const stamp=j.generatedAt?new Date(j.generatedAt):new Date();document.getElementById('status').textContent=`${allMatches.length} ${mode==='live'?'live ':''}matches · Updated ${stamp.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}`;if(mode==='live'){allMatches.slice(0,6).forEach(hydrateScore);setTimeout(()=>allMatches.slice(0,6).forEach(hydrateScore),1600)}}catch(e){if(gen!==loadGeneration)return;if(allMatches.length){document.getElementById('status').textContent='Showing last update · Refresh to retry'}else list.innerHTML='<div class="err">Live cricket is temporarily unavailable.<br><br><button class="back" onclick="load(mode,true)">RETRY</button></div>'}if(refreshTimer)clearInterval(refreshTimer);if(mode==='live')refreshTimer=setInterval(()=>{if(!document.hidden&&document.getElementById('home').style.display!=='none')load('live')},30000)}
function showTelegramBack(on){if(!tg?.BackButton)return;try{if(on){tg.BackButton.show();tg.BackButton.onClick(backHome)}else{tg.BackButton.offClick(backHome);tg.BackButton.hide()}}catch(e){}}
async function openMatch(key){if(!key)return;document.getElementById('home').style.display='none';const d=document.getElementById('detail');d.style.display='block';loading(d);showTelegramBack(true);try{const j=await api({action:'match',id:key});detailData=j.detail||{};detailTab='match';drawDetail();getBhav(key).then(x=>{if(document.getElementById('quickMarket'))renderQuickMarket(x);if(detailTab==='bhav')drawPanel()})}catch(e){d.innerHTML=`<button class="back" onclick="backHome()">← BACK</button><div class="err">Unable to load match details.<br><br><button class="back" onclick="openMatch('${esc(key)}')">RETRY</button></div>`}}
function backHome(){document.getElementById('detail').style.display='none';document.getElementById('home').style.display='block';detailData=null;showTelegramBack(false);window.scrollTo({top:0,behavior:'smooth'});if(Date.now()-lastHomeLoad>15000)load(mode)}
function targetRuns(t){if(!t||typeof t!=='object')return null;for(const k of ['runs','target','score','target_runs','targetRuns']){const v=Number(t[k]);if(Number.isFinite(v)&&v>0)return v}return null}
function targetBalls(t){if(!t||typeof t!=='object')return null;for(const k of ['balls','balls_remaining','ballsRemaining']){const v=Number(t[k]);if(Number.isFinite(v)&&v>=0)return v}return null}
function scoreRuns(s){const m=String(s||'').match(/^\s*(\d+)/);return m?Number(m[1]):null}
function scoreOvers(info){const m=String(info||'').match(/(\d+)(?:\.(\d+))?/);if(!m)return null;return Number(m[1])*6+Number(m[2]||0)}
function chaseInfo(target,m){const tr=targetRuns(target);if(!tr)return'';const h=scoreRuns(m.homeScore),a=scoreRuns(m.awayScore),hb=scoreOvers(m.homeInfo),ab=scoreOvers(m.awayInfo);let battingRuns=null,ballsUsed=null,team='Chasing side';if(ab!==null&&(hb===null||ab>=hb)){battingRuns=a;ballsUsed=ab;team=m.away?.name||team}else if(hb!==null){battingRuns=h;ballsUsed=hb;team=m.home?.name||team}const need=battingRuns===null?null:Math.max(0,tr-battingRuns);let balls=targetBalls(target);if(balls===null&&ballsUsed!==null)balls=Math.max(0,120-ballsUsed);if(need===null)return `<div class="chaseBox"><b>Target ${tr}</b></div>`;const rrr=balls>0?((need*6)/balls).toFixed(2):null;return `<div class="chaseBox"><b>${esc(team)} need ${need}${balls!==null?' from '+balls+' balls':''}</b><span>Target ${tr}${rrr?' · RRR '+rrr:''}</span></div>`}
function ballOutcome(e){const s=String(e?.commentary||e?.comment||e?.description||e?.text||'').toLowerCase();if(/six|6 runs|6 run/.test(s))return['6','six'];if(/four|4 runs|4 run/.test(s))return['4','boundary'];if(/wicket|out\b|bowled|caught|lbw|run out/.test(s))return['W','wicket'];if(/no.?ball/.test(s))return['NB','extra'];if(/wide/.test(s))return['WD','extra'];const m=s.match(/\b([0-3]) runs?\b/);if(m)return[m[1],''];if(/dot ball|no run/.test(s))return['•',''];return['•','']}
function lastSixHtml(rows){const a=(Array.isArray(rows)?rows:[]).slice(-6);if(!a.length)return'';return `<div class="lastSix"><span class="lastSixTitle">LAST 6</span>${a.map(e=>{const o=ballOutcome(e);return `<span class="ballChip ${o[1]}">${o[0]}</span>`}).join('')}</div>`}
function rateValue(v){if(v===null||v===undefined||v==='')return'';if(typeof v==='number'||typeof v==='string')return String(v);if(typeof v==='object'){for(const k of ['current','value','rate','run_rate','runRate'])if(v[k]!==undefined&&v[k]!==null)return String(v[k])}return''}
function normKey(s){return String(s||'').toLowerCase().replace(/[^a-z0-9]/g,'')}
function deepFind(root,aliases,depth=0,seen){if(root===null||root===undefined||depth>5||typeof root!=='object')return null;seen=seen||new Set();if(seen.has(root))return null;seen.add(root);const wanted=new Set(aliases.map(normKey));for(const [k,v] of Object.entries(root))if(wanted.has(normKey(k))&&v!==null&&v!==undefined)return v;for(const v of Object.values(root)){if(v&&typeof v==='object'){const found=deepFind(v,aliases,depth+1,seen);if(found!==null&&found!==undefined)return found}}return null}
function playerInfo(v){if(v===null||v===undefined)return null;if(typeof v==='string')return{name:v,stat:''};if(typeof v!=='object')return null;const p=(v.player&&typeof v.player==='object')?v.player:v,name=p.name||p.full_name||p.fullName||p.short_name||p.shortName||p.player_name||p.playerName||v.name||'';if(!name)return null;const runs=v.runs??v.score??p.runs??p.score,balls=v.balls??v.balls_faced??v.ballsFaced??p.balls??p.balls_faced,wickets=v.wickets??p.wickets,overs=v.overs??p.overs;let stat='';if(runs!==undefined&&runs!==null)stat=String(runs)+(balls!==undefined&&balls!==null?' ('+balls+')':'');else if(wickets!==undefined&&wickets!==null)stat=String(wickets)+' wkts'+(overs!==undefined&&overs!==null?' · '+overs+' ov':'');return{name:String(name),stat}}
function currentPlayersHtml(detail){const root=detail?.inplayData||{},striker=playerInfo(deepFind(root,['striker','current_striker','currentBatsman','current_batsman','batsman','batter','on_strike'])),bowler=playerInfo(deepFind(root,['bowler','current_bowler','currentBowler','bowling','currentBowling']));if(!striker&&!bowler)return'';return `<div class="playerStrip">${striker?`<div class="playerCard"><div class="playerRole">AT CREASE</div><div class="playerName">${esc(striker.name)}</div>${striker.stat?`<div class="playerStat">${esc(striker.stat)}</div>`:''}</div>`:''}${bowler?`<div class="playerCard"><div class="playerRole">BOWLER</div><div class="playerName">${esc(bowler.name)}</div>${bowler.stat?`<div class="playerStat">${esc(bowler.stat)}</div>`:''}</div>`:''}</div>`}
function quickMarketHtml(j){if(!j)return'';const main=findMatchMarket(j);if(!main)return'';const mv=values(main).slice(0,2),sessions=sessionMarkets(j,main);return `<div class="quickHead"><b>LIVE BHAV</b><span>LIVE MARKET</span></div><div class="quickOdds">${mv.map(v=>`<div class="quickOdd"><small>${esc(v.label||'Selection')}</small><strong>${esc(v.odd)}</strong></div>`).join('')}</div>${sessions.length?`<div class="sessionTitle">SESSION MARKETS</div><div class="sessionGrid">${sessions.map(e=>`<div class="sessionCard"><b>${esc(e.market||'Session')}</b><div class="sessionVals">${values(e).slice(0,3).map(v=>`<span>${esc(v.label||'Line')} <strong>${esc(v.odd)}</strong></span>`).join('')}</div></div>`).join('')}</div>`:''}`}
function renderQuickMarket(j){const el=document.getElementById('quickMarket');if(!el)return;const h=quickMarketHtml(j);if(h){el.style.display='block';el.innerHTML=h}else{el.style.display='none';el.innerHTML=''}}
function tabsHtml(){const moreOn=['more','graphs','stats','info'].includes(detailTab);return [['match','MATCH'],['bhav','BHAV'],['scorecard','SCORECARD'],['balls','BALLS'],['more','MORE']].map(([k,l])=>`<button class="dtab ${(detailTab===k||(k==='more'&&moreOn))?'on':''}" data-tab="${k}">${l}</button>`).join('')}
function drawDetail(){const d=document.getElementById('detail'),m=detailData?.match||{},cached=bhavCache.get(matchKey(m))?.data||null;d.innerHTML=`<button class="back" onclick="backHome()">← BACK</button><div class="scorehero"><div class="scoretop"><span>${esc(league(m))} · ${esc(m.format||'')}</span><span>${esc(prettyState(m.state)||'')}</span></div><div class="scoremain"><div class="side"><div class="teamIdentity">${teamMark(m.home)}</div><div class="sname">${esc(m.home?.name||'Home')}</div><div class="sval">${display(m.homeScore)}</div><div class="ta">${esc(m.homeInfo||'')}</div></div><div class="vs">VS</div><div class="side right"><div class="teamIdentity">${teamMark(m.away)}</div><div class="sname">${esc(m.away?.name||'Away')}</div><div class="sval">${display(m.awayScore)}</div><div class="ta">${esc(m.awayInfo||'')}</div></div></div><div class="report">${esc(m.report||prettyState(m.state)||'')}${detailData?.roanuz?.target?chaseInfo(detailData.roanuz.target,m):''}${lastSixHtml(detailData?.timeline||[])}</div></div><div id="quickMarket" class="quickMarket" style="${cached?'':'display:block'}">${cached?quickMarketHtml(cached):'<div class="quickLoading">Loading live BHAV…</div>'}</div><div class="dtabs">${tabsHtml()}</div><div id="panel" class="panel"></div>`;d.querySelectorAll('.dtab').forEach(b=>b.onclick=()=>{detailTab=b.dataset.tab;drawDetail()});drawPanel()}
function inningsRows(detail){if(Array.isArray(detail?.statistics)&&detail.statistics.length)return detail.statistics;if(Array.isArray(detail?.innings))return detail.innings;return[]}
function inningScore(row){if(!row||typeof row!=='object')return'';if(row.score_str)return String(row.score_str).split(' in ')[0];const s=row.score&&typeof row.score==='object'?row.score:{},runs=s.runs??row.runs??row.score,w=s.wickets??row.wickets;if(runs===undefined||runs===null||typeof runs==='object')return'';return String(runs)+(w!==undefined&&w!==null?'/'+w:'')}
function inningOvers(row){if(!row||typeof row!=='object')return'';let v=row.overs??row.over??(row.score&&typeof row.score==='object'?row.score.overs:null);if(Array.isArray(v))return v.length>1?`${v[0]}.${v[1]} ov`:'';return v!==undefined&&v!==null&&v!==''?String(v)+(String(v).toLowerCase().includes('ov')?'':' ov'):''}
function inningName(row,i){if(!row||typeof row!=='object')return `Innings ${i+1}`;const t=row.team||row.batting_team||row.battingTeam||row.team_name||row.name;if(typeof t==='string'&&t)return t;if(t&&typeof t==='object')return t.name||t.short_name||t.shortName||`Innings ${i+1}`;return `Innings ${i+1}`}
function scorecardHtml(detail){const rows=inningsRows(detail);if(!rows.length)return'<div class="notice">Scorecard will appear as soon as innings data is available.</div>';return `<div class="innings">${rows.map((r,i)=>`<div class="inning"><div class="inningTop"><div class="inningTeam">${esc(inningName(r,i))}</div><div class="inningScore">${esc(inningScore(r)||'—')}</div></div><div class="inningMeta">${esc(inningOvers(r))}</div></div>`).join('')}</div>`}
function ballsHtml(detail){const a=Array.isArray(detail?.timeline)?detail.timeline:[];if(!a.length)return'<div class="notice">Ball-by-ball will appear with the next live update.</div>';return `<div class="balls">${a.slice().reverse().slice(0,60).map((e,i)=>`<div class="ball"><b>${esc(e.over||e.ball||('#'+(i+1)))}</b><br>${esc(e.commentary||e.comment||e.description||e.text||'Delivery update')}</div>`).join('')}</div>`}
function ptitle(t){return `<div class="ptitle"><b>${esc(t)}</b></div>`}
function fullBhavHtml(j){const es=entries(j);if(!es.length)return'<div class="notice">Live BHAV is not available for this match right now.</div>';return es.map(e=>`<div class="notice"><b>${esc(e.market||'Market')}</b><br>${values(e).map(v=>`${esc(v.label||'Selection')} <b>${esc(v.odd)}</b>`).join(' · ')}</div>`).join('')}
function drawPanel(){const p=document.getElementById('panel'),detail=detailData||{},m=detail.match||{};if(detailTab==='match'){const rr=rateValue(detail.roanuz?.runRate);p.innerHTML=ptitle('MATCH SNAPSHOT')+`<div class="notice">${rr?`<div class="metricRow"><span class="metric">CRR <b>${esc(rr)}</b></span></div>`:''}${currentPlayersHtml(detail)}${lastSixHtml(detail.timeline||[])}</div>`}else if(detailTab==='scorecard'){p.innerHTML=ptitle('SCORECARD')+scorecardHtml(detail)}else if(detailTab==='balls'){p.innerHTML=ptitle('BALL-BY-BALL')+ballsHtml(detail)}else if(detailTab==='more'){p.innerHTML=ptitle('MORE')+'<div class="moreGrid"><button class="moreItem" data-more="graphs">GRAPHS<span>Match trends</span></button><button class="moreItem" data-more="stats">STATS<span>Match numbers</span></button><button class="moreItem" data-more="info">INFO<span>Venue and match details</span></button></div>';p.querySelectorAll('[data-more]').forEach(b=>b.onclick=()=>{detailTab=b.dataset.more;drawDetail()})}else if(detailTab==='bhav'){const key=matchKey(m),cached=bhavCache.get(key)?.data||null;p.innerHTML=ptitle('LIVE BHAV')+(cached?fullBhavHtml(cached):'<div class="loading"><div class="spin"></div>Loading…</div>');getBhav(key).then(j=>{if(detailTab==='bhav'&&document.getElementById('panel'))document.getElementById('panel').innerHTML=ptitle('LIVE BHAV')+fullBhavHtml(j)})}else if(detailTab==='graphs'){p.innerHTML=ptitle('MATCH TRENDS')+'<div class="notice">Trend data is loading…</div>';api({action:'graphs',key:matchKey(m)}).then(j=>{const g=j.graphs||{},items=Object.entries(g).slice(0,8);p.innerHTML=ptitle('MATCH TRENDS')+(items.length?items.map(([k,v])=>`<div class="kv"><span>${esc(k.replace(/_/g,' '))}</span><b>${esc(typeof v==='number'||typeof v==='string'?v:'Available')}</b></div>`).join(''):'<div class="notice">No trend data is available yet.</div>')}).catch(()=>p.innerHTML=ptitle('MATCH TRENDS')+'<div class="notice">Trend data is temporarily unavailable.</div>')}else if(detailTab==='stats'){p.innerHTML=ptitle('MATCH STATS')+scorecardHtml(detail)}else{const venue=detail.venue||{},items=[['Venue',venue.name],['City',venue.city],['Format',m.format],['Status',prettyState(m.state)]].filter(x=>x[1]);p.innerHTML=ptitle('MATCH INFO')+(items.length?items.map(x=>`<div class="kv"><span>${esc(x[0])}</span><b>${esc(x[1])}</b></div>`).join(''):'<div class="notice">Match information will appear here when available.</div>')}}
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{allMatches=[];load(b.dataset.mode,true)});
document.getElementById('refresh').onclick=()=>load(mode,true);
document.getElementById('search').oninput=render;
document.querySelector('.bottom').onclick=e=>{const b=e.target.closest('button');if(!b)return;document.querySelectorAll('.bottom button').forEach(x=>x.classList.toggle('on',x===b));const nav=b.dataset.nav;if(nav==='home'||nav==='live'){backHome();if(mode!=='live'||Date.now()-lastHomeLoad>10000){allMatches=[];load('live',true)}}else if(nav==='fixtures'){backHome();allMatches=[];load('upcoming',true)}else{backHome();setTimeout(()=>document.getElementById('search').focus(),100)}};
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&mode==='live'&&document.getElementById('home').style.display!=='none'&&Date.now()-lastHomeLoad>15000)load('live')});
window.addEventListener('unhandledrejection',e=>console.error('IBETIN UI promise error',e.reason));
window.addEventListener('error',e=>console.error('IBETIN UI error',e.message));
load('live',true);
</script>
</body>
</html>'''
    return html.replace('__API_PATH__', API_PATH)


v23._page = _page_v30
v23.liveline._page = _page_v30


def _self_test() -> None:
    page = _page_v30()
    checks = {
        'single_ui_owner': 'ibetin_liveline_v26' not in page and 'ibetin_liveline_v27' not in page,
        'home_tabs': 'UPCOMING' in page and 'RESULTS' in page,
        'detail_tabs': "['match','MATCH']" in page and "['bhav','BHAV']" in page and "['more','MORE']" in page,
        'inline_bhav': 'id="quickMarket"' in page and 'LIVE BHAV' in page and 'SESSION MARKETS' in page,
        'shared_bhav_cache': 'bhavCache' in page and 'BHAV_TTL=10000' in page and 'getBhav' in page,
        'main_odds': 'MATCH ODDS' in page and 'homeOddsHtml' in page,
        'no_provider_internals': 'ROANUZ V5 · PRIMARY DATA' not in page and 'HIGHLIGHTLY FALLBACK' not in page,
        'no_raw_json_ui': 'JSON.stringify' not in page,
        'scope_safe': 'detailData?.roanuz?.target' in page,
        'fast_score_hydrate': "action:'score'" in page,
        'safe_bottom_spacing': 'calc(175px + env(safe-area-inset-bottom))' in page,
        'telegram_back': 'tg.BackButton' in page,
        'friendly_errors': 'Unable to load match details.' in page,
    }
    live_matches = 0
    detail_ok = False
    source = ''
    try:
        rows, source = v25._fast_matches_cached('live')
        live_matches = len(rows or [])
        if rows:
            key = str(rows[0].get('roanuzMatchKey') or rows[0].get('id') or '')
            if key:
                detail, _ = v25._match_detail_cached(key)
                detail_ok = isinstance(detail, dict) and isinstance(detail.get('match'), dict)
    except Exception as exc:
        logger.warning('IBETIN V30 runtime self-test provider probe skipped: %s', str(exc)[:160])
    ok = all(checks.values()) and (detail_ok or live_matches == 0)
    (logger.info if ok else logger.error)(
        'IBETIN V30 unified self-test %s checks=%s live_matches=%s source=%s detail_ok=%s',
        'PASS' if ok else 'FAILED', checks, live_matches, source, detail_ok,
    )
    if not ok:
        raise RuntimeError(f'V30 unified UI self-test failed: {checks}')


_self_test()
logger.info('IBETIN V30 installed: inline BHAV + session markets + full BHAV tab over frozen V25 fast feed/cache')


# ---------------------------------------------------------------------------
# IBETIN V35 isolated premium preview
# Production /admin/liveline-ibetinv23 continues to use _page_v30 unchanged.
# ---------------------------------------------------------------------------
IBETIN_V35_PREVIEW_PATH = "/admin/ibetin-v35-preview"

IBETIN_V35_PREVIEW_CSS = r"""
/* V35 PREVIEW ONLY */
:root{--pbg:#020814;--ppanel:#06182b;--pline:#153f63;--pblue:#1497ff;--pgreen:#23d98b;--ppurple:#794cff;--ptext:#f4f9ff;--pmuted:#8fa8bf}
html,body{background:radial-gradient(circle at 50% -10%,#0b315e 0,#041425 35%,#020814 76%)!important;color:var(--ptext)!important}
body{padding-bottom:calc(105px + env(safe-area-inset-bottom))!important}
.top{background:linear-gradient(125deg,#031125,#092c55 72%,#12396b)!important;border-bottom:1px solid rgba(42,155,255,.24)!important;box-shadow:0 12px 32px rgba(0,0,0,.30)!important}
.mark{background:linear-gradient(145deg,#ffd553,#ffae17)!important;color:#152235!important;border-radius:12px!important}
.brand b{color:#fff!important}.brand span{color:#b7cae0!important}
.liveDot{background:rgba(20,157,91,.22)!important;border-color:#2bdd8d!important;box-shadow:0 0 20px rgba(35,217,139,.14)!important}
.tab{background:#0a2747!important;color:#a9bed2!important}.tab.on{background:linear-gradient(135deg,#178fff,#0a66d5)!important;color:#fff!important;box-shadow:0 8px 24px rgba(20,126,255,.22)!important}
.main{background:transparent!important}.search,.refresh{background:#06182b!important;color:#edf7ff!important;border-color:#154262!important;box-shadow:none!important}.search::placeholder{color:#6f8aa4!important}
.status,.league{color:#8da8c0!important}
.match{background:linear-gradient(180deg,#071b30,#051522)!important;border:1px solid #164463!important;border-left:4px solid #2b9cff!important;box-shadow:0 15px 34px rgba(0,0,0,.25)!important}.match.live{border-left-color:#ff536f!important}
.fmt,.ta,.si,.foot{color:#8da7bf!important}.tn{color:#fff!important}.sc{color:#f8fbff!important}.badge{background:#102b47!important;color:#a8c5df!important}.badge.live{background:rgba(255,83,111,.14)!important;color:#ff758a!important}
.oddsRow{background:#051522!important;border-top-color:#143b5a!important}.oddBox{background:linear-gradient(135deg,#0b6fd7,#0a3b78)!important;border-color:#1d99ff!important}.oddBox:nth-of-type(3){background:linear-gradient(135deg,#119c61,#075d3d)!important;border-color:#25d98b!important}.oddLabel{color:#cfe4f5!important}.oddValue{color:#fff!important}
.detail{background:transparent!important;padding-top:12px!important}.back{background:#08213a!important;color:#d9ecff!important;border:1px solid #174565!important;box-shadow:none!important}
.scorehero{background:radial-gradient(circle at 50% 10%,rgba(25,139,255,.20),transparent 30%),linear-gradient(180deg,#082342,#06182b)!important;border-color:#174c70!important;box-shadow:0 18px 38px rgba(0,0,0,.28)!important}
.scoretop{border-bottom-color:#16415f!important;color:#9cb5cc!important}.sname{color:#d9ecff!important}.sval{color:#fff!important}.vs{background:#0b2848!important;color:#d9ecff!important;border:1px solid #246da8!important}.report{background:#061729!important;border-top-color:#16415f!important;color:#c5d8e8!important}
.quickMarket,.panel{background:linear-gradient(180deg,#071b30,#061522)!important;border-color:#174767!important;box-shadow:0 14px 32px rgba(0,0,0,.24)!important}.quickHead b,.ptitle b{color:#fff!important}.quickHead span,.sessionTitle{color:#38b9ff!important}
.quickOdd{background:linear-gradient(135deg,#0a78e8,#08448d)!important;border-color:#20a4ff!important}.quickOdd:nth-child(2){background:linear-gradient(135deg,#10a466,#075c3d)!important;border-color:#2cde8c!important}.quickOdd small{color:#d7edff!important}.quickOdd strong{color:#fff!important;font-size:24px!important}
.sessionGrid{display:flex!important;gap:8px!important;overflow-x:auto!important;scrollbar-width:none!important}.sessionGrid::-webkit-scrollbar{display:none!important}.sessionCard{flex:0 0 min(74vw,240px)!important;background:linear-gradient(135deg,#0a448f,#082750)!important;border-color:#367ee0!important}.sessionCard:nth-child(even){background:linear-gradient(135deg,#5b2aad,#2f1c66)!important;border-color:#9b67ff!important}.sessionCard b,.sessionVals strong{color:#fff!important}.sessionVals{color:#c8dcef!important}
.dtab{background:#0a2139!important;color:#9eb7cd!important;border-color:#173f5f!important}.dtab.on{background:linear-gradient(135deg,#1594ff,#1268e7)!important;color:#fff!important;border-color:#2ca9ff!important}
.notice,.inning,.ball,.moreItem,.playerCard{background:#081a2c!important;border-color:#173e5d!important;color:#bad0e2!important}.playerName,.inningTeam,.inningScore,.moreItem,.kv b{color:#fff!important}.metric{background:#0b2a49!important;color:#a9c3d9!important}.ballChip{background:#244764!important;color:#fff!important}.ballChip.boundary{background:#1398ef!important}.ballChip.six{background:#7650e3!important}.ballChip.wicket{background:#e94d68!important}
.bottom{background:rgba(2,11,23,.98)!important;border:1px solid #153854!important;box-shadow:0 18px 40px rgba(0,0,0,.42)!important}.bottom .on{background:linear-gradient(180deg,rgba(27,137,255,.24),rgba(11,76,139,.16))!important}
/* V35 NAV CLEARANCE FIX */
.main{padding-bottom:calc(185px + env(safe-area-inset-bottom))!important}
.detail{padding-bottom:calc(185px + env(safe-area-inset-bottom))!important}
.bottom{left:16px!important;right:16px!important;bottom:calc(8px + env(safe-area-inset-bottom))!important;padding:6px!important;border-radius:18px!important}
.bottom button{height:48px!important;font-size:8px!important}
.bottom b{font-size:17px!important;margin-bottom:1px!important}
body:before{content:"PREVIEW";position:fixed;right:10px;top:8px;z-index:9999;background:#7b43f6;color:#fff;font-size:8px;font-weight:1000;letter-spacing:1px;padding:5px 8px;border-radius:999px;pointer-events:none}
.previewHomeOdds{padding:12px 13px 13px;border-top:1px solid #153d5d;background:#051522}
.previewOddsTitle{font-size:9px;font-weight:1000;color:#8fb1cc;letter-spacing:.7px;margin-bottom:8px}
.previewHomeGrid,.previewBhavGrid{display:grid;grid-template-columns:1fr 1fr;gap:9px}
.previewPrice{border-radius:14px;padding:12px 13px;border:1px solid #25a5ff;background:linear-gradient(135deg,#0b79e7,#083f86);min-width:0}
.previewPrice.green{border-color:#31df90;background:linear-gradient(135deg,#11a868,#075b3c)}
.previewPrice small{display:block;color:#d8edff;font-size:9px;font-weight:900;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.previewPrice strong{display:block;color:#fff;font-size:28px;line-height:1;margin-top:6px;font-weight:1000;font-variant-numeric:tabular-nums}
.previewBhav{margin-top:2px}
.previewBhavHead{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:10px}
.previewBhavHead b{font-size:17px;color:#fff}.previewBhavHead span{font-size:9px;color:#31baff;font-weight:1000}
.previewHist{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid #17496d;border-radius:12px;overflow:hidden;margin-top:9px}
.previewHist div{padding:8px 4px;text-align:center;background:#08223c;border-right:1px solid #17496d}.previewHist div:last-child{border-right:0}
.previewHist span{display:block;color:#7f9db7;font-size:7px;font-weight:900}.previewHist b{display:block;color:#fff;font-size:13px;margin-top:3px;font-variant-numeric:tabular-nums}.previewHist .cur b{color:#2db8ff}
.previewSessionTitle{font-size:10px;font-weight:1000;color:#35b9ff;margin:13px 0 7px}
.previewSessionStrip{display:flex;gap:8px;overflow-x:auto;scrollbar-width:none}.previewSessionStrip::-webkit-scrollbar{display:none}
.previewSessionCard{flex:0 0 min(76vw,250px);padding:11px;border-radius:13px;background:linear-gradient(135deg,#0b468f,#092855);border:1px solid #397fd7}
.previewSessionCard:nth-child(even){background:linear-gradient(135deg,#5a2bad,#2d1a64);border-color:#9c68ff}
.previewSessionCard>b{font-size:11px;color:#fff}.previewSessionVals{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
.previewSessionVals span{padding:5px 7px;border-radius:8px;background:rgba(255,255,255,.08);font-size:8px;color:#c6d9ea}.previewSessionVals b{color:#fff;font-size:12px;margin-left:3px}
.previewMarketList{display:grid;gap:8px}.previewMarketRow{background:#081a2c;border:1px solid #17405f;border-radius:12px;padding:11px}
.previewMarketRow>b{display:block;color:#fff;font-size:11px;margin-bottom:7px}.previewMarketVals{display:flex;gap:8px;flex-wrap:wrap;color:#a8c1d6;font-size:10px}.previewMarketVals strong{color:#fff}

"""


IBETIN_V35_MARKET_JS = r"""
<script>
(function(){
  function previewPriceFmt(v){
    if(v===null||v===undefined||v==='')return '—';
    const n=Number(v);
    return Number.isFinite(n)?esc(n.toFixed(2)):esc(v);
  }
  function previewLineFmt(v){
    if(v===null||v===undefined||v==='')return '—';
    const n=Number(v);
    if(!Number.isFinite(n))return esc(v);
    if(Number.isInteger(n))return esc(String(n));
    return esc(String(Math.round((n+Number.EPSILON)*100)/100));
  }
  homeOddsHtml=function(m){
    if(mode!=='live')return'';
    const c=bhavCache.get(matchKey(m));if(!c?.data)return'';
    const market=findMatchMarket(c.data);if(!market)return'';
    const vs=values(market).slice(0,2);
    return `<div class="previewHomeOdds"><div class="previewOddsTitle">MATCH ODDS</div><div class="previewHomeGrid">${vs.map((x,i)=>`<div class="previewPrice ${i===1?'green':''}"><small>${esc(x.label||'Selection')}</small><strong>${previewPriceFmt(x.odd)}</strong></div>`).join('')}</div></div>`;
  };
  quickMarketHtml=function(j){
    if(!j)return'';
    const main=findMatchMarket(j);if(!main)return'';
    const mv=values(main).slice(0,2),sessions=sessionMarkets(j,main);
    const current=mv[0]?.odd;
    return `<div class="previewBhav"><div class="previewBhavHead"><b>↗ LIVE BHAV</b><span>LIVE MARKET</span></div><div class="previewBhavGrid">${mv.map((v,i)=>`<div class="previewPrice ${i===1?'green':''}"><small>${esc(v.label||'Selection')}</small><strong>${previewPriceFmt(v.odd)}</strong></div>`).join('')}</div><div class="previewHist"><div><span>OPEN</span><b>—</b></div><div><span>MIN</span><b>—</b></div><div><span>MAX</span><b>—</b></div><div class="cur"><span>CURRENT</span><b>${previewPriceFmt(current)}</b></div></div>${sessions.length?`<div class="previewSessionTitle">SESSION MARKET</div><div class="previewSessionStrip">${sessions.map(e=>`<div class="previewSessionCard"><b>${esc(e.market||'Session')}</b><div class="previewSessionVals">${values(e).slice(0,4).map(v=>`<span>${esc(v.label||'Line')} <b>${previewLineFmt(v.odd)}</b></span>`).join('')}</div></div>`).join('')}</div>`:''}</div>`;
  };
  fullBhavHtml=function(j){
    const es=entries(j);if(!es.length)return'<div class="notice">Live BHAV is not available for this match right now.</div>';
    return `<div class="previewMarketList">${es.map(e=>{const session=/over|session|runs|line|total|fancy|innings/i.test(String(e?.market||''));return `<div class="previewMarketRow"><b>${esc(e.market||'Market')}</b><div class="previewMarketVals">${values(e).map(v=>`<span>${esc(v.label||'Selection')} <strong>${session?previewLineFmt(v.odd):previewPriceFmt(v.odd)}</strong></span>`).join('')}</div></div>`}).join('')}</div>`;
  };

  let previewWarmCycle=0;
  function previewWarmBhav(){
    if(mode!=='live'||!Array.isArray(allMatches)||!allMatches.length)return;
    const cycle=++previewWarmCycle;
    allMatches.slice(0,8).forEach((m,i)=>{
      const key=matchKey(m);if(!key)return;
      const cached=bhavCache.get(key);
      if(cached?.data && Date.now()-cached.ts < BHAV_TTL)return;
      setTimeout(()=>{
        if(cycle!==previewWarmCycle||mode!=='live')return;
        getBhav(key,false).then(()=>{
          if(cycle===previewWarmCycle && document.getElementById('home')?.style.display!=='none'){
            try{previewBaseRender()}catch(e){}
          }
        }).catch(()=>{});
      },i*90);
    });
  }

  const previewBaseRender=render;
  render=function(){
    previewBaseRender();
    if(mode==='live')previewWarmBhav();
  };

  const previewBaseOpenMatch=openMatch;
  openMatch=async function(key){
    if(!key)return;
    const bhavPromise=getBhav(key,false);
    const detailPromise=previewBaseOpenMatch(key);
    try{
      const market=await bhavPromise;
      if(market && document.getElementById('quickMarket'))renderQuickMarket(market);
      if(market && detailTab==='bhav' && document.getElementById('panel'))drawPanel();
    }catch(e){}
    return await detailPromise;
  };

  try{
    if(allMatches?.length){previewBaseRender();previewWarmBhav()}
    if(detailData)drawDetail();
  }catch(e){console.error('IBETIN preview renderer',e)}
  window.__IBETIN_V35_MARKET_RENDERER__=true;
  window.__IBETIN_V35_BHAV_PREFETCH__=true;
})();
</script>
"""


def _page_v35_preview() -> str:
    html = _page_v30()
    html = html.replace("<title>IBETIN Live Cricket</title>", "<title>IBETIN Premium UI Preview</title>", 1)
    html = html.replace("</style>", IBETIN_V35_PREVIEW_CSS + "\n</style>", 1)
    html = html.replace("</body>", IBETIN_V35_MARKET_JS + "\n</body>", 1)
    return html


IBETIN_V35_PREVIEW_BADGE_CSS = 'body:before{content:"PREVIEW";position:fixed;right:10px;top:8px;z-index:9999;background:#7b43f6;color:#fff;font-size:8px;font-weight:1000;letter-spacing:1px;padding:5px 8px;border-radius:999px;pointer-events:none}'


def _page_v35_production() -> str:
    html = _page_v30()
    live_css = IBETIN_V35_PREVIEW_CSS.replace(IBETIN_V35_PREVIEW_BADGE_CSS, "")
    html = html.replace("<title>IBETIN Live Cricket</title>", "<title>IBETIN Live Cricket</title>", 1)
    html = html.replace("</style>", live_css + "\n</style>", 1)
    html = html.replace("</body>", IBETIN_V35_MARKET_JS + "\n</body>", 1)
    return html


IBETIN_V36_BRAND_PREVIEW_PATH = "/admin/ibetin-v36-brand-preview"

IBETIN_V36_BRAND_CSS = r"""
/* V36 IBETIN.COM BRAND PREVIEW ONLY */
.brand b{font-size:20px!important;letter-spacing:.35px!important}
.brand b .dotcom{color:#2fb7ff;font-weight:1000}
.brand span{font-size:9px!important;letter-spacing:1.2px!important;font-weight:900!important;color:#9fc0db!important}
.mark{position:relative!important;background:linear-gradient(145deg,#ffe071,#ffb319)!important;box-shadow:0 8px 22px rgba(255,180,25,.20)!important}
.mark:after{content:".COM";position:absolute;right:-8px;bottom:-5px;background:#0b6ee0;color:#fff;font-size:6px;line-height:1;font-weight:1000;padding:4px 5px;border-radius:6px;border:2px solid #06182b}
.liveDot{font-size:9px!important;letter-spacing:.5px!important}
.top{padding-top:16px!important}
.ibBrandSig{margin:4px 16px 16px;padding:12px 14px;border:1px solid #143d5b;border-radius:14px;background:linear-gradient(135deg,rgba(9,37,66,.78),rgba(5,22,39,.82));display:flex;align-items:center;justify-content:space-between;gap:10px}
.ibBrandSig b{font-size:12px;color:#fff;letter-spacing:.5px}.ibBrandSig span{font-size:8px;color:#7fa4c3;letter-spacing:.8px;font-weight:900}
.loading:after{content:"IBETIN.COM";display:block;margin-top:7px;color:#3fb5ff;font-size:8px;font-weight:1000;letter-spacing:1.5px}
.match{position:relative}.match:after{content:"IBETIN.COM";position:absolute;right:10px;bottom:7px;font-size:6px;font-weight:1000;letter-spacing:1px;color:rgba(111,164,206,.35);pointer-events:none}
.scorehero:before{content:"IBETIN.COM LIVE";display:block;padding:7px 14px;background:linear-gradient(90deg,rgba(16,135,255,.12),rgba(22,210,137,.08));border-bottom:1px solid #153e5e;color:#69c8ff;font-size:7px;font-weight:1000;letter-spacing:1.2px}
body:before{content:"BRAND PREVIEW";position:fixed;right:10px;top:8px;z-index:9999;background:#0a76df;color:#fff;font-size:7px;font-weight:1000;letter-spacing:1px;padding:5px 8px;border-radius:999px;pointer-events:none}
"""


def _page_v36_brand_preview() -> str:
    html = _page_v35_production()
    html = html.replace("<title>IBETIN Live Cricket</title>", "<title>IBETIN.COM · Live Sports</title>", 1)
    html = html.replace(
        '<div class="brand"><div class="mark">I</div><div><b>IBETIN</b><span>LIVE CRICKET</span></div></div><div class="liveDot">● LIVE</div>',
        '<div class="brand"><div class="mark">I</div><div><b>IBETIN<span class="dotcom">.COM</span></b><span>LIVE SPORTS</span></div></div><div class="liveDot">● LIVE NOW</div>',
        1,
    )
    html = html.replace(
        'placeholder="Search match, team or tournament"',
        'placeholder="Search IBETIN Sports"',
        1,
    )
    html = html.replace(
        '<div id="status" class="status">Loading live cricket…</div>',
        '<div id="status" class="status">IBETIN.COM is loading live cricket…</div>',
        1,
    )
    html = html.replace(
        '<nav class="bottom">',
        '<div class="ibBrandSig"><b>IBETIN.COM</b><span>LIVE SPORTS · FAST SCORES</span></div><nav class="bottom">',
        1,
    )
    html = html.replace(
        "tg.setHeaderColor('#071a34');tg.setBackgroundColor('#eef3f8')",
        "tg.setHeaderColor('#020814');tg.setBackgroundColor('#020814')",
        1,
    )
    html = html.replace(
        "Unable to load match details.",
        "IBETIN.COM could not load this match right now.",
    )
    html = html.replace(
        "</style>",
        IBETIN_V36_BRAND_CSS + "\n</style>",
        1,
    )
    return html


IBETIN_V37_PROMO_PREVIEW_PATH = "/admin/ibetin-v37-promo-preview"

IBETIN_V37_PROMO_CSS = r"""
/* V37 LIVE LINE x IBETIN.COM PROMO PREVIEW */
.brand b{font-size:20px!important;letter-spacing:.6px!important}
.brand span{font-size:9px!important;letter-spacing:1.2px!important;font-weight:900!important;color:#9bb8d1!important}
.liveLineSub{display:block;margin-top:2px;font-size:8px;color:#74baff;font-weight:900;letter-spacing:.7px}
.ibPromoCard{margin:11px 0 0;border:1px solid #1a5e8b;border-radius:16px;background:linear-gradient(135deg,#08284a,#071a31 62%,#09263d);padding:13px;box-shadow:0 12px 28px rgba(0,0,0,.18)}
.ibPromoTop{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:9px}
.ibPromoBrand{font-size:12px;font-weight:1000;color:#fff;letter-spacing:.5px}.ibPromoBrand span{color:#38b8ff}
.ibPromoPill{font-size:7px;font-weight:1000;color:#9ed2f5;border:1px solid #215c83;background:#0b2a47;border-radius:999px;padding:5px 7px;letter-spacing:.7px}
.ibPromoTitle{font-size:14px;font-weight:1000;color:#fff;margin-bottom:4px}.ibPromoCopy{font-size:9px;line-height:1.45;color:#91abc2}
.ibPromoBtn{width:100%;margin-top:10px;height:44px;border:0;border-radius:12px;background:linear-gradient(135deg,#1496ff,#0d68d4);color:#fff;font-size:11px;font-weight:1000;letter-spacing:.4px}
.ibPromoLegal{margin-top:7px;font-size:7px;line-height:1.4;color:#6f8ca5;text-align:center}
.ibHomePromo{display:block;width:100%;border:0;border-top:1px solid #17405f;background:#061a2d;color:#58bdff;text-align:left;padding:9px 13px;font-size:9px;font-weight:1000;letter-spacing:.2px}
.ibHomePromo small{float:right;color:#6689a6;font-size:7px;font-weight:900}
.ibQuickPromo{display:flex;align-items:center;justify-content:space-between;gap:9px;margin-top:9px;padding:9px 10px;border:1px solid #1b5a82;border-radius:11px;background:linear-gradient(135deg,#09284a,#071a30)}
.ibQuickPromo div{min-width:0}.ibQuickPromo b{display:block;color:#fff;font-size:10px}.ibQuickPromo span{display:block;color:#7fa1bd;font-size:7px;margin-top:2px}
.ibQuickPromo button{flex:0 0 auto;border:0;border-radius:9px;background:#0f82e9;color:#fff;padding:8px 10px;font-size:8px;font-weight:1000}
.ibPowered{margin:2px 16px 14px;text-align:center;color:#6f8da7;font-size:7px;font-weight:900;letter-spacing:1px}
.detail{padding-bottom:calc(240px + env(safe-area-inset-bottom))!important}
body:before{content:"V37 PROMO PREVIEW";position:fixed;right:10px;top:8px;z-index:9999;background:#0d73d7;color:#fff;font-size:7px;font-weight:1000;letter-spacing:.9px;padding:5px 8px;border-radius:999px;pointer-events:none}
"""

IBETIN_V37_PROMO_JS = r"""
<script>
(function(){
  const IBETIN_LIVE_CRICKET_URL='https://ibetin.com/live/cricket';
  function openIbetinLive(){
    try{
      if(window.Telegram&&Telegram.WebApp&&typeof Telegram.WebApp.openLink==='function'){
        Telegram.WebApp.openLink(IBETIN_LIVE_CRICKET_URL);
        return;
      }
    }catch(e){}
    window.open(IBETIN_LIVE_CRICKET_URL,'_blank','noopener');
  }
  window.openIbetinLive=openIbetinLive;

  const v37BaseHomeOddsHtml=homeOddsHtml;
  homeOddsHtml=function(m){
    const base=v37BaseHomeOddsHtml(m);
    if(mode!=='live'||!base)return base;
    return base+'<button class="ibHomePromo" onclick="event.stopPropagation();openIbetinLive()">More live markets on ibetin.com → <small>18+</small></button>';
  };

  function quickPromoHtml(){
    return '<div class="ibQuickPromo" id="ibetinQuickPromo">'
      +'<div><b>More live markets on ibetin.com</b><span>18+ · Please gamble responsibly</span></div>'
      +'<button onclick="openIbetinLive()">VIEW →</button>'
      +'</div>';
  }

  function promoHtml(){
    return '<div class="ibPromoCard" id="ibetinPromoCard">'
      +'<div class="ibPromoTop"><div class="ibPromoBrand">IBETIN<span>.COM</span></div><div class="ibPromoPill">18+ · BET RESPONSIBLY</div></div>'
      +'<div class="ibPromoTitle">More live cricket markets</div>'
      +'<div class="ibPromoCopy">Continue to ibetin.com to view the live cricket betting section and available markets.</div>'
      +'<button class="ibPromoBtn" onclick="openIbetinLive()">VIEW LIVE CRICKET MARKETS →</button>'
      +'<div class="ibPromoLegal">18+ only. Availability depends on your location and local laws. Please gamble responsibly.</div>'
      +'</div>';
  }

  const v37BaseDrawDetail=drawDetail;
  drawDetail=function(){
    v37BaseDrawDetail();
    try{
      const q=document.getElementById('quickMarket');
      if(q){
        const grid=q.querySelector('.previewBhavGrid');
        if(grid && !document.getElementById('ibetinQuickPromo')){
          grid.insertAdjacentHTML('afterend',quickPromoHtml());
        }
        if(!document.getElementById('ibetinPromoCard')){
          q.insertAdjacentHTML('afterend',promoHtml());
        }
      }
    }catch(e){console.error('IBETIN V37 promo card',e)}
  };

  try{
    if(allMatches?.length)render();
    if(detailData)drawDetail();
  }catch(e){}
  window.__IBETIN_V37_PROMO__=true;
})();
</script>
"""


def _page_v37_promo_preview() -> str:
    html = _page_v35_production()
    html = html.replace("<title>IBETIN Live Cricket</title>", "<title>IBETIN Live Line · Powered by ibetin.com</title>", 1)
    html = html.replace(
        '<div class="brand"><div class="mark">I</div><div><b>IBETIN</b><span>LIVE CRICKET</span></div></div><div class="liveDot">● LIVE</div>',
        '<div class="brand"><div class="mark">I</div><div><b>IBETIN</b><span>LIVE LINE</span><small class="liveLineSub">POWERED BY IBETIN.COM</small></div></div><div class="liveDot">● LIVE</div>',
        1,
    )
    html = html.replace(
        '<nav class="bottom">',
        '<div class="ibPowered">IBETIN LIVE LINE · POWERED BY IBETIN.COM</div><nav class="bottom">',
        1,
    )
    html = html.replace("</style>", IBETIN_V37_PROMO_CSS + "\n</style>", 1)
    html = html.replace("</body>", IBETIN_V37_PROMO_JS + "\n</body>", 1)
    return html


def _preview_v37_url() -> str:
    root = v23.os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/") or "https://ibetin-app-production.up.railway.app"
    return f"{root}{IBETIN_V37_PROMO_PREVIEW_PATH}?{v23.urlencode({'t': v23.liveline._token(), 'v': '20260918-v37-promo2'})}"


def _install_v37_promo_preview_route() -> None:
    handler_cls = v23.liveline.base.ibetin_start.ibetin_entry.analytics.TrackingHandler
    if getattr(handler_cls, "_ibetin_v37_promo_preview_installed", False):
        return
    previous_get = handler_cls.do_GET

    def routed_get(self):
        parsed = v23.urlparse(self.path)
        if parsed.path == IBETIN_V37_PROMO_PREVIEW_PATH:
            if not v23.liveline._authorized(self.path):
                v23.liveline._send_html(self, 403, "<h3>IBETIN Live Line preview link is invalid.</h3>")
                return
            v23.liveline._send_html(self, 200, _page_v37_promo_preview())
            return
        previous_get(self)

    handler_cls.do_GET = routed_get
    handler_cls._ibetin_v37_promo_preview_installed = True
    logger.info("IBETIN V37 promo preview route installed at %s", IBETIN_V37_PROMO_PREVIEW_PATH)


def _preview_v36_url() -> str:
    root = v23.os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/") or "https://ibetin-app-production.up.railway.app"
    return f"{root}{IBETIN_V36_BRAND_PREVIEW_PATH}?{v23.urlencode({'t': v23.liveline._token(), 'v': '20260918-v36-brand'})}"


def _install_v36_brand_preview_route() -> None:
    handler_cls = v23.liveline.base.ibetin_start.ibetin_entry.analytics.TrackingHandler
    if getattr(handler_cls, "_ibetin_v36_brand_preview_installed", False):
        return
    previous_get = handler_cls.do_GET

    def routed_get(self):
        parsed = v23.urlparse(self.path)
        if parsed.path == IBETIN_V36_BRAND_PREVIEW_PATH:
            if not v23.liveline._authorized(self.path):
                v23.liveline._send_html(self, 403, "<h3>IBETIN.COM preview link is invalid.</h3>")
                return
            v23.liveline._send_html(self, 200, _page_v36_brand_preview())
            return
        previous_get(self)

    handler_cls.do_GET = routed_get
    handler_cls._ibetin_v36_brand_preview_installed = True
    logger.info("IBETIN V36 brand preview route installed at %s", IBETIN_V36_BRAND_PREVIEW_PATH)


def _preview_v35_url() -> str:
    root = v23.os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/") or "https://ibetin-app-production.up.railway.app"
    return f"{root}{IBETIN_V35_PREVIEW_PATH}?{v23.urlencode({'t': v23.liveline._token(), 'v': '20260918-v35-approved'})}"


def _install_v35_preview_route() -> None:
    handler_cls = v23.liveline.base.ibetin_start.ibetin_entry.analytics.TrackingHandler
    if getattr(handler_cls, "_ibetin_v35_preview_installed", False):
        return
    previous_get = handler_cls.do_GET

    def routed_get(self):
        parsed = v23.urlparse(self.path)
        if parsed.path == IBETIN_V35_PREVIEW_PATH:
            if not v23.liveline._authorized(self.path):
                v23.liveline._send_html(self, 403, "<h3>IBETIN preview link is invalid.</h3>")
                return
            v23.liveline._send_html(self, 200, _page_v35_preview())
            return
        previous_get(self)

    handler_cls.do_GET = routed_get
    handler_cls._ibetin_v35_preview_installed = True
    logger.info("IBETIN V35 isolated preview route installed at %s", IBETIN_V35_PREVIEW_PATH)


async def _previewui_command(update, context):
    user, message, chat = update.effective_user, update.effective_message, update.effective_chat
    if not user or not message or not chat:
        return
    if getattr(chat, "type", "") != "private":
        await message.reply_text("Open this preview from a private chat with the bot.")
        return
    await message.reply_text(
        "⚡ <b>IBETIN LIVE LINE · V37 PROMO PREVIEW</b>\n\n"
        "Live Line stays the free sports utility. ibetin.com appears as the parent brand and betting destination. "
        "Production LIVE remains on approved V35 until you approve this version.",
        parse_mode="HTML",
        reply_markup=v23.liveline.InlineKeyboardMarkup(
            [[v23.liveline.InlineKeyboardButton(
                "⚡ OPEN LIVE LINE V37",
                web_app=v23.liveline.WebAppInfo(url=_preview_v37_url()),
            )]]
        ),
        disable_web_page_preview=True,
    )


def _install_v35_preview_command() -> None:
    runtime = v23.liveline.base._runtime
    if getattr(runtime, "_ibetin_v35_preview_configured", False):
        return
    previous_config = runtime.configure_telegram_ui

    async def configure_with_preview(application):
        await previous_config(application)
        application.add_handler(v23.liveline.CommandHandler("previewui", _previewui_command))
        logger.info("IBETIN /previewui premium preview command registered")

    runtime.configure_telegram_ui = configure_with_preview
    runtime.app.configure_telegram_ui = configure_with_preview
    runtime._ibetin_v35_preview_configured = True


_install_v35_preview_route()
_install_v36_brand_preview_route()
_install_v37_promo_preview_route()
_install_v35_preview_command()

# Promote the approved V35 UI to the production Live route.
v23._page = _page_v35_production
v23.liveline._page = _page_v35_production
logger.info("IBETIN V35 promoted to production Live route; V30 remains rollback baseline")

app = v25.app

if __name__ == '__main__':
    app.base.ibetin_start.main()
