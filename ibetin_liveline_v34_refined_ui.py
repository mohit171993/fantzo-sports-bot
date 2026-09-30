import logging

import ibetin_liveline_v33_faithful_ui as v33

logger = logging.getLogger(__name__)

V34_CSS = r'''
/* V34 refined production polish: compact, safe, premium, no Telegram overlap */
:root{--v34bg:#020914;--v34panel:#07192b;--v34line:#153b5d;--v34blue:#168fff;--v34cyan:#26c1ff;--v34green:#27dd8a;--v34purple:#7b43f6;--v34text:#f6fbff;--v34muted:#8da8c0}
html,body{background:radial-gradient(circle at 50% 0,#082349 0,#041120 36%,#020914 78%)!important}
body{padding-bottom:calc(98px + env(safe-area-inset-bottom))!important}
.top{padding:12px 14px 10px!important}.brand b{font-size:27px!important}.brand span{font-size:9px!important}.liveDot{padding:8px 13px!important;font-size:11px!important}.tabs{margin-top:12px!important}.tab{height:44px!important}.main{padding:14px 14px calc(130px + env(safe-area-inset-bottom))!important}.search{height:48px!important}.refresh{height:48px!important;width:48px!important}.match{border-radius:17px!important}.team{padding:8px 13px!important}.mh{padding:11px 13px 4px!important}.foot{padding:9px 13px!important}
.bottom{left:12px!important;right:12px!important;bottom:calc(8px + env(safe-area-inset-bottom))!important;max-width:736px!important;border-radius:22px!important;padding:6px 8px!important;background:rgba(2,12,26,.97)!important;border:1px solid #143754!important;box-shadow:0 16px 36px rgba(0,0,0,.42)!important}.bottom button{height:50px!important;border-radius:14px!important;font-size:8px!important}.bottom b{font-size:17px!important;margin-bottom:1px!important}.bottom .on{background:linear-gradient(180deg,rgba(24,116,205,.24),rgba(16,74,127,.14))!important}
body.matchOpen{background:var(--v34bg)!important;overflow-x:hidden}.detail{padding:var(--tg-content-safe-area-inset-top,0px) 0 calc(132px + env(safe-area-inset-bottom))!important;min-height:100vh!important;background:transparent!important}.v33AppTop{display:none!important}.detail>.back{display:none!important}
.v33Hero{margin:10px 12px 0!important;padding:14px 14px 15px!important;border:1px solid #16496d!important;border-radius:22px!important;background:radial-gradient(circle at 50% 5%,rgba(31,126,255,.24),transparent 28%),radial-gradient(circle at 4% 82%,rgba(0,137,255,.18),transparent 25%),radial-gradient(circle at 96% 82%,rgba(117,52,255,.16),transparent 25%),linear-gradient(180deg,#071f3d 0%,#06172c 60%,#04111f 100%)!important;box-shadow:0 18px 42px rgba(0,0,0,.30)!important}.v33LiveFrom{display:none!important}.v33Series{font-size:14px!important;line-height:1.25!important;padding:0 58px!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}.v33Format{top:11px!important;right:11px!important;padding:6px 10px!important;font-size:9px!important}.v33Teams{grid-template-columns:1fr 44px 1fr!important;gap:9px!important;margin-top:12px!important}.v33Team .teamMark{width:50px!important;height:50px!important;border-width:3px!important;box-shadow:0 0 0 3px rgba(7,57,111,.65),0 0 18px rgba(26,147,255,.28)!important}.v33FlagWrap{margin-bottom:5px!important}.v33TeamName{font-size:17px!important;line-height:1.1!important}.v33TeamAbbr{font-size:9px!important}.v33TeamScore{font-size:36px!important;margin-top:8px!important;letter-spacing:-.8px!important}.v33TeamInfo{font-size:11px!important;margin-top:4px!important}.v33Vs{width:44px!important;height:44px!important;font-size:14px!important;border-width:1px!important}.v33Report{margin:12px auto 0!important;padding:8px 12px!important;font-size:11px!important;max-width:420px!important}
.v33Content{padding:10px 12px 155px!important}.v33Market,.v33Sessions,.v33Snapshot,.v33Panel{border-radius:17px!important;margin-bottom:10px!important;border-color:#164262!important;background:linear-gradient(180deg,#07192b,#051422)!important;box-shadow:0 12px 28px rgba(0,0,0,.22)!important}.v33Market{padding:12px!important}.v33Head{margin-bottom:10px!important}.v33Head strong{font-size:18px!important}.v33Head small{font-size:9px!important}.v33Odds{gap:8px!important}.v33Odd{padding:10px!important;gap:8px!important;border-radius:13px!important}.v33Odd .miniMark{width:40px!important;height:40px!important;font-size:10px!important}.v33OddName{font-size:11px!important}.v33OddVal{font-size:27px!important}.v33History{margin-top:8px!important;border-radius:11px!important}.v33Hist{padding:7px 4px!important}.v33Hist span{font-size:7px!important}.v33Hist b{font-size:13px!important;margin-top:2px!important}
.v33Sessions{padding:12px!important}.v33Sessions .v33Head{margin-bottom:9px!important}.v33SessionGrid{display:flex!important;grid-template-columns:none!important;gap:9px!important;overflow-x:auto!important;scroll-snap-type:x proximity!important;scrollbar-width:none!important;padding-bottom:2px!important}.v33SessionGrid::-webkit-scrollbar{display:none!important}.v33Session{flex:0 0 min(72vw,230px)!important;min-height:94px!important;scroll-snap-align:start!important;padding:11px!important;border-radius:13px!important}.v33SessionName{font-size:11px!important;line-height:1.25!important;min-height:28px!important}.v33SessionVals{gap:6px!important;margin-top:7px!important}.v33SessionVals span{font-size:8px!important;padding:5px 7px!important}.v33SessionVals b{font-size:12px!important}
.v33Tabs{gap:5px!important;margin:9px 0!important}.v33Tabs .dtab{height:44px!important;border-radius:12px!important;font-size:8px!important;letter-spacing:-.1px!important}.v33Snapshot{padding:12px!important}.v33SnapHead{margin-bottom:9px!important}.v33SnapHead strong{font-size:16px!important}.v33Metrics{border-radius:11px!important}.v33Metric{padding:8px 3px!important}.v33Metric span{font-size:7px!important}.v33Metric b{font-size:15px!important;margin-top:3px!important}.v33Snapshot .playerStrip{margin-top:9px!important;gap:7px!important}.v33Snapshot .playerCard{padding:9px!important}.v33Snapshot .playerName{font-size:11px!important}.v33Snapshot .playerStat{font-size:9px!important}.v33Snapshot .lastSix{margin-top:9px!important;padding-top:9px!important}.v33Snapshot .ballChip{width:32px!important;height:32px!important;font-size:9px!important}.v33Panel{padding:11px!important}
@media(max-width:390px){.v33Hero{margin-left:9px!important;margin-right:9px!important}.v33Content{padding-left:9px!important;padding-right:9px!important}.v33Series{font-size:12px!important;padding:0 52px!important}.v33TeamName{font-size:15px!important}.v33TeamScore{font-size:32px!important}.v33OddVal{font-size:24px!important}.v33Metrics{grid-template-columns:repeat(4,1fr)!important}.v33Session{flex-basis:78vw!important}}
'''

V34_JS = r'''
<script>
(function(){
  function safeWindowed(){
    try{
      if(tg){
        if(typeof tg.exitFullscreen==='function') tg.exitFullscreen();
        if(typeof tg.setHeaderColor==='function') tg.setHeaderColor('#020914');
        if(typeof tg.setBackgroundColor==='function') tg.setBackgroundColor('#020914');
        if(typeof tg.setBottomBarColor==='function') tg.setBottomBarColor('#020914');
      }
    }catch(e){}
  }
  function syncSafe(){
    try{
      const c=tg&&tg.contentSafeAreaInset;
      if(c&&Number.isFinite(Number(c.top))) document.documentElement.style.setProperty('--tg-content-safe-area-inset-top',Number(c.top)+'px');
    }catch(e){}
  }
  safeWindowed();syncSafe();
  try{if(tg&&typeof tg.expand==='function')tg.expand();}catch(e){}
  try{if(tg&&typeof tg.onEvent==='function'){tg.onEvent('safeAreaChanged',syncSafe);tg.onEvent('contentSafeAreaChanged',syncSafe);tg.onEvent('fullscreenChanged',()=>{if(document.body.classList.contains('matchOpen'))safeWindowed();});}}catch(e){}
  try{
    const prevOpen=openMatch;
    openMatch=async function(m){safeWindowed();syncSafe();const r=await prevOpen(m);safeWindowed();syncSafe();setTimeout(safeWindowed,80);setTimeout(safeWindowed,250);return r;};
  }catch(e){}
  try{
    const prevBack=backHome;
    backHome=function(){safeWindowed();const r=prevBack();syncSafe();return r;};
  }catch(e){}
  const mo=new MutationObserver(()=>{if(document.body.classList.contains('matchOpen')){safeWindowed();syncSafe();}});
  mo.observe(document.body,{attributes:true,attributeFilter:['class']});
  window.__IBETIN_V34_REFINED__=true;
})();
</script>
'''


def _page_v34() -> str:
    html = v33._page_v33()
    html = html.replace('</style>', V34_CSS + '\n</style>', 1)
    html = html.replace('</body>', V34_JS + '\n</body>', 1)
    return html

# Keep the existing Telegram route/API contract; swap only the rendered UI.
v33.v32.v31.v30.v23._page = _page_v34
v33.v32.v31.v30.v23.liveline._page = _page_v34


def _self_test() -> None:
    page = _page_v34()
    checks = {
        'refined_marker': 'window.__IBETIN_V34_REFINED__=true' in page,
        'telegram_safe_area': '--tg-content-safe-area-inset-top' in page,
        'no_duplicate_detail_header': '.v33AppTop{display:none!important}' in page,
        'no_forced_fullscreen': 'exitFullscreen' in page,
        'compact_hero': '.v33TeamScore{font-size:36px' in page,
        'swipe_sessions': 'scroll-snap-type:x proximity' in page,
        'nav_clearance': 'padding:10px 12px 155px' in page,
        'bhav_preserved': 'LIVE BHAV' in page,
        'session_preserved': 'SESSION MARKET' in page or 'SESSION MARKETS' in page,
        'backend_preserved': "action:'score'" in page and 'bhavCache' in page,
    }
    ok = all(checks.values())
    (logger.info if ok else logger.error)('IBETIN V34 refined UI self-test %s checks=%s','PASS' if ok else 'FAILED',checks)
    if not ok:
        raise RuntimeError(f'V34 refined UI self-test failed: {checks}')

_self_test()
logger.info('IBETIN V34 installed: compact premium UI + Telegram safe-area fix + swipe sessions')

app = v33.app

if __name__ == '__main__':
    app.base.ibetin_start.main()
