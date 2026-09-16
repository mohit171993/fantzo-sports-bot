import os
from urllib.parse import urlencode

import ibetin_liveline_trial as liveline

# Test-only V9 route. A new route prevents Telegram WebView from reusing an older preview.
liveline.LIVELINE_PATH = "/admin/liveline-ibetinv9"
liveline.LIVELINE_API_PATH = "/admin/liveline-ibetinv9/api"

import ibetin_light_start as light


def _ibetin_admin_url() -> str:
    root = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/") or "https://ibetin-app-production.up.railway.app"
    return f"{root}{liveline.LIVELINE_PATH}?{urlencode({'t': liveline._token(), 'v': '20260916-v9-premium-test'})}"


def _ibetin_page() -> str:
    html = light._light_page()
    html = html.replace("/admin/liveline/api", liveline.LIVELINE_API_PATH)

    # Small markup upgrades while keeping all existing JS/data bindings intact.
    html = html.replace(
        '<div class="brandLeft"><div class="brandMark">I</div><div class="brandText"><b>IBETIN</b><span>Cricket Live Line</span></div></div>',
        '<div class="brandLeft"><div class="brandMark">I</div><div class="brandText"><b>IBETIN</b><span>CRICKET · LIVE LINE</span></div></div>'
    )
    html = html.replace(
        '<div class="liveChip"><span class="pulseDot"></span> LIVE CENTER</div>',
        '<div class="liveChip"><span class="pulseDot"></span><span>TEST MODE</span></div>'
    )

    css = r'''
/* =========================================================
   IBETIN LIVE LINE V9 — TEST MODE
   Premium royal-blue + gold sportsbook identity
   ========================================================= */
:root{
  --bg:#edf2f8!important;
  --card:#ffffff!important;
  --ink:#17365f!important;
  --muted:#71839a!important;
  --line:#c7d5e5!important;
  --red:#e33a50!important;
  --red2:#ef5366!important;
  --redSoft:#fff1f3!important;
  --green:#17865f!important;
  --blue:#0a4da2!important;
  --gold:#ffc62d!important;
  --gold2:#ffda69!important;
  --navy:#07336f!important;
  --navy2:#0b4a99!important;
  --ice:#eef6ff!important;
  --shadow:0 4px 14px rgba(7,51,111,.09)!important;
  --shadow2:0 9px 24px rgba(7,51,111,.13)!important;
}
html,body{background:var(--bg)!important;color:var(--ink)!important}
body{padding-bottom:78px!important}

/* Header */
.topShell{
  background:linear-gradient(135deg,#062e67 0%,#0a4da2 62%,#0d5ab8 100%)!important;
  box-shadow:0 5px 18px rgba(5,43,96,.22)!important;
  border-bottom:3px solid var(--gold)!important;
}
.brandRow{height:64px!important;padding:0 13px!important;color:#fff!important}
.brandMark{
  width:38px!important;height:38px!important;border-radius:11px!important;
  background:linear-gradient(145deg,var(--gold2),var(--gold))!important;
  color:#17365f!important;font-size:20px!important;
  box-shadow:0 4px 12px rgba(0,0,0,.18)!important;
}
.brandText b{font-size:19px!important;color:#fff!important;letter-spacing:.7px!important}
.brandText span{font-size:8px!important;color:#cde1ff!important;opacity:1!important;letter-spacing:1px!important}
.liveChip{
  background:rgba(0,0,0,.12)!important;border:1px solid rgba(255,255,255,.24)!important;
  color:#fff!important;padding:7px 9px!important;font-size:8px!important;letter-spacing:.5px!important;
  box-shadow:inset 0 0 0 1px rgba(255,255,255,.04)!important
}
.pulseDot{background:var(--gold)!important;box-shadow:0 0 0 0 rgba(255,198,45,.65)!important}
@keyframes pulse{70%{box-shadow:0 0 0 7px rgba(255,198,45,0)}100%{box-shadow:0 0 0 0 rgba(255,198,45,0)}}

/* Main LIVE / UPCOMING / RESULTS */
.navCard{background:#082f68!important}
.navTabs{padding:6px 8px 7px!important;gap:6px!important}
.tab{
  background:rgba(255,255,255,.07)!important;color:#c8dcf7!important;
  border-radius:9px!important;padding:10px 4px!important;font-size:10px!important;
  border:1px solid rgba(255,255,255,.08)!important
}
.tab.active{
  background:linear-gradient(180deg,#ffd761,#ffc62d)!important;
  color:#17365f!important;border-color:#ffc62d!important;
  box-shadow:0 3px 8px rgba(255,198,45,.24)!important
}
.tab.active:after{display:none!important}

/* Page body */
.content,.detailWrap{padding:11px 10px 13px!important}
.sectionTitle{margin:2px 1px 10px!important;align-items:flex-end!important}
.sectionTitle b{font-size:14px!important;color:#163b70!important}
.status{font-size:8px!important;color:#7d8da1!important;margin-top:3px!important}
.refreshBtn{
  background:#fff!important;border-color:#c6d6e8!important;color:#0b4d9e!important;
  padding:7px 10px!important;font-weight:950!important;box-shadow:none!important
}

/* Match cards */
.list{gap:10px!important}
.match{
  border:1px solid #bdd0e5!important;border-radius:13px!important;
  box-shadow:0 4px 12px rgba(7,51,111,.08)!important;background:#fff!important;
  overflow:hidden!important
}
.match.liveCard:before{width:4px!important;background:var(--gold)!important}
.match:active{transform:scale(.994)!important}
.matchHead{
  background:linear-gradient(180deg,#0c4c99,#0a4289)!important;
  border-bottom:0!important;padding:9px 11px!important
}
.league{color:#fff!important;font-size:10px!important;letter-spacing:.05px!important}
.format{color:#c8ddf6!important;font-size:8px!important}
.badgeLive{
  background:#e63d53!important;color:#fff!important;border:1px solid rgba(255,255,255,.22)!important;
  box-shadow:0 2px 6px rgba(150,0,30,.18)!important
}
.badgeState{background:#f5f8fc!important;color:#416384!important;border:1px solid #d5e0ec!important}
.badgeResult{background:#e9f8f2!important;color:#167457!important;border-color:#ccebdd!important}
.matchBody{background:#fff!important;padding:8px 11px 7px!important}
.team{min-height:47px!important}
.teamBadge{
  width:37px!important;height:37px!important;border-radius:10px!important;
  background:#f4f8fd!important;border:1px solid #c5d5e7!important;color:#17457f!important;
  box-shadow:0 1px 4px rgba(7,51,111,.05)!important
}
.teamname{font-size:13px!important;color:#18395f!important}
.abbr{color:#8293a8!important}
.score{font-size:18px!important;color:#073f91!important;letter-spacing:-.25px!important}
.info{color:#8798ac!important}
.divider{background:#edf1f6!important;margin:0 47px!important}
.matchFoot{
  background:linear-gradient(90deg,#f5f9ff,#fffaf0)!important;
  border-top:1px solid #d7e2ee!important;padding:9px 11px!important
}
.report{color:#577089!important;font-weight:800!important}
.arrow{background:var(--gold)!important;color:#17365f!important;width:24px!important;height:24px!important}

/* Empty/loading */
.empty,.error{background:#fff!important;border:1px solid #c5d5e7!important;border-radius:13px!important;color:#687e97!important;box-shadow:var(--shadow)!important}
.spin{border-color:#d7e3ef!important;border-top-color:var(--gold)!important}

/* Match detail header */
.back{
  background:#073f91!important;color:#fff!important;border-color:#073f91!important;
  border-radius:9px!important;box-shadow:0 2px 7px rgba(7,63,145,.15)!important
}
.miniLive{background:#fff1f3!important;color:#d92f47!important;border-color:#ffd1d7!important}
.scoreHero{
  background:#fff!important;border:1px solid #bdd0e5!important;border-radius:15px!important;
  box-shadow:var(--shadow2)!important
}
.scoreTop{
  background:linear-gradient(180deg,#0c4c99,#073f91)!important;
  border-bottom:0!important;padding:10px 12px!important
}
.detailLeague{color:#fff!important;font-size:9px!important}
.matchState{color:#ffd65b!important}
.scoreMain{
  background:linear-gradient(180deg,#ffffff 0%,#f7fbff 100%)!important;
  padding:17px 9px 14px!important
}
.heroLogo{
  width:52px!important;height:52px!important;border-radius:12px!important;
  background:#fff!important;border:1px solid #c5d5e7!important;
  box-shadow:0 3px 9px rgba(7,51,111,.08)!important
}
.heroName{color:#17375f!important}
.heroScore{font-size:20px!important;color:#073f91!important}
.heroInfo{color:#8293a7!important}
.vsCircle{background:linear-gradient(145deg,#ffdb69,#ffc62d)!important;color:#17365f!important;font-weight:1000!important}
.resultStrip{
  background:linear-gradient(90deg,#fff8df,#fffdf7)!important;
  border-top:1px solid #f2dda1!important;color:#5f5435!important;padding:10px 12px!important
}

/* Detail tabs */
.detailTabs{
  background:#dfeafb!important;border:1px solid #c3d3e6!important;border-radius:11px!important;
  padding:4px!important;gap:4px!important;margin-bottom:9px!important
}
.detailTab{
  background:transparent!important;border:0!important;color:#315b8d!important;
  border-radius:8px!important;padding:8px 10px!important;box-shadow:none!important
}
.detailTab.active{
  background:linear-gradient(180deg,#ffd761,#ffc62d)!important;
  color:#17365f!important;border:0!important;box-shadow:0 2px 6px rgba(255,198,45,.22)!important
}

/* Content panels */
.panel{
  background:#fff!important;border:1px solid #c3d3e6!important;border-radius:13px!important;
  box-shadow:0 4px 12px rgba(7,51,111,.07)!important
}
.panelTitle{background:#e4eefb!important;border-bottom:1px solid #c7d6e8!important}
.panelTitle b{color:#0b428d!important;font-size:11px!important}
.sourceTag{background:#073f91!important;color:#fff!important}
.liveSummary{background:linear-gradient(120deg,#eef6ff,#fffaf0)!important}
.liveStatus{color:#153a6c!important}.liveReport{color:#617891!important}.subLabel{color:#7188a0!important}
.livegrid{gap:8px!important}
.mini{
  background:#f5f9fe!important;border:1px solid #d1deec!important;border-radius:10px!important;
  box-shadow:0 1px 4px rgba(7,51,111,.04)!important
}
.mini b{color:#17375f!important}.mini span{color:#71859b!important}
.overStrip{padding-top:1px!important}
.ballPill{background:#eaf2fc!important;color:#315c8c!important;border-color:#cbd9e9!important}
.ballPill.boundary{background:#fff4c9!important;color:#755500!important;border-color:#ffe080!important}
.ballPill.wicket{background:#fff0f2!important;color:#d92f47!important;border-color:#ffd0d6!important}
.ballNo{background:#073f91!important;color:#fff!important;border-radius:7px!important}
.ballText{color:#526b86!important}.ballText strong{color:#17355f!important}
.notice{color:#536d88!important;border-bottom-color:#dfe7f0!important}.notice b{color:#17355f!important}

/* Scorecard / stats */
.innings{border-top-color:#edf2f8!important}
.innTitle{background:#e4eefb!important;border-bottom-color:#c7d6e8!important;color:#0b428d!important}
.table th{background:#f1f6fc!important;color:#46698f!important}
.table td{border-bottom-color:#e0e8f1!important}.table td:first-child{color:#17355f!important}
.pill{background:#fff7d9!important;border-color:#ffe08a!important;color:#6e520c!important}

/* Bottom navigation */
.bottom{
  background:#062f69!important;border-top:3px solid var(--gold)!important;
  box-shadow:0 -4px 16px rgba(5,48,110,.20)!important
}
.bottomInner{height:66px!important}
.bottomItem{background:#062f69!important;color:#c5d8f2!important}
.bottomItem .ico{color:#fff!important}
.bottomItem.active{
  background:linear-gradient(180deg,#ffd65d,#ffc62d)!important;color:#17365f!important;
  margin:6px 4px!important;border-radius:10px!important
}
.bottomItem.active .ico{color:#17365f!important}

@media(min-width:600px){.match{min-height:186px!important}}
'''

    html = html.replace("</style>", css + "\n</style>", 1)
    html = html.replace("tg.setHeaderColor('#c71025')", "tg.setHeaderColor('#062f69')")
    html = html.replace("tg.setHeaderColor('#d7192d')", "tg.setHeaderColor('#062f69')")
    html = html.replace("tg.setBackgroundColor('#f2f3f5')", "tg.setBackgroundColor('#edf2f8')")
    return html


liveline.admin_url = _ibetin_admin_url
liveline._page = _ibetin_page

# Importing light installed the existing private /liveline command and data API.
# This remains test/admin preview only; no public menu changes are made here.
app = light.app

if __name__ == "__main__":
    app.base.ibetin_start.main()
