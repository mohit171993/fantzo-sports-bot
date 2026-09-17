import os
from urllib.parse import urlencode

import ibetin_liveline_trial as liveline
import ibetin_liveline_premium_test_start as premium

# Dedicated private TEST route for the clearer sectioned match list.
liveline.LIVELINE_PATH = "/admin/liveline-ibetinv11"
liveline.LIVELINE_API_PATH = "/admin/liveline-ibetinv11/api"


def _sections_admin_url() -> str:
    root = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/") or "https://ibetin-app-production.up.railway.app"
    return f"{root}{liveline.LIVELINE_PATH}?{urlencode({'t': liveline._token(), 'v': '20260917-v11-sections-test'})}"


def _sections_page() -> str:
    html = premium._premium_page()

    css = r'''
/* V11 — clearer match hierarchy: date > tournament > match */
.list{display:block!important}
.dayBlock{margin:0 0 16px}
.dayHead{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:2px 1px 8px;padding:0 2px}
.dayHeadLeft{display:flex;align-items:center;gap:8px;min-width:0}
.dayDot{width:8px;height:8px;border-radius:50%;background:var(--ibt-gold);box-shadow:0 0 0 4px rgba(255,201,40,.18);flex:none}
.dayTitle{font-size:12px;font-weight:1000;color:#123f75;letter-spacing:.2px;text-transform:uppercase}
.dayCount{font-size:8px;font-weight:900;color:#778aa1;background:#e7eef7;border:1px solid #d1deeb;padding:5px 7px;border-radius:999px;white-space:nowrap}
.leagueBlock{background:#fff;border:1px solid #cbd9e8;border-radius:14px;overflow:hidden;box-shadow:0 5px 16px rgba(15,57,112,.07);margin-bottom:10px}
.leagueSectionHead{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px 12px;background:linear-gradient(90deg,#082f68,#0a4c9d);color:#fff}
.leagueSectionLeft{display:flex;align-items:center;gap:9px;min-width:0}
.leagueIcon{width:28px;height:28px;border-radius:8px;background:#ffc928;color:#082d63;display:grid;place-items:center;font-size:12px;font-weight:1000;flex:none;box-shadow:0 3px 8px rgba(0,0,0,.12)}
.leagueSectionText{min-width:0}
.leagueSectionName{font-size:10px;font-weight:1000;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;letter-spacing:.15px}
.leagueSectionMeta{font-size:7px;color:#c9ddfa;margin-top:3px;text-transform:uppercase;letter-spacing:.5px}
.leagueCount{font-size:8px;font-weight:1000;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.18);padding:5px 7px;border-radius:999px;white-space:nowrap}
.leagueMatches{padding:9px;background:#f5f8fc;display:grid;gap:9px}
.leagueMatches .match{box-shadow:0 3px 10px rgba(15,57,112,.06)!important;border-radius:11px!important;margin:0!important}
.leagueMatches .matchHead{background:#eaf2fb!important;border-bottom:1px solid #d4e0ec!important;padding:8px 10px 8px 12px!important}
.leagueMatches .league{display:none!important}.leagueMatches .format{color:#597797!important;margin-top:0!important;font-weight:900!important;text-transform:uppercase!important}
.leagueMatches .badgeLive{font-size:7px!important}.leagueMatches .badgeState{font-size:7px!important}
.leagueMatches .matchBody{padding:7px 10px 6px 12px!important}.leagueMatches .team{min-height:45px!important}.leagueMatches .teamBadge{width:34px!important;height:34px!important}
.leagueMatches .score{font-size:17px!important}.leagueMatches .matchFoot{padding:8px 10px 8px 12px!important}.leagueMatches .arrow{width:23px!important;height:23px!important}
.sectionGuide{display:flex;align-items:center;gap:6px;overflow:auto;margin:0 0 10px;padding-bottom:2px;scrollbar-width:none}.sectionGuide::-webkit-scrollbar{display:none}
.guideChip{white-space:nowrap;background:#fff;border:1px solid #cedbe9;border-radius:999px;padding:6px 9px;color:#5e7691;font-size:8px;font-weight:900}
.guideChip strong{color:#0a4a99}
@media(min-width:600px){.leagueMatches{grid-template-columns:1fr 1fr}.leagueMatches .match{min-height:185px!important}}
'''
    html = html.replace("</style>", css + "\n</style>", 1)

    js = r'''
<script>
(function(){
  function safeDate(raw){
    if(!raw) return null;
    const d=new Date(raw);
    return Number.isNaN(d.getTime())?null:d;
  }
  function dateKey(m){
    const d=safeDate(m.startTime||m.startDate);
    if(!d) return 'unknown';
    return [d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-');
  }
  function dateLabel(key,mode){
    if(key==='live') return 'Live Now';
    if(key==='unknown') return mode==='results'?'Earlier Results':'Other Matches';
    const d=new Date(key+'T12:00:00');
    const now=new Date();
    const today=new Date(now.getFullYear(),now.getMonth(),now.getDate());
    const that=new Date(d.getFullYear(),d.getMonth(),d.getDate());
    const diff=Math.round((that-today)/86400000);
    if(diff===0) return 'Today · '+d.toLocaleDateString([], {day:'numeric',month:'short'});
    if(diff===1) return 'Tomorrow · '+d.toLocaleDateString([], {day:'numeric',month:'short'});
    if(diff===-1) return 'Yesterday · '+d.toLocaleDateString([], {day:'numeric',month:'short'});
    return d.toLocaleDateString([], {weekday:'short',day:'numeric',month:'short'});
  }
  function leagueName(m){return (m?.league?.name||'Other Cricket').trim()||'Other Cricket'}
  function matchCard(m,mode){
    return `<div class="match ${mode==='live'?'liveCard':''}" data-id="${esc(m.id)}"><div class="matchHead"><div class="leagueBox"><div class="league">${esc(leagueName(m))}</div><div class="format">${esc(m.format||m.dayType||'CRICKET')}</div></div>${modeBadge(mode,m)}</div><div class="matchBody">${teamLine(m.home,m.homeScore,m.homeInfo)}<div class="divider"></div>${teamLine(m.away,m.awayScore,m.awayInfo)}</div><div class="matchFoot"><div class="report">${esc(m.report||fmtTime(m.startTime)||m.state||'Tap for match details')}</div><div class="arrow">›</div></div></div>`;
  }
  function sectionHtml(title,items,mode){
    const byLeague=new Map();
    items.forEach(m=>{const k=leagueName(m);if(!byLeague.has(k))byLeague.set(k,[]);byLeague.get(k).push(m)});
    const leagues=[...byLeague.entries()].sort((a,b)=>b[1].length-a[1].length||a[0].localeCompare(b[0]));
    return `<section class="dayBlock"><div class="dayHead"><div class="dayHeadLeft"><span class="dayDot"></span><div class="dayTitle">${esc(title)}</div></div><div class="dayCount">${items.length} match${items.length===1?'':'es'}</div></div>${leagues.map(([league,matches])=>`<div class="leagueBlock"><div class="leagueSectionHead"><div class="leagueSectionLeft"><div class="leagueIcon">I</div><div class="leagueSectionText"><div class="leagueSectionName">${esc(league)}</div><div class="leagueSectionMeta">${mode==='live'?'LIVE TOURNAMENT':mode==='upcoming'?'UPCOMING FIXTURES':'COMPLETED MATCHES'}</div></div></div><div class="leagueCount">${matches.length}</div></div><div class="leagueMatches">${matches.map(m=>matchCard(m,mode)).join('')}</div></div>`).join('')}</section>`;
  }
  window.renderMatches=function(items,mode){
    const list=document.getElementById('list');
    if(!items.length){
      const msg=mode==='live'?'No live cricket matches right now.':mode==='upcoming'?'No upcoming matches found in the next few days.':'No recent results found.';
      list.innerHTML=`<div class="empty"><div class="emptyIcon">🏏</div><b>${msg}</b><div style="margin-top:7px">Check another section.</div></div>`;
      return;
    }
    const groups=new Map();
    items.forEach(m=>{
      const k=mode==='live'?'live':dateKey(m);
      if(!groups.has(k))groups.set(k,[]);
      groups.get(k).push(m);
    });
    let keys=[...groups.keys()];
    if(mode==='upcoming') keys.sort((a,b)=>a==='unknown'?1:b==='unknown'?-1:a.localeCompare(b));
    else if(mode==='results') keys.sort((a,b)=>a==='unknown'?1:b==='unknown'?-1:b.localeCompare(a));
    const guide=mode==='live'
      ? '<div class="sectionGuide"><span class="guideChip"><strong>LIVE</strong> grouped by tournament</span></div>'
      : `<div class="sectionGuide"><span class="guideChip"><strong>${mode==='upcoming'?'UPCOMING':'RESULTS'}</strong> grouped by date</span><span class="guideChip">then by tournament</span></div>`;
    list.innerHTML=guide+keys.map(k=>sectionHtml(dateLabel(k,mode),groups.get(k),mode)).join('');
    list.querySelectorAll('.match').forEach(x=>x.addEventListener('click',()=>openMatch(x.dataset.id)));
  };
  const oldLoadMode=window.loadMode;
  window.loadMode=async function(mode){
    const name=document.getElementById('sectionName');
    if(name) name.textContent=mode==='live'?'Live Now · By Tournament':mode==='upcoming'?'Upcoming · By Date & Tournament':'Results · By Date & Tournament';
    return oldLoadMode(mode);
  };
})();
</script>
'''
    html = html.replace("</body>", js + "\n</body>")
    return html


liveline.admin_url = _sections_admin_url
liveline._page = _sections_page

app = premium.app

if __name__ == "__main__":
    app.base.ibetin_start.main()
