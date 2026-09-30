import os
from urllib.parse import urlencode

import ibetin_liveline_trial as liveline

# Dedicated TEST route so Telegram cannot reuse an older cached WebApp page.
liveline.LIVELINE_PATH = "/admin/liveline-ibetinv10"
liveline.LIVELINE_API_PATH = "/admin/liveline-ibetinv10/api"

import ibetin_light_start as light


def _premium_admin_url() -> str:
    root = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/") or "https://ibetin-app-production.up.railway.app"
    return f"{root}{liveline.LIVELINE_PATH}?{urlencode({'t': liveline._token(), 'v': '20260916-v10-premium-test'})}"


def _premium_page() -> str:
    html = light._light_page()
    html = html.replace("/admin/liveline/api", liveline.LIVELINE_API_PATH)

    css = r'''
/* IBETIN LIVE LINE V10 — premium test UI */
:root{
  --ibt-bg:#f1f4f5;
  --ibt-card:#ffffff;
  --ibt-blue:#00ddff;
  --ibt-blue2:#00ddff;
  --ibt-blue3:#00ddff;
  --ibt-navy:#162025;
  --ibt-gold:#28e2ff;
  --ibt-gold2:#67ebff;
  --ibt-ink:#182228;
  --ibt-muted:#749298;
  --ibt-line:#dbe4e6;
  --ibt-soft:#f9fafa;
  --ibt-live:#e93a50;
  --ibt-green:#13845c;
  --ibt-shadow:0 8px 24px rgba(26,38,44,.10);
  --ibt-shadow2:0 14px 34px rgba(24,34,39,.14);
}
*{-webkit-tap-highlight-color:transparent}
html,body{background:var(--ibt-bg)!important;color:var(--ibt-ink)!important}
body{padding-bottom:82px!important}

/* Brand/header */
.topShell{
  position:sticky!important;top:0!important;z-index:40!important;
  background:linear-gradient(135deg,var(--ibt-navy) 0%,var(--ibt-blue) 52%,var(--ibt-blue2) 100%)!important;
  border-top:3px solid var(--ibt-gold)!important;
  box-shadow:0 6px 20px rgba(18,26,30,.22)!important;
}
.brandRow{height:66px!important;padding:0 14px!important;color:#fff!important}
.brandLeft{gap:10px!important}
.brandMark{
  width:38px!important;height:38px!important;border-radius:12px!important;
  background:linear-gradient(145deg,var(--ibt-gold2),var(--ibt-gold))!important;
  color:var(--ibt-navy)!important;box-shadow:0 5px 14px rgba(0,0,0,.18)!important;
  font-size:20px!important;font-weight:1000!important
}
.brandText b{font-size:19px!important;color:#fff!important;letter-spacing:.7px!important}
.brandText span{color:#e3eaeb!important;font-size:9px!important;letter-spacing:1px!important}
.liveChip{
  background:rgba(255,255,255,.10)!important;border:1px solid rgba(255,255,255,.22)!important;
  color:#fff!important;border-radius:999px!important;padding:7px 10px!important;font-weight:950!important
}
.liveChip:after{content:'TEST';margin-left:3px;background:var(--ibt-gold)!important;color:var(--ibt-navy)!important;border-radius:999px;padding:3px 6px;font-size:7px;font-weight:1000;letter-spacing:.5px}
.pulseDot{background:var(--ibt-live)!important;box-shadow:0 0 0 0 rgba(233,58,80,.55)!important}

/* Main mode tabs */
.navCard{background:#fff!important;border-bottom:1px solid #e1e9ea!important;box-shadow:0 2px 8px rgba(24,34,39,.05)!important}
.navTabs{padding:6px 10px!important;gap:7px!important;background:#fff!important}
.tab{
  border:1px solid #dde6e8!important;background:#fbfcfc!important;color:#55747a!important;
  border-radius:11px!important;padding:10px 4px!important;font-size:10px!important;letter-spacing:.35px!important
}
.tab.active{
  color:var(--ibt-navy)!important;background:linear-gradient(180deg,var(--ibt-gold2),var(--ibt-gold))!important;
  border-color:#00ddff!important;box-shadow:0 5px 12px rgba(20,224,255,.22)!important
}
.tab.active:after{display:none!important}

/* Page area */
.content,.detailWrap{background:var(--ibt-bg)!important;padding:12px!important}
.sectionTitle{margin:2px 1px 10px!important}
.sectionTitle b{font-size:14px!important;color:#00ddff!important;letter-spacing:.1px!important}
.status{font-size:9px!important;color:#7e9a9f!important;margin-top:3px!important}
.refreshBtn{
  background:#fff!important;border:1px solid #d3dee0!important;color:var(--ibt-blue)!important;
  border-radius:10px!important;padding:7px 10px!important;box-shadow:0 2px 6px rgba(24,34,40,.05)!important
}

/* Match cards */
.list{gap:12px!important}
.match{
  position:relative!important;background:#fff!important;border:1px solid #d3dee0!important;
  border-radius:14px!important;box-shadow:var(--ibt-shadow)!important;overflow:hidden!important
}
.match:before{content:'';position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--ibt-gold);z-index:2}
.match.liveCard:before{background:var(--ibt-live)!important}
.match:active{transform:scale(.995)!important}
.matchHead{
  background:linear-gradient(90deg,#00ddff,#00ddff)!important;border-bottom:0!important;
  padding:10px 12px 10px 14px!important
}
.league{color:#fff!important;font-size:10px!important;font-weight:1000!important;letter-spacing:.15px!important}
.format{color:#e3eaeb!important;font-size:8px!important}
.badgeLive{background:var(--ibt-live)!important;color:#fff!important;border:0!important;box-shadow:0 2px 7px rgba(233,58,80,.20)!important}
.badgeState{background:rgba(255,255,255,.13)!important;color:#fff!important;border:1px solid rgba(255,255,255,.22)!important}
.badgeResult{background:#eaf9f3!important;color:var(--ibt-green)!important;border-color:#caeadc!important}
.matchBody{padding:9px 12px 7px 14px!important;background:#fff!important}
.team{min-height:50px!important}
.teamBadge{
  width:38px!important;height:38px!important;border-radius:11px!important;background:#f7f9fa!important;
  border:1px solid #d8e2e4!important;color:#00ddff!important;box-shadow:0 2px 6px rgba(26,38,43,.05)!important
}
.teamname{font-size:13px!important;color:#00ddff!important;font-weight:950!important}
.abbr{color:#8ca3a8!important;font-size:8px!important}
.score{font-size:18px!important;color:var(--ibt-blue)!important;letter-spacing:.15px!important}
.info{color:#869ea3!important}
.divider{background:#f0f4f4!important;margin-left:50px!important}
.matchFoot{
  background:linear-gradient(90deg,#fafbfc,#f4f7f7)!important;border-top:1px solid #e0e8ea!important;
  padding:9px 12px 10px 14px!important
}
.report{color:#628289!important;font-size:9px!important;font-weight:750!important}
.arrow{background:var(--ibt-gold)!important;color:var(--ibt-navy)!important;width:25px!important;height:25px!important}

/* Empty/loading */
.empty,.error{background:#fff!important;border:1px solid #d4dfe1!important;border-radius:14px!important;box-shadow:var(--ibt-shadow)!important;color:#6f8e94!important}
.spin{border-color:#e2e9eb!important;border-top-color:var(--ibt-gold)!important}

/* Match detail */
.back{background:#fff!important;color:var(--ibt-blue)!important;border:1px solid #d3dee0!important;border-radius:10px!important;box-shadow:0 3px 9px rgba(25,36,42,.07)!important}
.miniLive{background:#fff0f2!important;color:var(--ibt-live)!important;border-color:#ffd5db!important}
.scoreHero{border-radius:15px!important;border:1px solid #d3dee0!important;box-shadow:var(--ibt-shadow2)!important;background:#fff!important}
.scoreTop{background:linear-gradient(90deg,var(--ibt-navy),var(--ibt-blue2))!important;border-bottom:0!important;padding:10px 12px!important}
.detailLeague{color:#fff!important;font-size:9px!important}
.matchState{color:var(--ibt-gold2)!important;font-size:8px!important}
.scoreMain{background:#fff!important;padding:18px 10px 15px!important}
.heroLogo{border-radius:13px!important;border-color:#d9e2e4!important;background:#f9fafa!important;box-shadow:0 3px 9px rgba(25,36,42,.06)!important}
.heroName{color:#00ddff!important;font-size:11px!important}
.heroScore{color:var(--ibt-blue)!important;font-size:20px!important}
.heroInfo{color:#869ea3!important}
.vsCircle{background:linear-gradient(145deg,var(--ibt-gold2),var(--ibt-gold))!important;color:var(--ibt-navy)!important;box-shadow:0 4px 10px rgba(25,224,255,.22)!important}
.resultStrip{background:linear-gradient(90deg,#f5f8f8,#ecf1f2)!important;border-top:1px solid #dde6e8!important;color:#4f6c71!important;font-weight:850!important}
.detailTabs{gap:7px!important;padding-bottom:9px!important}
.detailTab{background:#fff!important;color:#55747a!important;border:1px solid #d3dee0!important;border-radius:10px!important;padding:9px 11px!important}
.detailTab.active{background:var(--ibt-blue)!important;color:#fff!important;border-color:var(--ibt-blue)!important;box-shadow:0 4px 10px rgba(0,221,255,.15)!important}
.panel{border-radius:14px!important;border-color:#d3dee0!important;box-shadow:var(--ibt-shadow)!important}
.panelTitle{background:#f5f8f8!important;border-bottom-color:#dae4e6!important;padding:12px!important}
.panelTitle b{color:#00ddff!important;font-size:11px!important}
.sourceTag{background:var(--ibt-gold)!important;color:var(--ibt-navy)!important}
.liveSummary{background:linear-gradient(135deg,#f6f8f9,#f6f8f9)!important}
.liveStatus{color:#00ddff!important}
.liveReport{color:#708d93!important}
.livegrid{gap:9px!important;padding:0 11px 12px!important}
.mini{background:#fafbfc!important;border-color:#dde5e7!important;border-radius:10px!important;box-shadow:0 2px 6px rgba(25,36,42,.04)!important}
.mini b{color:#00ddff!important}.mini span{color:#749197!important}
.ballPill{background:#f3f6f6!important;color:#506e74!important;border-color:#dae3e5!important}
.ballPill.boundary{background:#e8eeef!important;color:#00ddff!important;border-color:#84efff!important}
.ballPill.wicket{background:#fff0f2!important;color:var(--ibt-live)!important;border-color:#ffd2d9!important}
.ballNo{background:var(--ibt-blue)!important;color:#fff!important;border-radius:8px!important}
.ballText{color:#54737a!important}.ballText strong{color:#00ddff!important}
.notice{color:#57777e!important;border-bottom-color:#e1e9ea!important}.notice b{color:#00ddff!important}
.innings{border-top-color:var(--ibt-bg)!important}.innTitle{background:#f0f4f5!important;color:#00ddff!important;border-bottom-color:#d9e3e5!important}
.table th{background:#f7f9f9!important;color:#58787f!important}.table td{border-bottom-color:#e6eced!important}
.pill{background:#e9eff0!important;border-color:#8df0ff!important;color:#00ddff!important}

/* Bottom navigation: cleaner and lighter */
.bottom{background:rgba(255,255,255,.98)!important;border-top:1px solid #d5e0e2!important;box-shadow:0 -5px 18px rgba(26,38,44,.09)!important}
.bottomInner{height:68px!important;padding:6px 8px!important;gap:4px!important}
.bottomItem{background:transparent!important;color:#7e9a9f!important;border-radius:12px!important}
.bottomItem span:first-child{color:#62858c!important}
.bottomItem.active{background:#f4f7f8!important;color:var(--ibt-blue)!important}
.bottomItem.active span:first-child{color:var(--ibt-blue)!important}

@media(min-width:600px){.content,.detailWrap{padding:16px!important}.match{min-height:192px!important}}
'''
    html = html.replace("</style>", css + "\n</style>", 1)
    html = html.replace("tg.setHeaderColor('#c71025')", "tg.setHeaderColor('#162025')")
    html = html.replace("tg.setHeaderColor('#d7192d')", "tg.setHeaderColor('#162025')")
    html = html.replace("tg.setHeaderColor('#ffffff')", "tg.setHeaderColor('#162025')")
    html = html.replace("tg.setBackgroundColor('#f2f4f5')", "tg.setBackgroundColor('#f1f4f5')")
    html = html.replace("tg.setBackgroundColor('#f4f6f7')", "tg.setBackgroundColor('#f1f4f5')")

    # Small visual polish without changing data/logic.
    inject = r'''
<script>
try{
  const brandSub=document.querySelector('.brandText span');
  if(brandSub) brandSub.textContent='CRICKET LIVE LINE · TEST MODE';
  const chip=document.querySelector('.liveChip');
  if(chip) chip.setAttribute('title','Private IBETIN test preview');
}catch(e){}
</script>
'''
    html = html.replace("</body>", inject + "\n</body>")
    return html


liveline.admin_url = _premium_admin_url
liveline._page = _premium_page

app = light.app

if __name__ == "__main__":
    app.base.ibetin_start.main()
