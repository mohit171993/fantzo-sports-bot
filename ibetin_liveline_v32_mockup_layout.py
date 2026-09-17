import logging

import ibetin_liveline_v31_premium_dark_ui as v31

logger = logging.getLogger(__name__)

V32_CSS = r'''
/* V32 real layout rebuild matching the approved premium concept */
.detail{padding-top:10px!important}.back{margin:0 0 10px!important}
.v32Hero{position:relative;overflow:hidden;border-radius:22px;border:1px solid #1669a4;background:
 radial-gradient(circle at 12% 48%,rgba(0,117,255,.35),transparent 30%),
 radial-gradient(circle at 88% 50%,rgba(255,94,31,.24),transparent 30%),
 linear-gradient(180deg,#06264d 0%,#05182d 58%,#03101d 100%);box-shadow:0 18px 40px rgba(0,0,0,.38);margin-bottom:12px}
.v32Hero:before{content:'';position:absolute;inset:0;background:linear-gradient(112deg,transparent 0 47%,rgba(20,166,255,.18) 48%,transparent 49%),linear-gradient(68deg,transparent 0 49%,rgba(255,102,38,.15) 50%,transparent 51%);pointer-events:none}
.v32Series{position:relative;padding:14px 14px 8px;text-align:center;color:#dcecff;font-size:12px;font-weight:900}.v32Format{display:inline-block;margin-left:7px;padding:5px 8px;border-radius:999px;background:linear-gradient(135deg,#5428b5,#7b34ef);font-size:9px;color:#fff}
.v32Score{position:relative;display:grid;grid-template-columns:1fr auto 1fr;gap:10px;align-items:center;padding:15px 14px 18px}.v32Team.right{text-align:right}.v32TeamMark{display:flex;margin-bottom:8px}.v32Team.right .v32TeamMark{justify-content:flex-end}.v32Team .teamMark{width:60px!important;height:60px!important;border:2px solid #2c8ce1!important;box-shadow:0 0 24px rgba(27,145,255,.25)!important}.v32Name{font-size:18px;font-weight:1000;color:#fff}.v32Abbr{font-size:10px;color:#84a6c4;margin-top:2px}.v32ScoreVal{font-size:38px;font-weight:1000;line-height:1.05;color:#fff;margin-top:8px;text-shadow:0 0 22px rgba(26,151,255,.24)}.v32Overs{font-size:12px;color:#9cb8d1;margin-top:5px}.v32Vs{width:48px;height:48px;border-radius:50%;display:grid;place-items:center;background:#06162a;border:1px solid #238ce0;color:#fff;font-size:13px;font-weight:1000;box-shadow:0 0 22px rgba(0,138,255,.28)}
.v32Status{position:relative;margin:0 14px 12px;padding:10px 12px;border-radius:999px;border:1px solid #167bd0;background:rgba(8,58,108,.6);text-align:center;color:#eaf7ff;font-size:13px;font-weight:900}.v32Status.live{border-color:#26d885;color:#dcffed;box-shadow:0 0 18px rgba(31,216,133,.15)}
.v32Bhav{border-radius:20px!important;padding:15px!important}.v32MarketHead{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:11px}.v32MarketHead strong{font-size:20px;color:#fff}.v32MarketHead span{font-size:10px;font-weight:900;color:#3cc1ff}.v32OddsGrid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.v32Odd{padding:14px;border-radius:15px;background:linear-gradient(135deg,#0875e6,#0b3b87);border:1px solid #1bacff;box-shadow:0 9px 20px rgba(0,91,210,.24)}.v32Odd:nth-child(2){background:linear-gradient(135deg,#0ba963,#086441);border-color:#34e597}.v32OddLabel{font-size:11px;color:#dff2ff;font-weight:900;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.v32OddValue{font-size:30px;font-weight:1000;color:#fff;margin-top:5px}.v32SessionTitle{display:flex;align-items:center;justify-content:space-between;margin:15px 0 8px;color:#dcecff;font-size:12px;font-weight:1000}.v32SessionTitle span{font-size:9px;color:#45e99b}.v32Sessions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.v32Session{padding:12px;border-radius:13px;background:linear-gradient(135deg,#0c3d87,#0b2452);border:1px solid #2c7fe4}.v32Session:nth-child(even){background:linear-gradient(135deg,#53249f,#2d1765);border-color:#975cff}.v32SessionName{font-size:10px;font-weight:1000;color:#fff}.v32SessionVals{display:flex;gap:7px;flex-wrap:wrap;margin-top:7px}.v32SessionVals span{font-size:10px;color:#b9d0e5}.v32SessionVals b{color:#fff;font-size:13px}
.v32Card{margin-top:11px;border-radius:18px;background:linear-gradient(180deg,#071a2e,#061426);border:1px solid #164562;box-shadow:0 14px 30px rgba(0,0,0,.25);padding:14px}.v32CardTitle{display:flex;justify-content:space-between;align-items:center;margin-bottom:11px;color:#edf7ff;font-size:17px;font-weight:1000}.v32CardTitle small{font-size:9px;color:#ff6077}.v32Metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.v32Metric{background:#081c31;border:1px solid #153c5d;border-radius:12px;padding:10px;text-align:center}.v32Metric span{display:block;font-size:8px;color:#7898b5;font-weight:900;letter-spacing:.5px}.v32Metric b{display:block;margin-top:5px;color:#fff;font-size:17px}.v32Meta{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:9px}.v32MetaBox{background:#08192b;border:1px solid #143550;border-radius:12px;padding:10px}.v32MetaBox span{display:block;font-size:8px;color:#7191ae;font-weight:900}.v32MetaBox b{display:block;margin-top:4px;font-size:10px;color:#dcecff;line-height:1.35}.v32Recent .playerStrip{margin-top:0!important}.v32Recent .lastSix{margin-top:12px!important}
.v32Tabs{margin-top:11px!important}.v32Tabs .dtab{height:52px!important}.v32Tabs .dtab.on{background:linear-gradient(135deg,#0a82f7,#6728df)!important;box-shadow:0 0 24px rgba(57,122,255,.28)!important}
.v32Panel{margin-top:0!important}.v32Panel:empty{display:none!important}
@media(max-width:430px){.v32ScoreVal{font-size:34px}.v32Team .teamMark{width:54px!important;height:54px!important}.v32Name{font-size:16px}.v32Metrics{grid-template-columns:repeat(3,1fr)}.v32Sessions{grid-template-columns:1fr}.v32OddValue{font-size:27px}}
'''

V32_JS = r'''
<script>
(function(){
  const oldQuickMarketHtml=quickMarketHtml;
  const oldDrawPanel=drawPanel;

  function v32ScoreOnly(s){return String(s||'—')}
  function v32OversOnly(s){return String(s||'')}
  function v32StatusText(m){return prettyState(m?.state)||'LIVE'}
  function v32TossText(t){
    if(!t)return'';
    if(typeof t==='string')return t;
    if(typeof t==='object')return String(t.message||t.text||t.winner||t.team||t.result||'');
    return'';
  }
  function v32VenueText(v){if(!v||typeof v!=='object')return'';return [v.name,v.city].filter(Boolean).join(' · ')}
  function v32Metric(label,value){if(value===null||value===undefined||value==='')return'';return `<div class="v32Metric"><span>${esc(label)}</span><b>${esc(value)}</b></div>`}
  function v32Snapshot(detail,m){
    const rr=rateValue(detail?.roanuz?.runRate);
    const target=targetRuns(detail?.roanuz?.target);
    const h=scoreRuns(m.homeScore),a=scoreRuns(m.awayScore);
    let batting=null;if(String(m.awayInfo||''))batting=a;else if(String(m.homeInfo||''))batting=h;
    const need=(target&&batting!==null)?Math.max(0,target-batting):null;
    const toss=v32TossText(detail?.roanuz?.toss),venue=v32VenueText(detail?.venue);
    const status=v32StatusText(m);
    const metrics=[v32Metric('CRR',rr),v32Metric('1ST INNS',m.homeScore),v32Metric('2ND INNS',m.awayScore),v32Metric('TARGET',target),v32Metric('REQ. RUNS',need)].filter(Boolean).join('');
    const meta=[toss?`<div class="v32MetaBox"><span>TOSS</span><b>${esc(toss)}</b></div>`:'',venue?`<div class="v32MetaBox"><span>VENUE</span><b>${esc(venue)}</b></div>`:''].join('');
    return `<div class="v32Card"><div class="v32CardTitle">MATCH SNAPSHOT <small>${esc(status)}</small></div><div class="v32Metrics">${metrics}</div>${meta?`<div class="v32Meta">${meta}</div>`:''}</div>`;
  }
  function v32Recent(detail){
    const players=currentPlayersHtml(detail),last=lastSixHtml(detail?.timeline||[]);
    if(!players&&!last)return'';
    return `<div class="v32Card v32Recent"><div class="v32CardTitle">PLAYERS & RECENT</div>${players}${last}</div>`;
  }
  function v32QuickMarketHtml(j){
    if(!j)return'';
    const main=findMatchMarket(j),mv=main?values(main).slice(0,2):[],sessions=sessionMarkets(j,main).slice(0,4);
    if(!mv.length&&!sessions.length)return'';
    return `<div class="v32MarketHead"><strong>▥ LIVE BHAV</strong><span>LIVE MARKET ›</span></div>`+
      (mv.length?`<div class="v32OddsGrid">${mv.map(v=>`<div class="v32Odd"><div class="v32OddLabel">${esc(v.label||'Selection')}</div><div class="v32OddValue">${esc(v.odd)}</div></div>`).join('')}</div>`:'')+
      (sessions.length?`<div class="v32SessionTitle">◴ SESSION MARKETS <span>LIVE</span></div><div class="v32Sessions">${sessions.map(e=>`<div class="v32Session"><div class="v32SessionName">${esc(e.market||'Session')}</div><div class="v32SessionVals">${values(e).slice(0,4).map(v=>`<span>${esc(v.label||'Line')} <b>${esc(v.odd)}</b></span>`).join('')}</div></div>`).join('')}</div>`:'');
  }
  quickMarketHtml=v32QuickMarketHtml;

  drawDetail=function(){
    const d=document.getElementById('detail'),m=detailData?.match||{},cached=bhavCache.get(matchKey(m))?.data||null,status=v32StatusText(m),isLive=status==='LIVE';
    d.innerHTML=`<button class="back" onclick="backHome()">← BACK</button>
      <div class="v32Hero">
        <div class="v32Series">${esc(league(m))}${m.format?`<span class="v32Format">${esc(m.format)}</span>`:''}</div>
        <div class="v32Score">
          <div class="v32Team"><div class="v32TeamMark">${teamMark(m.home)}</div><div class="v32Name">${esc(m.home?.name||'Home')}</div><div class="v32Abbr">${esc(m.home?.abbr||'')}</div><div class="v32ScoreVal">${v32ScoreOnly(m.homeScore)}</div><div class="v32Overs">${esc(v32OversOnly(m.homeInfo))}</div></div>
          <div class="v32Vs">VS</div>
          <div class="v32Team right"><div class="v32TeamMark">${teamMark(m.away)}</div><div class="v32Name">${esc(m.away?.name||'Away')}</div><div class="v32Abbr">${esc(m.away?.abbr||'')}</div><div class="v32ScoreVal">${v32ScoreOnly(m.awayScore)}</div><div class="v32Overs">${esc(v32OversOnly(m.awayInfo))}</div></div>
        </div>
        <div class="v32Status ${isLive?'live':''}">${esc(status)}</div>
      </div>
      <div id="quickMarket" class="quickMarket v32Bhav">${cached?v32QuickMarketHtml(cached):'<div class="quickLoading">Loading live BHAV & sessions…</div>'}</div>
      ${v32Snapshot(detailData||{},m)}
      ${v32Recent(detailData||{})}
      <div class="dtabs v32Tabs">${tabsHtml()}</div>
      <div id="panel" class="panel v32Panel"></div>`;
    d.querySelectorAll('.dtab').forEach(b=>b.onclick=()=>{detailTab=b.dataset.tab;drawDetail()});
    drawPanel();
  };

  drawPanel=function(){
    if(detailTab==='match'){
      const p=document.getElementById('panel');if(p)p.innerHTML='';return;
    }
    return oldDrawPanel();
  };

  window.__IBETIN_V32_LAYOUT__=true;
})();
</script>
'''


def _page_v32() -> str:
    html = v31._page_v31()
    html = html.replace('</style>', V32_CSS + '\n</style>', 1)
    html = html.replace('</body>', V32_JS + '\n</body>', 1)
    return html

# Serve V32 from the existing Telegram/V23 route and keep the API contract unchanged.
v31.v30.v23._page = _page_v32
v31.v30.v23.liveline._page = _page_v32


def _self_test() -> None:
    page = _page_v32()
    checks = {
        'real_layout_override': 'window.__IBETIN_V32_LAYOUT__=true' in page,
        'stadium_score_hero': 'v32Hero' in page and 'v32Score' in page,
        'large_live_bhav': 'v32OddsGrid' in page and 'LIVE BHAV' in page,
        'real_session_renderer': 'SESSION MARKETS' in page and 'sessionMarkets(j,main)' in page,
        'snapshot_grid': 'MATCH SNAPSHOT' in page and 'v32Metrics' in page,
        'players_recent': 'PLAYERS & RECENT' in page,
        'tabs_preserved': "['bhav','BHAV']" in page and "['scorecard','SCORECARD']" in page,
        'backend_preserved': "action:'score'" in page and 'bhavCache' in page,
        'no_fake_session_number': '148–150' not in page and '148 - 150' not in page,
    }
    ok = all(checks.values())
    (logger.info if ok else logger.error)('IBETIN V32 layout self-test %s checks=%s','PASS' if ok else 'FAILED',checks)
    if not ok:
        raise RuntimeError(f'V32 layout self-test failed: {checks}')

_self_test()
logger.info('IBETIN V32 installed: approved premium mockup layout served on existing Telegram V23 route')

app = v31.app

if __name__ == '__main__':
    app.base.ibetin_start.main()
