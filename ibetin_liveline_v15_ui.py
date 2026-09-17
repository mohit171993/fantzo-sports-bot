import logging
import os
from urllib.parse import urlencode

import ibetin_liveline_trial as liveline
import ibetin_liveline_v14_efficient as v14

logger = logging.getLogger(__name__)

# Fresh route so Telegram WebView cannot reuse cached V14 markup.
liveline.LIVELINE_PATH = "/admin/liveline-ibetinv15"
liveline.LIVELINE_API_PATH = "/admin/liveline-ibetinv15/api"


def _v15_admin_url() -> str:
    root = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/") or "https://ibetin-app-production.up.railway.app"
    return f"{root}{liveline.LIVELINE_PATH}?{urlencode({'t': liveline._token(), 'v': '20260917-v15-arena-ui'})}"


def _v15_page() -> str:
    html = v14._v14_page()

    css = r'''
/* ============================================================
   IBETIN V15 — ARENA UI
   Visual-only layer over the V14 API-saver backend.
   ============================================================ */
:root{
  --a-bg:#f2f5f9;--a-card:#ffffff;--a-ink:#10243e;--a-muted:#72849a;
  --a-navy:#061b3d;--a-blue:#0a4f9f;--a-blue2:#176fcf;--a-gold:#f6c844;
  --a-red:#ef4357;--a-green:#0e9b68;--a-line:#dce5ef;
  --a-soft:#f7f9fc;--a-shadow:0 8px 26px rgba(8,38,78,.08);
  --a-shadow2:0 14px 36px rgba(8,38,78,.13);
}
html,body{background:var(--a-bg)!important}
body{padding-bottom:80px!important}
*{scrollbar-width:none}*::-webkit-scrollbar{display:none}

/* App shell */
.topShell{
  position:sticky!important;top:0!important;z-index:50!important;
  background:linear-gradient(128deg,#051832 0%,#082d63 48%,#0a4f9f 100%)!important;
  border-top:0!important;box-shadow:0 5px 20px rgba(2,19,44,.24)!important
}
.topShell:before{content:'';position:absolute;left:0;right:0;top:0;height:3px;background:linear-gradient(90deg,#f6c844,#ffe486,#f6c844)}
.brandRow{height:64px!important;padding:3px 13px 0!important}
.brandMark{width:38px!important;height:38px!important;border-radius:12px!important;background:linear-gradient(145deg,#ffe38b,#f6c844)!important;color:#092952!important;box-shadow:0 6px 16px rgba(0,0,0,.19)!important}
.brandText b{font-size:18px!important;letter-spacing:.9px!important}.brandText span{font-size:7px!important;letter-spacing:1.25px!important;color:#bfd7f4!important}
.liveChip{padding:6px 8px!important;background:rgba(255,255,255,.09)!important;border-color:rgba(255,255,255,.17)!important}
.liveChip:after{content:'V15'!important;background:#f6c844!important;color:#082950!important;padding:3px 6px!important}

/* Compact mode nav directly under app header */
.navCard{position:sticky!important;top:64px!important;z-index:42!important;background:rgba(255,255,255,.96)!important;backdrop-filter:blur(14px)!important;border-bottom:1px solid #dce5ef!important;box-shadow:0 3px 12px rgba(8,38,78,.055)!important}
.navTabs{padding:7px 10px!important;gap:6px!important;background:transparent!important}
.tab{height:38px!important;border:1px solid #dae4ee!important;border-radius:11px!important;background:#f8fafc!important;color:#71849a!important;font-size:9px!important;font-weight:950!important;letter-spacing:.25px!important;box-shadow:none!important;transition:.18s ease!important}
.tab.active{background:#082f68!important;color:#fff!important;border-color:#082f68!important;box-shadow:0 5px 12px rgba(7,46,100,.18)!important}

/* Main content */
.content,.detailWrap{background:var(--a-bg)!important;padding:10px 10px 14px!important;max-width:760px!important;margin:auto!important}
.sectionTitle{margin:3px 1px 8px!important}.sectionTitle b{font-size:13px!important;color:#173a66!important}.status{font-size:8px!important;color:#8494a6!important}
.refreshBtn{border-radius:9px!important;background:#fff!important;border-color:#d5e0eb!important;color:#24578d!important;box-shadow:none!important}

/* V15 dashboard hero */
.v15ArenaHero{position:relative;overflow:hidden;margin:0 0 10px;border-radius:17px;background:linear-gradient(135deg,#061b3d 0%,#073d82 62%,#0f66c4 100%);color:#fff;padding:14px 14px 12px;box-shadow:0 14px 32px rgba(7,43,92,.18)}
.v15ArenaHero:before{content:'';position:absolute;width:180px;height:180px;border-radius:50%;right:-72px;top:-92px;background:rgba(255,255,255,.08)}
.v15ArenaHero:after{content:'';position:absolute;width:120px;height:120px;border-radius:50%;right:12px;bottom:-78px;background:rgba(246,200,68,.12)}
.v15HeroTop{position:relative;z-index:1;display:flex;align-items:center;justify-content:space-between;gap:10px}
.v15HeroEyebrow{font-size:7px;font-weight:1000;letter-spacing:1.35px;color:#aecaec}.v15HeroTitle{font-size:18px;font-weight:1000;letter-spacing:-.25px;margin-top:3px}.v15HeroPill{flex:none;border:1px solid rgba(255,255,255,.18);background:rgba(255,255,255,.10);border-radius:999px;padding:6px 8px;font-size:7px;font-weight:1000;color:#d9e9fb}
.v15HeroStats{position:relative;z-index:1;display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-top:13px}.v15HeroStat{background:rgba(255,255,255,.09);border:1px solid rgba(255,255,255,.12);border-radius:11px;padding:9px 8px}.v15HeroStat b{display:block;font-size:13px;color:#fff}.v15HeroStat span{display:block;font-size:6px;color:#bcd2ea;margin-top:3px;letter-spacing:.55px;font-weight:900}

/* Search / filters: look like product controls, not admin controls */
.v12Command{border-radius:15px!important;border:1px solid #d9e3ed!important;box-shadow:0 5px 18px rgba(8,38,78,.055)!important;background:#fff!important;margin-bottom:10px!important}
.v12Sports{padding:10px 9px 7px!important}.v12Sport{height:34px!important;border-radius:10px!important;padding:0 10px!important;background:#f7f9fc!important;border-color:#e0e7ef!important;color:#6d8198!important;font-size:8px!important}.v12Sport.active{background:#082f68!important;border-color:#082f68!important;color:#fff!important;box-shadow:none!important}
.v12SearchRow{padding:0 9px 8px!important}.v12SearchBox{min-height:39px!important;border-radius:10px!important;background:#f8fafc!important;border-color:#dde5ee!important;box-shadow:none!important}.v12SearchBox input{font-size:10px!important}.v12Clear{border-radius:10px!important;background:#f8fafc!important;border-color:#dde5ee!important;color:#5e7590!important}
.v12Filters{padding:0 9px 9px!important}.v12Filter{border-radius:8px!important;background:#f7f9fc!important;border-color:#e0e7ef!important;color:#75879a!important;padding:7px 9px!important}.v12Filter.active{background:#fff6d7!important;border-color:#efd073!important;color:#765b08!important;box-shadow:none!important}
.v12QuickStat{padding:8px 9px!important;background:#fafbfd!important;border-color:#e6ecf2!important}.v14Efficiency{margin-left:auto!important;background:#eaf8f1!important}

/* Day/tournament hierarchy */
.dayBlock{margin-bottom:13px!important}.dayHead{padding:0 2px!important;margin:0 0 7px!important}.dayDot{width:7px!important;height:7px!important;background:#0d60b9!important;box-shadow:0 0 0 4px rgba(13,96,185,.09)!important}.dayTitle{font-size:10px!important;color:#294d73!important;letter-spacing:.4px!important}.dayCount{font-size:7px!important;background:#fff!important;border-color:#dce5ef!important;color:#8191a2!important}
.leagueBlock{border:1px solid #dce5ee!important;border-radius:15px!important;box-shadow:0 6px 20px rgba(8,38,78,.055)!important;margin-bottom:9px!important;overflow:hidden!important}
.leagueSectionHead{padding:9px 10px!important;background:#fff!important;color:#173b66!important;border-bottom:1px solid #e8edf3!important}
.leagueIcon{width:29px!important;height:29px!important;border-radius:9px!important;background:#eef5fd!important;color:#0b56a7!important;border:1px solid #d7e6f5!important;box-shadow:none!important}
.leagueSectionName{font-size:9px!important;color:#193f6b!important}.leagueSectionMeta{font-size:6px!important;color:#91a0b0!important;letter-spacing:.7px!important}.leagueCount{background:#f5f8fb!important;border-color:#e2e8ef!important;color:#73869a!important;font-size:7px!important}.v13Collapse{background:#f4f7fa!important;border:1px solid #e0e7ee!important;color:#63809c!important}
.leagueMatches{padding:7px!important;gap:7px!important;background:#f7f9fc!important}

/* Match cards — minimal, data-first */
.leagueMatches .match{border-radius:13px!important;border:1px solid #dce5ee!important;box-shadow:0 3px 12px rgba(8,38,78,.045)!important;background:#fff!important;transition:transform .14s ease,box-shadow .14s ease!important}
.leagueMatches .match:active{transform:scale(.992)!important}.match:before{width:3px!important;background:#f6c844!important}.match.liveCard:before{background:#ef4357!important}
.leagueMatches .matchHead{padding:7px 9px 7px 11px!important;background:#fbfcfe!important;border-bottom:1px solid #eef2f6!important}.leagueMatches .format{font-size:6px!important;color:#8395a8!important;letter-spacing:.65px!important}.badgeLive{background:#fff0f2!important;color:#df3147!important;border:1px solid #ffd1d8!important;box-shadow:none!important}.badgeState{background:#eef5fd!important;color:#4b6f94!important;border:1px solid #d8e7f6!important}.badgeResult{background:#edf9f4!important;color:#14845c!important;border-color:#d0eddf!important}
.leagueMatches .matchBody{padding:5px 9px 4px 11px!important}.leagueMatches .team{min-height:43px!important}.leagueMatches .teamBadge{width:33px!important;height:33px!important;border-radius:10px!important;background:#f4f7fb!important;border-color:#e0e7ef!important;color:#285781!important;box-shadow:none!important}.teamname{font-size:12px!important;color:#142f50!important}.abbr{font-size:7px!important;color:#99a6b4!important}.score{font-size:17px!important;color:#0a4d96!important}.info{font-size:7px!important;color:#91a0af!important}.divider{background:#f0f3f7!important}
.leagueMatches .matchFoot{min-height:36px!important;padding:7px 8px 7px 11px!important;background:#fbfcfd!important;border-top:1px solid #eef2f6!important}.report{font-size:8px!important;color:#697f96!important}.arrow{width:23px!important;height:23px!important;border-radius:8px!important;background:#eef4fb!important;color:#1d5e9e!important;box-shadow:none!important}
.v13Pin{top:5px!important;right:6px!important;width:25px!important;height:25px!important;border-radius:8px!important;box-shadow:none!important}.match.v13Pinned{outline:1.5px solid #edcc64!important}.match.v13Pinned:after{font-size:5px!important;top:9px!important;color:#8b6a0b!important}
.v13CardBhav{padding:6px 8px 6px 11px!important;background:#fff!important;border-top:1px solid #f0f3f7!important}.v13BhavLabel{font-size:6px!important;color:#91a0af!important}.v13BhavOdd{padding:6px!important;border-radius:8px!important;background:#f1f7fd!important;border-color:#dceaf7!important;color:#0c559f!important;font-size:9px!important}.v13BhavOdd span{font-size:5px!important}

/* Detail screen */
.back{height:36px!important;border-radius:10px!important;background:#fff!important;color:#24578d!important;border:1px solid #d8e2ec!important;box-shadow:none!important}
.v13MiniScore{top:64px!important;border-radius:13px!important;background:linear-gradient(120deg,#061b3d,#083e80)!important;border:0!important;box-shadow:0 8px 22px rgba(6,33,71,.16)!important;padding:9px 11px!important}.v13MiniTeam{font-size:7px!important}.v13MiniVal{font-size:13px!important}.v13MiniLive{font-size:6px!important;background:#ef4357!important}
.scoreHero{border:0!important;border-radius:16px!important;box-shadow:var(--a-shadow)!important;overflow:hidden!important}.scoreTop{padding:9px 11px!important;background:#fff!important;border-bottom:1px solid #edf1f5!important}.detailLeague{color:#456888!important;font-size:8px!important}.matchState{color:#71849a!important;font-size:7px!important}.scoreMain{padding:16px 8px 13px!important}.heroLogo{width:48px!important;height:48px!important;border-radius:14px!important;background:#f6f8fb!important;border-color:#e1e7ee!important;box-shadow:none!important}.heroName{font-size:10px!important;color:#233f5d!important}.heroScore{font-size:21px!important;color:#083f7f!important}.heroInfo{font-size:7px!important}.vsCircle{width:31px!important;height:31px!important;background:#fff5cf!important;color:#755500!important;box-shadow:none!important;border:1px solid #f1d374!important}.resultStrip{padding:9px 10px!important;background:#fbfcfe!important;border-color:#edf1f5!important;color:#617991!important;font-size:8px!important}
.v12Pulse{border-radius:15px!important;background:linear-gradient(135deg,#061b3d,#0a4f9f)!important;border:0!important;box-shadow:0 10px 25px rgba(8,43,91,.16)!important}.v12PulseTop{padding:9px 11px!important}.v12PulseBody{padding:11px!important}.v12PulseMain{font-size:12px!important}.v12PulseSub{font-size:8px!important}.v13PlayerLine{gap:6px!important}.v13Player{padding:7px!important;border-radius:8px!important}.v13PulseBalls{gap:4px!important}.v13Ball{min-width:27px!important;height:27px!important}
.detailTabs{top:113px!important;padding:5px 0 8px!important;background:var(--a-bg)!important;gap:6px!important}.detailTab{height:34px!important;padding:0 10px!important;border-radius:9px!important;background:#fff!important;border:1px solid #dce5ee!important;color:#687f96!important;font-size:7px!important;box-shadow:none!important}.detailTab.active{background:#082f68!important;color:#fff!important;border-color:#082f68!important;box-shadow:none!important}
.panel{border:1px solid #dce5ee!important;border-radius:14px!important;box-shadow:var(--a-shadow)!important;background:#fff!important}.panelTitle{padding:10px 11px!important;background:#fbfcfe!important;border-bottom:1px solid #edf1f5!important}.panelTitle b{font-size:9px!important;color:#214b77!important}.sourceTag{font-size:5px!important;border-radius:999px!important;background:#fff5cf!important;color:#755600!important}
.liveSummary{background:#f8fafc!important}.livegrid{padding:0 9px 10px!important;gap:7px!important}.mini{border-radius:9px!important;background:#f8fafc!important;border-color:#e3e9ef!important;box-shadow:none!important}.mini b{font-size:9px!important}.mini span{font-size:7px!important}.notice{font-size:8px!important;line-height:1.45!important;padding:10px!important}.table{font-size:8px!important}.table th{font-size:7px!important}.pill{font-size:7px!important}
.v12BhavHead{padding:11px!important;background:linear-gradient(135deg,#061b3d,#0a4f9f)!important}.v12BhavHead b{font-size:10px!important}.v12Book{padding:8px 10px!important}.v12Odd{font-size:10px!important}.v12BhavNote{font-size:6px!important}
.v13GraphCard{border-radius:11px!important;border-color:#e0e7ee!important;box-shadow:none!important}.v13GraphTitle{background:#fafbfd!important}.v13Chart svg{height:140px!important}

/* Fixed mobile navigation */
.bottom{background:rgba(255,255,255,.97)!important;backdrop-filter:blur(14px)!important;border-top:1px solid #dce4ed!important;box-shadow:0 -6px 20px rgba(7,31,63,.07)!important}.bottomInner{height:67px!important;padding:5px 7px!important}.bottomItem{border-radius:11px!important;color:#8a99aa!important;font-size:7px!important}.bottomItem .ico{font-size:16px!important}.bottomItem.active{background:#eef5fd!important;color:#0b4d94!important}.bottomItem.active .ico{color:#0b4d94!important}

/* Motion and accessibility */
@media(prefers-reduced-motion:no-preference){.match,.detailTab,.tab,.v12Sport,.v12Filter,.bottomItem{transition:.16s ease!important}.leagueBlock{animation:v15fade .20s ease both}@keyframes v15fade{from{opacity:.25;transform:translateY(3px)}to{opacity:1;transform:none}}}
@media(min-width:600px){.v15ArenaHero{padding:18px}.v15HeroStats{max-width:440px}.leagueMatches{grid-template-columns:1fr 1fr!important}.detailWrap{max-width:720px!important}}
'''
    html = html.replace("</style>", css + "\n</style>", 1)

    js = r'''
<script>
(function(){
  let lastItems=[];
  let lastMode='live';

  function haptic(kind='light'){
    try{const h=window.Telegram?.WebApp?.HapticFeedback;if(h)h.impactOccurred(kind)}catch(e){}
  }

  function ensureHero(){
    const home=document.getElementById('home');
    const command=document.getElementById('v12Command');
    if(!home||!command||document.getElementById('v15ArenaHero')) return;
    const hero=document.createElement('section');
    hero.id='v15ArenaHero';hero.className='v15ArenaHero';
    hero.innerHTML=`<div class="v15HeroTop"><div><div class="v15HeroEyebrow">IBETIN SPORTS INTELLIGENCE</div><div class="v15HeroTitle">Cricket Live Center</div></div><div class="v15HeroPill">FAST · CLEAN · LIVE</div></div><div class="v15HeroStats"><div class="v15HeroStat"><b id="v15LiveCount">0</b><span>LIVE MATCHES</span></div><div class="v15HeroStat"><b id="v15TourCount">0</b><span>TOURNAMENTS</span></div><div class="v15HeroStat"><b id="v15PinCount">0</b><span>PINNED</span></div></div>`;
    command.insertAdjacentElement('beforebegin',hero);
  }

  function refreshHero(items,mode){
    ensureHero();
    const live=document.getElementById('v15LiveCount'),tour=document.getElementById('v15TourCount'),pin=document.getElementById('v15PinCount');
    if(live) live.textContent=mode==='live'?String((items||[]).length):'—';
    const leagues=new Set((items||[]).map(m=>String(m?.league?.name||'').trim()).filter(Boolean));
    if(tour) tour.textContent=String(leagues.size);
    try{const pins=new Set(JSON.parse(localStorage.getItem('ibetin-v13-pins')||'[]'));if(pin)pin.textContent=String(pins.size)}catch(e){if(pin)pin.textContent='0'}
  }

  const oldRender=window.renderMatches;
  window.renderMatches=function(items,mode){
    lastItems=Array.isArray(items)?items:[];lastMode=mode||'live';
    oldRender(items,mode);
    refreshHero(lastItems,lastMode);
    document.querySelectorAll('#list .match').forEach(card=>{
      card.setAttribute('role','button');card.setAttribute('tabindex','0');
      card.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();card.click()}});
      card.addEventListener('click',()=>haptic('light'),{once:true});
    });
  };

  const oldDetail=window.renderDetail;
  window.renderDetail=function(){oldDetail();haptic('medium');setTimeout(()=>{document.querySelectorAll('.detailTab').forEach(b=>b.addEventListener('click',()=>haptic('light')))},0)};

  // Make top-level controls feel native in Telegram.
  setTimeout(()=>{
    ensureHero();
    refreshHero(lastItems,lastMode);
    document.querySelectorAll('.tab,.v12Sport,.v12Filter,.bottomItem,.v13Pin').forEach(el=>el.addEventListener('click',()=>haptic('light')));
    const sub=document.querySelector('.brandText span');if(sub)sub.textContent='SPORTS LIVE CENTER · PRIVATE TEST';
    try{window.Telegram?.WebApp?.setHeaderColor('#061b3d');window.Telegram?.WebApp?.setBackgroundColor('#f2f5f9')}catch(e){}
  },90);

  // Update pinned count whenever the user taps a pin.
  document.addEventListener('click',e=>{
    if(!e.target.closest('.v13Pin'))return;
    setTimeout(()=>refreshHero(lastItems,lastMode),25);
  });
})();
</script>
'''
    html = html.replace("</body>", js + "\n</body>")
    html = html.replace("ELITE SPORTS COMMAND CENTER · API-SAVER TEST", "ARENA SPORTS COMMAND CENTER · PRIVATE TEST")
    return html


liveline.admin_url = _v15_admin_url
liveline._page = _v15_page

app = v14.app

logger.info("IBETIN Live Line V15 Arena UI installed on private test route")

if __name__ == "__main__":
    app.base.ibetin_start.main()
