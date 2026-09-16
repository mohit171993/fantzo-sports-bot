import os
from urllib.parse import urlencode

import ibetin_liveline_trial as liveline
import ibetin_light_start as light


def _theme_admin_url() -> str:
    root = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/") or "https://ibetin-app-production.up.railway.app"
    return f"{root}{liveline.LIVELINE_PATH}?{urlencode({'t': liveline._token(), 'v': '20260916-v5-ibetin'})}"


def _theme_page() -> str:
    html = light._light_page()
    theme_css = r'''
/* IBETIN core Mini App theme alignment */
:root{--bg:#f5f7fb!important;--card:#ffffff!important;--ink:#172033!important;--text:#172033!important;--muted:#64748b!important;--line:#dce3ed!important;--blue:#2563eb!important;--navy:#172033!important;--soft:#f8fafc!important;--shadow:0 2px 10px rgba(23,32,51,.055)!important;--shadow2:0 4px 16px rgba(23,32,51,.075)!important}
html,body{background:#f5f7fb!important;color:#172033!important}
.topShell,.appbar{background:#fff!important;background-image:none!important;border-bottom:1px solid #dce3ed!important;box-shadow:0 1px 6px rgba(23,32,51,.05)!important}
.brandRow,.brandrow{color:#172033!important;height:58px!important}
.brandMark,.mark{background:#172033!important;color:#fff!important;border-radius:11px!important;box-shadow:none!important}
.brandText b,.logo{color:#172033!important}.brandText span{color:#64748b!important;opacity:1!important}
.liveChip,.beta{background:#f8fafc!important;color:#475569!important;border:1px solid #dce3ed!important}.pulseDot{background:#2563eb!important}
.navCard,.navtabs,.navTabs{background:#fff!important}.tab{background:#fff!important;color:#64748b!important}.tab.active{color:#172033!important}.tab.active:after{background:#2563eb!important}
.content,.detailWrap{background:#f5f7fb!important}.sectionTitle b{color:#172033!important}.status{color:#738196!important}.refreshBtn{background:#fff!important;border-color:#dce3ed!important;color:#475569!important}
.match{background:#fff!important;border:1px solid #dce3ed!important;border-radius:18px!important;box-shadow:0 2px 10px rgba(23,32,51,.055)!important}.match.liveCard:before{background:#2563eb!important;width:3px!important}
.matchHead{border-bottom-color:#edf1f6!important}.league{color:#172033!important}.format,.abbr,.info{color:#738196!important}
.badgeLive{background:#e11d48!important;color:#fff!important}.badgeState{background:#eef2f7!important;color:#475569!important}.badgeResult{background:#eef6ff!important;color:#2563eb!important}
.teamBadge,.teamDot{background:#f8fafc!important;border-color:#dce3ed!important;color:#475569!important}.teamname,.score{color:#172033!important}.divider{background:#edf1f6!important}
.matchFoot{background:#fbfcfe!important;border-top-color:#edf1f6!important}.report{color:#64748b!important}.arrow{background:#eef2f7!important;color:#475569!important}
.empty,.error{background:#fff!important;border-color:#dce3ed!important;color:#64748b!important}.spin{border-color:#e2e8f0!important;border-top-color:#2563eb!important}
.back{background:#fff!important;color:#172033!important;border:1px solid #dce3ed!important;box-shadow:none!important}.miniLive{background:#eff6ff!important;color:#2563eb!important;border-color:#dbeafe!important}
.scoreHero,.detailHead{background:#fff!important;border:1px solid #dce3ed!important;border-radius:22px!important;box-shadow:0 2px 10px rgba(23,32,51,.055)!important}.scoreTop,.detailLeague{background:#f8fafc!important;border-bottom-color:#dce3ed!important}.detailLeague{color:#475569!important}.matchState{color:#2563eb!important}
.heroLogo{background:#f8fafc!important;border-color:#dce3ed!important}.heroName,.heroScore,.bigScore{color:#172033!important}.heroInfo,.sub{color:#738196!important}.vsCircle{background:#eef2f7!important;color:#64748b!important}
.resultStrip{background:#f8fafc!important;border-top-color:#dce3ed!important;color:#475569!important}
.detailTab{background:#fff!important;color:#64748b!important;border:1px solid #dce3ed!important;box-shadow:none!important}.detailTab.active{background:#172033!important;border-color:#172033!important;color:#fff!important}
.panel{background:#fff!important;border:1px solid #dce3ed!important;border-radius:18px!important;box-shadow:0 2px 10px rgba(23,32,51,.055)!important}.panelTitle,.panel h3{border-bottom-color:#dce3ed!important}.panelTitle b,.panel h3{color:#172033!important}
.sourceTag{background:#eff6ff!important;color:#2563eb!important}.liveSummary{background:#f8fafc!important}.liveStatus{color:#172033!important}.liveReport{color:#64748b!important}.subLabel{color:#738196!important}
.mini{background:#f8fafc!important;border-color:#e2e8f0!important}.mini b{color:#172033!important}.mini span{color:#64748b!important}.notice{background:#fff!important;border-bottom-color:#edf1f6!important;color:#475569!important}.notice b{color:#172033!important}
.ballNo{background:#eff6ff!important;color:#2563eb!important}.ballPill{background:#f1f5f9!important;color:#475569!important;border-color:#e2e8f0!important}.ballPill.wicket{background:#fff1f2!important;color:#e11d48!important;border-color:#ffe4e6!important}.ballPill.boundary{background:#eff6ff!important;color:#2563eb!important;border-color:#dbeafe!important}
.innings{border-top-color:#f5f7fb!important}.innTitle{background:#f8fafc!important;border-bottom-color:#dce3ed!important;color:#172033!important}.table th{background:#f8fafc!important;color:#64748b!important}.table td{border-bottom-color:#edf1f6!important}.pill{background:#f8fafc!important;border-color:#dce3ed!important;color:#475569!important}
.bottom{background:#fff!important;border-top:1px solid #dce3ed!important;box-shadow:0 -2px 10px rgba(23,32,51,.045)!important}.bottomItem{background:#fff!important;color:#64748b!important}.bottomItem.active{color:#2563eb!important}
'''
    html = html.replace('</style>', theme_css + '\n</style>', 1)
    html = html.replace("tg.setHeaderColor('#c71025')", "tg.setHeaderColor('#ffffff')")
    html = html.replace("tg.setHeaderColor('#d7192d')", "tg.setHeaderColor('#ffffff')")
    html = html.replace("tg.setBackgroundColor('#f2f3f5')", "tg.setBackgroundColor('#f5f7fb')")
    return html


liveline.admin_url = _theme_admin_url
liveline._page = _theme_page

import ibetin_admin_fix_start as app

if __name__ == "__main__":
    app.base.ibetin_start.main()
