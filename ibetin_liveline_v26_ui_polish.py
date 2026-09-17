import logging

import ibetin_liveline_v25_fast_cache as v25

logger = logging.getLogger(__name__)

_ORIGINAL_PAGE = v25._page_fast


def _page_v26() -> str:
    html = _ORIGINAL_PAGE()

    # Public-facing branding: hide internal release/provider language.
    html = html.replace('<div class="v">V25 · FAST</div>', '<div class="v publicLive">● LIVE</div>', 1)
    html = html.replace('ROANUZ PRIMARY', 'LIVE DATA')

    # Detail header should never expose raw provider state such as `in_play`.
    html = html.replace(
        "<span>${esc(m.state||'')}</span>",
        "<span class=\"liveState\">${esc(prettyState(m.state)||'')}</span>",
        1,
    )

    # Consumer cricket UI: all seven match tabs fit on one row; no browser scrollbar.
    ui_css = r"""
.detail{overflow-x:hidden}
.publicLive{background:rgba(20,180,110,.16)!important;border-color:rgba(120,240,180,.24)!important;color:#dff9eb!important}
.dtabs{display:grid!important;grid-template-columns:repeat(7,minmax(0,1fr));gap:4px!important;overflow:visible!important;scrollbar-width:none!important;-ms-overflow-style:none!important}
.dtabs::-webkit-scrollbar{display:none!important}
.dtab{min-width:0!important;width:100%!important;padding:0 2px!important;font-size:7.4px!important;letter-spacing:0!important}
.scoretop{font-size:9px!important}.scoretop span:first-child{max-width:78%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.liveState{font-weight:1000;color:#d72d45;letter-spacing:.3px}
.sname{font-size:11px!important;line-height:1.2}.sval{font-size:27px!important}.ta{font-size:9px!important}
.report{font-size:10px!important;line-height:1.4}
.notice{font-size:11px!important;line-height:1.55!important}
.metricRow{display:flex;gap:7px;flex-wrap:wrap;margin-top:8px}.metric{display:inline-flex;gap:4px;align-items:center;background:#eef4fb;color:#345b80;border-radius:999px;padding:6px 8px;font-size:10px;font-weight:700}.metric b{color:#073f7e}
.chaseBox{background:linear-gradient(135deg,#f5f9ff,#edf5fc);border:1px solid #deebf7;border-radius:11px;padding:10px 11px;margin-top:8px}.chaseBox b{font-size:12px;color:#083f7f}.chaseBox span{display:block;margin-top:4px;color:#657f98;font-size:10px}
.bottom button{font-size:8.5px!important}.bottom b{font-size:15px!important}
"""
    html = html.replace('</style><link rel="icon" href="data:"></head>', ui_css + '</style><link rel="icon" href="data:"></head>', 1)

    # Helpers for clean chase equation and cricket metrics. Function declarations are hoisted.
    helpers = r"""
function rateValue(v){
  if(v===null||v===undefined||v==='')return'';
  if(typeof v==='number')return Number.isFinite(v)?v.toFixed(2):'';
  if(typeof v==='string'){const n=Number(v);return Number.isFinite(n)?n.toFixed(2):v}
  if(typeof v==='object'){
    for(const k of ['value','rate','run_rate','current','crr']){if(v[k]!==undefined&&v[k]!==null){const n=Number(v[k]);if(Number.isFinite(n))return n.toFixed(2)}}
  }
  return'';
}
function scoreRuns(s){const m=String(s||'').match(/(\d+)/);return m?Number(m[1]):0}
function oversBalls(info){const m=String(info||'').match(/(\d+)\.(\d+)/);return m?(Number(m[1])*6+Number(m[2])):0}
function chaseInfo(target,m){
  if(!target||typeof target!=='object')return'';
  const targetRuns=Number(target.runs||target.target||target.score||0);
  const totalBalls=Number(target.balls||0);
  if(!targetRuns)return'';
  const homeRuns=scoreRuns(m.homeScore),awayRuns=scoreRuns(m.awayScore);
  const homeBalls=oversBalls(m.homeInfo),awayBalls=oversBalls(m.awayInfo);
  let currentRuns=homeRuns,currentBalls=homeBalls,team=m.home?.name||'Batting team';
  if(awayBalls>homeBalls||(!homeBalls&&awayRuns)){currentRuns=awayRuns;currentBalls=awayBalls;team=m.away?.name||'Batting team'}
  const need=Math.max(0,targetRuns-currentRuns),left=totalBalls?Math.max(0,totalBalls-currentBalls):0;
  if(need===0)return `<div class="chaseBox"><b>${esc(team)} reached the target</b></div>`;
  const rrr=left?((need*6)/left):0;
  return `<div class="chaseBox"><b>${esc(team)} need ${need}${left?' from '+left+' balls':''}</b><span>Target ${targetRuns}${left&&rrr?' · Required rate '+rrr.toFixed(2):''}</span></div>`;
}
"""
    marker = "document.querySelectorAll('.tab').forEach(b=>b.onclick"
    html = html.replace(marker, helpers + marker, 1)

    # Replace provider-shaped target JSON with a human-readable chase equation and CRR.
    old_match_panel = "if(tab==='match'){const rr=x.roanuz?.runRate;const target=x.roanuz?.target;p.innerHTML=ptitle('LIVE MATCH')+`<div class=\"notice\"><b>${esc(m.report||m.state||'Match status')}</b><br>${target?`Target: ${esc(JSON.stringify(target).slice(0,120))}<br>`:''}${rr?`Run rate: ${esc(JSON.stringify(rr).slice(0,120))}`:''}</div>`}"
    new_match_panel = "if(tab==='match'){const rr=x.roanuz?.runRate;const target=x.roanuz?.target;const rv=rateValue(rr);p.innerHTML=ptitle('LIVE MATCH')+`<div class=\"notice\"><b>${esc(m.report||prettyState(m.state)||'Match status')}</b>${target?chaseInfo(target,m):''}${rv?`<div class=\"metricRow\"><span class=\"metric\">CRR <b>${esc(rv)}</b></span></div>`:''}</div>`}"
    html = html.replace(old_match_panel, new_match_panel, 1)

    return html


# Patch only the rendered page. All V25 cache/feed/detail functions remain unchanged.
v25.v23._page = _page_v26
v25.v23.liveline._page = _page_v26


def _ui_self_test() -> None:
    page = _page_v26()
    checks = {
        'no_public_version': 'V25 · FAST' not in page,
        'live_badge': 'publicLive' in page,
        'clean_provider_label': 'ROANUZ PRIMARY' not in page,
        'live_state': 'prettyState(m.state)' in page,
        'chase_equation': 'chaseInfo(target,m)' in page,
        'crr': 'CRR <b>' in page,
        'tabs_fit': 'grid-template-columns:repeat(7' in page,
        'v25_fast_feed_preserved': 'hydrateScore' in page,
    }
    ok = all(checks.values())
    (logger.info if ok else logger.error)("IBETIN V26 UI self-test %s checks=%s", "PASS" if ok else "FAILED", checks)
    if not ok:
        raise RuntimeError(f"V26 UI self-test failed: {checks}")


_ui_self_test()
logger.info("IBETIN V26 installed: consumer UI polish over unchanged V25 fast cache/feed")

app = v25.app

if __name__ == '__main__':
    app.base.ibetin_start.main()
