import logging

import ibetin_liveline_v30_unified_ui as v30

logger = logging.getLogger(__name__)

PREMIUM_CSS = r'''
/* IBETIN V31 premium dark/neon presentation layer. Data/API logic remains V30/V25. */
:root{
  --bg:#0a0908;--navy:#13110f;--blue:#e52a34;--gold:#ffd34d;--ink:#f6fbff;
  --muted:#aba8a5;--card:#171513;--live:#ff4f69;--green:#20d787;
  --shadow:0 14px 34px rgba(0,0,0,.34)
}
html,body{background:
  radial-gradient(circle at 15% 0%,rgba(220,27,37,.22),transparent 28%),
  radial-gradient(circle at 90% 10%,rgba(210,153,39,.18),transparent 25%),
  linear-gradient(180deg,#100e0d 0%,#0a0908 38%,#090808 100%)!important;
  color:#f5f9ff!important}
body{min-height:100vh}
.shell{background:transparent}
.top{background:
  radial-gradient(circle at 72% 0%,rgba(229,46,55,.22),transparent 32%),
  linear-gradient(125deg,#13110f,#272420 72%,#6d0e12)!important;
  border-bottom:1px solid rgba(230,55,64,.26);box-shadow:0 10px 28px rgba(0,0,0,.28)!important}
.mark{display:none!important}
.brand{gap:0!important}.brand b{font-size:28px!important;letter-spacing:1.3px!important;color:#fff!important;text-shadow:0 2px 16px rgba(231,59,68,.15)}
.brand b::first-letter{color:#ffd43d}
.brand span{color:#c6c2bf!important;letter-spacing:2px!important;font-size:10px!important}
.liveDot{background:linear-gradient(180deg,rgba(16,166,98,.25),rgba(10,80,52,.3))!important;border:1px solid #31de8f!important;color:#dfffee!important;box-shadow:0 0 18px rgba(43,231,145,.28);padding:9px 14px!important}
.tabs{gap:10px!important}.tab{height:52px!important;background:rgba(42,39,35,.74)!important;color:#c1bebb!important;border:1px solid rgba(224,112,118,.1)!important}.tab.on{background:linear-gradient(135deg,#b5161e,#7b1318)!important;color:#fff!important;border-color:#e42730!important;box-shadow:0 8px 22px rgba(220,27,37,.24)}
.main,.detail{background:transparent!important}
.search,.refresh{background:#171514!important;border:1px solid #5a1518!important;color:#f0eeeb!important;box-shadow:0 10px 24px rgba(0,0,0,.2)!important}.search::placeholder{color:#85827f!important}.refresh{color:#eb5d64!important}
.status{color:#96928f!important}.league{color:#dd8b8f!important;text-transform:uppercase;letter-spacing:.45px}
.match{background:linear-gradient(180deg,#191715,#141211)!important;border:1px solid #5a1216!important;border-left:3px solid #d41b24!important;box-shadow:0 14px 30px rgba(0,0,0,.26)!important}.match.live{border-left-color:#ff4f69!important}.fmt{color:#9d9a97!important}.badge{background:#252220!important;color:#d98a8e!important}.badge.live{background:rgba(255,54,86,.14)!important;color:#ff6f84!important;border:1px solid rgba(255,77,105,.25)}
.miniMark,.teamMark{background:linear-gradient(145deg,#292522,#1e1c19)!important;color:#f29a9e!important;border:1px solid #922329!important;box-shadow:inset 0 0 0 2px rgba(255,255,255,.02)}
.tn{color:#f3f8ff!important}.ta,.si{color:#8f8c88!important}.sc{color:#ffffff!important;text-shadow:0 0 18px rgba(230,51,60,.2)}
.oddsRow{background:#151311!important;border-top:1px solid #2b2824!important}.oddsTitle{color:#d17378!important}.oddBox{background:linear-gradient(135deg,#b2161e,#6e0e12)!important;border:1px solid #e53039!important;box-shadow:0 6px 15px rgba(196,24,33,.18)}.oddBox:nth-child(3){background:linear-gradient(135deg,#0b9258,#08603f)!important;border-color:#29db8d!important}.oddLabel{color:#eeecea!important}.oddValue{color:#fff!important;font-size:15px!important}.foot{border-top:1px solid #2b2824!important;color:#8f8c88!important}
.empty,.err,.loading{background:#171513!important;color:#a6a3a1!important;box-shadow:var(--shadow)!important;border:1px solid #2d2a27!important}.spin{border-color:#2e2b28!important;border-top-color:#e73a43!important}
.back{background:#191715!important;color:#f1efed!important;border:1px solid #6e161a!important;box-shadow:none!important}
.scorehero{position:relative;background:
  radial-gradient(circle at 14% 52%,rgba(227,28,38,.24),transparent 30%),
  radial-gradient(circle at 86% 50%,rgba(255,86,36,.18),transparent 28%),
  linear-gradient(180deg,#181614 0%,#151311 55%,#100e0d 100%)!important;
  border:1px solid #87151b!important;box-shadow:0 16px 38px rgba(0,0,0,.34)!important;overflow:hidden!important}
.scorehero:before{content:'';position:absolute;inset:0;pointer-events:none;background:
  linear-gradient(112deg,transparent 0 47%,rgba(227,28,38,.12) 48%,transparent 49%),
  linear-gradient(68deg,transparent 0 49%,rgba(255,91,38,.10) 50%,transparent 51%)}
.scoretop{position:relative;color:#b6b2af!important;border-bottom:1px solid rgba(184,54,60,.22)!important;background:rgba(14,13,12,.38)!important}.scoremain,.report{position:relative}.scoremain{padding:24px 14px!important}.sname{color:#f6f4f3!important;font-size:15px!important}.sval{color:#fff!important;font-size:36px!important;text-shadow:0 0 20px rgba(229,41,51,.25)}.teamMark{width:52px!important;height:52px!important;font-size:13px!important}.vs{width:46px!important;height:46px!important;background:#171513!important;color:#fff!important;border:1px solid #c52b33!important;box-shadow:0 0 22px rgba(231,58,67,.22)}.report{background:rgba(11,10,9,.55)!important;border-top:1px solid rgba(177,42,49,.24)!important;color:#b6b3b0!important}
.chaseBox{background:linear-gradient(135deg,rgba(148,18,25,.32),rgba(38,35,33,.42))!important;border:1px solid #aa1f26!important}.chaseBox b{color:#f4f3f2!important}.chaseBox span{color:#b2aeaa!important}
.quickMarket{background:linear-gradient(180deg,#191715,#141211)!important;border:1px solid #8b151b!important;box-shadow:0 16px 34px rgba(0,0,0,.28)!important;padding:15px!important}.quickHead b{font-size:18px!important;color:#fff!important}.quickHead b:before{content:'▥ ';color:#e63941}.quickHead span{color:#e94b53!important;letter-spacing:.6px}.quickOdds{gap:10px!important}.quickOdd{padding:14px!important;background:linear-gradient(135deg,#cb1922,#7e1015)!important;border:1px solid #e6353e!important;box-shadow:0 8px 18px rgba(184,23,31,.24)}.quickOdd:nth-child(2){background:linear-gradient(135deg,#0da15f,#07623f)!important;border-color:#36e798!important}.quickOdd small{color:#f0eeeb!important;font-size:11px!important}.quickOdd strong{color:#fff!important;font-size:27px!important;text-shadow:0 0 18px rgba(255,255,255,.12)}
.sessionTitle{color:#e7e6e4!important;font-size:12px!important;letter-spacing:.6px!important;margin-top:15px!important}.sessionTitle:before{content:'◴ ';color:#3fe99a}.sessionGrid{grid-template-columns:repeat(2,minmax(0,1fr));gap:9px!important}.sessionCard{background:linear-gradient(135deg,#851016,#2e2a27)!important;border:1px solid #e52b34!important;padding:12px!important;box-shadow:0 7px 16px rgba(160,20,27,.18)}.sessionCard:nth-child(even){background:linear-gradient(135deg,#bb8b2b,#bc8b29)!important;border-color:#ebc270!important}.sessionCard b{color:#fff!important;font-size:11px!important}.sessionVals{color:#c5c2bf!important}.sessionVals strong{color:#fff!important;font-size:13px!important}.quickLoading{color:#a6a29f!important}
.dtabs{gap:7px!important}.dtab{height:48px!important;background:#171513!important;border:1px solid #62171b!important;color:#aaa6a3!important}.dtab.on{background:linear-gradient(135deg,#e31e28,#d89c24)!important;color:#fff!important;border-color:#ec686e!important;box-shadow:0 0 20px rgba(231,65,73,.22)}
.panel{background:linear-gradient(180deg,#181614,#141311)!important;border:1px solid #60161a!important;box-shadow:0 14px 32px rgba(0,0,0,.25)!important}.ptitle b{color:#f6f4f3!important;font-size:16px!important}.notice{background:#181614!important;color:#adaaa7!important;border:1px solid #521518!important}.metric{background:#25221f!important;color:#d98f93!important;border:1px solid #6e171b!important}.metric b{color:#fff!important}.playerCard{background:#171614!important;border:1px solid #541619!important}.playerRole{color:#938f8b!important}.playerName{color:#f5f3f2!important}.playerStat{color:#a6a3a0!important}.ballChip{background:#5e171b!important;color:#f0eeeb!important}.ballChip.boundary{background:#dd1b25!important;color:#fff!important}.ballChip.six{background:#d7a644!important;color:#fff!important}.ballChip.wicket{background:#cf334d!important;color:#fff!important}.ballChip.extra{background:#b78515!important;color:#fff!important}
.inning{background:#171614!important;border:1px solid #521518!important}.inningTeam{color:#ebeae8!important}.inningScore{color:#fff!important}.inningMeta{color:#979390!important}.ball{background:#171614!important;color:#c0bebb!important;border:1px solid #2c2926!important}.moreItem{background:#181614!important;border:1px solid #59171a!important;color:#f0eeeb!important}.moreItem span{color:#8f8c89!important}.kv{border-bottom-color:#2b2825!important;color:#aaa8a5!important}.kv b{color:#f5f3f2!important}
.bottom{background:rgba(15,14,12,.97)!important;border:1px solid #611216!important;box-shadow:0 14px 38px rgba(0,0,0,.5)!important}.bottom button{color:#9f9c98!important}.bottom .on{background:linear-gradient(180deg,rgba(126,20,25,.55),rgba(40,37,33,.65))!important;color:#fff!important}.bottom button:nth-child(2) b{color:#ff526e!important;text-shadow:0 0 14px rgba(255,70,99,.42)}
@media(max-width:430px){.brand b{font-size:25px!important}.sval{font-size:33px!important}.teamMark{width:47px!important;height:47px!important}.quickOdd strong{font-size:24px!important}.sessionGrid{grid-template-columns:1fr}.quickHead b{font-size:16px!important}}
'''


def _page_v31() -> str:
    html = v30._page_v30()
    html = html.replace("tg.setHeaderColor('#1b1917');tg.setBackgroundColor('#f4f3f2')",
                        "tg.setHeaderColor('#13110f');tg.setBackgroundColor('#0a0908')")
    html = html.replace('</style>', PREMIUM_CSS + '\n</style>', 1)
    return html


v30.v23._page = _page_v31
v30.v23.liveline._page = _page_v31


def _self_test() -> None:
    page = _page_v31()
    checks = {
        'premium_theme': 'IBETIN V31 premium dark/neon presentation layer' in page,
        'dark_background': '--bg:#0a0908' in page,
        'live_bhav': 'LIVE BHAV' in page,
        'session_markets': 'SESSION MARKETS' in page,
        'detail_tabs': "['match','MATCH']" in page and "['bhav','BHAV']" in page,
        'v30_backend_preserved': "action:'score'" in page and 'bhavCache' in page,
        'telegram_dark': "tg.setBackgroundColor('#0a0908')" in page,
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
