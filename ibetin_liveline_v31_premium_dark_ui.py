import logging

import ibetin_liveline_v30_unified_ui as v30

logger = logging.getLogger(__name__)

PREMIUM_CSS = r'''
/* IBETIN V31 premium dark/neon presentation layer. Data/API logic remains V30/V25. */
:root{
  --bg:#030911;--navy:#050f1f;--blue:#1080ff;--gold:#4da0ff;--ink:#f6fbff;
  --muted:#92a4be;--card:#091424;--live:#ff4f69;--green:#20d787;
  --shadow:0 14px 34px rgba(0,0,0,.34)
}
html,body{background:
  radial-gradient(circle at 15% 0%,rgba(12,116,235,.22),transparent 28%),
  radial-gradient(circle at 90% 10%,rgba(39,119,210,.18),transparent 25%),
  linear-gradient(180deg,#050d1a 0%,#030911 38%,#03080f 100%)!important;
  color:#f5f9ff!important}
body{min-height:100vh}
.shell{background:transparent}
.top{background:
  radial-gradient(circle at 72% 0%,rgba(20,130,255,.22),transparent 32%),
  linear-gradient(125deg,#050f1f,#092042 72%,#063a75)!important;
  border-bottom:1px solid rgba(30,135,255,.26);box-shadow:0 10px 28px rgba(0,0,0,.28)!important}
.mark{display:none!important}
.brand{gap:0!important}.brand b{font-size:28px!important;letter-spacing:1.3px!important;color:#fff!important;text-shadow:0 2px 16px rgba(35,138,255,.15)}
.brand b::first-letter{color:#3d98ff}
.brand span{color:#adbed8!important;letter-spacing:2px!important;font-size:10px!important}
.liveDot{background:linear-gradient(180deg,rgba(16,166,98,.25),rgba(10,80,52,.3))!important;border:1px solid #31de8f!important;color:#dfffee!important;box-shadow:0 0 18px rgba(43,231,145,.28);padding:9px 14px!important}
.tabs{gap:10px!important}.tab{height:52px!important;background:rgba(15,36,67,.74)!important;color:#acbad0!important;border:1px solid rgba(112,164,224,.1)!important}.tab.on{background:linear-gradient(135deg,#0c60bf,#13447b)!important;color:#fff!important;border-color:#1a7ef1!important;box-shadow:0 8px 22px rgba(12,116,235,.24)}
.main,.detail{background:transparent!important}
.search,.refresh{background:#091424!important;border:1px solid #15355a!important;color:#dfebfc!important;box-shadow:0 10px 24px rgba(0,0,0,.2)!important}.search::placeholder{color:#6a7d9a!important}.refresh{color:#499eff!important}
.status{color:#7c8ea9!important}.league{color:#8bb1dd!important;text-transform:uppercase;letter-spacing:.45px}
.match{background:linear-gradient(180deg,#0a1628,#07111f)!important;border:1px solid #12345a!important;border-left:3px solid #1b71d4!important;box-shadow:0 14px 30px rgba(0,0,0,.26)!important}.match.live{border-left-color:#ff4f69!important}.fmt{color:#8295b2!important}.badge{background:#0f203a!important;color:#8aafd9!important}.badge.live{background:rgba(255,54,86,.14)!important;color:#ff6f84!important;border:1px solid rgba(255,77,105,.25)}
.miniMark,.teamMark{background:linear-gradient(145deg,#0f2340,#0d1a2e)!important;color:#8dc2ff!important;border:1px solid #235792!important;box-shadow:inset 0 0 0 2px rgba(255,255,255,.02)}
.tn{color:#f3f8ff!important}.ta,.si{color:#7387a4!important}.sc{color:#ffffff!important;text-shadow:0 0 18px rgba(26,133,255,.2)}
.oddsRow{background:#081221!important;border-top:1px solid #132541!important}.oddsTitle{color:#739fd1!important}.oddBox{background:linear-gradient(135deg,#0b5ebd,#0b3b71)!important;border:1px solid #1683ff!important;box-shadow:0 6px 15px rgba(0,103,220,.18)}.oddBox:nth-child(3){background:linear-gradient(135deg,#0b9258,#08603f)!important;border-color:#29db8d!important}.oddLabel{color:#dce9fc!important}.oddValue{color:#fff!important;font-size:15px!important}.foot{border-top:1px solid #132541!important;color:#7387a4!important}
.empty,.err,.loading{background:#091323!important;color:#90a0b7!important;box-shadow:var(--shadow)!important;border:1px solid #172842!important}.spin{border-color:#172945!important;border-top-color:#2289ff!important}
.back{background:#091527!important;color:#e1ecfd!important;border:1px solid #163f6e!important;box-shadow:none!important}
.scorehero{position:relative;background:
  radial-gradient(circle at 14% 52%,rgba(0,119,255,.24),transparent 30%),
  radial-gradient(circle at 86% 50%,rgba(36,138,255,.18),transparent 28%),
  linear-gradient(180deg,#081427 0%,#081221 55%,#050d19 100%)!important;
  border:1px solid #154a87!important;box-shadow:0 16px 38px rgba(0,0,0,.34)!important;overflow:hidden!important}
.scorehero:before{content:'';position:absolute;inset:0;pointer-events:none;background:
  linear-gradient(112deg,transparent 0 47%,rgba(0,119,255,.12) 48%,transparent 49%),
  linear-gradient(68deg,transparent 0 49%,rgba(38,139,255,.10) 50%,transparent 51%)}
.scoretop{position:relative;color:#9daec8!important;border-bottom:1px solid rgba(54,115,184,.22)!important;background:rgba(4,12,24,.38)!important}.scoremain,.report{position:relative}.scoremain{padding:24px 14px!important}.sname{color:#ecf3fd!important;font-size:15px!important}.sval{color:#fff!important;font-size:36px!important;text-shadow:0 0 20px rgba(15,127,255,.25)}.teamMark{width:52px!important;height:52px!important;font-size:13px!important}.vs{width:46px!important;height:46px!important;background:#081324!important;color:#fff!important;border:1px solid #2b73c5!important;box-shadow:0 0 22px rgba(34,137,255,.22)}.report{background:rgba(3,9,18,.55)!important;border-top:1px solid rgba(42,105,177,.24)!important;color:#9caeca!important}
.chaseBox{background:linear-gradient(135deg,rgba(4,78,162,.32),rgba(18,33,57,.42))!important;border:1px solid #1f60aa!important}.chaseBox b{color:#e9f1fd!important}.chaseBox span{color:#90a8cc!important}
.quickMarket{background:linear-gradient(180deg,#091628,#07111f)!important;border:1px solid #154c8b!important;box-shadow:0 16px 34px rgba(0,0,0,.28)!important;padding:15px!important}.quickHead b{font-size:18px!important;color:#fff!important}.quickHead b:before{content:'▥ ';color:#2088ff}.quickHead span{color:#3593ff!important;letter-spacing:.6px}.quickOdds{gap:10px!important}.quickOdd{padding:14px!important;background:linear-gradient(135deg,#0c6bd8,#0a4384)!important;border:1px solid #1c86ff!important;box-shadow:0 8px 18px rgba(0,97,207,.24)}.quickOdd:nth-child(2){background:linear-gradient(135deg,#0da15f,#07623f)!important;border-color:#36e798!important}.quickOdd small{color:#dfebfc!important;font-size:11px!important}.quickOdd strong{color:#fff!important;font-size:27px!important;text-shadow:0 0 18px rgba(255,255,255,.12)}
.sessionTitle{color:#d7e3f4!important;font-size:12px!important;letter-spacing:.6px!important;margin-top:15px!important}.sessionTitle:before{content:'◴ ';color:#3fe99a}.sessionGrid{grid-template-columns:repeat(2,minmax(0,1fr));gap:9px!important}.sessionCard{background:linear-gradient(135deg,#0b468a,#0f274b)!important;border:1px solid #2882e8!important;padding:12px!important;box-shadow:0 7px 16px rgba(0,84,180,.18)}.sessionCard:nth-child(even){background:linear-gradient(135deg,#2662a6,#173d69)!important;border-color:#5ca8ff!important}.sessionCard b{color:#fff!important;font-size:11px!important}.sessionVals{color:#adbed7!important}.sessionVals strong{color:#fff!important;font-size:13px!important}.quickLoading{color:#8a9ebb!important}
.dtabs{gap:7px!important}.dtab{height:48px!important;background:#091424!important;border:1px solid #173a62!important;color:#90a2bd!important}.dtab.on{background:linear-gradient(135deg,#0a79f7,#2478d8)!important;color:#fff!important;border-color:#55a4ff!important;box-shadow:0 0 20px rgba(41,141,255,.22)}
.panel{background:linear-gradient(180deg,#091426,#081120)!important;border:1px solid #163960!important;box-shadow:0 14px 32px rgba(0,0,0,.25)!important}.ptitle b{color:#ecf3fd!important;font-size:16px!important}.notice{background:#0a1525!important;color:#95a6bf!important;border:1px solid #153152!important}.metric{background:#0f2039!important;color:#8fb2d9!important;border:1px solid #17406e!important}.metric b{color:#fff!important}.playerCard{background:#0a1424!important;border:1px solid #163354!important}.playerRole{color:#768aa8!important}.playerName{color:#eaf2fd!important}.playerStat{color:#8b9ebb!important}.ballChip{background:#17385e!important;color:#dfebfc!important}.ballChip.boundary{background:#0b74ed!important;color:#fff!important}.ballChip.six{background:#4489d7!important;color:#fff!important}.ballChip.wicket{background:#cf334d!important;color:#fff!important}.ballChip.extra{background:#1461b8!important;color:#fff!important}
.inning{background:#0a1424!important;border:1px solid #153152!important}.inningTeam{color:#dbe7f8!important}.inningScore{color:#fff!important}.inningMeta{color:#7c8fab!important}.ball{background:#0a1424!important;color:#acbacf!important;border:1px solid #142742!important}.moreItem{background:#0a1525!important;border:1px solid #173659!important;color:#dfebfc!important}.moreItem span{color:#7387a5!important}.kv{border-bottom-color:#142640!important;color:#94a4bb!important}.kv b{color:#eaf2fd!important}
.bottom{background:rgba(4,12,24,.97)!important;border:1px solid #123761!important;box-shadow:0 14px 38px rgba(0,0,0,.5)!important}.bottom button{color:#8497b3!important}.bottom .on{background:linear-gradient(180deg,rgba(20,69,126,.55),rgba(15,34,62,.65))!important;color:#fff!important}.bottom button:nth-child(2) b{color:#ff526e!important;text-shadow:0 0 14px rgba(255,70,99,.42)}
@media(max-width:430px){.brand b{font-size:25px!important}.sval{font-size:33px!important}.teamMark{width:47px!important;height:47px!important}.quickOdd strong{font-size:24px!important}.sessionGrid{grid-template-columns:1fr}.quickHead b{font-size:16px!important}}
'''


def _page_v31() -> str:
    html = v30._page_v30()
    html = html.replace("tg.setHeaderColor('#09172c');tg.setBackgroundColor('#eff2f7')",
                        "tg.setHeaderColor('#050f1f');tg.setBackgroundColor('#030911')")
    html = html.replace('</style>', PREMIUM_CSS + '\n</style>', 1)
    return html


v30.v23._page = _page_v31
v30.v23.liveline._page = _page_v31


def _self_test() -> None:
    page = _page_v31()
    checks = {
        'premium_theme': 'IBETIN V31 premium dark/neon presentation layer' in page,
        'dark_background': '--bg:#030911' in page,
        'live_bhav': 'LIVE BHAV' in page,
        'session_markets': 'SESSION MARKETS' in page,
        'detail_tabs': "['match','MATCH']" in page and "['bhav','BHAV']" in page,
        'v30_backend_preserved': "action:'score'" in page and 'bhavCache' in page,
        'telegram_dark': "tg.setBackgroundColor('#030911')" in page,
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
