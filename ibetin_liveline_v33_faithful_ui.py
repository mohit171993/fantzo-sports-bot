import logging

import ibetin_liveline_v32_mockup_layout as v32

logger = logging.getLogger(__name__)

V33_CSS = r'''
/* V33 faithful premium implementation */
:root{--v33bg:#0c0b0a;--v33navy:#141311;--v33card:#191715;--v33line:#70161a;--v33cyan:#e63941;--v33blue:#e52d36;--v33green:#20dd87;--v33purple:#e7b85a;--v33red:#ff536f;--v33text:#f6fbff;--v33muted:#aeaba7}
html,body{background:radial-gradient(circle at 50% 0,#25221f 0,#100e0d 32%,#090808 75%);color:var(--v33text)!important}
body{padding-bottom:calc(86px + env(safe-area-inset-bottom))!important}.shell{max-width:760px;background:transparent}.top{background:linear-gradient(180deg,#1c1917,#131110)!important;border-bottom:1px solid rgba(235,94,101,.18);box-shadow:0 12px 32px rgba(0,0,0,.25)!important}.mark{width:7px!important;height:43px!important;border-radius:3px!important;background:linear-gradient(180deg,#ffd34e,#f6a800)!important;color:transparent!important;font-size:0!important}.brand{gap:9px!important}.brand b{font-size:30px!important;line-height:1!important;letter-spacing:-1px!important;color:white}.brand span{font-size:10px!important;letter-spacing:2.2px!important;color:#cfccca!important}.liveDot{font-size:13px!important;padding:9px 15px!important;border:1px solid #28e585!important;background:rgba(11,116,70,.28)!important;box-shadow:0 0 20px rgba(39,229,133,.2);color:#eafff2!important}.tabs{gap:8px!important}.tab{background:#25221f!important;color:#c3c0bd!important;border:1px solid #5c1216!important}.tab.on{background:linear-gradient(135deg,#e4252f,#c61921)!important;color:#fff!important;border-color:#e6343d!important;box-shadow:0 7px 24px rgba(229,46,55,.25)}
.main{background:transparent!important}.search,.refresh{background:#171513!important;color:#f5f3f2!important;border-color:#5f171b!important;box-shadow:none!important}.search::placeholder{color:#979390}.status,.league{color:#a7a4a1!important}.match{background:linear-gradient(180deg,#1a1816,#141211)!important;border:1px solid #64171b!important;border-left:3px solid #e8434b!important;box-shadow:0 14px 30px rgba(0,0,0,.22)!important}.match.live{border-left-color:#ff4e69!important}.fmt,.ta,.si,.foot{color:#a9a6a3!important}.tn{color:#fff!important}.sc{color:#f6f4f3!important}.badge{background:#282522!important;color:#e99fa3!important}.badge.live{background:rgba(255,74,105,.14)!important;color:#ff7389!important;border:1px solid rgba(255,83,111,.35)}.oddsRow{background:#141311!important;border-top-color:#5e1519!important}.oddBox{background:linear-gradient(135deg,#c31821,#740e13)!important;border-color:#e31c26!important}.oddBox:nth-of-type(3){background:linear-gradient(135deg,#0e9d60,#075d3d)!important;border-color:#25d98b!important}.oddLabel{color:#e7e4e1!important}.oddValue{color:white!important}
.bottom{left:0!important;right:0!important;bottom:0!important;max-width:none!important;border-radius:0!important;padding:8px 14px calc(8px + env(safe-area-inset-bottom))!important;background:rgba(12,11,10,.98)!important;border-top:1px solid #2c2926!important;box-shadow:0 -12px 30px rgba(0,0,0,.25)!important}.bottom button{height:62px!important;color:#b5b2af!important}.bottom .on{background:transparent!important;color:#fff!important}.bottom .on b{color:#e73f47!important;text-shadow:0 0 18px rgba(231,63,71,.6)}
body.matchOpen .top{display:none!important}body.matchOpen .main{display:none!important}body.matchOpen{background:#0a0908!important}.detail{padding:0 0 calc(96px + env(safe-area-inset-bottom))!important;background:#0a0908!important;min-height:100vh}.detail>.back{display:none!important}
.v33AppTop{position:sticky;top:0;z-index:45;display:grid;grid-template-columns:48px 1fr auto;align-items:center;gap:8px;padding:12px 16px;background:rgba(14,12,11,.96);backdrop-filter:blur(14px);border-bottom:1px solid #2e2b27}.v33Menu{width:40px;height:40px;border:0;background:transparent;color:#fff;font-size:28px}.v33Brand{display:flex;align-items:center;gap:8px;min-width:0}.v33Bar{width:6px;height:38px;border-radius:3px;background:linear-gradient(180deg,#ffd44f,#f4a500)}.v33Word b{display:block;color:#fff;font-size:29px;line-height:1;letter-spacing:-1px}.v33Word span{display:block;color:#bfbcba;font-size:9px;letter-spacing:2px;margin-top:4px}.v33Live{display:flex;align-items:center;gap:8px;padding:9px 13px;border-radius:999px;border:1px solid #2fe486;background:rgba(11,89,57,.3);color:#fff;font-size:12px;font-weight:1000;box-shadow:0 0 22px rgba(47,228,134,.16)}.v33Live i{width:10px;height:10px;border-radius:50%;background:#5bff9e;box-shadow:0 0 12px #5bff9e}
.v33Hero{position:relative;overflow:hidden;border-bottom:1px solid #631418;background:radial-gradient(circle at 50% 18%,rgba(230,49,58,.26),transparent 26%),radial-gradient(circle at 10% 70%,rgba(228,36,46,.2),transparent 24%),radial-gradient(circle at 90% 70%,rgba(255,95,33,.18),transparent 24%),linear-gradient(180deg,#221f1c 0%,#171513 52%,#0f0e0c 100%);padding:18px 18px 20px}.v33Hero:before,.v33Hero:after{content:'';position:absolute;bottom:14%;width:46%;height:2px;opacity:.8}.v33Hero:before{left:7%;background:linear-gradient(90deg,transparent,#e63941)}.v33Hero:after{right:7%;background:linear-gradient(90deg,#ff6d2f,transparent)}.v33Series{text-align:center;font-size:18px;font-weight:1000;color:#fff;position:relative;z-index:2}.v33Format{position:absolute;right:14px;top:14px;padding:8px 13px;border-radius:999px;background:linear-gradient(135deg,#be8c28,#e6b552);border:1px solid #ecc67a;color:#fff;font-size:11px;font-weight:900}.v33LiveFrom{text-align:center;margin-top:14px;color:#dfa9ac;font-size:9px;letter-spacing:3px;position:relative;z-index:2}.v33Teams{display:grid;grid-template-columns:1fr 58px 1fr;gap:10px;align-items:center;margin-top:12px;position:relative;z-index:2}.v33Team.right{text-align:right}.v33FlagWrap{display:flex;margin-bottom:7px}.v33Team.right .v33FlagWrap{justify-content:flex-end}.v33Team .teamMark{width:68px!important;height:68px!important;border:4px solid #e6343d!important;box-shadow:0 0 0 4px rgba(105,13,18,.8),0 0 24px rgba(230,51,60,.35)!important}.v33TeamName{font-size:21px;font-weight:1000;color:#fff}.v33TeamAbbr{font-size:11px;color:#c0bebb;margin-top:2px}.v33TeamScore{font-size:48px;font-weight:1000;line-height:1;color:#fff;margin-top:12px;letter-spacing:-1px}.v33TeamInfo{font-size:14px;color:#f0eeeb;margin-top:6px}.v33Vs{width:58px;height:58px;border-radius:50%;display:grid;place-items:center;background:rgba(19,17,16,.95);border:2px solid #d3262f;color:#fff;font-size:18px;font-weight:1000;box-shadow:0 0 20px rgba(228,39,48,.35)}.v33Report{margin:18px auto 0;max-width:470px;border:1px solid #b8171f;background:rgba(28,25,22,.72);border-radius:999px;padding:10px 14px;text-align:center;color:#f5f3f2;font-size:13px;font-weight:900;position:relative;z-index:2}
.v33Content{padding:12px 14px 20px}.v33Market,.v33Sessions,.v33Snapshot,.v33Panel{background:linear-gradient(180deg,#191715,#131210);border:1px solid #6d161a;border-radius:18px;box-shadow:0 14px 30px rgba(0,0,0,.24);margin-bottom:11px}.v33Market{padding:14px}.v33Head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:12px}.v33Head strong{font-size:21px;color:#fff}.v33Head .accent{color:#e73f47}.v33Head small{color:#e8424b;font-size:10px;font-weight:900}.v33Odds{display:grid;grid-template-columns:1fr 1fr;gap:10px}.v33Odd{display:grid;grid-template-columns:auto 1fr;gap:10px;align-items:center;padding:13px;border-radius:14px;background:linear-gradient(135deg,#de1b25,#871117);border:1px solid #e73a43;min-width:0}.v33Odd.green{background:linear-gradient(135deg,#12a766,#075c3c);border-color:#2fe18d}.v33Odd .miniMark{width:48px!important;height:48px!important;background:#fff!important;color:#831016!important}.v33OddName{font-size:14px;font-weight:900;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.v33OddVal{font-size:34px;font-weight:1000;line-height:1;color:#fff;margin-top:3px}.v33History{display:grid;grid-template-columns:repeat(4,1fr);margin-top:10px;border-radius:13px;border:1px solid #792024;overflow:hidden}.v33Hist{padding:9px 5px;text-align:center;background:#26221f;border-right:1px solid #792024}.v33Hist:last-child{border-right:0}.v33Hist span{display:block;font-size:8px;color:#b0aca9;font-weight:900}.v33Hist b{display:block;margin-top:3px;font-size:16px;color:#fff}.v33Hist.min b{color:#4fe19b}.v33Hist.max b{color:#ff667e}.v33Hist.current b{color:#e84850}
.v33Sessions{padding:13px}.v33SessionGrid{display:grid;grid-template-columns:1fr 1fr;gap:9px}.v33Session{padding:12px;border-radius:13px;background:linear-gradient(135deg,#8e1118,#2e2a26);border:1px solid #de343c}.v33Session:nth-child(even){background:linear-gradient(135deg,#bb8b2a,#65161a);border-color:#ebc475}.v33SessionName{font-size:12px;font-weight:1000;color:#fff}.v33SessionVals{display:flex;gap:8px;flex-wrap:wrap;margin-top:7px}.v33SessionVals span{padding:5px 8px;border-radius:8px;background:rgba(255,255,255,.08);color:#edc8ca;font-size:9px}.v33SessionVals b{color:#fff;font-size:13px;margin-left:3px}.v33Tabs{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:11px 0!important}.v33Tabs .dtab{height:54px!important;background:#1e1c19!important;color:#c1bebb!important;border:1px solid #5b171a!important;border-radius:13px!important}.v33Tabs .dtab.on{background:linear-gradient(135deg,#e6343d,#e4242e)!important;border-color:#e8474f!important;color:#fff!important;box-shadow:0 8px 24px rgba(229,41,51,.25)!important}.v33Snapshot{padding:14px}.v33SnapHead{display:flex;align-items:center;justify-content:space-between;margin-bottom:11px}.v33SnapHead strong{font-size:18px;color:#fff}.v33SnapHead span{font-size:10px;font-weight:1000;color:#ff637c}.v33Metrics{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid #701a1e;border-radius:13px;overflow:hidden}.v33Metric{padding:11px 5px;text-align:center;background:#1f1c1a;border-right:1px solid #701a1e}.v33Metric:last-child{border-right:0}.v33Metric span{display:block;font-size:8px;color:#adaaa6;font-weight:900}.v33Metric b{display:block;font-size:20px;color:#fff;margin-top:4px}.v33Snapshot .playerStrip{margin-top:12px!important;gap:9px!important}.v33Snapshot .playerCard{background:#181715!important;border-color:#60171b!important}.v33Snapshot .playerRole{color:#a4a09c!important}.v33Snapshot .playerName{color:#fff!important;font-size:13px!important}.v33Snapshot .playerStat{color:#ccc9c6!important}.v33Snapshot .lastSix{margin-top:13px!important;padding-top:11px;border-top:1px solid #5e171b}.v33Snapshot .ballChip{background:#6b2528!important;color:#fff!important;width:38px!important;height:38px!important}.v33Snapshot .ballChip.boundary{background:#e3202a!important}.v33Snapshot .ballChip.six{background:#e5b14a!important}.v33Snapshot .ballChip.wicket{background:#e84861!important}.v33Panel{padding:13px}.v33Panel .notice,.v33Panel .inning,.v33Panel .ball,.v33Panel .moreItem{background:#181614!important;border-color:#5d171a!important;color:#dad8d6!important}.v33Panel .ptitle b,.v33Panel .inningTeam,.v33Panel .inningScore,.v33Panel .moreItem,.v33Panel .kv b{color:#fff!important}.v33Panel .kv{border-color:#2e2b28!important;color:#b0aca9!important}
@media(max-width:430px){.v33Series{font-size:15px;padding-right:56px;padding-left:56px}.v33Team .teamMark{width:58px!important;height:58px!important}.v33TeamName{font-size:17px}.v33TeamScore{font-size:40px}.v33Odds{grid-template-columns:1fr 1fr}.v33SessionGrid{grid-template-columns:1fr 1fr}.v33Metrics{grid-template-columns:repeat(4,1fr)}.v33Metric b{font-size:17px}.v33Tabs{gap:5px}.v33Tabs .dtab{font-size:8px!important}.v33Word b{font-size:26px}.v33Live{padding:8px 10px;font-size:10px}}
'''

V33_JS = r'''
<script>
(function(){
  const previousOpenMatch=openMatch, previousBackHome=backHome;
  function v33RunRate(){return rateValue(detailData?.roanuz?.runRate)||'—'}
  function v33Overs(){const m=detailData?.match||{};return String(m.awayInfo||m.homeInfo||'').replace(/\s*ov$/i,'')||'—'}
  function v33Target(){const t=targetRuns(detailData?.roanuz?.target);return t||'—'}
  function v33RRR(){
    const m=detailData?.match||{},t=targetRuns(detailData?.roanuz?.target);if(!t)return'—';
    const a=scoreRuns(m.awayScore),h=scoreRuns(m.homeScore),ab=scoreOvers(m.awayInfo),hb=scoreOvers(m.homeInfo);let runs=null,balls=null;
    if(ab!==null&&(hb===null||ab>=hb)){runs=a;balls=ab}else if(hb!==null){runs=h;balls=hb}if(runs===null||balls===null)return'—';
    const left=Math.max(0,120-balls),need=Math.max(0,t-runs);return left>0?((need*6)/left).toFixed(2):'—';
  }
  function v33Series(m){return league(m)+(m?.format?` · ${m.format}`:'')}
  function v33AppHeader(){return `<div class="v33AppTop"><button class="v33Menu" onclick="backHome()">‹</button><div class="v33Brand"><i class="v33Bar"></i><div class="v33Word"><b>IBETIN</b><span>LIVE CRICKET. BIGGER THRILLS.</span></div></div><div class="v33Live"><i></i> LIVE</div></div>`}
  function v33Market(j,m){
    const main=j?findMatchMarket(j):null, mv=main?values(main).slice(0,2):[], sessions=j?sessionMarkets(j,main).slice(0,4):[];
    const odds=mv.length?mv.map((v,i)=>`<div class="v33Odd ${i===1?'green':''}">${miniMark(i===0?m.home:m.away)}<div><div class="v33OddName">${esc(v.label||((i===0?m.home:m.away)?.name)||'Selection')}</div><div class="v33OddVal">${esc(v.odd)}</div></div></div>`).join(''):`<div class="notice">Live match odds are loading…</div>`;
    const current=mv[0]?.odd||'—';
    const hist=`<div class="v33History"><div class="v33Hist"><span>OPEN</span><b>—</b></div><div class="v33Hist min"><span>MIN</span><b>—</b></div><div class="v33Hist max"><span>MAX</span><b>—</b></div><div class="v33Hist current"><span>CURRENT</span><b>${esc(current)}</b></div></div>`;
    const sessionBlock=sessions.length?`<div class="v33Sessions"><div class="v33Head"><strong>◴ SESSION MARKET</strong><small>VIEW ALL ›</small></div><div class="v33SessionGrid">${sessions.map(e=>`<div class="v33Session"><div class="v33SessionName">${esc(e.market||'Session')}</div><div class="v33SessionVals">${values(e).slice(0,4).map(v=>`<span>${esc(v.label||'Line')} <b>${esc(v.odd)}</b></span>`).join('')}</div></div>`).join('')}</div></div>`:'';
    return `<div class="v33Market"><div class="v33Head"><strong><span class="accent">↗</span> LIVE BHAV</strong><small>LIVE MARKET ›</small></div><div class="v33Odds">${odds}</div>${hist}</div>${sessionBlock}`;
  }
  function v33Snapshot(detail,m){
    return `<div class="v33Snapshot"><div class="v33SnapHead"><strong>▥ MATCH SNAPSHOT</strong><span>● ${esc(prettyState(m.state)||'LIVE')}</span></div><div class="v33Metrics"><div class="v33Metric"><span>CRR</span><b>${esc(v33RunRate())}</b></div><div class="v33Metric"><span>RRR</span><b>${esc(v33RRR())}</b></div><div class="v33Metric"><span>OVERS</span><b>${esc(v33Overs())}</b></div><div class="v33Metric"><span>TARGET</span><b>${esc(v33Target())}</b></div></div>${currentPlayersHtml(detail)}${lastSixHtml(detail.timeline||[])}</div>`;
  }
  function v33RenderMarket(key,m){
    const c=bhavCache.get(key);const mount=document.getElementById('v33Markets');if(c?.data&&mount){mount.innerHTML=v33Market(c.data,m);return}
    api({action:'bhav',matchId:key},false).then(j=>{bhavCache.set(key,{ts:Date.now(),data:j});const el=document.getElementById('v33Markets');if(el)el.innerHTML=v33Market(j,m)}).catch(()=>{const el=document.getElementById('v33Markets');if(el)el.innerHTML=v33Market(null,m)});
  }
  drawDetail=function(){
    const d=document.getElementById('detail'),detail=detailData||{},m=detail.match||{},key=matchKey(m),status=prettyState(m.state)||'LIVE';
    document.body.classList.add('matchOpen');
    d.innerHTML=`${v33AppHeader()}<div class="v33Hero"><div class="v33Series">${esc(v33Series(m))}</div><div class="v33Format">◉ ${esc(m.format||'CRICKET')}</div><div class="v33LiveFrom">LIVE CRICKET</div><div class="v33Teams"><div class="v33Team"><div class="v33FlagWrap">${teamMark(m.home)}</div><div class="v33TeamAbbr">${esc(m.home?.abbr||'')}</div><div class="v33TeamName">${esc(m.home?.name||'Home')}</div><div class="v33TeamScore">${display(m.homeScore)}</div><div class="v33TeamInfo">${esc(m.homeInfo||'')}</div></div><div class="v33Vs">VS</div><div class="v33Team right"><div class="v33FlagWrap">${teamMark(m.away)}</div><div class="v33TeamAbbr">${esc(m.away?.abbr||'')}</div><div class="v33TeamName">${esc(m.away?.name||'Away')}</div><div class="v33TeamScore">${display(m.awayScore)}</div><div class="v33TeamInfo">${esc(m.awayInfo||'')}</div></div></div><div class="v33Report">${esc(m.report||status)}</div></div><div class="v33Content"><div id="v33Markets"></div><div class="dtabs v33Tabs">${tabsHtml()}</div>${detailTab==='match'?v33Snapshot(detail,m):''}<div id="panel" class="panel v33Panel"></div></div>`;
    d.querySelectorAll('.dtab').forEach(b=>b.onclick=()=>{detailTab=b.dataset.tab;drawDetail()});
    if(detailTab==='match'){const p=document.getElementById('panel');if(p)p.style.display='none'}else{const p=document.getElementById('panel');if(p)p.style.display='block';drawPanel()}
    v33RenderMarket(key,m);
  };
  openMatch=async function(key){document.body.classList.add('matchOpen');try{if(tg?.requestFullscreen)tg.requestFullscreen()}catch(e){};return previousOpenMatch(key)};
  backHome=function(){document.body.classList.remove('matchOpen');try{if(tg?.exitFullscreen)tg.exitFullscreen()}catch(e){};return previousBackHome()};
  try{if(tg){tg.setHeaderColor('#0c0b0a');tg.setBackgroundColor('#0c0b0a')}}catch(e){}
  window.__IBETIN_V33_FAITHFUL__=true;
})();
</script>
'''


def _page_v33() -> str:
    html = v32._page_v32()
    html = html.replace('</style>', V33_CSS + '\n</style>', 1)
    html = html.replace('</body>', V33_JS + '\n</body>', 1)
    return html

v32.v31.v30.v23._page = _page_v33
v32.v31.v30.v23.liveline._page = _page_v33


def _self_test() -> None:
    page = _page_v33()
    checks = {
        'full_detail_shell': 'v33AppTop' in page and 'body.matchOpen .top{display:none' in page,
        'stadium_hero': 'v33Hero' in page and 'v33Teams' in page,
        'premium_bhav': 'v33Odds' in page and 'LIVE BHAV' in page,
        'history_strip': 'OPEN' in page and 'CURRENT' in page,
        'real_sessions': 'SESSION MARKET' in page and 'sessionMarkets(j,main)' in page,
        'five_tabs': 'v33Tabs' in page and 'tabsHtml()' in page,
        'snapshot': 'MATCH SNAPSHOT' in page and 'v33Metrics' in page,
        'fullscreen_attempt': 'requestFullscreen' in page,
        'no_fake_session_values': '2.10' not in page and '2.45' not in page,
    }
    ok = all(checks.values())
    (logger.info if ok else logger.error)('IBETIN V33 faithful UI self-test %s checks=%s','PASS' if ok else 'FAILED',checks)
    if not ok:
        raise RuntimeError(f'V33 faithful UI self-test failed: {checks}')

_self_test()
logger.info('IBETIN V33 installed: faithful premium mockup implementation on existing Telegram route')

app = v32.app

if __name__ == '__main__':
    app.base.ibetin_start.main()
