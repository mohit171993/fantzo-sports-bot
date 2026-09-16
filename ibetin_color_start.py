import os
from urllib.parse import urlencode

import ibetin_liveline_trial as liveline
import ibetin_light_start as light


def _color_admin_url() -> str:
    root = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/") or "https://ibetin-app-production.up.railway.app"
    return f"{root}{liveline.LIVELINE_PATH}?{urlencode({'t': liveline._token(), 'v': '20260916-v4-color'})}"


_COLOR_STYLE = r'''
<style id="ibetin-color-v4">
:root{
  --bg:#fff7fb!important;
  --red:#ff3158!important;
  --red2:#ff5a38!important;
  --redSoft:#fff0f5!important;
  --green:#11a86b!important;
  --blue:#2d74f6!important;
  --purple:#7c55f7;
  --orange:#ff8b2c;
  --cyan:#00a9c7;
  --yellow:#f4b000;
}
html,body{background:linear-gradient(180deg,#fff4f8 0%,#f6f9ff 42%,#f7fff9 100%)!important}
.topShell{background:linear-gradient(120deg,#ff3158 0%,#ff6a3d 42%,#7a57f6 100%)!important;box-shadow:0 7px 22px rgba(185,45,100,.24)!important}
.brandMark{background:linear-gradient(145deg,#fff,#fff3c4)!important;color:#ff3158!important;box-shadow:0 4px 14px rgba(82,20,55,.22)!important}
.liveChip{background:rgba(255,255,255,.22)!important;border-color:rgba(255,255,255,.58)!important}
.navCard{background:rgba(255,255,255,.98)!important}
.navTabs .tab:nth-child(1).active{color:#ff3158!important}.navTabs .tab:nth-child(1).active:after{background:linear-gradient(90deg,#ff3158,#ff7559)!important}
.navTabs .tab:nth-child(2).active{color:#2d74f6!important}.navTabs .tab:nth-child(2).active:after{background:linear-gradient(90deg,#2d74f6,#23b6e8)!important}
.navTabs .tab:nth-child(3).active{color:#11a86b!important}.navTabs .tab:nth-child(3).active:after{background:linear-gradient(90deg,#11a86b,#63cd78)!important}
.content,.detailWrap{background:transparent!important}
.refreshBtn{background:linear-gradient(135deg,#fff,#fff4fa)!important;border-color:#ffdce7!important;color:#a34967!important}
.match{border:0!important;box-shadow:0 7px 22px rgba(42,55,82,.10)!important;background:#fff!important}
.match:nth-child(4n+1){box-shadow:0 7px 22px rgba(255,49,88,.11)!important}.match:nth-child(4n+2){box-shadow:0 7px 22px rgba(45,116,246,.11)!important}.match:nth-child(4n+3){box-shadow:0 7px 22px rgba(17,168,107,.11)!important}.match:nth-child(4n){box-shadow:0 7px 22px rgba(124,85,247,.11)!important}
.match.liveCard:before{width:5px!important;background:linear-gradient(180deg,#ff3158,#ff8a3c,#7b55f7)!important}
.matchHead{background:linear-gradient(90deg,#fff8fb,#fff 50%,#f7faff)!important}
.badgeLive{background:linear-gradient(135deg,#ff3158,#ff7047)!important;box-shadow:0 3px 8px rgba(255,49,88,.22)!important}
.badgeState{background:#edf4ff!important;color:#2d65c7!important}.badgeResult{background:#e8fbf1!important;color:#0d9760!important}
.team:nth-child(1) .teamBadge{background:linear-gradient(145deg,#eaf3ff,#f6f0ff)!important;border-color:#d5e4ff!important;color:#3368cc!important}
.team:nth-child(3) .teamBadge,.team:nth-child(2) .teamBadge{background:linear-gradient(145deg,#eafcf3,#fff7d8)!important;border-color:#d5f1e2!important;color:#148a5a!important}
.team:nth-child(1) .score{color:#235fc8!important}.team:nth-child(3) .score,.team:nth-child(2) .score{color:#8a43d8!important}
.matchFoot{background:linear-gradient(90deg,#fff9fb,#f8fbff,#f7fff9)!important}.arrow{background:linear-gradient(135deg,#ffeaf1,#eaf2ff)!important;color:#8d4cc4!important}
.empty,.error{border:0!important;background:linear-gradient(145deg,#ffffff,#fff8fc)!important;box-shadow:0 8px 24px rgba(70,52,88,.10)!important}
.spin{border-color:#f1e8ef!important;border-top-color:#7b55f7!important}
.back{border:0!important;background:linear-gradient(135deg,#fff,#f4f0ff)!important;color:#6c4fc5!important;box-shadow:0 4px 14px rgba(84,63,154,.10)!important}.miniLive{background:linear-gradient(90deg,#ffe8ef,#fff3df)!important;color:#e32952!important;border-color:#ffd2df!important}
.scoreHero{border:0!important;box-shadow:0 10px 30px rgba(55,51,91,.13)!important;background:linear-gradient(145deg,#fff,#fff9fd 45%,#f7f9ff)!important;position:relative}.scoreHero:before{content:"";display:block;height:5px;background:linear-gradient(90deg,#ff3158,#ff9b31,#2d74f6,#7c55f7,#11a86b)}
.scoreTop{background:linear-gradient(90deg,#fff5f8,#f7f9ff,#f2fff8)!important}.matchState{color:#ff3158!important}
.heroTeam:first-child .heroLogo{background:linear-gradient(145deg,#eaf3ff,#f1ecff)!important;border-color:#d7e4ff!important}.heroTeam:last-child .heroLogo{background:linear-gradient(145deg,#e9fff3,#fff3d8)!important;border-color:#d8f3e5!important}
.heroTeam:first-child .heroScore{color:#245fc5!important}.heroTeam:last-child .heroScore{color:#8b48d0!important}.vsCircle{background:linear-gradient(135deg,#ffe8ef,#eef3ff)!important;color:#9b4fbc!important}
.resultStrip{background:linear-gradient(90deg,#fff0f5,#fff8dc,#eff7ff)!important;border-top-color:#ffe0e8!important;color:#654d62!important}
.detailTab{border:0!important;background:#fff!important;box-shadow:0 3px 10px rgba(47,56,78,.08)!important}.detailTab.active{background:linear-gradient(135deg,#ff3158,#ff7350,#7c55f7)!important;color:#fff!important;box-shadow:0 5px 13px rgba(191,62,121,.24)!important}
.panel{border:0!important;box-shadow:0 8px 24px rgba(45,53,75,.10)!important}.panelTitle{background:linear-gradient(90deg,#fff8fb,#f6f9ff,#f4fff8)!important}.sourceTag{background:linear-gradient(135deg,#eaf2ff,#f1eaff)!important;color:#5656cb!important}
.liveSummary{background:linear-gradient(120deg,#fff0f5,#fff9e8 52%,#f1f7ff)!important}.liveStatus{color:#cc2b53!important}
.livegrid .mini:nth-child(1){background:linear-gradient(145deg,#eef5ff,#f8fbff)!important;border-color:#dce9ff!important}.livegrid .mini:nth-child(2){background:linear-gradient(145deg,#edfff5,#f8fff8)!important;border-color:#d8f4e3!important}.livegrid .mini:nth-child(3){background:linear-gradient(145deg,#fff5df,#fffaf1)!important;border-color:#ffe8b7!important}
.ballPill{background:#f4f1ff!important;border-color:#e4dcff!important;color:#684dc3!important}.ballPill.wicket{background:#ffe8ef!important;color:#e12650!important;border-color:#ffcbd8!important}.ballPill.boundary{background:linear-gradient(145deg,#e8f4ff,#ecfbff)!important;color:#1674c8!important;border-color:#cce9ff!important}
.ballRow:nth-child(odd){background:#fffafd!important}.ballNo{background:linear-gradient(135deg,#ffe9f0,#fff3df)!important;color:#d92d55!important}
.notice:nth-child(odd){background:#fffafd!important}.innings{border-top-color:#f7f0f6!important}.innTitle{background:linear-gradient(90deg,#fff2f6,#f3f7ff)!important;color:#603c7c!important}.table th{background:#f7f6ff!important;color:#625e92!important}.pill:nth-child(4n+1){background:#fff0f5!important;border-color:#ffd7e1!important;color:#ba3152!important}.pill:nth-child(4n+2){background:#edf4ff!important;border-color:#d6e6ff!important;color:#2861bd!important}.pill:nth-child(4n+3){background:#ecfbf3!important;border-color:#d5f0e1!important;color:#16865a!important}.pill:nth-child(4n){background:#f4efff!important;border-color:#e5dbff!important;color:#6b4bc1!important}
.bottom{background:rgba(255,255,255,.97)!important;border-top-color:#eee5ef!important;box-shadow:0 -5px 18px rgba(74,48,77,.09)!important}.bottomItem{background:transparent!important}.bottomItem:nth-child(1) .ico{color:#7c55f7}.bottomItem:nth-child(2) .ico{color:#ff3158}.bottomItem:nth-child(3) .ico{color:#2d74f6}.bottomItem:nth-child(4) .ico{color:#11a86b}.bottomItem:nth-child(5) .ico{color:#ff8b2c}.bottomItem.active{color:#7c55f7!important}
</style>
'''


def _color_page() -> str:
    html = light._light_page()
    html = html.replace("</head>", _COLOR_STYLE + "</head>", 1)
    html = html.replace("</body>", "<script>try{const w=window.Telegram&&window.Telegram.WebApp;if(w){w.setHeaderColor('#ff3158');w.setBackgroundColor('#fff7fb')}}catch(e){}</script></body>", 1)
    return html


liveline.admin_url = _color_admin_url
liveline._page = _color_page

if __name__ == "__main__":
    light.app.base.ibetin_start.main()
