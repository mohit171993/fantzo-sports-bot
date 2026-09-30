import logging

import ibetin_liveline_v32_mockup_layout as v32

logger = logging.getLogger(__name__)

V33_CSS = r'''
/* V33 faithful premium implementation */
:root{--v33bg:#030a13;--v33navy:#081120;--v33card:#091628;--v33line:#164070;--v33cyan:#2088ff;--v33blue:#1381ff;--v33green:#20dd87;--v33purple:#429aff;--v33red:#ff536f;--v33text:#f6fbff;--v33muted:#95a6c0}
html,body{background:radial-gradient(circle at 50% 0,#0b1f3d 0,#050d1a 32%,#03080f 75%);color:var(--v33text)!important}
body{padding-bottom:calc(86px + env(safe-area-inset-bottom))!important}.shell{max-width:760px;background:transparent}.top{background:linear-gradient(180deg,#09172d,#06101f)!important;border-bottom:1px solid rgba(74,158,255,.18);box-shadow:0 12px 32px rgba(0,0,0,.25)!important}.mark{width:7px!important;height:43px!important;border-radius:3px!important;background:linear-gradient(180deg,#4ea1ff,#0073f6)!important;color:transparent!important;font-size:0!important}.brand{gap:9px!important}.brand b{font-size:30px!important;line-height:1!important;letter-spacing:-1px!important;color:white}.brand span{font-size:10px!important;letter-spacing:2.2px!important;color:#bbc9de!important}.liveDot{font-size:13px!important;padding:9px 15px!important;border:1px solid #28e585!important;background:rgba(11,116,70,.28)!important;box-shadow:0 0 20px rgba(39,229,133,.2);color:#eafff2!important}.tabs{gap:8px!important}.tab{background:#0d1f3a!important;color:#acbcd4!important;border:1px solid #12355c!important}.tab.on{background:linear-gradient(135deg,#0a7cff,#1469cb)!important;color:#fff!important;border-color:#1b85ff!important;box-shadow:0 7px 24px rgba(20,130,255,.25)}
.main{background:transparent!important}.search,.refresh{background:#091424!important;color:#eaf2fd!important;border-color:#17395f!important;box-shadow:none!important}.search::placeholder{color:#7c8fab}.status,.league{color:#8d9fbb!important}.match{background:linear-gradient(180deg,#0a1729,#07111f)!important;border:1px solid #173b64!important;border-left:3px solid #2c8eff!important;box-shadow:0 14px 30px rgba(0,0,0,.22)!important}.match.live{border-left-color:#ff4e69!important}.fmt,.ta,.si,.foot{color:#90a2bc!important}.tn{color:#fff!important}.sc{color:#ecf3fd!important}.badge{background:#12233c!important;color:#9fc2e9!important}.badge.live{background:rgba(255,74,105,.14)!important;color:#ff7389!important;border:1px solid rgba(255,83,111,.35)}.oddsRow{background:#081120!important;border-top-color:#15375e!important}.oddBox{background:linear-gradient(135deg,#0a67d1,#0a3d78)!important;border-color:#1779e8!important}.oddBox:nth-of-type(3){background:linear-gradient(135deg,#0e9d60,#075d3d)!important;border-color:#25d98b!important}.oddLabel{color:#d2e0f6!important}.oddValue{color:white!important}
.bottom{left:0!important;right:0!important;bottom:0!important;max-width:none!important;border-radius:0!important;padding:8px 14px calc(8px + env(safe-area-inset-bottom))!important;background:rgba(3,10,19,.98)!important;border-top:1px solid #132643!important;box-shadow:0 -12px 30px rgba(0,0,0,.25)!important}.bottom button{height:62px!important;color:#9eaec6!important}.bottom .on{background:transparent!important;color:#fff!important}.bottom .on b{color:#278cff!important;text-shadow:0 0 18px rgba(39,140,255,.6)}
body.matchOpen .top{display:none!important}body.matchOpen .main{display:none!important}body.matchOpen{background:#030911!important}.detail{padding:0 0 calc(96px + env(safe-area-inset-bottom))!important;background:#030911!important;min-height:100vh}.detail>.back{display:none!important}
.v33AppTop{position:sticky;top:0;z-index:45;display:grid;grid-template-columns:48px 1fr auto;align-items:center;gap:8px;padding:12px 16px;background:rgba(3,11,23,.96);backdrop-filter:blur(14px);border-bottom:1px solid #152845}.v33Menu{width:40px;height:40px;border:0;background:transparent;color:#fff;font-size:28px}.v33Brand{display:flex;align-items:center;gap:8px;min-width:0}.v33Bar{width:6px;height:38px;border-radius:3px;background:linear-gradient(180deg,#4fa1ff,#0072f4)}.v33Word b{display:block;color:#fff;font-size:29px;line-height:1;letter-spacing:-1px}.v33Word span{display:block;color:#abb9ce;font-size:9px;letter-spacing:2px;margin-top:4px}.v33Live{display:flex;align-items:center;gap:8px;padding:9px 13px;border-radius:999px;border:1px solid #2fe486;background:rgba(11,89,57,.3);color:#fff;font-size:12px;font-weight:1000;box-shadow:0 0 22px rgba(47,228,134,.16)}.v33Live i{width:10px;height:10px;border-radius:50%;background:#5bff9e;box-shadow:0 0 12px #5bff9e}
.v33Hero{position:relative;overflow:hidden;border-bottom:1px solid #143963;background:radial-gradient(circle at 50% 18%,rgba(24,132,255,.26),transparent 26%),radial-gradient(circle at 10% 70%,rgba(9,124,255,.2),transparent 24%),radial-gradient(circle at 90% 70%,rgba(33,137,255,.18),transparent 24%),linear-gradient(180deg,#091c37 0%,#081324 52%,#040c18 100%);padding:18px 18px 20px}.v33Hero:before,.v33Hero:after{content:'';position:absolute;bottom:14%;width:46%;height:2px;opacity:.8}.v33Hero:before{left:7%;background:linear-gradient(90deg,transparent,#2088ff)}.v33Hero:after{right:7%;background:linear-gradient(90deg,#2f90ff,transparent)}.v33Series{text-align:center;font-size:18px;font-weight:1000;color:#fff;position:relative;z-index:2}.v33Format{position:absolute;right:14px;top:14px;padding:8px 13px;border-radius:999px;background:linear-gradient(135deg,#2361a7,#3995ff);border:1px solid #67aeff;color:#fff;font-size:11px;font-weight:900}.v33LiveFrom{text-align:center;margin-top:14px;color:#a9c2df;font-size:9px;letter-spacing:3px;position:relative;z-index:2}.v33Teams{display:grid;grid-template-columns:1fr 58px 1fr;gap:10px;align-items:center;margin-top:12px;position:relative;z-index:2}.v33Team.right{text-align:right}.v33FlagWrap{display:flex;margin-bottom:7px}.v33Team.right .v33FlagWrap{justify-content:flex-end}.v33Team .teamMark{width:68px!important;height:68px!important;border:4px solid #2b86ef!important;box-shadow:0 0 0 4px rgba(7,56,111,.8),0 0 24px rgba(26,133,255,.35)!important}.v33TeamName{font-size:21px;font-weight:1000;color:#fff}.v33TeamAbbr{font-size:11px;color:#abbad0;margin-top:2px}.v33TeamScore{font-size:48px;font-weight:1000;line-height:1;color:#fff;margin-top:12px;letter-spacing:-1px}.v33TeamInfo{font-size:14px;color:#dfebfc;margin-top:6px}.v33Vs{width:58px;height:58px;border-radius:50%;display:grid;place-items:center;background:rgba(6,16,31,.95);border:2px solid #2677d3;color:#fff;font-size:18px;font-weight:1000;box-shadow:0 0 20px rgba(35,127,232,.35)}.v33Report{margin:18px auto 0;max-width:470px;border:1px solid #1662b9;background:rgba(6,22,47,.72);border-radius:999px;padding:10px 14px;text-align:center;color:#eaf2fd;font-size:13px;font-weight:900;position:relative;z-index:2}
.v33Content{padding:12px 14px 20px}.v33Market,.v33Sessions,.v33Snapshot,.v33Panel{background:linear-gradient(180deg,#091527,#07111e);border:1px solid #163f6d;border-radius:18px;box-shadow:0 14px 30px rgba(0,0,0,.24);margin-bottom:11px}.v33Market{padding:14px}.v33Head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:12px}.v33Head strong{font-size:21px;color:#fff}.v33Head .accent{color:#278cff}.v33Head small{color:#2b8eff;font-size:10px;font-weight:900}.v33Odds{display:grid;grid-template-columns:1fr 1fr;gap:10px}.v33Odd{display:grid;grid-template-columns:auto 1fr;gap:10px;align-items:center;padding:13px;border-radius:14px;background:linear-gradient(135deg,#0c75ed,#074791);border:1px solid #2289ff;min-width:0}.v33Odd.green{background:linear-gradient(135deg,#12a766,#075c3c);border-color:#2fe18d}.v33Odd .miniMark{width:48px!important;height:48px!important;background:#fff!important;color:#0c4587!important}.v33OddName{font-size:14px;font-weight:900;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.v33OddVal{font-size:34px;font-weight:1000;line-height:1;color:#fff;margin-top:3px}.v33History{display:grid;grid-template-columns:repeat(4,1fr);margin-top:10px;border-radius:13px;border:1px solid #204a79;overflow:hidden}.v33Hist{padding:9px 5px;text-align:center;background:#0d203c;border-right:1px solid #204a79}.v33Hist:last-child{border-right:0}.v33Hist span{display:block;font-size:8px;color:#93a7c6;font-weight:900}.v33Hist b{display:block;margin-top:3px;font-size:16px;color:#fff}.v33Hist.min b{color:#4fe19b}.v33Hist.max b{color:#ff667e}.v33Hist.current b{color:#3191ff}
.v33Sessions{padding:13px}.v33SessionGrid{display:grid;grid-template-columns:1fr 1fr;gap:9px}.v33Session{padding:12px;border-radius:13px;background:linear-gradient(135deg,#0a4b95,#0e264a);border:1px solid #3483de}.v33Session:nth-child(even){background:linear-gradient(135deg,#2766ae,#163b65);border-color:#61abff}.v33SessionName{font-size:12px;font-weight:1000;color:#fff}.v33SessionVals{display:flex;gap:8px;flex-wrap:wrap;margin-top:7px}.v33SessionVals span{padding:5px 8px;border-radius:8px;background:rgba(255,255,255,.08);color:#c8d9ed;font-size:9px}.v33SessionVals b{color:#fff;font-size:13px;margin-left:3px}.v33Tabs{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:11px 0!important}.v33Tabs .dtab{height:54px!important;background:#0d1a2e!important;color:#aabad2!important;border:1px solid #17375b!important;border-radius:13px!important}.v33Tabs .dtab.on{background:linear-gradient(135deg,#1b85ff,#157df3)!important;border-color:#3091ff!important;color:#fff!important;box-shadow:0 8px 24px rgba(15,127,255,.25)!important}.v33Snapshot{padding:14px}.v33SnapHead{display:flex;align-items:center;justify-content:space-between;margin-bottom:11px}.v33SnapHead strong{font-size:18px;color:#fff}.v33SnapHead span{font-size:10px;font-weight:1000;color:#ff637c}.v33Metrics{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid #1a4270;border-radius:13px;overflow:hidden}.v33Metric{padding:11px 5px;text-align:center;background:#0b1a32;border-right:1px solid #1a4270}.v33Metric:last-child{border-right:0}.v33Metric span{display:block;font-size:8px;color:#94a5bf;font-weight:900}.v33Metric b{display:block;font-size:20px;color:#fff;margin-top:4px}.v33Snapshot .playerStrip{margin-top:12px!important;gap:9px!important}.v33Snapshot .playerCard{background:#0a1526!important;border-color:#173960!important}.v33Snapshot .playerRole{color:#839abd!important}.v33Snapshot .playerName{color:#fff!important;font-size:13px!important}.v33Snapshot .playerStat{color:#b7c5db!important}.v33Snapshot .lastSix{margin-top:13px!important;padding-top:11px;border-top:1px solid #17385e}.v33Snapshot .ballChip{background:#25466b!important;color:#fff!important;width:38px!important;height:38px!important}.v33Snapshot .ballChip.boundary{background:#107af4!important}.v33Snapshot .ballChip.six{background:#4892e7!important}.v33Snapshot .ballChip.wicket{background:#e84861!important}.v33Panel{padding:13px}.v33Panel .notice,.v33Panel .inning,.v33Panel .ball,.v33Panel .moreItem{background:#0a1525!important;border-color:#17385d!important;color:#cad5e6!important}.v33Panel .ptitle b,.v33Panel .inningTeam,.v33Panel .inningScore,.v33Panel .moreItem,.v33Panel .kv b{color:#fff!important}.v33Panel .kv{border-color:#182942!important;color:#97a8c2!important}
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
  try{if(tg){tg.setHeaderColor('#030a13');tg.setBackgroundColor('#030a13')}}catch(e){}
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
