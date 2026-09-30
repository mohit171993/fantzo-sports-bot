import logging

import ibetin_liveline_v30_unified_ui as v30

logger = logging.getLogger(__name__)

PREMIUM_CSS = r'''
/* IBETIN V31 premium dark/neon presentation layer. Data/API logic remains V30/V25. */
:root{
  --bg:#040607;--navy:#070b0c;--blue:#10dfff;--gold:#4de7ff;--ink:#fafbfb;
  --muted:#98b2b8;--card:#090d0f;--live:#ff4f69;--green:#20d787;
  --shadow:0 14px 34px rgba(0,0,0,.34)
}
html,body{background:
  radial-gradient(circle at 15% 0%,rgba(0,221,255,.22),transparent 28%),
  radial-gradient(circle at 90% 10%,rgba(0,221,255,.18),transparent 25%),
  linear-gradient(180deg,#06090b 0%,#040607 38%,#040506 100%)!important;
  color:#f9fbfb!important}
body{min-height:100vh}
.shell{background:transparent}
.top{background:
  radial-gradient(circle at 72% 0%,rgba(20,224,255,.22),transparent 32%),
  linear-gradient(125deg,#070b0c,#0f161a 72%,#19252a)!important;
  border-bottom:1px solid rgba(30,225,255,.26);box-shadow:0 10px 28px rgba(0,0,0,.28)!important}
.mark{display:none!important}
.brand{gap:0!important}.brand b{font-size:28px!important;letter-spacing:1.3px!important;color:#fff!important;text-shadow:0 2px 16px rgba(35,226,255,.15)}
.brand b::first-letter{color:#3de5ff}
.brand span{color:#b8cacd!important;letter-spacing:2px!important;font-size:10px!important}
.liveDot{background:linear-gradient(180deg,rgba(16,166,98,.25),rgba(19,27,31,.3))!important;border:1px solid #31de8f!important;color:#dfffee!important;box-shadow:0 0 18px rgba(43,231,145,.28);padding:9px 14px!important}
.tabs{gap:10px!important}.tab{height:52px!important;background:rgba(17,24,28,.74)!important;color:#b2c6ca!important;border:1px solid rgba(81,232,255,.1)!important}.tab.on{background:linear-gradient(135deg,#00ddff,#00ddff)!important;color:#fff!important;border-color:#0cdfff!important;box-shadow:0 8px 22px rgba(0,221,255,.24)}
.main,.detail{background:transparent!important}
.search,.refresh{background:#090d0f!important;border:1px solid #172126!important;color:#eaf0f1!important;box-shadow:0 10px 24px rgba(0,0,0,.2)!important}.search::placeholder{color:#6c9198!important}.refresh{color:#49e7ff!important}
.status{color:#7fa0a6!important}.league{color:#69ebff!important;text-transform:uppercase;letter-spacing:.45px}
.match{background:linear-gradient(180deg,#0a0f11,#080b0d)!important;border:1px solid #162025!important;border-left:3px solid #00ddff!important;box-shadow:0 14px 30px rgba(0,0,0,.26)!important}.match.live{border-left-color:#ff4f69!important}.fmt{color:#88a6ac!important}.badge{background:#0f1619!important;color:#64eaff!important}.badge.live{background:rgba(255,54,86,.14)!important;color:#ff6f84!important;border:1px solid rgba(255,77,105,.25)}
.miniMark,.teamMark{background:linear-gradient(145deg,#10181b,#0c1214)!important;color:#8df0ff!important;border:1px solid #00ddff!important;box-shadow:inset 0 0 0 2px rgba(255,255,255,.02)}
.tn{color:#f8fafa!important}.ta,.si{color:#7799a0!important}.sc{color:#ffffff!important;text-shadow:0 0 18px rgba(26,224,255,.2)}
.oddsRow{background:#080c0e!important;border-top:1px solid #11191d!important}.oddsTitle{color:#45e6ff!important}.oddBox{background:linear-gradient(135deg,#00ddff,#1a252b)!important;border:1px solid #16e0ff!important;box-shadow:0 6px 15px rgba(0,221,255,.18)}.oddBox:nth-child(3){background:linear-gradient(135deg,#0b9258,#151f24)!important;border-color:#29db8d!important}.oddLabel{color:#e9eeef!important}.oddValue{color:#fff!important;font-size:15px!important}.foot{border-top:1px solid #11191d!important;color:#7799a0!important}
.empty,.err,.loading{background:#090d0f!important;color:#93aeb4!important;box-shadow:var(--shadow)!important;border:1px solid #121b1f!important}.spin{border-color:#131b20!important;border-top-color:#22e2ff!important}
.back{background:#0a0e10!important;color:#ecf1f2!important;border:1px solid #00ddff!important;box-shadow:none!important}
.scorehero{position:relative;background:
  radial-gradient(circle at 14% 52%,rgba(0,221,255,.24),transparent 30%),
  radial-gradient(circle at 86% 50%,rgba(36,226,255,.18),transparent 28%),
  linear-gradient(180deg,#0a0e10 0%,#080c0e 55%,#06090a 100%)!important;
  border:1px solid #00ddff!important;box-shadow:0 16px 38px rgba(0,0,0,.34)!important;overflow:hidden!important}
.scorehero:before{content:'';position:absolute;inset:0;pointer-events:none;background:
  linear-gradient(112deg,transparent 0 47%,rgba(0,221,255,.12) 48%,transparent 49%),
  linear-gradient(68deg,transparent 0 49%,rgba(38,226,255,.10) 50%,transparent 51%)}
.scoretop{position:relative;color:#a5bcc0!important;border-bottom:1px solid rgba(0,221,255,.22)!important;background:rgba(6,8,10,.38)!important}.scoremain,.report{position:relative}.scoremain{padding:24px 14px!important}.sname{color:#f3f6f6!important;font-size:15px!important}.sval{color:#fff!important;font-size:36px!important;text-shadow:0 0 20px rgba(15,223,255,.25)}.teamMark{width:52px!important;height:52px!important;font-size:13px!important}.vs{width:46px!important;height:46px!important;background:#090d0f!important;color:#fff!important;border:1px solid #00ddff!important;box-shadow:0 0 22px rgba(34,226,255,.22)}.report{background:rgba(4,6,7,.55)!important;border-top:1px solid rgba(0,221,255,.24)!important;color:#a5bcc1!important}
.chaseBox{background:linear-gradient(135deg,rgba(0,221,255,.32),rgba(15,22,26,.42))!important;border:1px solid #00ddff!important}.chaseBox b{color:#f1f4f5!important}.chaseBox span{color:#9fb8bd!important}
.quickMarket{background:linear-gradient(180deg,#0a0f11,#080b0d)!important;border:1px solid #00ddff!important;box-shadow:0 16px 34px rgba(0,0,0,.28)!important;padding:15px!important}.quickHead b{font-size:18px!important;color:#fff!important}.quickHead b:before{content:'▥ ';color:#20e1ff}.quickHead span{color:#35e4ff!important;letter-spacing:.6px}.quickOdds{gap:10px!important}.quickOdd{padding:14px!important;background:linear-gradient(135deg,#00ddff,#00ddff)!important;border:1px solid #1ce1ff!important;box-shadow:0 8px 18px rgba(0,221,255,.24)}.quickOdd:nth-child(2){background:linear-gradient(135deg,#0da15f,#161f24)!important;border-color:#36e798!important}.quickOdd small{color:#eaf0f1!important;font-size:11px!important}.quickOdd strong{color:#fff!important;font-size:27px!important;text-shadow:0 0 18px rgba(255,255,255,.12)}
.sessionTitle{color:#e1e9ea!important;font-size:12px!important;letter-spacing:.6px!important;margin-top:15px!important}.sessionTitle:before{content:'◴ ';color:#3fe99a}.sessionGrid{grid-template-columns:repeat(2,minmax(0,1fr));gap:9px!important}.sessionCard{background:linear-gradient(135deg,#00ddff,#131b1f)!important;border:1px solid #11dfff!important;padding:12px!important;box-shadow:0 7px 16px rgba(0,221,255,.18)}.sessionCard:nth-child(even){background:linear-gradient(135deg,#00ddff,#00ddff)!important;border-color:#5ce9ff!important}.sessionCard b{color:#fff!important;font-size:11px!important}.sessionVals{color:#b7c9cd!important}.sessionVals strong{color:#fff!important;font-size:13px!important}.quickLoading{color:#92aeb3!important}
.dtabs{gap:7px!important}.dtab{height:48px!important;background:#090d0f!important;border:1px solid #19242a!important;color:#97b1b6!important}.dtab.on{background:linear-gradient(135deg,#02ddff,#00ddff)!important;color:#fff!important;border-color:#55e8ff!important;box-shadow:0 0 20px rgba(41,226,255,.22)}
.panel{background:linear-gradient(180deg,#0a0e10,#080c0e)!important;border:1px solid #182329!important;box-shadow:0 14px 32px rgba(0,0,0,.25)!important}.ptitle b{color:#f3f6f6!important;font-size:16px!important}.notice{background:#0a0e10!important;color:#9bb4b9!important;border:1px solid #151f23!important}.metric{background:#0f1519!important;color:#69ebff!important;border:1px solid #00ddff!important}.metric b{color:#fff!important}.playerCard{background:#090e10!important;border:1px solid #162024!important}.playerRole{color:#7b9ca3!important}.playerName{color:#f1f5f6!important}.playerStat{color:#92aeb4!important}.ballChip{background:#182328!important;color:#eaf0f1!important}.ballChip.boundary{background:#00ddff!important;color:#fff!important}.ballChip.six{background:#1ce1ff!important;color:#fff!important}.ballChip.wicket{background:#cf334d!important;color:#fff!important}.ballChip.extra{background:#00ddff!important;color:#fff!important}
.inning{background:#090e10!important;border:1px solid #151f23!important}.inningTeam{color:#e6eced!important}.inningScore{color:#fff!important}.inningMeta{color:#80a0a7!important}.ball{background:#090e10!important;color:#b2c5c9!important;border:1px solid #121a1e!important}.moreItem{background:#0a0e10!important;border:1px solid #172127!important;color:#eaf0f1!important}.moreItem span{color:#779aa1!important}.kv{border-bottom-color:#11191d!important;color:#98b2b7!important}.kv b{color:#f1f5f6!important}
.bottom{background:rgba(6,8,10,.97)!important;border:1px solid #182228!important;box-shadow:0 14px 38px rgba(0,0,0,.5)!important}.bottom button{color:#8aa7ad!important}.bottom .on{background:linear-gradient(180deg,rgba(0,221,255,.55),rgba(16,23,26,.65))!important;color:#fff!important}.bottom button:nth-child(2) b{color:#ff526e!important;text-shadow:0 0 14px rgba(255,70,99,.42)}
@media(max-width:430px){.brand b{font-size:25px!important}.sval{font-size:33px!important}.teamMark{width:47px!important;height:47px!important}.quickOdd strong{font-size:24px!important}.sessionGrid{grid-template-columns:1fr}.quickHead b{font-size:16px!important}}
'''


def _page_v31() -> str:
    html = v30._page_v30()
    html = html.replace("tg.setHeaderColor('#0b1012');tg.setBackgroundColor('#f1f4f5')",
                        "tg.setHeaderColor('#070b0c');tg.setBackgroundColor('#040607')")
    html = html.replace('</style>', PREMIUM_CSS + '\n</style>', 1)
    return html


v30.v23._page = _page_v31
v30.v23.liveline._page = _page_v31


def _self_test() -> None:
    page = _page_v31()
    checks = {
        'premium_theme': 'IBETIN V31 premium dark/neon presentation layer' in page,
        'dark_background': '--bg:#040607' in page,
        'live_bhav': 'LIVE BHAV' in page,
        'session_markets': 'SESSION MARKETS' in page,
        'detail_tabs': "['match','MATCH']" in page and "['bhav','BHAV']" in page,
        'v30_backend_preserved': "action:'score'" in page and 'bhavCache' in page,
        'telegram_dark': "tg.setBackgroundColor('#040607')" in page,
        'no_fake_session_data': '148 - 150' not in page and '148–150' not in page,
    }
    ok = all(checks.values())
    (logger.info if ok else logger.error)(
        'IBETIN V31 premium UI self-test %s checks=%s',
        'PASS' if ok else 'FAILED', checks,
    )
    if not ok:
        raise RuntimeError(f'V31 premium UI self-test failed: {checks}')


_self_test()
logger.info('IBETIN V31 installed: premium colorful dark UI over stable V30/V25 data stack')

app = v30.app

if __name__ == '__main__':
    app.base.ibetin_start.main()
