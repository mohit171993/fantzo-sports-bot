import logging
import re

import ibetin_liveline_v26_ui_polish as v26

logger = logging.getLogger(__name__)
v25 = v26.v25
_ORIGINAL_PAGE = v26._page_v26


def _page_v27() -> str:
    html = _ORIGINAL_PAGE()

    # Consumer-facing naming: keep the product simple and remove terminal language.
    html = html.replace("LIVE CRICKET TERMINAL", "LIVE CRICKET", 1)

    premium_css = r"""
/* V27 premium consumer presentation only — no feed/provider logic changes. */
.scorehero{border:1px solid #e5ebf2;box-shadow:0 10px 28px rgba(6,39,78,.09);border-radius:18px!important}
.scoretop{padding:11px 13px!important;background:#fbfdff}.scoremain{padding:20px 14px!important;min-height:132px}
.side{min-width:0}.teamIdentity{display:flex;align-items:center;gap:7px;margin-bottom:6px}.side.right .teamIdentity{justify-content:flex-end}
.teamMark{width:34px;height:34px;border-radius:50%;background:linear-gradient(145deg,#eaf2fb,#dfeaf6);border:1px solid #d7e3ef;display:grid;place-items:center;overflow:hidden;flex:none;box-shadow:0 2px 7px rgba(9,52,98,.08)}
.teamMark img{width:100%;height:100%;object-fit:cover}.teamFallback{width:100%;height:100%;display:grid;place-items:center;font-size:10px;font-weight:1000;color:#0a4f98}
.sname{font-size:12px!important;font-weight:900!important}.sval{font-size:30px!important;letter-spacing:-.6px}.vs{width:36px!important;height:36px!important;font-size:9px!important;box-shadow:inset 0 0 0 1px #f0dfa4}
.report{padding:11px 13px!important;background:#fbfdff!important}.reportText{font-size:10px;font-weight:700;color:#506b85;margin-bottom:7px}
.chaseBox{margin-top:7px!important;background:linear-gradient(135deg,#edf6ff,#f7fbff)!important;border-color:#d6e8f8!important}.chaseBox b{font-size:13px!important}.chaseBox span{font-size:10px!important}
.dtabs{grid-template-columns:repeat(4,minmax(0,1fr))!important;gap:6px!important;margin:10px 0!important}.dtab{height:42px!important;font-size:9px!important;border:1px solid #e5ebf2!important;box-shadow:0 2px 8px rgba(6,37,70,.035)}.dtab.on{border-color:#0a315f!important}
.playerStrip{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:9px}.playerCard{background:#f7f9fc;border:1px solid #e8edf3;border-radius:11px;padding:9px 10px;min-width:0}.playerRole{font-size:7px;font-weight:1000;color:#8b9caf;letter-spacing:.6px;margin-bottom:4px}.playerName{font-size:10px;font-weight:900;color:#173a5e;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.playerStat{font-size:9px;color:#617b93;margin-top:3px}
.lastSix{display:flex;align-items:center;gap:5px;overflow:hidden;margin-top:9px}.lastSixTitle{font-size:7px;font-weight:1000;color:#8194a7;letter-spacing:.5px;margin-right:2px;white-space:nowrap}.ballChip{width:28px;height:28px;border-radius:50%;display:grid;place-items:center;background:#eaf1f8;color:#294d70;font-size:9px;font-weight:1000;flex:none}.ballChip.boundary{background:#e6f4ff;color:#0968b7}.ballChip.six{background:#efe9ff;color:#6943b5}.ballChip.wicket{background:#fff0f2;color:#d02f47}.ballChip.extra{background:#fff6db;color:#856200}
.moreGrid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.moreItem{border:1px solid #e5ebf2;background:#f8fafc;border-radius:12px;padding:13px 10px;text-align:left;color:#234766;font-size:10px;font-weight:900}.moreItem span{display:block;font-size:8px;font-weight:600;color:#7d90a3;margin-top:4px}
.premiumSnapshot{padding:11px!important}.metricRow{margin-top:0!important}
.bottom{grid-template-columns:repeat(4,1fr)!important;padding:7px!important;border-radius:18px!important}.bottom button{height:46px!important;font-size:9px!important}.bottom b{font-size:16px!important;margin-bottom:1px}
@media(max-width:390px){.sval{font-size:27px!important}.scoremain{padding:17px 10px!important}.playerStrip{grid-template-columns:1fr}.ballChip{width:26px;height:26px}.dtab{font-size:8px!important}}
"""
    html = html.replace('</style><link rel="icon" href="data:"></head>', premium_css + '</style><link rel="icon" href="data:"></head>', 1)

    # Cleaner four-item bottom navigation. Results remains directly available in the top tabs.
    html = re.sub(
        r'<nav class="bottom">.*?</nav>',
        '<nav class="bottom"><button class="on" data-nav="home"><b>⌂</b>HOME</button><button data-nav="live"><b style="color:#ff5b6f">●</b>LIVE</button><button data-nav="cricket"><b>◷</b>FIXTURES</button><button data-nav="more"><b>⌕</b>SEARCH</button></nav>',
        html,
        count=1,
        flags=re.S,
    )

    helpers = r"""
function teamInitials(t){const n=String(t?.name||t?.abbr||'TEAM').trim();const p=n.split(/\s+/).filter(Boolean);return (p.length>1?(p[0][0]+p[1][0]):n.slice(0,2)).toUpperCase()}
function teamMark(t){
  const u=t?.logo||t?.logoUrl||t?.image||t?.imageUrl||t?.flag||t?.flagUrl||'';
  const initials=esc(teamInitials(t));
  if(u)return `<span class="teamMark"><img src="${esc(u)}" alt="" onerror="this.style.display='none';this.nextElementSibling.style.display='grid'"><span class="teamFallback" style="display:none">${initials}</span></span>`;
  return `<span class="teamMark"><span class="teamFallback">${initials}</span></span>`;
}
function normKey(s){return String(s||'').toLowerCase().replace(/[^a-z0-9]/g,'')}
function deepFind(root,aliases,depth=0,seen){
  if(root===null||root===undefined||depth>5)return null;
  if(typeof root!=='object')return null;
  seen=seen||new Set();if(seen.has(root))return null;seen.add(root);
  const wanted=new Set(aliases.map(normKey));
  for(const [k,v] of Object.entries(root)){if(wanted.has(normKey(k))&&v!==null&&v!==undefined)return v}
  for(const v of Object.values(root)){if(v&&typeof v==='object'){const x=deepFind(v,aliases,depth+1,seen);if(x!==null&&x!==undefined)return x}}
  return null;
}
function playerInfo(v){
  if(v===null||v===undefined)return null;
  if(typeof v==='string')return {name:v,stat:''};
  if(typeof v!=='object')return null;
  const p=(v.player&&typeof v.player==='object')?v.player:v;
  const name=p.name||p.full_name||p.fullName||p.short_name||p.shortName||p.player_name||p.playerName||v.name||'';
  if(!name)return null;
  const runs=v.runs??v.score??p.runs??p.score;
  const balls=v.balls??v.balls_faced??v.ballsFaced??p.balls??p.balls_faced;
  const wickets=v.wickets??p.wickets;
  const overs=v.overs??p.overs;
  let stat='';
  if(runs!==undefined&&runs!==null)stat=String(runs)+(balls!==undefined&&balls!==null?' ('+balls+')':'');
  else if(wickets!==undefined&&wickets!==null)stat=String(wickets)+' wkts'+(overs!==undefined&&overs!==null?' · '+overs+' ov':'');
  return {name:String(name),stat};
}
function currentPlayersHtml(x){
  const root=x?.inplayData||{};
  const striker=playerInfo(deepFind(root,['striker','current_striker','currentBatsman','current_batsman','batsman','batter','on_strike']));
  const bowler=playerInfo(deepFind(root,['bowler','current_bowler','currentBowler','bowling','currentBowling']));
  if(!striker&&!bowler)return'';
  return `<div class="playerStrip">${striker?`<div class="playerCard"><div class="playerRole">AT CREASE</div><div class="playerName">${esc(striker.name)}</div>${striker.stat?`<div class="playerStat">${esc(striker.stat)}</div>`:''}</div>`:''}${bowler?`<div class="playerCard"><div class="playerRole">BOWLER</div><div class="playerName">${esc(bowler.name)}</div>${bowler.stat?`<div class="playerStat">${esc(bowler.stat)}</div>`:''}</div>`:''}</div>`;
}
function ballOutcome(e){
  const s=String(e?.commentary||e?.comment||e?.description||e?.text||'').toLowerCase();
  if(/six|6 runs|6 run/.test(s))return['6','six'];
  if(/four|4 runs|4 run/.test(s))return['4','boundary'];
  if(/wicket|out\b|bowled|caught|lbw|run out/.test(s))return['W','wicket'];
  if(/no.?ball/.test(s))return['NB','extra'];
  if(/wide/.test(s))return['WD','extra'];
  const m=s.match(/\b([0-3]) runs?\b/);if(m)return[m[1],m[1]==='0'?'':''];
  if(/dot ball|no run/.test(s))return['•',''];
  return['•',''];
}
function lastSixHtml(rows){
  const a=(Array.isArray(rows)?rows:[]).slice(-6);if(!a.length)return'';
  return `<div class="lastSix"><span class="lastSixTitle">LAST 6</span>${a.map(e=>{const o=ballOutcome(e);return `<span class="ballChip ${o[1]}">${o[0]}</span>`}).join('')}</div>`;
}
"""
    marker = "document.querySelectorAll('.tab').forEach(b=>b.onclick"
    html = html.replace(marker, helpers + marker, 1)

    # Team identity treatment in the main scoreboard. Uses provider artwork when present, initials otherwise.
    html = html.replace(
        '<div class="side"><div class="sname">${esc(m.home?.name||\'Home\')}</div>',
        '<div class="side"><div class="teamIdentity">${teamMark(m.home)}</div><div class="sname">${esc(m.home?.name||\'Home\')}</div>',
        1,
    )
    html = html.replace(
        '<div class="side right"><div class="sname">${esc(m.away?.name||\'Away\')}</div>',
        '<div class="side right"><div class="teamIdentity">${teamMark(m.away)}</div><div class="sname">${esc(m.away?.name||\'Away\')}</div>',
        1,
    )

    # Put the most useful live information directly under the score.
    html = html.replace(
        '<div class="report">${esc(m.report||m.state||\'\')}</div>',
        '<div class="report"><div class="reportText">${esc(m.report||prettyState(m.state)||\'\')}</div>${x.roanuz?.target?chaseInfo(x.roanuz.target,m):\'\'}${lastSixHtml(x.timeline||[])}</div>',
        1,
    )

    # Four primary tabs. Advanced features live behind MORE instead of crowding the match center.
    old_tabs = "function tabs(){return [['match','MATCH'],['bhav','BHAV'],['scorecard','SCORECARD'],['balls','BALLS'],['graphs','GRAPHS'],['stats','STATS'],['info','INFO']].map(([k,l])=>`<button class=\"dtab ${tab===k?'on':''}\" data-tab=\"${k}\">${l}</button>`).join('')}"
    new_tabs = "function tabs(){const moreOn=['more','bhav','graphs','stats','info'].includes(tab);return [['match','MATCH'],['scorecard','SCORECARD'],['balls','BALLS'],['more','MORE']].map(([k,l])=>`<button class=\"dtab ${(tab===k||(k==='more'&&moreOn))?'on':''}\" data-tab=\"${k}\">${l}</button>`).join('')}"
    html = html.replace(old_tabs, new_tabs, 1)

    # Match tab: compact live snapshot with current batter/bowler when the provider supplies them.
    old_match = "if(tab==='match'){const rr=x.roanuz?.runRate;const target=x.roanuz?.target;const rv=rateValue(rr);p.innerHTML=ptitle('LIVE MATCH')+`<div class=\"notice\"><b>${esc(m.report||prettyState(m.state)||'Match status')}</b>${target?chaseInfo(target,m):''}${rv?`<div class=\"metricRow\"><span class=\"metric\">CRR <b>${esc(rv)}</b></span></div>`:''}</div>`}"
    new_match = "if(tab==='match'){const rr=x.roanuz?.runRate;const rv=rateValue(rr);p.innerHTML=ptitle('MATCH SNAPSHOT')+`<div class=\"notice premiumSnapshot\">${rv?`<div class=\"metricRow\"><span class=\"metric\">CRR <b>${esc(rv)}</b></span></div>`:''}${currentPlayersHtml(x)}${lastSixHtml(x.timeline||[])}</div>`}"
    html = html.replace(old_match, new_match, 1)

    # MORE opens advanced features without exposing seven cramped tabs.
    html = html.replace(
        "else{p.innerHTML=ptitle('MATCH INFO')+",
        "else if(tab==='more'){p.innerHTML=ptitle('MORE')+'<div class=\"moreGrid\"><button class=\"moreItem\" onclick=\"tab=\\'bhav\\';drawDetail()\">BHAV<span>Live market view</span></button><button class=\"moreItem\" onclick=\"tab=\\'graphs\\';drawDetail()\">GRAPHS<span>Match trends</span></button><button class=\"moreItem\" onclick=\"tab=\\'stats\\';drawDetail()\">STATS<span>Detailed numbers</span></button><button class=\"moreItem\" onclick=\"tab=\\'info\\';drawDetail()\">INFO<span>Venue and match details</span></button></div>'}else{p.innerHTML=ptitle('MATCH INFO')+",
        1,
    )

    return html


# UI-only patch. Keep all V25/V26 data, caching and API behavior intact.
v25.v23._page = _page_v27
v25.v23.liveline._page = _page_v27


def _ui_self_test() -> None:
    page = _page_v27()
    checks = {
        "premium_scoreboard": "teamIdentity" in page and "teamMark(m.home)" in page,
        "four_detail_tabs": "['more','MORE']" in page and "repeat(4" in page,
        "player_strip": "currentPlayersHtml" in page and "AT CREASE" in page,
        "last_six": "lastSixHtml" in page and "LAST 6" in page,
        "advanced_more": "moreGrid" in page and "Live market view" in page,
        "clean_bottom_nav": "FIXTURES" in page and "repeat(4" in page,
        "fast_feed_preserved": "hydrateScore" in page and "__scoreHydrateBusy" in page,
        "no_terminal_label": "LIVE CRICKET TERMINAL" not in page,
    }
    ok = all(checks.values())
    (logger.info if ok else logger.error)("IBETIN V27 premium UI self-test %s checks=%s", "PASS" if ok else "FAILED", checks)
    if not ok:
        raise RuntimeError(f"V27 premium UI self-test failed: {checks}")


_ui_self_test()
logger.info("IBETIN V27 installed: premium consumer UI over unchanged V25 fast feed/cache")

app = v25.app

if __name__ == "__main__":
    app.base.ibetin_start.main()
