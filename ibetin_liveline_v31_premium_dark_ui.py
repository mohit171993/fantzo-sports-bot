import logging

import ibetin_liveline_v30_unified_ui as v30

logger = logging.getLogger(__name__)

PREMIUM_CSS = r'''
/* IBETIN V31 premium dark/neon presentation layer. Data/API logic remains V30/V25. */
:root{
  --bg:#020a14;--navy:#031225;--blue:#1094ff;--gold:#ffd34d;--ink:#f6fbff;
  --muted:#8ea7c2;--card:#07182b;--live:#ff4f69;--green:#20d787;
  --shadow:0 14px 34px rgba(0,0,0,.34)
}
html,body{background:
  radial-gradient(circle at 15% 0%,rgba(12,111,235,.22),transparent 28%),
  radial-gradient(circle at 90% 10%,rgba(96,39,210,.18),transparent 25%),
  linear-gradient(180deg,#03101f 0%,#020914 38%,#020812 100%)!important;
  color:#f5f9ff!important}
body{min-height:100vh}
.shell{background:transparent}
.top{background:
  radial-gradient(circle at 72% 0%,rgba(20,116,255,.22),transparent 32%),
  linear-gradient(125deg,#031225,#05284f 72%,#063f75)!important;
  border-bottom:1px solid rgba(30,155,255,.26);box-shadow:0 10px 28px rgba(0,0,0,.28)!important}
.mark{display:none!important}
.brand{gap:0!important}.brand b{font-size:28px!important;letter-spacing:1.3px!important;color:#fff!important;text-shadow:0 2px 16px rgba(35,150,255,.15)}
.brand b::first-letter{color:#ffd43d}
.brand span{color:#a9c2dc!important;letter-spacing:2px!important;font-size:10px!important}
.liveDot{background:linear-gradient(180deg,rgba(16,166,98,.25),rgba(10,80,52,.3))!important;border:1px solid #31de8f!important;color:#dfffee!important;box-shadow:0 0 18px rgba(43,231,145,.28);padding:9px 14px!important}
.tabs{gap:10px!important}.tab{height:52px!important;background:rgba(12,45,79,.74)!important;color:#a9bdd3!important;border:1px solid rgba(112,170,224,.1)!important}.tab.on{background:linear-gradient(135deg,#0c61bf,#133d7b)!important;color:#fff!important;border-color:#1a8bf1!important;box-shadow:0 8px 22px rgba(12,118,235,.24)}
.main,.detail{background:transparent!important}
.search,.refresh{background:#08182a!important;border:1px solid #15395a!important;color:#dcecff!important;box-shadow:0 10px 24px rgba(0,0,0,.2)!important}.search::placeholder{color:#66829e!important}.refresh{color:#49b9ff!important}
.status{color:#7892ad!important}.league{color:#8bb8dd!important;text-transform:uppercase;letter-spacing:.45px}
.match{background:linear-gradient(180deg,#081b2f,#061425)!important;border:1px solid #12375a!important;border-left:3px solid #1b79d4!important;box-shadow:0 14px 30px rgba(0,0,0,.26)!important}.match.live{border-left-color:#ff4f69!important}.fmt{color:#7e9ab6!important}.badge{background:#0c2945!important;color:#8ab5d9!important}.badge.live{background:rgba(255,54,86,.14)!important;color:#ff6f84!important;border:1px solid rgba(255,77,105,.25)}
.miniMark,.teamMark{background:linear-gradient(145deg,#0c2c4c,#0b1f36)!important;color:#8dcaff!important;border:1px solid #235f92!important;box-shadow:inset 0 0 0 2px rgba(255,255,255,.02)}
.tn{color:#f3f8ff!important}.ta,.si{color:#6f8da8!important}.sc{color:#ffffff!important;text-shadow:0 0 18px rgba(26,151,255,.2)}
.oddsRow{background:#061527!important;border-top:1px solid #102f4d!important}.oddsTitle{color:#73a5d1!important}.oddBox{background:linear-gradient(135deg,#0b5fbd,#0b3671)!important;border:1px solid #168cff!important;box-shadow:0 6px 15px rgba(0,106,220,.18)}.oddBox:nth-child(3){background:linear-gradient(135deg,#0b9258,#08603f)!important;border-color:#29db8d!important}.oddLabel{color:#d9edff!important}.oddValue{color:#fff!important;font-size:15px!important}.foot{border-top:1px solid #102f4d!important;color:#6f8da8!important}
.empty,.err,.loading{background:#07182a!important;color:#8ca4bb!important;box-shadow:var(--shadow)!important;border:1px solid #15314d!important}.spin{border-color:#153451!important;border-top-color:#22a8ff!important}
.back{background:#071a2e!important;color:#dff1ff!important;border:1px solid #16466e!important;box-shadow:none!important}
.scorehero{position:relative;background:
  radial-gradient(circle at 14% 52%,rgba(0,126,255,.24),transparent 30%),
  radial-gradient(circle at 86% 50%,rgba(255,86,36,.18),transparent 28%),
  linear-gradient(180deg,#06192e 0%,#061527 55%,#04101e 100%)!important;
  border:1px solid #155187!important;box-shadow:0 16px 38px rgba(0,0,0,.34)!important;overflow:hidden!important}
.scorehero:before{content:'';position:absolute;inset:0;pointer-events:none;background:
  linear-gradient(112deg,transparent 0 47%,rgba(0,157,255,.12) 48%,transparent 49%),
  linear-gradient(68deg,transparent 0 49%,rgba(255,91,38,.10) 50%,transparent 51%)}
.scoretop{position:relative;color:#99b3cc!important;border-bottom:1px solid rgba(54,127,184,.22)!important;background:rgba(3,14,28,.38)!important}.scoremain,.report{position:relative}.scoremain{padding:24px 14px!important}.sname{color:#eaf5ff!important;font-size:15px!important}.sval{color:#fff!important;font-size:36px!important;text-shadow:0 0 20px rgba(15,151,255,.25)}.teamMark{width:52px!important;height:52px!important;font-size:13px!important}.vs{width:46px!important;height:46px!important;background:#06172b!important;color:#fff!important;border:1px solid #2b80c5!important;box-shadow:0 0 22px rgba(34,147,255,.22)}.report{background:rgba(2,11,21,.55)!important;border-top:1px solid rgba(42,117,177,.24)!important;color:#98b5ce!important}
.chaseBox{background:linear-gradient(135deg,rgba(4,87,162,.32),rgba(16,35,67,.42))!important;border:1px solid #1f6eaa!important}.chaseBox b{color:#e7f7ff!important}.chaseBox span{color:#8bb2d1!important}
.quickMarket{background:linear-gradient(180deg,#071b30,#061425)!important;border:1px solid #15588b!important;box-shadow:0 16px 34px rgba(0,0,0,.28)!important;padding:15px!important}.quickHead b{font-size:18px!important;color:#fff!important}.quickHead b:before{content:'▥ ';color:#20b9ff}.quickHead span{color:#35b9ff!important;letter-spacing:.6px}.quickOdds{gap:10px!important}.quickOdd{padding:14px!important;background:linear-gradient(135deg,#0c6bd8,#0a3b84)!important;border:1px solid #1ca6ff!important;box-shadow:0 8px 18px rgba(0,91,207,.24)}.quickOdd:nth-child(2){background:linear-gradient(135deg,#0da15f,#07623f)!important;border-color:#36e798!important}.quickOdd small{color:#dcefff!important;font-size:11px!important}.quickOdd strong{color:#fff!important;font-size:27px!important;text-shadow:0 0 18px rgba(255,255,255,.12)}
.sessionTitle{color:#d5e7f6!important;font-size:12px!important;letter-spacing:.6px!important;margin-top:15px!important}.sessionTitle:before{content:'◴ ';color:#3fe99a}.sessionGrid{grid-template-columns:repeat(2,minmax(0,1fr));gap:9px!important}.sessionCard{background:linear-gradient(135deg,#0b3f8a,#0b2659)!important;border:1px solid #287fe8!important;padding:12px!important;box-shadow:0 7px 16px rgba(0,74,180,.18)}.sessionCard:nth-child(even){background:linear-gradient(135deg,#5526a6,#2c1769)!important;border-color:#945cff!important}.sessionCard b{color:#fff!important;font-size:11px!important}.sessionVals{color:#a9c3db!important}.sessionVals strong{color:#fff!important;font-size:13px!important}.quickLoading{color:#86a4bf!important}
.dtabs{gap:7px!important}.dtab{height:48px!important;background:#07182b!important;border:1px solid #173e62!important;color:#8ca6c1!important}.dtab.on{background:linear-gradient(135deg,#0a82f7,#5a24d8)!important;color:#fff!important;border-color:#55b9ff!important;box-shadow:0 0 20px rgba(41,135,255,.22)}
.panel{background:linear-gradient(180deg,#071a2d,#061426)!important;border:1px solid #164260!important;box-shadow:0 14px 32px rgba(0,0,0,.25)!important}.ptitle b{color:#eaf6ff!important;font-size:16px!important}.notice{background:#081a2c!important;color:#91abc3!important;border:1px solid #153552!important}.metric{background:#0d2943!important;color:#8fb8d9!important;border:1px solid #17476e!important}.metric b{color:#fff!important}.playerCard{background:#08192b!important;border:1px solid #163754!important}.playerRole{color:#7190ad!important}.playerName{color:#e8f5ff!important}.playerStat{color:#87a5bf!important}.ballChip{background:#173b5e!important;color:#dcefff!important}.ballChip.boundary{background:#0b84ed!important;color:#fff!important}.ballChip.six{background:#7244d7!important;color:#fff!important}.ballChip.wicket{background:#cf334d!important;color:#fff!important}.ballChip.extra{background:#b78515!important;color:#fff!important}
.inning{background:#08192b!important;border:1px solid #153652!important}.inningTeam{color:#d9ebfa!important}.inningScore{color:#fff!important}.inningMeta{color:#7895af!important}.ball{background:#08192b!important;color:#a9bfd2!important;border:1px solid #12324e!important}.moreItem{background:#081a2c!important;border:1px solid #173a59!important;color:#dcecff!important}.moreItem span{color:#6f8ea9!important}.kv{border-bottom-color:#12314c!important;color:#90a9bf!important}.kv b{color:#e8f4ff!important}
.bottom{background:rgba(3,14,29,.97)!important;border:1px solid #123b61!important;box-shadow:0 14px 38px rgba(0,0,0,.5)!important}.bottom button{color:#809bb7!important}.bottom .on{background:linear-gradient(180deg,rgba(20,78,126,.55),rgba(12,43,74,.65))!important;color:#fff!important}.bottom button:nth-child(2) b{color:#ff526e!important;text-shadow:0 0 14px rgba(255,70,99,.42)}
@media(max-width:430px){.brand b{font-size:25px!important}.sval{font-size:33px!important}.teamMark{width:47px!important;height:47px!important}.quickOdd strong{font-size:24px!important}.sessionGrid{grid-template-columns:1fr}.quickHead b{font-size:16px!important}}
'''


def _page_v31() -> str:
    html = v30._page_v30()
    html = html.replace("tg.setHeaderColor('#071a34');tg.setBackgroundColor('#eef3f8')",
                        "tg.setHeaderColor('#031225');tg.setBackgroundColor('#020a14')")
    html = html.replace('</style>', PREMIUM_CSS + '\n</style>', 1)
    return html


v30.v23._page = _page_v31
v30.v23.liveline._page = _page_v31


def _self_test() -> None:
    page = _page_v31()
    checks = {
        'premium_theme': 'IBETIN V31 premium dark/neon presentation layer' in page,
        'dark_background': '--bg:#020a14' in page,
        'live_bhav': 'LIVE BHAV' in page,
        'session_markets': 'SESSION MARKETS' in page,
        'detail_tabs': "['match','MATCH']" in page and "['bhav','BHAV']" in page,
        'v30_backend_preserved': "action:'score'" in page and 'bhavCache' in page,
        'telegram_dark': "tg.setBackgroundColor('#020a14')" in page,
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
