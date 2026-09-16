import os
from urllib.parse import urlencode

import ibetin_liveline_trial as liveline

# New route as well as a new visual build: avoids Telegram reusing an older WebApp page.
liveline.LIVELINE_PATH = "/admin/liveline-ibetinv8"
liveline.LIVELINE_API_PATH = "/admin/liveline-ibetinv8/api"

import ibetin_light_start as light


def _ibetin_admin_url() -> str:
    root = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/") or "https://ibetin-app-production.up.railway.app"
    return f"{root}{liveline.LIVELINE_PATH}?{urlencode({'t': liveline._token(), 'v': '20260916-v8-blue-gold'})}"


def _ibetin_page() -> str:
    html = light._light_page()
    html = html.replace("/admin/liveline/api", liveline.LIVELINE_API_PATH)
    css = r'''
/* IBETIN sportsbook identity: royal blue + gold/yellow + pale-blue market surfaces */
:root{--bg:#edf2f7!important;--card:#fff!important;--text:#17355f!important;--muted:#6f8198!important;--line:#c7d6e8!important;--red:#e23a4e!important;--blue:#073f91!important;--gold:#ffbe20!important;--navy:#073775!important;--soft:#f4f8fd!important;--shadow:0 2px 7px rgba(10,55,117,.08)!important}
html,body{background:#edf2f7!important;color:#17355f!important}
body{padding-bottom:72px!important}
.appbar{background:#073775!important;border-bottom:0!important;box-shadow:0 3px 12px rgba(5,48,110,.22)!important}
.brandrow{height:60px!important;color:#fff!important}.logo{color:#fff!important;font-size:19px!important;letter-spacing:.6px!important}.mark{background:#ffbe20!important;color:#173b72!important;border-radius:9px!important;box-shadow:none!important}.beta{background:#ffbe20!important;color:#173b72!important;border-color:#ffbe20!important;font-weight:950!important}
.navtabs{background:#073775!important;padding:0 8px!important}.tab{background:#073775!important;color:#c6d8f2!important;padding:12px 3px 13px!important}.tab.active{color:#ffcc46!important}.tab.active:after{background:#ffbe20!important;height:4px!important;left:18%!important;right:18%!important}
.content,.detailWrap{background:#edf2f7!important;padding:10px!important}.status{color:#72849b!important}.list{gap:9px!important}
.match{border:1px solid #bed0e5!important;border-radius:10px!important;box-shadow:0 2px 7px rgba(10,55,117,.07)!important;background:#fff!important}.matchHead{background:#dfeafb!important;border-bottom:1px solid #c7d6e8!important;padding:9px 11px!important}.league{color:#0b428d!important;font-weight:950!important}.live{background:#e23a4e!important;color:#fff!important}.state{background:#fff!important;color:#315b8d!important;border:1px solid #bfcfe2!important}.matchBody{background:#fff!important;padding:8px 11px!important}.team{min-height:43px!important}.teamDot{background:#f4f8fd!important;border-color:#c3d3e6!important;color:#17457f!important;border-radius:9px!important}.teamname{color:#17355f!important}.score{color:#073f91!important;font-size:17px!important}.info{color:#7d8fa6!important}.matchFoot{background:#f5f9ff!important;border-top-color:#d5e0ee!important;color:#5b708b!important}
.empty,.error{background:#fff!important;border-color:#c3d3e6!important;border-radius:10px!important;color:#667b94!important}.spin{border-color:#d5e2f0!important;border-top-color:#ffbe20!important}
.back{background:#073f91!important;color:#fff!important;border-color:#073f91!important;border-radius:8px!important}.detailHead{background:#fff!important;border-color:#c3d3e6!important;border-radius:10px!important;box-shadow:0 2px 7px rgba(10,55,117,.07)!important}.detailLeague{background:#073f91!important;color:#fff!important;border-bottom:0!important}.scoreHero{background:#fff!important}.bigScore{color:#073f91!important}.sub{color:#647b95!important}
.detailTabs{background:#e4eefb!important;border-color:#c3d3e6!important;border-radius:9px!important;box-shadow:none!important;padding:4px!important}.detailTab{background:transparent!important;color:#315b8d!important;border-radius:7px!important}.detailTab.active{background:#ffbe20!important;color:#173b72!important}.detailTab.active:after{display:none!important}
.panel{background:#fff!important;border-color:#c3d3e6!important;border-radius:10px!important;box-shadow:0 2px 7px rgba(10,55,117,.06)!important}.panel h3{background:#dfeafb!important;color:#0b428d!important;border-bottom-color:#c7d6e8!important}.livegrid{background:#fff!important}.mini{background:#f3f7fc!important;border-color:#d2dfea!important;border-radius:8px!important}.mini b{color:#17355f!important}.mini span{color:#71859c!important}.notice{color:#506b88!important;border-bottom-color:#dce5ef!important}.notice b{color:#17355f!important}.ballNo{background:#073f91!important;color:#fff!important;border-radius:7px!important}.sourceTag{background:#ffbe20!important;color:#173b72!important}.ballRow{border-bottom-color:#dce5ef!important}
.innings{border-top-color:#edf2f7!important}.innTitle{background:#dfeafb!important;border-bottom-color:#c7d6e8!important;color:#0b428d!important}.table th{background:#f0f6fd!important;color:#3b638f!important}.table td{border-bottom-color:#e0e8f1!important}.pill{background:#fff8df!important;border-color:#ffe08a!important;color:#70520c!important}
.bottom{background:#073775!important;border-top:0!important;box-shadow:0 -3px 12px rgba(5,48,110,.18)!important}.bottomInner{height:64px!important}.bottomItem{background:#073775!important;color:#c9dbf4!important}.bottomItem span:first-child{color:#fff!important}.bottomItem.active{background:#ffbe20!important;color:#173b72!important}.bottomItem.active span:first-child{color:#173b72!important}
'''
    html = html.replace("</style>", css + "\n</style>", 1)
    html = html.replace("tg.setHeaderColor('#ffffff')", "tg.setHeaderColor('#073775')")
    html = html.replace("tg.setBackgroundColor('#f4f5f7')", "tg.setBackgroundColor('#edf2f7')")
    return html


liveline.admin_url = _ibetin_admin_url
liveline._page = _ibetin_page

app = light.app

if __name__ == "__main__":
    app.base.ibetin_start.main()
