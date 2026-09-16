import os
from urllib.parse import urlencode

import ibetin_liveline_trial as liveline

# Use a brand-new WebApp path so Telegram cannot reuse the earlier Live Line page.
liveline.LIVELINE_PATH = "/admin/liveline-ibetin-v7"
liveline.LIVELINE_API_PATH = "/admin/liveline-ibetin-v7/api"

import ibetin_exact_theme_start as exact


def _site_admin_url() -> str:
    root = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/") or "https://ibetin-app-production.up.railway.app"
    return f"{root}{liveline.LIVELINE_PATH}?{urlencode({'t': liveline._token(), 'v': '20260916-v7-site-blue-gold'})}"


def _site_page() -> str:
    html = exact._exact_page()
    html = html.replace("/admin/liveline/api", liveline.LIVELINE_API_PATH)
    brand_css = r'''
/* IBETIN website visual identity: royal blue + gold + clean sportsbook surfaces */
:root{
  --bg:#edf2f7!important;
  --ink:#10316b!important;
  --muted:#6e7f96!important;
  --muted2:#8392a6!important;
  --line:#cbd8e8!important;
  --soft:#f4f8fd!important;
  --blue:#073f91!important;
  --red:#e53b4f!important;
  --green:#16865c!important;
  --gold:#ffbe20!important;
  --gold2:#ffd15a!important;
  --navy:#073775!important;
}
html,body{background:#edf2f7!important;color:#15263f!important}
.wrap{padding-top:0!important}
.top{
  margin:0 -14px 14px!important;
  padding:15px 14px!important;
  min-height:62px!important;
  background:linear-gradient(180deg,#0a438f 0%,#073775 100%)!important;
  color:#fff!important;
  box-shadow:0 3px 10px rgba(5,48,110,.20)!important;
}
.brand{color:#fff!important;font-size:21px!important;letter-spacing:1.1px!important}
.pill{background:var(--gold)!important;border-color:var(--gold)!important;color:#173461!important;font-weight:950!important;box-shadow:0 2px 5px rgba(0,0,0,.12)!important}
.hero{
  background:linear-gradient(135deg,#0a438f 0%,#0b55b5 100%)!important;
  border:0!important;color:#fff!important;border-radius:16px!important;
  box-shadow:0 5px 16px rgba(7,63,145,.18)!important
}
.hero .eyebrow{color:#b9d3ff!important}.hero h1{color:#fff!important}.hero p{color:#d9e8ff!important}
.modeTabs{gap:7px!important}.modeTab{background:#fff!important;border-color:#c7d6e8!important;color:#17427a!important;border-radius:10px!important;box-shadow:0 1px 3px rgba(22,57,104,.05)!important}.modeTab.active{background:var(--gold)!important;color:#15386b!important;border-color:var(--gold)!important;box-shadow:0 3px 8px rgba(255,190,32,.25)!important}
.sectionHead b{color:#123a73!important}.status{color:#72849a!important}.refresh{background:#fff!important;border-color:#c7d6e8!important;color:#0b4c9f!important}
.match{border-color:#c7d6e8!important;border-radius:13px!important;box-shadow:0 2px 7px rgba(18,56,111,.07)!important}.matchTop{background:#e5effb!important;border-bottom-color:#c7d6e8!important}.league{color:#0b3f88!important}.format{color:#66809f!important}.liveTag{background:#fff1f2!important;color:#d92f44!important;border-color:#ffd2d8!important}.stateTag{background:#fff!important;color:#365d8c!important;border:1px solid #c7d6e8!important}.resultTag{background:#eaf8f2!important;color:#157451!important;border-color:#c9eadb!important}
.matchBody{background:#fff!important}.teamBadge{background:#f4f8fd!important;border-color:#cbd8e8!important;border-radius:9px!important;color:#17427a!important}.teamName{color:#18365f!important}.score{color:#0a3f8b!important}.abbr,.scoreInfo{color:#7c8fa7!important}.matchFoot{background:#f7faff!important;border-top-color:#d6e1ee!important}.report{color:#60768f!important}.go{color:#0b4c9f!important}
.empty,.error{background:#fff!important;border-color:#c7d6e8!important;color:#667d97!important}.spin{border-color:#d9e4f0!important;border-top-color:var(--gold)!important}
.back{background:#073f91!important;color:#fff!important;border-color:#073f91!important}.detailLive{background:#fff1f2!important;color:#d92f44!important;border-color:#ffd2d8!important}
.scoreCard{border-color:#c7d6e8!important;border-radius:15px!important;box-shadow:0 3px 10px rgba(18,56,111,.08)!important}.scoreMeta{background:#073f91!important;border-bottom:0!important}.scoreLeague,.scoreState{color:#fff!important}.versus{background:#fff!important}.sideLogo{background:#f4f8fd!important;border-color:#cbd8e8!important;border-radius:10px!important}.sideName{color:#18365f!important}.sideScore{color:#073f91!important}.sideInfo{color:#758aa3!important}.vs{background:var(--gold)!important;color:#173461!important}.result{background:#edf5ff!important;border-top-color:#c7d6e8!important;color:#31577f!important}
.detailTab{background:#fff!important;border-color:#c7d6e8!important;color:#31577f!important}.detailTab.active{background:var(--gold)!important;border-color:var(--gold)!important;color:#173461!important}
.panel{border-color:#c7d6e8!important;border-radius:13px!important;box-shadow:0 2px 7px rgba(18,56,111,.06)!important}.panelTitle{background:#e5effb!important;border-bottom-color:#c7d6e8!important}.panelTitle b{color:#0b3f88!important}.sourceTag{background:#073f91!important;color:#fff!important}.notice{color:#526b87!important;border-bottom-color:#dde6f0!important}.notice b{color:#173a68!important}.liveGrid{background:#fff!important}.mini{background:#f4f8fd!important;border-color:#d5e0ed!important}.mini b{color:#173a68!important}.mini span{color:#71859d!important}.ballNo{background:#073f91!important;color:#fff!important}
.innings{border-top-color:#edf2f7!important}.innTitle{background:#e5effb!important;border-bottom-color:#c7d6e8!important;color:#0b3f88!important}.table th{background:#f1f6fc!important;color:#46698f!important}.table td{border-bottom-color:#e1e9f2!important}.statPill{background:#fff8df!important;border-color:#ffe08a!important;color:#76550a!important}
.nav{background:#073775!important;border-top:0!important;box-shadow:0 -3px 12px rgba(5,48,110,.18)!important}.nav button{color:#c8dbf5!important}.nav button strong{color:#fff!important}.nav button.active{background:var(--gold)!important;color:#173461!important}.nav button.active strong{color:#173461!important}
'''
    html = html.replace("</style>", brand_css + "\n</style>", 1)
    html = html.replace("tg.setHeaderColor('#ffffff')", "tg.setHeaderColor('#073775')")
    html = html.replace("tg.setBackgroundColor('#f5f7fb')", "tg.setBackgroundColor('#edf2f7')")
    return html


liveline.admin_url = _site_admin_url
liveline._page = _site_page

# exact imported the app stack and installed Live Line using our new route globals above.
app = exact.app

if __name__ == "__main__":
    app.base.ibetin_start.main()
