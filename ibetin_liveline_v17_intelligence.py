import logging
import os
from urllib.parse import urlencode

import ibetin_liveline_trial as liveline
import ibetin_liveline_v16_best as v16

logger = logging.getLogger(__name__)

# Fresh private route so Telegram WebView cannot reuse V16 markup.
liveline.LIVELINE_PATH = "/admin/liveline-ibetinv17"
liveline.LIVELINE_API_PATH = "/admin/liveline-ibetinv17/api"


def _v17_admin_url() -> str:
    root = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/") or "https://ibetin-app-production.up.railway.app"
    return f"{root}{liveline.LIVELINE_PATH}?{urlencode({'t': liveline._token(), 'v': '20260917-v17-intelligence'})}"


def _v17_page() -> str:
    html = v16._v16_page()

    css = r'''
/* ============================================================
   IBETIN V17 — MATCH INTELLIGENCE
   Adds richer UI using data already present in currentDetail.
   No additional provider calls.
   ============================================================ */
.liveChip:after{content:'V17'!important}

.v17IntelStrip{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin:0 0 9px}
.v17IntelStrip>div{min-width:0;background:#fff;border:1px solid #dce5ee;border-radius:10px;padding:8px 9px;box-shadow:0 3px 10px rgba(8,38,78,.04)}
.v17IntelStrip small{display:block;font-size:5px;font-weight:1000;color:#8b9bac;letter-spacing:.55px;text-transform:uppercase;margin-bottom:3px}.v17IntelStrip b{display:block;font-size:8px;color:#244c75;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.v17IntelStrip span{display:block;font-size:6px;color:#7f91a4;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

.v17IntelTab{position:relative}.v17IntelTab:after{content:'NEW';position:absolute;top:-5px;right:-3px;background:#f6c844;color:#17385c;border-radius:999px;padding:2px 4px;font-size:4px;font-weight:1000;letter-spacing:.35px}
.v17IntelPanel{display:grid;gap:9px}
.v17Card{border:1px solid #dce5ee;border-radius:13px;background:#fff;overflow:hidden}.v17CardHead{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:9px 10px;background:#fafbfd;border-bottom:1px solid #edf1f5}.v17CardHead b{font-size:8px;color:#244c75;letter-spacing:.25px}.v17CardHead span{font-size:6px;color:#8798a9}.v17CardBody{padding:9px 10px}
.v17MetaGrid{display:grid;grid-template-columns:repeat(2,1fr);gap:7px}.v17Meta{background:#f7f9fc;border:1px solid #e6ebf0;border-radius:9px;padding:8px}.v17Meta small{display:block;font-size:5px;color:#8a99aa;font-weight:900;letter-spacing:.45px;text-transform:uppercase}.v17Meta strong{display:block;margin-top:4px;font-size:9px;color:#1f456d;line-height:1.35}
.v17Performers{display:grid;grid-template-columns:1fr 1fr;gap:7px}.v17Performer{border:1px solid #e2e8ef;border-radius:10px;background:linear-gradient(145deg,#fff,#f8fbff);padding:9px}.v17Performer small{font-size:5px;color:#8596a7;font-weight:1000;letter-spacing:.45px}.v17Performer b{display:block;font-size:9px;color:#1d446c;margin:4px 0 3px}.v17Performer span{font-size:6px;color:#72869a;line-height:1.45}
.v17Partners{display:grid;gap:6px}.v17Partner{display:grid;grid-template-columns:1fr auto;align-items:center;gap:9px;border:1px solid #e3e9ef;background:#fafbfd;border-radius:10px;padding:8px 9px}.v17PartnerNames{font-size:7px;color:#385b7c;font-weight:850;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.v17PartnerNames strong{color:#163c65}.v17PartnerStat{text-align:right}.v17PartnerStat b{font-size:10px;color:#0b4f97}.v17PartnerStat span{display:block;font-size:5px;color:#8b9aab;margin-top:2px}
.v17PartnerBar{grid-column:1/-1;height:4px;background:#edf2f6;border-radius:999px;overflow:hidden}.v17PartnerBar>i{display:block;height:100%;border-radius:999px;background:linear-gradient(90deg,#0a58ad,#f6c844)}

.v17SquadTop{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px}.v17XiCount{font-size:6px;font-weight:1000;color:#6e849a;background:#f5f8fb;border:1px solid #e2e8ee;border-radius:999px;padding:5px 7px}.v17Squad{display:grid;gap:6px}.v17Player{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:center;border:1px solid #e3e9ef;border-radius:9px;padding:8px;background:#fafbfd}.v17PlayerMain{min-width:0}.v17PlayerMain b{display:block;font-size:8px;color:#254a71;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.v17PlayerMain span{display:block;font-size:5px;color:#8898a9;margin-top:2px;text-transform:uppercase;letter-spacing:.35px}.v17XiBtn{min-width:58px;height:27px;border-radius:8px;border:1px solid #dae3ec;background:#fff;color:#617c96;font-size:6px;font-weight:1000}.v17XiBtn.on{background:#fff5cf;border-color:#efd06b;color:#745700}
.v17Empty{padding:12px;border:1px dashed #d8e2ec;border-radius:10px;color:#8797a7;font-size:7px;text-align:center;background:#fbfcfd}
.v17IntelNote{font-size:6px;color:#8897a7;line-height:1.5;padding:0 2px}

html[data-v16-theme="dark"] .v17IntelStrip>div,html[data-v16-theme="dark"] .v17Card{background:#0d1c2d!important;border-color:#203449!important}
html[data-v16-theme="dark"] .v17CardHead{background:#101f31!important;border-color:#213448!important}
html[data-v16-theme="dark"] .v17CardHead b,html[data-v16-theme="dark"] .v17IntelStrip b,html[data-v16-theme="dark"] .v17Meta strong,html[data-v16-theme="dark"] .v17Performer b,html[data-v16-theme="dark"] .v17PartnerNames strong,html[data-v16-theme="dark"] .v17PlayerMain b{color:#d9e8f7!important}
html[data-v16-theme="dark"] .v17Meta,html[data-v16-theme="dark"] .v17Performer,html[data-v16-theme="dark"] .v17Partner,html[data-v16-theme="dark"] .v17Player,html[data-v16-theme="dark"] .v17XiCount{background:#122337!important;border-color:#25394f!important}
html[data-v16-theme="dark"] .v17XiBtn{background:#0d1c2d!important;border-color:#284057!important;color:#a9bdd1!important}html[data-v16-theme="dark"] .v17XiBtn.on{background:#3a341d!important;color:#f6dc7d!important;border-color:#6d5d27!important}

@media(min-width:600px){.v17IntelPanel{grid-template-columns:1fr 1fr}.v17Card.v17Wide{grid-column:1/-1}.v17Squad{grid-template-columns:1fr 1fr}}
'''
    html = html.replace("</style>", css + "\n</style>", 1)

    js = r'''
<script>
(function(){
  const XI_KEY='ibetin-v17-myxi';
  let customIntel=false;

  function detailData(){
    try{return (typeof currentDetail!=='undefined'&&currentDetail)||window.currentDetail||{}}catch(e){return window.currentDetail||{}}
  }
  function safe(v,fallback='—'){return(v===null||v===undefined||v==='')?fallback:String(v)}
  function playerNameV17(obj){return obj?.player?.name||obj?.name||obj?.fullName||'Player'}
  function playerRole(obj){return obj?.role||obj?.player?.role||obj?.position||obj?.type||''}
  function xiMap(){try{return JSON.parse(localStorage.getItem(XI_KEY)||'{}')||{}}catch(e){return{}}}
  function setXiMap(x){try{localStorage.setItem(XI_KEY,JSON.stringify(x))}catch(e){}}
  function matchId(){return String(detailData()?.match?.id||'')}
  function selectedXi(){const all=xiMap();const raw=all[matchId()]||[];return new Set(Array.isArray(raw)?raw:[])}
  function saveXi(set){const all=xiMap();all[matchId()]=[...set];setXiMap(all)}

  function bestBat(){
    const a=detailData().bestBatsmen||[];return a[0]||null
  }
  function bestBowl(){
    const a=detailData().bestBowlers||[];return a[0]||null
  }
  function statsText(obj,type){
    const s=obj?.player?.statistics||obj?.statistics||obj||{};
    if(type==='bat'){
      const runs=s.runs??s.score,balls=s.balls,sr=s.strikeRate??s.battingStrikeRate;
      return `${safe(runs)} runs${balls!=null?' · '+safe(balls)+' balls':''}${sr!=null?' · SR '+safe(sr):''}`
    }
    const ov=s.overs,w=s.wickets,r=s.runs??s.concededRuns??s.runsConceded,eco=s.economy;
    return `${w!=null?safe(w)+' wkts':'Bowling'}${ov!=null?' · '+safe(ov)+' ov':''}${r!=null?' · '+safe(r)+' runs':''}${eco!=null?' · Econ '+safe(eco):''}`
  }

  function partnerships(){
    const out=[];(detailData().statistics||[]).forEach((inn,innIdx)=>{
      (inn?.inningPartnerships||[]).forEach((p,i)=>out.push({...p,_inn:inn?.name||('Innings '+(innIdx+1)),_idx:i}))
    });
    return out.sort((a,b)=>Number(b?.runs||0)-Number(a?.runs||0)).slice(0,5)
  }

  function squadList(){
    const raw=detailData().squad||[];
    const out=[];
    raw.forEach((item,i)=>{
      if(Array.isArray(item?.players)) item.players.forEach((p,j)=>out.push({...p,_team:item?.team?.name||item?.name||'' ,_key:String(p?.id||`${i}-${j}`)}));
      else out.push({...item,_key:String(item?.id||i)});
    });
    return out.slice(0,30)
  }

  function intelligenceHtml(){
    const x=detailData(),m=x.match||{},v=x.venue||{},f=x.forecast||{},bat=bestBat(),bowl=bestBowl(),parts=partnerships(),squad=squadList(),sel=selectedXi();
    const season=m.league?.season||'';
    const series=`${safe(m.league?.name,'Cricket')}${season?' · '+season:''}`;
    const venue=[v.name,v.city,v.country].filter(Boolean).join(' · ')||'Venue not available';
    const weather=[f.status,f.temperature,f.wind].filter(Boolean).join(' · ')||'Weather not available';
    const maxRuns=Math.max(1,...parts.map(p=>Number(p?.runs||0)));
    const partnerHtml=parts.length?parts.map(p=>`<div class="v17Partner"><div class="v17PartnerNames"><strong>${esc(p.firstPlayer?.name||'')}</strong>${p.secondPlayer?.name?' + '+esc(p.secondPlayer.name):''}<span style="display:block;margin-top:3px;font-size:5px;color:#91a0af">${esc(p._inn)}</span></div><div class="v17PartnerStat"><b>${esc(safe(p.runs,'0'))}</b><span>${esc(safe(p.balls,'—'))} balls</span></div><div class="v17PartnerBar"><i style="width:${Math.max(8,Math.round((Number(p.runs||0)/maxRuns)*100))}%"></i></div></div>`).join(''):'<div class="v17Empty">Partnership data is not available yet for this match.</div>';
    const squadHtml=squad.length?squad.map(p=>{const key=String(p._key),on=sel.has(key);return `<div class="v17Player"><div class="v17PlayerMain"><b>${esc(playerNameV17(p))}</b><span>${esc([p._team,playerRole(p),p.country].filter(Boolean).join(' · ')||'Squad player')}</span></div><button type="button" class="v17XiBtn ${on?'on':''}" data-v17xi="${esc(key)}">${on?'✓ MY XI':'+ MY XI'}</button></div>`}).join(''):'<div class="v17Empty">Squad data is not available yet for this match.</div>';
    return `<div class="v17IntelPanel">
      <section class="v17Card"><div class="v17CardHead"><b>TOURNAMENT & VENUE</b><span>match context</span></div><div class="v17CardBody"><div class="v17MetaGrid"><div class="v17Meta"><small>Series</small><strong>${esc(series)}</strong></div><div class="v17Meta"><small>Format</small><strong>${esc(safe(m.format||m.dayType,'Cricket'))}</strong></div><div class="v17Meta"><small>Venue</small><strong>${esc(venue)}</strong></div><div class="v17Meta"><small>Weather</small><strong>${esc(weather)}</strong></div></div></div></section>
      <section class="v17Card"><div class="v17CardHead"><b>TOP PERFORMERS</b><span>current match data</span></div><div class="v17CardBody"><div class="v17Performers"><div class="v17Performer"><small>BEST BATTER</small><b>${esc(bat?playerNameV17(bat):'Waiting for data')}</b><span>${esc(bat?statsText(bat,'bat'):'No batting leader yet')}</span></div><div class="v17Performer"><small>BEST BOWLER</small><b>${esc(bowl?playerNameV17(bowl):'Waiting for data')}</b><span>${esc(bowl?statsText(bowl,'bowl'):'No bowling leader yet')}</span></div></div></div></section>
      <section class="v17Card v17Wide"><div class="v17CardHead"><b>KEY PARTNERSHIPS</b><span>top ${parts.length||0}</span></div><div class="v17CardBody"><div class="v17Partners">${partnerHtml}</div></div></section>
      <section class="v17Card v17Wide"><div class="v17CardHead"><b>SQUAD · MY XI</b><span>personal selection</span></div><div class="v17CardBody"><div class="v17SquadTop"><div class="v17IntelNote">Pick up to 11 players for your personal XI preview. This does not change the official playing XI.</div><span class="v17XiCount" id="v17XiCount">${sel.size}/11</span></div><div class="v17Squad">${squadHtml}</div></div></section>
    </div>`
  }

  function intelStripHtml(){
    const x=detailData(),m=x.match||{},v=x.venue||{},f=x.forecast||{};
    const series=(m.league?.name||'Cricket')+(m.league?.season?' · '+m.league.season:'');
    const venue=[v.name,v.city].filter(Boolean).join(' · ')||'Venue pending';
    const weather=[f.status,f.temperature].filter(Boolean).join(' · ')||'Weather pending';
    return `<div class="v17IntelStrip"><div><small>Series</small><b>${esc(series)}</b><span>${esc(m.format||m.dayType||'Cricket')}</span></div><div><small>Venue</small><b>${esc(venue)}</b><span>${esc(v.country||'')}</span></div><div><small>Conditions</small><b>${esc(weather)}</b><span>${esc(f.wind||'')}</span></div></div>`
  }

  function ensureIntelStrip(){
    const d=document.getElementById('detail');if(!d||d.querySelector('.v17IntelStrip'))return;
    const tabs=d.querySelector('.detailTabs');if(!tabs)return;
    tabs.insertAdjacentHTML('beforebegin',intelStripHtml());
  }

  function ensureIntelTab(){
    const tabs=document.querySelector('#detail .detailTabs');if(!tabs)return;
    let btn=tabs.querySelector('[data-tab="intel"]');
    if(!btn){btn=document.createElement('button');btn.type='button';btn.className='detailTab v17IntelTab';btn.dataset.tab='intel';btn.textContent='INTEL';tabs.appendChild(btn);btn.addEventListener('click',()=>{try{currentTab='intel'}catch(e){}customIntel=true;tabs.querySelectorAll('.detailTab').forEach(x=>x.classList.toggle('active',x===btn));renderIntelPanel();try{window.Telegram?.WebApp?.HapticFeedback?.impactOccurred('light')}catch(e){}})}
  }

  function renderIntelPanel(){
    const p=document.getElementById('panel');if(!p)return;p.innerHTML=intelligenceHtml();bindXiButtons();
  }

  function bindXiButtons(){
    const p=document.getElementById('panel');if(!p)return;
    p.querySelectorAll('[data-v17xi]').forEach(btn=>btn.addEventListener('click',()=>{
      const key=btn.dataset.v17xi;const set=selectedXi();
      if(set.has(key))set.delete(key);else{if(set.size>=11){try{toast('My XI can contain up to 11 players')}catch(e){};return}set.add(key)}
      saveXi(set);renderIntelPanel();try{window.Telegram?.WebApp?.HapticFeedback?.impactOccurred('light')}catch(e){}
    }));
  }

  const baseRenderDetail=window.renderDetail;
  window.renderDetail=function(){customIntel=false;baseRenderDetail();ensureIntelStrip();ensureIntelTab();};

  const baseRenderPanel=window.renderPanel;
  window.renderPanel=function(){
    if(customIntel){renderIntelPanel();return}
    const out=baseRenderPanel();setTimeout(()=>{ensureIntelStrip();ensureIntelTab()},0);return out
  };

  document.addEventListener('click',e=>{
    const t=e.target.closest('.detailTab');if(!t||t.dataset.tab==='intel')return;customIntel=false;
  });

  setTimeout(()=>{
    if(document.getElementById('detail')?.style.display!=='none'){ensureIntelStrip();ensureIntelTab()}
    const sub=document.querySelector('.brandText span');if(sub)sub.textContent='SPORTS INTELLIGENCE · PRIVATE TEST';
  },150);
})();
</script>
'''
    html = html.replace("</body>", js + "\n</body>")
    html = html.replace("IBETIN SPORTS INTELLIGENCE · V16 PRIVATE TEST", "IBETIN SPORTS INTELLIGENCE · V17 PRIVATE TEST")
    return html


liveline.admin_url = _v17_admin_url
liveline._page = _v17_page

app = v16.app

logger.info("IBETIN Live Line V17 match intelligence installed on private test route")

if __name__ == "__main__":
    app.base.ibetin_start.main()
