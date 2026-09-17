import logging
import os
from urllib.parse import parse_qs, urlencode, urlparse

import ibetin_liveline_trial as liveline
import ibetin_liveline_sections_test_start as sections

logger = logging.getLogger(__name__)

# V12 remains a private /liveline test build. A fresh route prevents Telegram
# Android WebView from reusing an older cached preview.
liveline.LIVELINE_PATH = "/admin/liveline-ibetinv12"
liveline.LIVELINE_API_PATH = "/admin/liveline-ibetinv12/api"


def _v12_admin_url() -> str:
    root = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/") or "https://ibetin-app-production.up.railway.app"
    return f"{root}{liveline.LIVELINE_PATH}?{urlencode({'t': liveline._token(), 'v': '20260917-v12-command-center'})}"


# Keep the currently installed match/score/Roanuz API behavior and add an
# isolated Highlightly PRO odds action for the new BHAV tab.
_previous_api = liveline._api


def _normalize_bhav(match_id: str, odds_type: str):
    params = {
        "matchId": match_id,
        "oddsType": odds_type,
        "limit": 50,
        "offset": 0,
    }
    data = liveline._highlightly("/cricket/odds", params, ttl=45)
    rows = data if isinstance(data, list) else []
    record = None
    for row in rows:
        if isinstance(row, dict) and str(row.get("matchId") or "") == match_id:
            record = row
            break
    if record is None and rows and isinstance(rows[0], dict):
        record = rows[0]
    odds = record.get("odds") if isinstance(record, dict) else []
    if not isinstance(odds, list):
        odds = []

    preferred = {
        "bet365": 0,
        "stake.com": 1,
        "unibet": 2,
        "parimatch": 3,
        "fanduel": 4,
    }
    normalized = []
    for item in odds:
        if not isinstance(item, dict):
            continue
        market = str(item.get("market") or "").strip()
        if market and market.casefold() != "match winner":
            continue
        values = item.get("values") or item.get("odds") or []
        if not isinstance(values, list):
            values = []
        clean_values = []
        for value in values:
            if not isinstance(value, dict):
                continue
            label = str(value.get("value") or value.get("name") or value.get("label") or "").strip()
            odd = value.get("odd")
            if label and odd not in (None, ""):
                clean_values.append({"label": label, "odd": odd})
        if not clean_values:
            continue
        normalized.append(
            {
                "bookmaker": str(item.get("bookmakerName") or item.get("bookmaker") or "Bookmaker"),
                "bookmakerId": item.get("bookmakerId"),
                "type": str(item.get("type") or odds_type),
                "market": market or "Match Winner",
                "values": clean_values,
            }
        )
    normalized.sort(key=lambda x: preferred.get(x["bookmaker"].casefold(), 50))
    return normalized[:12]


def _v12_api(handler):
    query = parse_qs(urlparse(handler.path).query)
    action = (query.get("action") or [""])[0].strip().lower()
    if action != "bhav":
        return _previous_api(handler)

    try:
        match_id = (query.get("matchId") or query.get("id") or [""])[0].strip()
        if not match_id or not match_id.isdigit():
            liveline._send_json(handler, 400, {"ok": False, "error": "Invalid match id"})
            return
        requested = (query.get("oddsType") or ["live"])[0].strip().lower()
        odds_type = requested if requested in {"live", "prematch"} else "live"
        entries = _normalize_bhav(match_id, odds_type)
        used_type = odds_type
        # A live match can temporarily have no in-play market. In that case show
        # the latest prematch market rather than a blank tab, clearly labelled.
        if not entries and odds_type == "live":
            entries = _normalize_bhav(match_id, "prematch")
            used_type = "prematch" if entries else "live"
        liveline._send_json(
            handler,
            200,
            {
                "ok": True,
                "matchId": match_id,
                "oddsType": used_type,
                "requestedType": odds_type,
                "market": "Match Winner",
                "source": "Highlightly PRO",
                "entries": entries,
            },
        )
    except Exception as exc:
        logger.exception("IBETIN V12 BHAV API failed")
        liveline._send_json(handler, 502, {"ok": False, "error": str(exc)})


liveline._api = _v12_api


def _v12_page() -> str:
    html = sections._sections_page()

    css = r'''
/* V12 — IBETIN Sports Command Center */
:root{
  --v12-navy:#061f46;--v12-blue:#073b83;--v12-blue2:#0b5fc5;
  --v12-gold:#ffc928;--v12-goldSoft:#fff7d6;--v12-surface:#ffffff;
  --v12-bg:#edf3f9;--v12-line:#d5e1ee;--v12-ink:#102f55;--v12-muted:#6d8299;
  --v12-green:#11855d;--v12-red:#e6384f;
}
html,body{background:var(--v12-bg)!important}
.topShell{background:linear-gradient(120deg,#061f46 0%,#073b83 60%,#0b55ad 100%)!important;border-top:3px solid var(--v12-gold)!important}
.brandRow{height:62px!important}
.brandMark{border-radius:11px!important;transform:rotate(-2deg)}
.brandText b{letter-spacing:1px!important}.brandText span{opacity:.88!important}
.liveChip:after{content:'V12 TEST'!important}

/* Sports command bar */
.v12Command{margin:0 0 12px;background:linear-gradient(145deg,#fff,#f7fbff);border:1px solid #cbdbea;border-radius:16px;box-shadow:0 8px 22px rgba(9,48,100,.08);overflow:hidden}
.v12Sports{display:flex;gap:7px;overflow:auto;padding:10px 10px 8px;scrollbar-width:none}.v12Sports::-webkit-scrollbar{display:none}
.v12Sport{border:1px solid #d6e1ed;background:#f8fbff;color:#58718d;border-radius:999px;padding:8px 11px;font-size:9px;font-weight:950;white-space:nowrap;display:flex;align-items:center;gap:5px}
.v12Sport.active{background:linear-gradient(180deg,#0b55ad,#073b83);border-color:#073b83;color:#fff;box-shadow:0 4px 10px rgba(7,59,131,.16)}
.v12Sport .soon{font-size:6px;background:#e8eef6;color:#7890aa;border-radius:999px;padding:2px 4px}.v12Sport.active .soon{display:none}
.v12SearchRow{display:grid;grid-template-columns:1fr auto;gap:8px;padding:0 10px 9px}
.v12SearchBox{display:flex;align-items:center;gap:8px;background:#fff;border:1px solid #cfdeec;border-radius:11px;padding:0 10px;min-height:40px;box-shadow:inset 0 1px 2px rgba(15,55,100,.02)}
.v12SearchBox span{font-size:14px}.v12SearchBox input{width:100%;border:0;outline:0;background:transparent;color:#153b68;font-size:11px;font-weight:750}
.v12SearchBox input::placeholder{color:#94a5b7;font-weight:650}
.v12Clear{border:1px solid #d1dfec;background:#fff;color:#315b87;border-radius:11px;padding:0 11px;font-size:9px;font-weight:950}
.v12Filters{display:flex;gap:6px;overflow:auto;padding:0 10px 10px;scrollbar-width:none}.v12Filters::-webkit-scrollbar{display:none}
.v12Filter{border:1px solid #d4e0ec;background:#fff;color:#607892;border-radius:9px;padding:7px 10px;font-size:8px;font-weight:950;white-space:nowrap}
.v12Filter.active{background:var(--v12-goldSoft);border-color:#f1c538;color:#634a00;box-shadow:0 3px 8px rgba(255,193,25,.12)}
.v12QuickStat{display:flex;align-items:center;justify-content:space-between;gap:8px;border-top:1px solid #e0e8f1;padding:8px 10px;background:#f8fbff;color:#72869d;font-size:8px;font-weight:800}
.v12QuickStat strong{color:#174b83}.v12FeedDot{display:inline-block;width:6px;height:6px;border-radius:50%;background:#1b9d6b;margin-right:5px}

/* Make hierarchy calmer and easier to scan */
.dayHead{margin-top:5px!important}.dayTitle{font-size:11px!important}.dayDot{background:#0a55b3!important;box-shadow:0 0 0 4px rgba(10,85,179,.10)!important}
.leagueBlock{border-radius:15px!important;border-color:#cfdeeb!important;box-shadow:0 5px 16px rgba(13,53,98,.055)!important}
.leagueSectionHead{background:#fff!important;color:#133f72!important;border-bottom:1px solid #d8e3ee!important;padding:10px 11px!important}
.leagueIcon{background:#eaf3ff!important;color:#0a4f9f!important;box-shadow:none!important;border:1px solid #cfe1f4!important}
.leagueSectionName{font-size:10px!important}.leagueSectionMeta{color:#8296aa!important}.leagueCount{background:#f0f5fb!important;border-color:#d8e3ee!important;color:#5d7690!important}
.leagueMatches{background:#f8fbfe!important;padding:8px!important}
.leagueMatches .match{border:1px solid #d5e1ed!important;border-radius:12px!important;box-shadow:0 3px 9px rgba(10,48,96,.045)!important}
.leagueMatches .match:before{width:3px!important}.leagueMatches .matchHead{background:#fff!important}.leagueMatches .format{color:#315f8e!important}
.leagueMatches .matchFoot{background:#f8fbff!important}.leagueMatches .arrow{border-radius:8px!important}
.v12Hidden{display:none!important}
.v12NoResults{background:#fff;border:1px solid #d3e0ec;border-radius:14px;padding:22px 14px;text-align:center;color:#73869b;font-size:10px;margin:8px 0}

/* Live Pulse */
.v12Pulse{margin:0 0 10px;border-radius:14px;overflow:hidden;background:linear-gradient(135deg,#061f46,#0a4d9f);color:#fff;box-shadow:0 10px 24px rgba(8,48,102,.16);border:1px solid #174f8f}
.v12PulseTop{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:10px 12px;border-bottom:1px solid rgba(255,255,255,.12)}
.v12PulseTop b{font-size:9px;letter-spacing:.65px}.v12PulseBadge{background:#e6384f;border-radius:999px;padding:4px 7px;font-size:7px;font-weight:1000}
.v12PulseBody{padding:12px}.v12PulseMain{font-size:13px;font-weight:1000;line-height:1.45}.v12PulseSub{margin-top:5px;color:#c9dcf4;font-size:9px;line-height:1.45}
.v12PulseGrid{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-top:10px}.v12PulseStat{background:rgba(255,255,255,.09);border:1px solid rgba(255,255,255,.12);border-radius:9px;padding:8px;text-align:center}.v12PulseStat b{display:block;color:#ffdf74;font-size:10px}.v12PulseStat span{display:block;color:#bcd0e9;font-size:7px;margin-top:3px}

/* BHAV */
.v12BhavHead{padding:13px 12px;background:linear-gradient(135deg,#062958,#084a98);color:#fff}.v12BhavHeadLine{display:flex;align-items:center;justify-content:space-between;gap:8px}.v12BhavHead b{font-size:12px}.v12BhavHead small{display:block;margin-top:5px;color:#c9dcf3;font-size:8px}.v12MarketTag{background:var(--v12-gold);color:#17345a;border-radius:999px;padding:5px 8px;font-size:7px;font-weight:1000}
.v12BhavTeams{display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:10px 11px 4px}.v12BhavTeam{background:#f5f9fe;border:1px solid #d7e4f0;border-radius:10px;padding:9px;text-align:center;color:#193f6d;font-size:9px;font-weight:950}
.v12Book{display:grid;grid-template-columns:minmax(78px,1.3fr) 1fr 1fr;align-items:center;gap:7px;padding:9px 11px;border-top:1px solid #e2eaf2}.v12BookName{min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#4e6680;font-size:8px;font-weight:900}.v12Odd{background:#edf5ff;border:1px solid #cee0f4;border-radius:9px;padding:8px 5px;text-align:center;color:#0b4e9d;font-size:11px;font-weight:1000}.v12Odd span{display:block;color:#7790a9;font-size:6px;margin-bottom:3px;text-transform:uppercase}.v12BhavNote{padding:9px 11px;background:#fff9e4;color:#745e16;border-top:1px solid #f4e3a1;font-size:7px;line-height:1.45}

/* Better detail tabs */
.detailTabs{position:sticky;top:0;z-index:8;background:var(--v12-bg)!important;padding-top:4px!important}
.detailTab{font-size:8px!important;padding:9px 10px!important}.detailTab.active{background:#073b83!important;border-color:#073b83!important}

/* Bottom nav: all five controls functional in V12 */
.bottomInner{grid-template-columns:repeat(5,1fr)!important}.bottomItem:last-child{cursor:pointer}
@media(min-width:600px){.v12Command{margin-left:auto;margin-right:auto}.v12BhavTeams{padding-left:16px;padding-right:16px}.v12Book{padding-left:16px;padding-right:16px}}
'''
    html = html.replace("</style>", css + "\n</style>", 1)

    js = r'''
<script>
(function(){
  const state={query:'',format:'all',items:[],mode:'live'};

  function installCommandCenter(){
    const home=document.getElementById('home');
    const title=home&&home.querySelector('.sectionTitle');
    if(!home||!title||document.getElementById('v12Command')) return;
    const box=document.createElement('div');
    box.id='v12Command';
    box.className='v12Command';
    box.innerHTML=`
      <div class="v12Sports">
        <button class="v12Sport active" data-sport="cricket">🏏 Cricket</button>
        <button class="v12Sport" data-sport="football">⚽ Football <span class="soon">NEXT</span></button>
        <button class="v12Sport" data-sport="basketball">🏀 Basketball <span class="soon">NEXT</span></button>
        <button class="v12Sport" data-sport="more">＋ More Sports <span class="soon">NEXT</span></button>
      </div>
      <div class="v12SearchRow">
        <label class="v12SearchBox"><span>⌕</span><input id="v12Search" autocomplete="off" placeholder="Search team, tournament or match"></label>
        <button class="v12Clear" id="v12Clear">CLEAR</button>
      </div>
      <div class="v12Filters">
        <button class="v12Filter active" data-format="all">ALL</button>
        <button class="v12Filter" data-format="t20">T20</button>
        <button class="v12Filter" data-format="odi">ODI</button>
        <button class="v12Filter" data-format="test">TEST</button>
        <button class="v12Filter" data-format="women">WOMEN</button>
      </div>
      <div class="v12QuickStat"><span><span class="v12FeedDot"></span><strong>Roanuz + Highlightly</strong> connected</span><span id="v12VisibleCount">—</span></div>`;
    home.insertBefore(box,title);

    const search=document.getElementById('v12Search');
    search.addEventListener('input',()=>{state.query=search.value.trim().toLowerCase();applyFilters()});
    document.getElementById('v12Clear').addEventListener('click',()=>{search.value='';state.query='';state.format='all';document.querySelectorAll('.v12Filter').forEach(x=>x.classList.toggle('active',x.dataset.format==='all'));applyFilters();search.focus()});
    box.querySelectorAll('.v12Filter').forEach(btn=>btn.addEventListener('click',()=>{state.format=btn.dataset.format;box.querySelectorAll('.v12Filter').forEach(x=>x.classList.toggle('active',x===btn));applyFilters()}));
    box.querySelectorAll('.v12Sport:not(.active)').forEach(btn=>btn.addEventListener('click',()=>{
      const old=btn.querySelector('.soon');
      if(old){const prev=old.textContent;old.textContent='SOON';setTimeout(()=>old.textContent=prev,1200)}
    }));
  }

  function cardPasses(card){
    const txt=(card.textContent||'').toLowerCase();
    if(state.query&&!txt.includes(state.query)) return false;
    if(state.format==='all') return true;
    if(state.format==='women') return /women|womens|women's|\bw\b/.test(txt);
    const fmt=(card.querySelector('.format')?.textContent||'').toLowerCase();
    if(state.format==='t20') return /t20|twenty/.test(fmt);
    if(state.format==='odi') return /odi|one day/.test(fmt);
    if(state.format==='test') return /test|first class/.test(fmt);
    return true;
  }

  function applyFilters(){
    let visible=0;
    document.querySelectorAll('#list .match').forEach(card=>{const yes=cardPasses(card);card.classList.toggle('v12Hidden',!yes);if(yes)visible++});
    document.querySelectorAll('#list .leagueBlock').forEach(block=>{const yes=[...block.querySelectorAll('.match')].some(x=>!x.classList.contains('v12Hidden'));block.classList.toggle('v12Hidden',!yes)});
    document.querySelectorAll('#list .dayBlock').forEach(block=>{const yes=[...block.querySelectorAll('.match')].some(x=>!x.classList.contains('v12Hidden'));block.classList.toggle('v12Hidden',!yes)});
    const count=document.getElementById('v12VisibleCount');if(count)count.textContent=visible+' shown';
    let empty=document.getElementById('v12NoResults');
    if(!visible&&state.items.length){if(!empty){empty=document.createElement('div');empty.id='v12NoResults';empty.className='v12NoResults';empty.innerHTML='<b>No matches found</b><br><br>Try another team, tournament or format.';document.getElementById('list').appendChild(empty)}}else if(empty)empty.remove();
  }

  installCommandCenter();
  const oldRenderMatches=window.renderMatches;
  window.renderMatches=function(items,mode){state.items=Array.isArray(items)?items:[];state.mode=mode;oldRenderMatches(items,mode);applyFilters()};

  // Make the fifth bottom action useful instead of leaving an inactive control.
  const bottom=[...document.querySelectorAll('.bottomItem')];
  if(bottom[4]){
    bottom[4].innerHTML='<span class="ico">⌕</span><span>SEARCH</span>';
    bottom[4].onclick=function(){backHome();setTimeout(()=>{const s=document.getElementById('v12Search');if(s){s.focus();s.scrollIntoView({behavior:'smooth',block:'center'})}},30)};
  }
  if(bottom[0]) bottom[0].querySelector('span:last-child').textContent='CENTER';

  function pulseValue(obj,names){for(const name of names){if(obj&&obj[name]!==undefined&&obj[name]!==null&&obj[name]!=='')return obj[name]}return '—'}
  function decorateDetail(){
    const detail=document.getElementById('detail');
    const hero=detail&&detail.querySelector('.scoreHero');
    if(!hero||detail.querySelector('.v12Pulse'))return;
    const x=currentDetail||{},m=x.match||{},inp=x.inplayData||{};
    const pulse=document.createElement('div');pulse.className='v12Pulse';
    const isLive=/in play|live|innings|stumps|lunch|tea|drinks/i.test(String(m.state||''));
    const bats=inp.batsmen||[],bowl=inp.bowlers||[];
    const striker=bats[0]||{},bowler=bowl[0]||{};
    const main=m.report||m.state||'Match Center';
    pulse.innerHTML=`<div class="v12PulseTop"><b>⚡ LIVE PULSE</b><span class="v12PulseBadge">${isLive?'LIVE':'MATCH'}</span></div><div class="v12PulseBody"><div class="v12PulseMain">${esc(main)}</div><div class="v12PulseSub">Instant situation view · detailed score, balls and bhav below</div><div class="v12PulseGrid"><div class="v12PulseStat"><b>${esc(pulseValue(striker?.player?.statistics||striker,['runs']))}</b><span>STRIKER RUNS</span></div><div class="v12PulseStat"><b>${esc(pulseValue(bowler?.player?.statistics||bowler,['wickets']))}</b><span>BOWLER WKTS</span></div><div class="v12PulseStat"><b>${esc((x.timeline||[]).length)}</b><span>LIVE EVENTS</span></div></div></div>`;
    hero.insertAdjacentElement('afterend',pulse);
  }

  const oldRenderDetail=window.renderDetail;
  window.renderDetail=function(){oldRenderDetail();decorateDetail()};

  // Replace only the tab labels/order. Existing internal keys continue to drive
  // the original renderers, so Scorecard/Commentary/Stats/Info stay untouched.
  window.tabs=function(){return [['live','MATCH'],['bhav','BHAV'],['scorecard','SCORECARD'],['commentary','BALLS'],['stats','STATS'],['info','INFO']].map(([x,label])=>`<button class="detailTab ${currentTab===x?'active':''}" data-tab="${x}">${label}</button>`).join('')};

  const oldRenderPanel=window.renderPanel;
  const bhavCache=new Map();
  function oddsTypeForMatch(m){return /in play|live|innings|stumps|lunch|tea|drinks/i.test(String(m?.state||''))?'live':'prematch'}
  function teamLabel(label,m){const x=String(label||'').toLowerCase();if(x==='home')return m?.home?.abbr||m?.home?.name||'Home';if(x==='away')return m?.away?.abbr||m?.away?.name||'Away';return label||'—'}
  function bhavHtml(j,m){
    const entries=j?.entries||[];
    if(!entries.length)return `<div class="v12BhavHead"><div class="v12BhavHeadLine"><b>BHAV · MATCH WINNER</b><span class="v12MarketTag">${esc((j?.oddsType||'').toUpperCase())}</span></div><small>Highlightly PRO market feed</small></div><div class="notice"><b>Bhav is not available for this match right now.</b><br>Scores and live line continue normally.</div>`;
    const rows=entries.map(e=>{const vals=e.values||[];const a=vals[0]||{},b=vals[1]||{};return `<div class="v12Book"><div class="v12BookName">${esc(e.bookmaker||'Bookmaker')}</div><div class="v12Odd"><span>${esc(teamLabel(a.label,m))}</span>${n(a.odd)}</div><div class="v12Odd"><span>${esc(teamLabel(b.label,m))}</span>${n(b.odd)}</div></div>`}).join('');
    return `<div class="v12BhavHead"><div class="v12BhavHeadLine"><b>BHAV · MATCH WINNER</b><span class="v12MarketTag">${esc((j.oddsType||'').toUpperCase())}</span></div><small>${esc(j.source||'Highlightly PRO')} · Multiple bookmaker prices</small></div><div class="v12BhavTeams"><div class="v12BhavTeam">${esc(m?.home?.name||'Home')}</div><div class="v12BhavTeam">${esc(m?.away?.name||'Away')}</div></div>${rows}<div class="v12BhavNote">Odds are informational market data and can change. Session/fancy markets are not shown unless a provider supplies them directly.</div>`;
  }
  window.renderPanel=function(){
    if(currentTab!=='bhav')return oldRenderPanel();
    const p=document.getElementById('panel'),m=(currentDetail||{}).match||{};
    const type=oddsTypeForMatch(m),key=String(m.id||'')+':'+type;
    p.innerHTML='<div class="loading"><div class="spin"></div>Loading bhav…</div>';
    if(bhavCache.has(key)){p.innerHTML=bhavHtml(bhavCache.get(key),m);return}
    api({action:'bhav',matchId:m.id,oddsType:type}).then(j=>{bhavCache.set(key,j);if(currentTab==='bhav')p.innerHTML=bhavHtml(j,m)}).catch(e=>{if(currentTab==='bhav')p.innerHTML=`<div class="notice"><b>Bhav feed unavailable</b><br>${esc(e.message)}</div>`});
  };

  // The base page already loaded live matches before this script executes.
  // Re-render once so the V12 wrapper owns the current list and filter state.
  if(window.currentMode) setTimeout(()=>loadMode(currentMode),25);
})();
</script>
'''
    html = html.replace("</body>", js + "\n</body>")
    html = html.replace("CRICKET LIVE LINE · TEST MODE", "SPORTS COMMAND CENTER · TEST MODE")
    return html


liveline.admin_url = _v12_admin_url
liveline._page = _v12_page

app = sections.app

logger.info("IBETIN Live Line V12 command center installed on private test route")

if __name__ == "__main__":
    app.base.ibetin_start.main()
