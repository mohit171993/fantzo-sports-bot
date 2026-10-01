"""CSS + JS for the Live Line Match Centre (see liveline_match_center.py).

One structural stylesheet driven by CSS variables; the brand only sets the
palette so IBETIN keeps black/cyan neon and DURA keeps carbon/red/gold.
"""

THEMES = {
    "ibetin": {
        "bg": "#030607", "panel": "#0a1216", "panel2": "#0c171b", "line": "rgba(25,227,255,.14)",
        "text": "#eef9fb", "muted": "#8aa5ab", "accent": "#19e3ff", "accentInk": "#021014",
        "accentSoft": "rgba(25,227,255,.12)", "glow": "rgba(25,227,255,.35)", "good": "#27dd8a",
        "four": "#27dd8a", "six": "#2f7dff", "wicket": "#ff4d67", "extra": "#ffb547",
        "barA": "#19e3ff", "barB": "#2f7dff", "head": "'Sora','Space Grotesk',Arial,sans-serif",
    },
    "dura": {
        "bg": "#0b0908", "panel": "#1b1714", "panel2": "#241e19", "line": "rgba(216,178,90,.24)",
        "text": "#f4ecdc", "muted": "#b3a692", "accent": "#d42a20", "accentInk": "#ffffff",
        "accentSoft": "rgba(212,42,32,.16)", "glow": "rgba(212,42,32,.35)", "good": "#d8b25a",
        "four": "#d8b25a", "six": "#f3dc98", "wicket": "#ff5a4e", "extra": "#e0a04a",
        "barA": "#d42a20", "barB": "#d8b25a", "head": "'Barlow Condensed','Sora','Space Grotesk',Arial,sans-serif",
    },
}

_CSS = r"""
/* __LIVELINE_MATCH_CENTRE__ : scorecard, commentary, overs, squads, table, info, football */
:root{--mcBg:%(bg)s;--mcPanel:%(panel)s;--mcPanel2:%(panel2)s;--mcLine:%(line)s;--mcText:%(text)s;--mcMuted:%(muted)s;--mcAcc:%(accent)s;--mcInk:%(accentInk)s;--mcSoft:%(accentSoft)s;--mcGlow:%(glow)s;--mcGood:%(good)s;--mcFour:%(four)s;--mcSix:%(six)s;--mcW:%(wicket)s;--mcX:%(extra)s;--mcBarA:%(barA)s;--mcBarB:%(barB)s;--mcHead:%(head)s}
html body #detail .dtabs{display:flex!important;grid-template-columns:none!important;gap:6px!important;overflow-x:auto!important;scroll-snap-type:x proximity;scrollbar-width:none;padding:2px 2px 4px!important;margin:10px 0 8px!important;-webkit-overflow-scrolling:touch}
html body #detail .dtabs::-webkit-scrollbar{display:none}
html body #detail .dtabs .dtab{flex:0 0 auto!important;min-width:0!important;width:auto!important;padding:0 14px!important;height:40px!important;border-radius:12px!important;font-size:10.5px!important;letter-spacing:.6px!important;white-space:nowrap!important;scroll-snap-align:start}
.mc{color:var(--mcText);font-variant-numeric:tabular-nums}
.mc *{box-sizing:border-box}
.mcCard{background:linear-gradient(180deg,var(--mcPanel2),var(--mcPanel));border:1px solid var(--mcLine);border-radius:16px;padding:12px;margin:0 0 10px;box-shadow:0 10px 26px rgba(0,0,0,.24)}
.mcH{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:0 0 9px}
.mcH b{font:800 13px/1.2 var(--mcHead);letter-spacing:.6px;text-transform:uppercase;color:var(--mcText)}
.mcH span{font-size:9.5px;font-weight:800;letter-spacing:.8px;color:var(--mcMuted);text-transform:uppercase}
.mcPill{display:inline-flex;align-items:center;gap:5px;padding:4px 8px;border-radius:999px;background:var(--mcSoft);color:var(--mcAcc);font-size:9.5px;font-weight:900;letter-spacing:.7px}
.mcPill.live:before{content:"";width:6px;height:6px;border-radius:50%%;background:var(--mcW);box-shadow:0 0 0 3px rgba(255,77,103,.18);animation:mcBlink 1.2s infinite}
@keyframes mcBlink{50%%{opacity:.35}}
.mcMetrics{display:grid;grid-template-columns:repeat(4,1fr);gap:6px}
.mcMetric{background:rgba(255,255,255,.03);border:1px solid var(--mcLine);border-radius:12px;padding:8px 6px;text-align:center;min-width:0}
.mcMetric span{display:block;font-size:8.5px;font-weight:900;letter-spacing:.8px;color:var(--mcMuted);text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mcMetric b{display:block;margin-top:3px;font:800 17px/1.1 var(--mcHead);color:var(--mcText)}
.mcMetric.hot b{color:var(--mcAcc)}
.mcNeed{margin-top:9px;padding:9px 11px;border-radius:12px;background:var(--mcSoft);color:var(--mcText);font-size:12px;font-weight:700;line-height:1.35}
.mcNeed b{color:var(--mcAcc)}
.mcProj{display:flex;gap:6px;margin-top:8px}
.mcProj div{flex:1;padding:7px 4px;border-radius:10px;border:1px dashed var(--mcLine);text-align:center;font-size:9px;color:var(--mcMuted);font-weight:800;letter-spacing:.4px}
.mcProj b{display:block;font:800 15px/1.1 var(--mcHead);color:var(--mcText);margin-top:2px}
.mcWin{margin-top:2px}
.mcWinRow{display:flex;justify-content:space-between;font-size:11px;font-weight:800;margin-bottom:6px}
.mcWinRow b{font:800 18px/1 var(--mcHead)}
.mcWinRow .r{text-align:right}
.mcWinBar{display:flex;height:9px;border-radius:999px;overflow:hidden;background:rgba(255,255,255,.06)}
.mcWinBar i{display:block;height:100%%}
.mcWinBar i:first-child{background:var(--mcBarA)}.mcWinBar i:last-child{background:var(--mcBarB)}
.mcWinNote{margin-top:6px;font-size:9px;color:var(--mcMuted);letter-spacing:.3px}
.mcT{width:100%%;border-collapse:collapse;font-size:12px}
.mcT th{font-size:8.5px;font-weight:900;letter-spacing:.8px;color:var(--mcMuted);text-transform:uppercase;text-align:right;padding:0 3px 6px;white-space:nowrap}
.mcT th:first-child,.mcT td:first-child{text-align:left;padding-left:0}
.mcT td{padding:7px 3px;text-align:right;border-top:1px solid var(--mcLine);vertical-align:top;white-space:nowrap}
.mcT td.n{white-space:normal;width:52%%}
.mcT td.n b{display:block;font-size:12.5px;font-weight:800;color:var(--mcText)}
.mcT td.n small{display:block;margin-top:2px;font-size:10px;color:var(--mcMuted);font-weight:600;line-height:1.25}
.mcT td.r{font-weight:900;color:var(--mcText)}
.mcT tr.on td.n b{color:var(--mcAcc)}
.mcT.bat tr.on td.n b:after{content:" *";color:var(--mcAcc)}
.mcT tr.out td{opacity:.86}
.mcT .dim{color:var(--mcMuted)}
.mcSum{display:flex;justify-content:space-between;align-items:baseline;padding:8px 0 0;margin-top:2px;border-top:1px solid var(--mcLine);font-size:11.5px;color:var(--mcMuted);gap:8px}
.mcSum b{color:var(--mcText);font-weight:900}
.mcTot{font:800 15px/1.1 var(--mcHead);color:var(--mcText)}
.mcYet{margin-top:8px;font-size:11px;line-height:1.45;color:var(--mcMuted)}
.mcYet b{color:var(--mcText);font-weight:800;margin-right:4px;font-size:9.5px;letter-spacing:.7px;text-transform:uppercase}
.mcInnTabs{display:flex;gap:6px;overflow-x:auto;scrollbar-width:none;margin:0 0 10px}
.mcInnTabs::-webkit-scrollbar{display:none}
.mcInnTabs button{flex:0 0 auto;border:1px solid var(--mcLine);background:var(--mcPanel);color:var(--mcMuted);border-radius:12px;padding:8px 12px;font-family:inherit;font-weight:800;font-size:11px;line-height:1.2;text-align:left}
.mcInnTabs button b{display:block;font:800 14px/1.1 var(--mcHead);color:var(--mcText);margin-top:2px}
.mcInnTabs button.on{border-color:var(--mcAcc);background:var(--mcSoft);color:var(--mcAcc);box-shadow:0 0 0 1px var(--mcGlow) inset}
.mcInnHead{display:flex;justify-content:space-between;align-items:flex-end;gap:8px;margin-bottom:8px}
.mcInnHead .t{font:800 15px/1.15 var(--mcHead);color:var(--mcText)}
.mcInnHead .t small{display:block;font-family:inherit;font-weight:700;font-size:10px;line-height:1.3;color:var(--mcMuted);letter-spacing:.4px;margin-top:2px}
.mcInnHead .s{font:800 24px/1 var(--mcHead);color:var(--mcText);text-align:right}
.mcInnHead .s small{display:block;font-family:inherit;font-weight:700;font-size:10px;line-height:1.3;color:var(--mcMuted);margin-top:3px}
.mcChips{display:flex;flex-wrap:wrap;gap:6px}
.mcFow{padding:6px 8px;border-radius:10px;border:1px solid var(--mcLine);font-size:10.5px;color:var(--mcMuted);line-height:1.25}
.mcFow b{color:var(--mcText);font-weight:900;margin-right:3px}
.mcPart{padding:8px 0;border-top:1px solid var(--mcLine)}
.mcPart:first-of-type{border-top:0}
.mcPartTop{display:flex;justify-content:space-between;font-size:11px;color:var(--mcMuted);margin-bottom:5px;gap:6px}
.mcPartTop b{color:var(--mcText);font-weight:900}
.mcPartBar{display:flex;height:6px;border-radius:999px;overflow:hidden;background:rgba(255,255,255,.06)}
.mcPartBar i:first-child{background:var(--mcBarA)}.mcPartBar i:last-child{background:var(--mcBarB)}
.mcPartNames{display:flex;justify-content:space-between;font-size:10.5px;margin-top:4px;color:var(--mcText);gap:6px}
.mcPartNames span:last-child{text-align:right}
.mcBall{display:inline-grid;place-items:center;min-width:26px;height:26px;padding:0 5px;border-radius:999px;font-family:inherit;font-weight:900;font-size:11px;line-height:1;background:rgba(255,255,255,.06);color:var(--mcText);border:1px solid var(--mcLine)}
.mcBall.dot{color:var(--mcMuted)}
.mcBall.four{background:var(--mcFour);color:#05110b;border-color:transparent}
.mcBall.six{background:var(--mcSix);color:#12051f;border-color:transparent}
.mcBall.wicket{background:var(--mcW);color:#fff;border-color:transparent}
.mcBall.extra{color:var(--mcX);border-color:var(--mcX)}
.mcOverRow{display:grid;grid-template-columns:44px 1fr 46px;align-items:center;gap:8px;padding:8px 0;border-top:1px solid var(--mcLine)}
.mcOverRow:first-child{border-top:0}
.mcOverRow .o{font:800 11px/1.2 var(--mcHead);color:var(--mcMuted);letter-spacing:.4px}
.mcOverRow .o b{display:block;color:var(--mcText);font-size:15px}
.mcOverRow .bs{display:flex;flex-wrap:wrap;gap:5px}
.mcOverRow .rn{text-align:right;font:800 16px/1 var(--mcHead);color:var(--mcText)}
.mcOverRow .rn small{display:block;font-family:inherit;font-weight:800;font-size:8.5px;line-height:1.2;color:var(--mcMuted);letter-spacing:.6px;margin-top:2px}
.mcMan{display:flex;align-items:flex-end;gap:4px;height:92px;padding:6px 0 0;border-bottom:1px solid var(--mcLine)}
.mcMan div{flex:1;min-width:0;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%%}
.mcMan i{display:block;width:100%%;max-width:22px;border-radius:5px 5px 2px 2px;background:linear-gradient(180deg,var(--mcBarA),var(--mcSoft))}
.mcMan em{font-style:normal;font-size:9px;font-weight:900;color:var(--mcText);margin-bottom:3px}
.mcMan u{display:block;width:6px;height:6px;border-radius:50%%;background:var(--mcW);margin-bottom:3px;text-decoration:none}
.mcManX{display:flex;gap:4px;margin-top:4px}.mcManX span{flex:1;text-align:center;font-size:8.5px;color:var(--mcMuted);font-weight:800}
.mcCom{display:grid;grid-template-columns:40px 1fr;gap:9px;padding:10px 0;border-top:1px solid var(--mcLine)}
.mcCom:first-child{border-top:0}
.mcCom .l{display:flex;flex-direction:column;align-items:center;gap:5px}
.mcCom .l small{font:800 10.5px/1 var(--mcHead);color:var(--mcMuted)}
.mcCom p{margin:0;font-size:12.5px;line-height:1.42;color:var(--mcText)}
.mcCom p small{display:block;margin-top:4px;font-size:10px;color:var(--mcMuted);font-weight:700;letter-spacing:.2px}
.mcCom.wicket{background:linear-gradient(90deg,rgba(255,77,103,.12),transparent 70%%);border-radius:12px;padding-left:6px;padding-right:6px}
.mcCom.six p,.mcCom.four p{font-weight:600}
.mcOverHead{display:flex;justify-content:space-between;align-items:center;margin:12px 0 2px;padding:7px 10px;border-radius:10px;background:rgba(255,255,255,.035);font-size:10px;font-weight:900;letter-spacing:.7px;color:var(--mcMuted);text-transform:uppercase}
.mcOverHead:first-child{margin-top:0}
.mcOverHead b{color:var(--mcText)}
.mcPlayers{display:grid;grid-template-columns:1fr;gap:0}
.mcPl{display:flex;align-items:center;gap:10px;padding:8px 0;border-top:1px solid var(--mcLine)}
.mcPl:first-child{border-top:0}
.mcAv{flex:0 0 32px;width:32px;height:32px;border-radius:50%%;display:grid;place-items:center;font:900 11px/1 var(--mcHead);background:var(--mcSoft);color:var(--mcAcc);border:1px solid var(--mcLine)}
.mcPl .nm{flex:1;min-width:0}
.mcPl .nm b{display:block;font-size:12.5px;color:var(--mcText);font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mcPl .nm small{display:block;font-size:10px;color:var(--mcMuted);text-transform:capitalize;margin-top:1px}
.mcTag{font-size:8.5px;font-weight:900;letter-spacing:.6px;padding:3px 6px;border-radius:6px;background:var(--mcSoft);color:var(--mcAcc);margin-left:4px}
.mcSeg{display:flex;gap:6px;margin-bottom:10px}
.mcSeg button{flex:1;border:1px solid var(--mcLine);background:var(--mcPanel);color:var(--mcMuted);border-radius:12px;height:38px;font-family:inherit;font-weight:900;font-size:11px;line-height:1;letter-spacing:.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding:0 8px}
.mcSeg button.on{border-color:var(--mcAcc);color:var(--mcInk);background:var(--mcAcc);box-shadow:0 6px 16px var(--mcGlow)}
.mcKV{display:flex;justify-content:space-between;gap:14px;padding:10px 0;border-top:1px solid var(--mcLine);font-size:12px}
.mcKV:first-child{border-top:0}
.mcKV span{color:var(--mcMuted);font-weight:700;flex:0 0 auto}
.mcKV b{color:var(--mcText);font-weight:800;text-align:right;line-height:1.35}
.mcNote{padding:14px 12px;border-radius:12px;background:rgba(255,255,255,.03);border:1px dashed var(--mcLine);color:var(--mcMuted);font-size:12px;line-height:1.45;text-align:center}
.mcRes{padding:10px 12px;border-radius:12px;background:var(--mcSoft);color:var(--mcText);font-weight:800;font-size:12.5px;margin-bottom:10px}
.mcMini{display:flex;justify-content:space-between;gap:8px;margin-top:9px;font-size:11px;color:var(--mcMuted)}
.mcMini b{color:var(--mcText);font-weight:800}
.mcSk{height:12px;border-radius:6px;background:linear-gradient(90deg,rgba(255,255,255,.04),rgba(255,255,255,.09),rgba(255,255,255,.04));background-size:200%% 100%%;animation:mcSk 1.2s infinite;margin:8px 0}
@keyframes mcSk{to{background-position:-200%% 0}}
.mcSport{display:flex;gap:6px;margin:0 0 10px;padding:4px;border-radius:14px;background:rgba(255,255,255,.035);border:1px solid var(--mcLine)}
.mcSport button{flex:1;height:38px;border:0;border-radius:11px;background:transparent;color:var(--mcMuted);font-family:inherit;font-weight:900;font-size:11.5px;line-height:1;letter-spacing:.8px}
.mcSport button.on{background:var(--mcAcc);color:var(--mcInk);box-shadow:0 6px 16px var(--mcGlow)}
body.mcFootball .top .tabs,body.mcFootball #home #status,body.mcFootball #home #list,body.mcFootball #home .tools,body.mcFootball .v39FavFilter,body.mcFootball .v40Coming{display:none!important}
#mcFootball{display:none}
body.mcFootball #mcFootball{display:block}
.mcFbLeague{display:flex;align-items:center;gap:7px;margin:14px 2px 7px;font-size:10px;font-weight:900;letter-spacing:.8px;color:var(--mcMuted);text-transform:uppercase}
.mcFbLeague img{width:16px;height:16px;object-fit:contain}
.mcFb{display:grid;grid-template-columns:1fr auto;gap:6px 10px;align-items:center;padding:11px 12px;margin-bottom:8px;border-radius:14px;border:1px solid var(--mcLine);background:linear-gradient(180deg,var(--mcPanel2),var(--mcPanel))}
.mcFb.live{border-color:var(--mcAcc);box-shadow:0 0 0 1px var(--mcGlow) inset}
.mcFbTeam{display:flex;align-items:center;gap:8px;min-width:0;font-size:13px;font-weight:800;color:var(--mcText)}
.mcFbTeam img{width:20px;height:20px;object-fit:contain}
.mcFbTeam span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mcFbGoal{font:800 18px/1 var(--mcHead);color:var(--mcText);text-align:right;min-width:22px}
.mcFbMeta{grid-column:1/-1;display:flex;justify-content:space-between;font-size:10px;font-weight:800;letter-spacing:.5px;color:var(--mcMuted);padding-top:6px;border-top:1px solid var(--mcLine)}
.mcFbMeta .lv{color:var(--mcW)}
.mcCom.four{background:linear-gradient(90deg,color-mix(in srgb,var(--mcFour) 14%%,transparent),transparent 70%%);border-radius:12px;padding-left:6px;padding-right:6px}
.mcCom.six{background:linear-gradient(90deg,color-mix(in srgb,var(--mcSix) 18%%,transparent),transparent 70%%);border-radius:12px;padding-left:6px;padding-right:6px}
.mcCom p em{font-style:normal;font-weight:900;color:var(--mcW)}
.mcCom p i{font-style:normal;font-weight:800;color:var(--mcMuted);font-size:10.5px}
.mcOverHead .bw{font-weight:800;color:var(--mcMuted);text-transform:none;letter-spacing:.2px}
.mcOverHead .mcSc{color:var(--mcText);font:inherit}
.mcMore{margin-top:10px;font-size:10.5px;color:var(--mcMuted);text-align:center;font-weight:800;letter-spacing:.4px}
.mcSrc{display:flex;justify-content:space-between;align-items:center;gap:8px;margin:0 2px 8px;font-size:9.5px;font-weight:800;letter-spacing:.6px;color:var(--mcMuted);text-transform:uppercase}
.mcSrc b{color:var(--mcAcc)}
.mcManS{overflow-x:auto;scrollbar-width:none;padding-bottom:2px}.mcManS::-webkit-scrollbar{display:none}
.mcManS .mcMan,.mcManS .mcManX{min-width:100%%}
.mcManS .mcMan div,.mcManS .mcManX span{flex:1 0 11px}
.mcWorm svg{display:block;width:100%%;height:auto}
.mcWorm .ax{stroke:var(--mcLine);stroke-width:1}
.mcWorm text{fill:var(--mcMuted);font-size:8px;font-weight:800;font-family:inherit}
.mcLegend{display:flex;gap:12px;flex-wrap:wrap;margin-top:6px;font-size:10px;font-weight:800;color:var(--mcMuted)}
.mcLegend i{display:inline-block;width:14px;height:3px;border-radius:2px;margin-right:5px;vertical-align:middle}
.mcOS{display:grid;grid-template-columns:44px 1fr auto;gap:8px;align-items:center;padding:9px 0;border-top:1px solid var(--mcLine)}
.mcOS:first-child{border-top:0}
.mcOS .o{font:800 11px/1.2 var(--mcHead);color:var(--mcMuted)}.mcOS .o b{display:block;color:var(--mcText);font-size:15px}
.mcOS .d{min-width:0;font-size:10.5px;line-height:1.4;color:var(--mcMuted)}
.mcOS .d b{color:var(--mcText);font-weight:800}
.mcOS .d .bs{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:4px}
.mcOS .d .bs .mcBall{min-width:21px;height:21px;font-size:9.5px}
.mcOS .r{text-align:right;font:800 16px/1 var(--mcHead);color:var(--mcText)}
.mcOS .r small{display:block;font-family:inherit;font-weight:800;font-size:9px;line-height:1.3;color:var(--mcMuted);margin-top:3px;white-space:nowrap}
.mcOS.wk .r{color:var(--mcW)}
#mcOddsBox{display:none;margin-top:10px}
#mcOddsBox.on{display:block}
.mcOdds{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.mcOdd{position:relative;padding:11px 12px;border-radius:14px;border:1px solid var(--mcLine);background:rgba(255,255,255,.03);min-width:0}
.mcOdd.fav{border-color:var(--mcAcc);background:var(--mcSoft);box-shadow:0 0 0 1px var(--mcGlow) inset}
.mcOdd .nm{display:block;font-size:10px;font-weight:900;letter-spacing:.6px;color:var(--mcMuted);text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mcOdd b{display:block;margin-top:4px;font:800 26px/1 var(--mcHead);color:var(--mcText)}
.mcOdd.fav b{color:var(--mcAcc)}
.mcOdd small{display:block;margin-top:5px;font-size:10px;font-weight:700;color:var(--mcMuted)}
.mcOdd.fav .nm{padding-right:34px}
.mcOdd .tag{position:absolute;top:9px;right:9px;font-size:8px;font-weight:900;letter-spacing:.6px;padding:2px 6px;border-radius:6px;background:var(--mcAcc);color:var(--mcInk)}
.mcOddDraw{margin-top:8px;display:flex;justify-content:space-between;font-size:11px;color:var(--mcMuted);font-weight:800}
.mcOddDraw b{color:var(--mcText)}
@media(max-width:360px){.mcMetric b{font-size:15px}.mcT{font-size:11px}.mcT td.n{width:46%%}}
@media(prefers-reduced-motion:reduce){.mcPill.live:before,.mcSk{animation:none}}
"""

_JS = r"""
<script>
(function(){
  'use strict';
  const mcBrand='%(brand)s';
  document.documentElement.setAttribute('data-mc-brand',mcBrand);
  window.__LIVELINE_MATCH_CENTRE__=true;
  const MC={cache:new Map(),busy:new Map(),pts:new Map(),inn:{},sq:{},sig:{},fb:null,fbAt:0,fbBusy:null,fbFilter:'live',timer:null};
  const TABS=[['match','LIVE'],['bhav','BHAV'],['scorecard','SCORECARD'],['comms','COMMENTARY'],['overs','OVERS'],['squads','SQUADS'],['table','TABLE'],['info','INFO']];
  const OWN=new Set(['match','scorecard','comms','overs','squads','table','info']);
  const E=v=>String(v===null||v===undefined?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const N=(v,d)=>{const n=Number(v);return Number.isFinite(n)?(d===undefined?String(n):n.toFixed(d)):'—'};
  const has=v=>v!==null&&v!==undefined&&v!=='';
  function curKey(){try{return matchKey((detailData&&detailData.match)||{})}catch(e){return''}}
  function head(t,sub){return `<div class="mcH"><b>${E(t)}</b>${sub?`<span>${sub}</span>`:''}</div>`}
  function note(t){return `<div class="mcNote">${E(t)}</div>`}
  function skel(){return '<div class="mcCard"><div class="mcSk" style="width:40%%"></div><div class="mcSk"></div><div class="mcSk" style="width:75%%"></div><div class="mcSk" style="width:60%%"></div></div>'}
  function ball(b){return `<span class="mcBall ${E(b.k||'')}">${E(b.t)}</span>`}
  function initials(n){const p=String(n||'?').trim().split(/\s+/);return ((p[0]||'?')[0]+((p[1]||'')[0]||'')).toUpperCase()}
  async function center(k,force){
    if(!k)return null;const c=MC.cache.get(k);
    if(!force&&c&&Date.now()-c.ts<12000)return c.data;
    if(MC.busy.has(k))return MC.busy.get(k);
    const p=api({action:'center',id:k},false).then(j=>{const d=j&&j.center||null;MC.cache.set(k,{ts:Date.now(),data:d});return d})
      .catch(()=>{const d=c?c.data:null;MC.cache.set(k,{ts:Date.now()-6000,data:d});return d}).finally(()=>MC.busy.delete(k));
    MC.busy.set(k,p);return p;
  }
  /* ------------------------------------------------------------ LIVE */
  function winHtml(w){
    if(!w||!w.teams||w.teams.length<2)return'';
    const a=w.teams[0],b=w.teams[1],sum=(Number(a.pct)||0)+(Number(b.pct)||0)||100,pa=Math.round((a.pct/sum)*100);
    return `<div class="mcCard mcWin">${head('Win probability','Live model')}<div class="mcWinRow"><div>${E(a.code||a.name)}<br><b>${N(a.pct,0)}%%</b></div><div class="r">${E(b.code||b.name)}<br><b>${N(b.pct,0)}%%</b></div></div><div class="mcWinBar"><i style="width:${pa}%%"></i><i style="width:${100-pa}%%"></i></div>${has(w.draw)?`<div class="mcWinNote">Draw ${N(w.draw,0)}%%</div>`:''}</div>`;
  }
  function liveHtml(c){
    const L=c.live;let h='';
    if(c.result&&c.result.text)h+=`<div class="mcRes">${E(c.result.text)}</div>`;
    if(!L){
      h+=`<div class="mcCard">${head('Match status',E(String(c.status||'').replace(/_/g,' ')))}${c.toss?`<div class="mcNeed">${E(c.toss)}</div>`:note('Live numbers start with the first ball.')}</div>`;
      return h+(c.innings&&c.innings.length?inningsSummary(c):'');
    }
    const m=[['CRR',has(L.crr)?N(L.crr,2):'—',true]];
    if(has(L.target)){m.push(['RRR',has(L.rrr)?N(L.rrr,2):'—',true]);m.push(['TARGET',L.target]);m.push(['NEED',has(L.need)?L.need:'—']);}
    else{m.push(['SCORE',`${L.runs}/${L.wickets}`]);m.push(['OVERS',L.overs||'—']);m.push(['P\u2019SHIP',L.partnership?`${L.partnership.runs}(${L.partnership.balls})`:'—']);}
    h+=`<div class="mcCard">${head(L.team?L.team.name+' batting':'Live','<span class="mcPill live">LIVE</span>')}<div class="mcMetrics">${m.map(x=>`<div class="mcMetric ${x[2]?'hot':''}"><span>${x[0]}</span><b>${E(x[1])}</b></div>`).join('')}</div>`;
    if(has(L.target)&&has(L.need)){h+=`<div class="mcNeed">${L.need>0?`Need <b>${E(L.need)}</b> run${L.need==1?'':'s'}${has(L.ballsLeft)?` from <b>${E(L.ballsLeft)}</b> ball${L.ballsLeft==1?'':'s'}`:''}`:'Scores level / target reached'}${L.requiredText?`<br><small>${E(L.requiredText)}</small>`:''}</div>`;}
    else if(L.requiredText){h+=`<div class="mcNeed">${E(L.requiredText)}</div>`}
    if(L.lead||L.trail)h+=`<div class="mcNeed">${E(L.lead||L.trail)}</div>`;
    if(L.projected&&L.projected.length)h+=`<div class="mcProj">${L.projected.map(p=>`<div>@ ${N(p.rate,1)} RPO<b>${E(p.score)}</b></div>`).join('')}</div><div class="mcWinNote">Projected score at the current and higher run rates</div>`;
    h+='</div>';
    h+=winHtml(L.winProbability);
    if(L.batters&&L.batters.length){
      h+=`<div class="mcCard">${head('At the crease',L.partnership?`P'ship ${E(L.partnership.runs)} (${E(L.partnership.balls)})`:'')}<table class="mcT bat"><tr><th>Batter</th><th>R</th><th>B</th><th>4s</th><th>6s</th><th>SR</th></tr>${L.batters.map(b=>`<tr class="${b.strike?'on':''}"><td class="n"><b>${E(b.name)}</b></td><td class="r">${E(b.r)}</td><td>${E(b.b)}</td><td>${E(b['4s'])}</td><td>${E(b['6s'])}</td><td class="dim">${has(b.sr)?N(b.sr,1):'—'}</td></tr>`).join('')}</table>`;
      if(L.bowler)h+=`<table class="mcT" style="margin-top:8px"><tr><th>Bowler</th><th>O</th><th>M</th><th>R</th><th>W</th><th>ECO</th></tr><tr class="on"><td class="n"><b>${E(L.bowler.name)}</b></td><td>${E(L.bowler.o)}</td><td>${E(L.bowler.m)}</td><td>${E(L.bowler.r)}</td><td class="r">${E(L.bowler.w)}</td><td class="dim">${has(L.bowler.eco)?N(L.bowler.eco,2):'—'}</td></tr>${L.prevBowler?`<tr><td class="n"><b>${E(L.prevBowler.name)}</b><small>Previous over</small></td><td>${E(L.prevBowler.o)}</td><td>${E(L.prevBowler.m)}</td><td>${E(L.prevBowler.r)}</td><td class="r">${E(L.prevBowler.w)}</td><td class="dim">${has(L.prevBowler.eco)?N(L.prevBowler.eco,2):'—'}</td></tr>`:''}</table>`;
      if(L.lastWicket)h+=`<div class="mcMini"><span>Last wicket</span><b>${E(L.lastWicket.name)}${has(L.lastWicket.r)?` ${E(L.lastWicket.r)}(${E(L.lastWicket.b)})`:''} · ${E(L.lastWicket.score)}${L.lastWicket.overs?` (${E(L.lastWicket.overs)} ov)`:''}</b></div>`;
      h+='</div>';
    }
    if(L.recentOvers&&L.recentOvers.length)h+=`<div class="mcCard">${head('Recent overs','This innings')}${L.recentOvers.slice().reverse().map(o=>`<div class="mcOverRow"><div class="o">OVER<b>${E(o.over||'')}</b></div><div class="bs">${o.balls.map(ball).join('')}</div><div class="rn">${E(o.runs)}<small>RUNS</small></div></div>`).join('')}</div>`;
    if(c.toss)h+=`<div class="mcCard">${head('Toss')}<div style="font-size:12.5px;font-weight:700">${E(c.toss)}</div></div>`;
    return h;
  }
  function inningsSummary(c){return `<div class="mcCard">${head('Innings')}${c.innings.map(i=>`<div class="mcKV"><span>${E(i.team.name)}</span><b>${E(i.runs)}/${E(i.wickets)} <span class="dim" style="font-weight:700">(${E(i.overs||'0')} ov)</span></b></div>`).join('')}</div>`}
  /* ------------------------------------------------------- SCORECARD */
  function scorecardHtml(c){
    const inns=c.innings||[];if(!inns.length)return note('The scorecard opens with the first ball.');
    const k=c.key;let sel=MC.inn[k];if(sel===undefined||!inns[sel]){const li=inns.findIndex(i=>i.live);sel=li>=0?li:inns.length-1}
    const tabs=inns.length>1?`<div class="mcInnTabs">${inns.map((i,n)=>`<button data-inn="${n}" class="${n===sel?'on':''}">${E(i.team.code||i.team.name)}${inns.filter(x=>x.team.side===i.team.side).length>1?' '+E(i.number)+(i.number=='1'?'st':'nd'):''}<b>${E(i.runs)}/${E(i.wickets)}</b></button>`).join('')}</div>`:'';
    const i=inns[sel],ex=i.extras||{};
    let h=tabs+`<div class="mcCard"><div class="mcInnHead"><div class="t">${E(i.team.name)}<small>${i.live?'<span class="mcPill live">LIVE</span> ':''}${has(i.rr)?'RR '+N(i.rr,2):''}${has(i.fours)?` · 4s ${E(i.fours)}`:''}${has(i.sixes)?` · 6s ${E(i.sixes)}`:''}</small></div><div class="s">${E(i.runs)}/${E(i.wickets)}<small>${E(i.overs||'0')} overs</small></div></div>`;
    h+=`<table class="mcT bat"><tr><th>Batter</th><th>R</th><th>B</th><th>4s</th><th>6s</th><th>SR</th></tr>${(i.batting||[]).map(b=>`<tr class="${b.onStrike?'on':''} ${b.out?'out':''}"><td class="n"><b>${E(b.name)}</b><small>${E(b.how)}</small></td><td class="r">${E(b.r)}</td><td>${E(b.b)}</td><td>${E(b['4s'])}</td><td>${E(b['6s'])}</td><td class="dim">${has(b.sr)?N(b.sr,1):'—'}</td></tr>`).join('')}</table>`;
    h+=`<div class="mcSum"><span>Extras <b>${E(ex.total||0)}</b> (b ${E(ex.b||0)}, lb ${E(ex.lb||0)}, w ${E(ex.w||0)}, nb ${E(ex.nb||0)}${ex.p?`, p ${E(ex.p)}`:''})</span></div>`;
    h+=`<div class="mcSum"><span>Total</span><span class="mcTot">${E(i.runs)}/${E(i.wickets)} <small style="font-size:11px;color:var(--mcMuted)">(${E(i.overs||'0')} ov)</small></span></div>`;
    if(i.yetToBat&&i.yetToBat.length)h+=`<div class="mcYet"><b>${i.complete?'Did not bat':'Yet to bat'}</b>${E(i.yetToBat.join(', '))}</div>`;
    h+='</div>';
    if(i.fow&&i.fow.length)h+=`<div class="mcCard">${head('Fall of wickets')}<div class="mcChips">${i.fow.map(f=>`<div class="mcFow"><b>${E(f.score)}</b>${E(f.name)}${f.overs?` · ${E(f.overs)} ov`:''}</div>`).join('')}</div></div>`;
    if(i.bowling&&i.bowling.length)h+=`<div class="mcCard">${head('Bowling')}<table class="mcT"><tr><th>Bowler</th><th>O</th><th>M</th><th>R</th><th>W</th><th>ECO</th></tr>${i.bowling.map(b=>`<tr class="${b.bowling?'on':''}"><td class="n"><b>${E(b.name)}</b></td><td>${E(b.o)}</td><td>${E(b.m)}</td><td>${E(b.r)}</td><td class="r">${E(b.w)}</td><td class="dim">${has(b.eco)?N(b.eco,2):'—'}</td></tr>`).join('')}</table></div>`;
    else h+=`<div class="mcCard">${head('Bowling')}${note('Bowling figures appear here once the provider publishes them.')}</div>`;
    if(i.partnerships&&i.partnerships.length){
      const max=Math.max(...i.partnerships.map(p=>p.runs||0),1);
      h+=`<div class="mcCard">${head('Partnerships')}${i.partnerships.map(p=>{const t=(p.a.r||0)+(p.b.r||0)||1,pa=Math.round((p.a.r||0)/t*100),w=Math.max(18,Math.round((p.runs||0)/max*100));return `<div class="mcPart"><div class="mcPartTop"><span>${E(p.wicket)}${['st','nd','rd'][p.wicket-1]||'th'} wicket${p.active?' · <span class="mcPill live">LIVE</span>':''}</span><b>${E(p.runs)} (${E(p.balls)})</b></div><div class="mcPartBar" style="width:${w}%%"><i style="width:${pa}%%"></i><i style="width:${100-pa}%%"></i></div><div class="mcPartNames"><span>${E(p.a.name)} ${E(p.a.r)}(${E(p.a.b)})</span><span>${E(p.b.name)} ${E(p.b.r)}(${E(p.b.b)})</span></div></div>`}).join('')}</div>`;
    }
    return h;
  }
  /* ------------------------------------------------------ COMMENTARY */
  function commsHtml(c){
    const rows=c.commentary||[];if(!rows.length)return note('Ball-by-ball commentary appears with the next delivery.');
    let h='<div class="mcCard">'+head('Commentary','Latest first'),last=null;
    rows.forEach(r=>{const g=(r.innings||'')+':'+(r.over||'');if(g!==last){last=g;const inOver=rows.filter(x=>(x.innings||'')+':'+(x.over||'')===g);const runs=inOver.reduce((s,x)=>s+(Number(x.runs)||0),0);h+=`<div class="mcOverHead"><span>Over <b>${E(r.over||'')}</b></span><span>${E(runs)} runs${inOver.some(x=>x.k==='wicket')?' · <b style="color:var(--mcW)">W</b>':''}</span></div>`}
      h+=`<div class="mcCom ${E(r.k||'')}"><div class="l">${ball(r)}<small>${E(r.ball)}</small></div><p>${E(r.text||'Delivery update')}${r.score?`<small>${E(r.score)}</small>`:''}</p></div>`});
    return h+'</div>';
  }
  /* ----------------------------------------------------------- OVERS */
  function oversData(c){
    const map=new Map();
    (c.commentary||[]).slice().reverse().forEach(r=>{if(!r.over)return;const g=(r.innings||'')+':'+r.over;if(!map.has(g))map.set(g,{over:r.over,innings:r.innings,balls:[],runs:0,wk:0});const o=map.get(g);o.balls.push({t:r.t,k:r.k});o.runs+=Number(r.runs)||0;if(r.k==='wicket')o.wk++});
    const L=c.live;
    if(L&&L.recentOvers)L.recentOvers.forEach(o=>{const g=(L.innings||'')+':'+o.over;map.set(g,{over:o.over,innings:L.innings,balls:o.balls,runs:o.runs,wk:o.wickets||0,full:true})});
    const legal=o=>o.balls.filter(b=>!/(wd|nb)$/.test(String(b.t))).length;
    const rows=Array.from(map.values()).sort((a,b)=>(a.innings||'').localeCompare(b.innings||'')||a.over-b.over);
    const last=rows[rows.length-1];
    return rows.filter(o=>o.full||legal(o)>=6||o===last);
  }
  function oversHtml(c){
    const ov=oversData(c);if(!ov.length)return note('Over-by-over timeline appears once the innings starts.');
    const cur=ov.filter(o=>o.innings===(c.live&&c.live.innings)||!c.live),use=(cur.length?cur:ov).slice(-12),max=Math.max(...use.map(o=>o.runs),6);
    let h=`<div class="mcCard">${head('Runs per over','Last '+use.length+' overs')}<div class="mcMan">${use.map(o=>`<div><em>${E(o.runs)}</em>${o.wk?'<u></u>':''}<i style="height:${Math.max(4,Math.round(o.runs/max*62))}px"></i></div>`).join('')}</div><div class="mcManX">${use.map(o=>`<span>${E(o.over)}</span>`).join('')}</div></div>`;
    h+=`<div class="mcCard">${head('Over timeline','Latest first')}${ov.slice().reverse().map(o=>`<div class="mcOverRow"><div class="o">OVER<b>${E(o.over)}</b></div><div class="bs">${o.balls.map(ball).join('')}</div><div class="rn">${E(o.runs)}<small>${o.wk?o.wk+' WKT':'RUNS'}</small></div></div>`).join('')}</div>`;
    return h;
  }
  /* ---------------------------------------------------------- SQUADS */
  function squadsHtml(c){
    const sq=(c.squads||[]).filter(s=>s.xi&&s.xi.length);if(!sq.length)return note('Squads and playing XI appear here once they are announced.');
    let s=MC.sq[c.key]||0;if(!sq[s])s=0;const t=sq[s];
    const row=p=>`<div class="mcPl"><span class="mcAv">${E(initials(p.name))}</span><div class="nm"><b>${E(p.name)}${p.c?'<span class="mcTag">C</span>':''}${p.wk?'<span class="mcTag">WK</span>':''}</b>${p.role?`<small>${E(p.role)}</small>`:''}</div></div>`;
    return `<div class="mcSeg">${sq.map((x,n)=>`<button data-sq="${n}" class="${n===s?'on':''}">${E(x.team.name)}</button>`).join('')}</div><div class="mcCard">${head(t.announced?'Playing XI':'Squad',E(t.team.code))}<div class="mcPlayers">${t.xi.map(row).join('')}</div></div>${t.bench&&t.bench.length?`<div class="mcCard">${head('Bench')}<div class="mcPlayers">${t.bench.map(row).join('')}</div></div>`:''}`;
  }
  /* ----------------------------------------------------------- TABLE */
  function tableHtml(c,pts){
    if(!pts)return skel();
    const g=(pts.groups||[]).filter(x=>x.rows&&x.rows.length);
    if(!g.length)return `<div class="mcCard">${head('Points table',E(c.tournament&&c.tournament.name||''))}${note('No points table for this series (bilateral series or table not published yet).')}</div>`;
    return g.map(x=>`<div class="mcCard">${head(x.name||'Standings',E(pts.tournament||''))}<table class="mcT"><tr><th>Team</th><th>P</th><th>W</th><th>L</th><th>NR</th><th>PTS</th><th>NRR</th></tr>${x.rows.map((r,n)=>`<tr><td class="n"><b>${n+1}. ${E(r.code||r.team)}</b><small>${E(r.team)}</small></td><td>${E(r.p)}</td><td>${E(r.w)}</td><td>${E(r.l)}</td><td>${E(r.nr)}</td><td class="r">${E(r.pts)}</td><td class="dim">${has(r.nrr)?(r.nrr>0?'+':'')+N(r.nrr,3):'—'}</td></tr>`).join('')}</table></div>`).join('');
  }
  function loadPoints(k){
    const c=MC.pts.get(k);if(c&&Date.now()-c.ts<600000)return Promise.resolve(c.data);
    return api({action:'points',id:k},false).then(j=>{const d=j.points||{groups:[]};MC.pts.set(k,{ts:Date.now(),data:d});return d}).catch(()=>({groups:[]}));
  }
  /* ------------------------------------------------------------ INFO */
  function infoHtml(c){
    const rows=(c.info||[]).slice();
    if(c.startAt){try{rows.splice(2,0,['Start',new Date(c.startAt*1000).toLocaleString([],{weekday:'short',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})])}catch(e){}}
    if(c.status)rows.push(['Status',String(c.playStatus||c.status).replace(/_/g,' ').replace(/\b\w/g,x=>x.toUpperCase())]);
    let h=c.result&&c.result.text?`<div class="mcRes">${E(c.result.text)}</div>`:'';
    h+=`<div class="mcCard">${head('Match info')}${rows.length?rows.map(r=>`<div class="mcKV"><span>${E(r[0])}</span><b>${E(r[1])}</b></div>`).join(''):note('Match information will appear here when available.')}</div>`;
    if(c.messages&&c.messages.length)h+=`<div class="mcCard">${head('Match notes')}${c.messages.map(m=>`<div class="mcKV"><b style="text-align:left">${E(m)}</b></div>`).join('')}</div>`;
    return h;
  }

  /* ------------------------------------------------- ROANUZ FULL FEEDS */
  const FEED={balls:new Map(),summary:new Map(),busy:new Map(),inn:{},filt:{},quick:0};
  function feedGet(kind,k,force){
    const store=FEED[kind],c=store.get(k),ttl=kind==='balls'?10000:30000,bk=kind+':'+k;
    if(!force&&c&&Date.now()-c.ts<ttl)return Promise.resolve(c.data);
    if(FEED.busy.has(bk))return FEED.busy.get(bk);
    const p=api({action:kind==='balls'?'balls':'oversummary',id:k},false).then(j=>{const d=j&&(kind==='balls'?j.balls:j.summary)||null;const v=d||(c&&c.data)||{none:true,reason:(j&&j.reason)||'unavailable'};store.set(k,{ts:Date.now(),data:v});return v})
      .catch(()=>{const v=(c&&c.data)||{none:true,reason:'unavailable'};store.set(k,{ts:Date.now()-5000,data:v});return v}).finally(()=>FEED.busy.delete(bk));
    FEED.busy.set(bk,p);return p;
  }
  function innPick(kind,k,inns,live){let s=FEED.inn[kind+k];if(s===undefined||!inns[s]){s=inns.length-1}return s}
  function innTabs(kind,inns,sel){return inns.length>1?`<div class="mcInnTabs">${inns.map((i,n)=>`<button data-finn="${kind}:${n}" class="${n===sel?'on':''}">${E(i.label)}<b>${kind==='summary'?`${E(i.runs)}/${E(i.wickets||0)}`:`${E(i.overs.length)} ov`}</b></button>`).join('')}</div>`:''}
  function fullCommsHtml(c,f){
    if(!f||f.none||!f.innings||!f.innings.length){
      const why=f&&f.reason==='not_live'?'Ball-by-ball commentary starts with the first delivery.':'Full ball-by-ball feed is unavailable right now — showing the latest deliveries.';
      return (c.commentary&&c.commentary.length?`<div class="mcSrc"><span>${E(why)}</span></div>`+commsHtml(c):note(why));
    }
    const inns=f.innings,sel=innPick('balls',c.key,inns),i=inns[sel],flt=FEED.filt[c.key]||'all';
    const keep=b=>flt==='all'||(flt==='w'?b.k==='wicket':(b.k==='four'||b.k==='six'));
    let h=innTabs('balls',inns,sel)+`<div class="mcSeg"><button data-flt="all" class="${flt==='all'?'on':''}">ALL BALLS</button><button data-flt="w" class="${flt==='w'?'on':''}">WICKETS</button><button data-flt="b" class="${flt==='b'?'on':''}">4s &amp; 6s</button></div>`;
    h+=`<div class="mcCard">${head('Ball by ball',(f.live?'<span class="mcPill live">LIVE</span> ':'')+E(i.label))}`;
    let any=false;
    i.overs.forEach(o=>{const bs=o.balls.filter(keep);if(!bs.length)return;any=true;
      h+=`<div class="mcOverHead"><span>Over <b>${E(o.over)}</b>${o.bowler?` <span class="bw">· ${E(o.bowler)}</span>`:''}</span><span>${E(o.runs)} run${o.runs==1?'':'s'}${o.wickets?` · <b style="color:var(--mcW)">${E(o.wickets)}W</b>`:''}${o.score?` · <span class="mcSc">${E(o.score.replace(/ in .*$/,''))}</span>`:''}</span></div>`;
      bs.slice().reverse().forEach(b=>{h+=`<div class="mcCom ${E(b.k||'')}"><div class="l">${ball(b)}<small>${E(b.ball)}</small></div><p>${b.k==='wicket'&&!/wicket/i.test(b.text||'')?'<em>WICKET</em> ':''}${E(b.text||'Delivery update')}${b.k==='wicket'&&b.out?`<small>${E(b.out)}${b.how?' · '+E(b.how):''}</small>`:''}${b.score?`<small>${E(b.score)}</small>`:''}</p></div>`})});
    if(!any)h+=note(flt==='w'?'No wickets in this innings yet.':'No boundaries in this innings yet.');
    h+='</div>';
    if(!f.complete)h+='<div class="mcMore">Loading earlier overs…</div>';
    return h;
  }
  function wormSvg(inns,maxOv){
    const W=320,H=150,P=24,mx=Math.max(maxOv,1),my=Math.max(...inns.map(i=>i.runs||0),10);
    const x=o=>P+(W-P-6)*(o/mx),y=r=>H-16-(H-28)*(r/my);
    const col=['var(--mcBarA)','var(--mcBarB)','var(--mcSix)','var(--mcX)'];
    let g=`<line class="ax" x1="${P}" y1="${H-16}" x2="${W-4}" y2="${H-16}"/><line class="ax" x1="${P}" y1="8" x2="${P}" y2="${H-16}"/>`;
    [0.5,1].forEach(t=>{g+=`<text x="2" y="${y(my*t)+3}">${Math.round(my*t)}</text>`});
    const step=mx>30?10:5;for(let o=step;o<=mx;o+=step)g+=`<text x="${x(o)-4}" y="${H-4}">${o}</text>`;
    inns.forEach((i,n)=>{const pts=[[0,0]].concat(i.overs.map(o=>[o.over,o.total||0]));g+=`<polyline fill="none" stroke="${col[n%%4]}" stroke-width="2.2" stroke-linejoin="round" points="${pts.map(p=>x(p[0]).toFixed(1)+','+y(p[1]).toFixed(1)).join(' ')}"/>`;
      i.overs.filter(o=>o.wickets).forEach(o=>{g+=`<circle cx="${x(o.over).toFixed(1)}" cy="${y(o.total||0).toFixed(1)}" r="3.2" fill="var(--mcW)" stroke="var(--mcPanel)" stroke-width="1"/>`})});
    return `<div class="mcWorm"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Worm chart">${g}</svg><div class="mcLegend">${inns.map((i,n)=>`<span><i style="background:${col[n%%4]}"></i>${E(i.label)} ${E(i.runs)}/${E(i.wickets||0)}</span>`).join('')}<span><i style="background:var(--mcW);width:7px;height:7px;border-radius:50%%"></i>Wicket</span></div></div>`;
  }
  function fullOversHtml(c,s){
    if(!s||s.none||!s.innings||!s.innings.length){
      const why=s&&s.reason==='not_live'?'Over-by-over summary starts after the first over.':'Full over summary is unavailable right now — showing recent overs.';
      return `<div class="mcSrc"><span>${E(why)}</span></div>`+oversHtml(c);
    }
    const inns=s.innings,sel=innPick('summary',c.key,inns),i=inns[sel];
    const per=(c.format||'').toLowerCase().indexOf('odi')>=0?50:(c.format||'').toLowerCase().indexOf('t20')>=0?20:0;
    const maxOv=Math.max(per,...inns.map(x=>x.overs.length?x.overs[x.overs.length-1].over:0));
    const bb=FEED.balls.get(c.key),bbd=bb&&bb.data&&bb.data.innings?bb.data.innings.find(x=>x.innings===i.innings):null;
    const ballsFor=n=>{if(!bbd)return null;const o=bbd.overs.find(x=>x.over===n);return o?o.balls:null};
    const mx=Math.max(i.maxOver||0,6);
    let h=innTabs('summary',inns,sel);
    h+=`<div class="mcCard">${head('Runs per over',E(i.label)+' · '+i.overs.length+' overs')}<div class="mcManS"><div class="mcMan">${i.overs.map(o=>`<div><em>${E(o.runs)}</em>${o.wickets?'<u></u>':''}<i style="height:${Math.max(3,Math.round(o.runs/mx*60))}px"></i></div>`).join('')}</div><div class="mcManX">${i.overs.map(o=>`<span>${o.over%%5===0||i.overs.length<=12?E(o.over):''}</span>`).join('')}</div></div></div>`;
    h+=`<div class="mcCard">${head('Worm','Cumulative runs')}${wormSvg(inns,maxOv)}</div>`;
    h+=`<div class="mcCard">${head('Over by over','Latest first')}${i.overs.slice().reverse().map(o=>{const bs=ballsFor(o.over);const bat=(o.batters||[]).map(b=>`<b>${E(b.name)}</b> ${E(b.r)}(${E(b.b)})`).join(' · ');const bw=(o.bowlers||[])[0];
      return `<div class="mcOS ${o.wickets?'wk':''}"><div class="o">OVER<b>${E(o.over)}</b></div><div class="d">${bs?`<div class="bs">${bs.map(ball).join('')}</div>`:''}${bat?`<div>${bat}</div>`:''}${bw?`<div>${E(bw.name)} <b>${E(bw.o)}-${E(bw.r)}-${E(bw.w)}</b></div>`:''}${has(o.rrr)?`<div>RRR <b>${N(o.rrr,2)}</b>${has(o.need)?` · need <b>${E(o.need)}</b>`:''}</div>`:''}</div><div class="r">${E(o.runs)}${o.wickets?` <span style="font-size:11px">${E(o.wickets)}W</span>`:''}<small>${E(o.total)}/${E(o.totalWickets||0)}${has(o.rr)?' · RR '+N(o.rr,2):''}</small></div></div>`}).join('')}</div>`;
    if(!s.complete)h+='<div class="mcMore">Loading earlier overs…</div>';
    return h;
  }
  function feedPaint(tab,c){
    const p=document.getElementById('panel');if(!p)return;
    const kind=tab==='comms'?'balls':'summary',k=c.key,cached=FEED[kind].get(k);
    const render=d=>{const pp=document.getElementById('panel');if(!pp||detailTab!==tab||curKey()!==k)return;const html='<div class="mc">'+(tab==='comms'?fullCommsHtml(c,d):fullOversHtml(c,d))+'</div>';if(MC.sig[tab]===html&&pp.querySelector('.mc'))return;MC.sig[tab]=html;pp.innerHTML=html;bindFeed(tab,c,d)};
    if(cached)render(cached.data);else p.innerHTML='<div class="mc">'+skel()+skel()+'</div>';
    const fresh=!cached||Date.now()-cached.ts>(kind==='balls'?10000:30000);
    const extra=kind==='summary'&&!FEED.balls.get(k)?feedGet('balls',k,false):Promise.resolve();
    if(fresh||!cached)Promise.all([feedGet(kind,k,false),extra]).then(([d])=>{render(d);if(d&&!d.none&&!d.complete&&FEED.quick<12){FEED.quick++;setTimeout(()=>{if(detailTab===tab&&curKey()===k){const cur=FEED[kind].get(k);if(cur)cur.ts=0;feedPaint(tab,c)}},4000)}});
  }
  function bindFeed(tab,c,d){
    const p=document.getElementById('panel');if(!p)return;
    p.querySelectorAll('[data-finn]').forEach(b=>b.onclick=()=>{const [kind,n]=b.dataset.finn.split(':');FEED.inn[kind+c.key]=Number(n);MC.sig={};feedPaint(tab,c)});
    p.querySelectorAll('[data-flt]').forEach(b=>b.onclick=()=>{FEED.filt[c.key]=b.dataset.flt;MC.sig={};feedPaint(tab,c)});
  }
  /* ------------------------------------------------ ROANUZ LIVE ODDS */
  function oddsHtml(o){
    if(!o||!o.teams||o.teams.length<2)return '';
    return `<div class="mc"><div class="mcCard">${head('Live odds · Match winner','Roanuz')}<div class="mcOdds">${o.teams.map(t=>`<div class="mcOdd ${t.code===o.favourite?'fav':''}">${t.code===o.favourite?'<span class="tag">FAV</span>':''}<span class="nm">${E(t.name)}</span><b>${N(t.decimal,2)}</b><small>${t.fractional?E(t.fractional)+' · ':''}${has(t.pct)?`Win ${N(t.pct,0)}%%`:has(t.implied)?`Implied ${N(t.implied,0)}%%`:''}</small></div>`).join('')}</div>${o.draw&&has(o.draw.decimal)?`<div class="mcOddDraw"><span>Draw</span><b>${N(o.draw.decimal,2)}${has(o.draw.pct)?` · ${N(o.draw.pct,0)}%%`:''}</b></div>`:''}<div class="mcWinNote">Decimal odds and win probability from the Roanuz live odds feed · updates while the match is live</div></div></div>`;
  }
  function oddsBox(){let b=document.getElementById('mcOddsBox');const p=document.getElementById('panel');if(!b&&p&&p.parentNode){b=document.createElement('div');b.id='mcOddsBox';p.parentNode.insertBefore(b,p.nextSibling)}return b}
  function paintOdds(c){const b=oddsBox();if(!b)return;const html=c&&c.isLive?oddsHtml(c.odds):'';b.innerHTML=html;b.classList.toggle('on',!!html&&detailTab==='bhav')}
  const R={match:liveHtml,scorecard:scorecardHtml,comms:commsHtml,overs:oversHtml,squads:squadsHtml,info:infoHtml};
  function paint(tab,c,force){
    const p=document.getElementById('panel');if(!p)return;
    if(tab==='table'){const k=c.key;const cached=MC.pts.get(k);p.innerHTML='<div class="mc">'+tableHtml(c,cached&&cached.data)+'</div>';if(!cached)loadPoints(k).then(d=>{if(detailTab==='table'&&curKey()===k){const pp=document.getElementById('panel');if(pp)pp.innerHTML='<div class="mc">'+tableHtml(c,d)+'</div>'}});return}
    if(tab==='comms'||tab==='overs'){feedPaint(tab,c);return}
    const html='<div class="mc">'+R[tab](c)+'</div>';
    if(!force&&MC.sig[tab]===html&&p.querySelector('.mc'))return;
    MC.sig[tab]=html;p.innerHTML=html;
    p.querySelectorAll('[data-inn]').forEach(b=>b.onclick=()=>{MC.inn[c.key]=Number(b.dataset.inn);paint('scorecard',c,true)});
    p.querySelectorAll('[data-sq]').forEach(b=>b.onclick=()=>{MC.sq[c.key]=Number(b.dataset.sq);paint('squads',c,true)});
  }
  function legacy(tab,prev){
    const p=document.getElementById('panel');if(!p)return;
    const map={scorecard:'scorecard',comms:'balls',info:'info',match:'match'};
    if(map[tab]){const keep=detailTab;detailTab=map[tab];try{prev()}finally{detailTab=keep}return}
    p.innerHTML='<div class="mc">'+note(tab==='squads'?'Squads appear here once they are announced.':tab==='table'?'No points table for this match yet.':'This view opens when the live feed for this match is available.')+'</div>';
  }
  if(typeof tabsHtml==='function'){
    tabsHtml=function(){const cur=['more','graphs','stats'].includes(detailTab)?'info':detailTab;return TABS.map(([k,l])=>`<button class="dtab ${cur===k?'on':''}" data-tab="${k}">${l}</button>`).join('')};
  }
  if(typeof drawPanel==='function'){
    const prevPanel=drawPanel;
    drawPanel=function(){
      if(['more','graphs','stats'].includes(detailTab))detailTab='info';
      const tab=detailTab;const ob=document.getElementById('mcOddsBox');if(ob)ob.classList.toggle('on',tab==='bhav'&&!!ob.innerHTML);
      if(tab==='bhav'){const r=prevPanel();const k0=curKey();const c0=MC.cache.get(k0);if(c0&&c0.data)paintOdds(c0.data);center(k0).then(d=>{if(detailTab==='bhav'&&curKey()===k0)paintOdds(d)});return r}
      if(!OWN.has(tab))return prevPanel();
      const k=curKey(),p=document.getElementById('panel');if(!p)return;
      MC.sig={};
      const c=MC.cache.get(k);
      if(c&&c.data)paint(tab,c.data,true);else if(tab==='match')prevPanel();else p.innerHTML='<div class="mc">'+skel()+'</div>';
      center(k).then(d=>{if(detailTab!==tab||curKey()!==k)return;if(d)paint(tab,d);else if(!(c&&c.data))legacy(tab,prevPanel)});
      requestAnimationFrame(()=>{const on=document.querySelector('#detail .dtabs .dtab.on');if(on&&on.scrollIntoView)try{on.scrollIntoView({block:'nearest',inline:'center'})}catch(e){}});
    };
  }
  function tick(){
    const d=document.getElementById('detail');
    if(!d||d.style.display==='none'||!detailData||!(OWN.has(detailTab)||detailTab==='bhav')||document.hidden){const ob=document.getElementById('mcOddsBox');if(ob&&detailTab!=='bhav')ob.classList.remove('on');return}
    const k=curKey(),c=MC.cache.get(k);if(!c||!c.data||!c.data.isLive)return;
    const tab=detailTab;
    if(tab==='comms'||tab==='overs'){const kind=tab==='comms'?'balls':'summary';feedGet(kind,k,true).then(()=>{if(detailTab===tab&&curKey()===k)feedPaint(tab,c.data)});return}
    center(k,true).then(x=>{if(!x||curKey()!==k)return;if(detailTab==='bhav')paintOdds(x);else if(OWN.has(detailTab)&&detailTab!=='table')paint(detailTab,x)});
  }
  MC.timer=setInterval(tick,15000);
  /* -------------------------------------------------------- FOOTBALL */
  function fbTeam(t){return `<div class="mcFbTeam">${t.logo?`<img src="${E(t.logo)}" alt="" loading="lazy" onerror="this.remove()">`:''}<span>${E(t.name)}</span></div>`}
  function fbCard(m){
    const live=m.phase==='live',score=has(m.hg)||has(m.ag);
    let st=live?(has(m.clock)?`${m.clock}'`:E(m.status)):m.phase==='upcoming'?(m.start?new Date(m.start).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}):'Scheduled'):E(m.status);
    return `<div class="mcFb ${live?'live':''}">${fbTeam(m.home)}<div class="mcFbGoal">${score?E(m.hg??'-'):''}</div>${fbTeam(m.away)}<div class="mcFbGoal">${score?E(m.ag??'-'):''}</div><div class="mcFbMeta"><span class="${live?'lv':''}">${live?'● LIVE · ':''}${st}</span><span>${m.pens?'Pens '+E(m.pens):m.phase==='done'?'FULL TIME':''}</span></div></div>`;
  }
  function fbRender(){
    const box=document.getElementById('mcFootball');if(!box)return;
    const all=MC.fb||[],live=all.filter(m=>m.phase==='live'),rows=MC.fbFilter==='live'?live:all;
    let h=`<div class="mcSeg"><button data-fb="live" class="${MC.fbFilter==='live'?'on':''}">LIVE (${live.length})</button><button data-fb="all" class="${MC.fbFilter==='all'?'on':''}">TODAY (${all.length})</button></div>`;
    if(MC.fb===null)h+=skel()+skel();
    else if(!rows.length)h+=note(MC.fbFilter==='live'?'No live football right now. Check TODAY for kick-off times.':'No football fixtures available right now.');
    else{let lg=null;rows.forEach(m=>{const g=m.league+'|'+m.country;if(g!==lg){lg=g;h+=`<div class="mcFbLeague">${m.leagueLogo?`<img src="${E(m.leagueLogo)}" alt="" onerror="this.remove()">`:''}${E(m.league||'Football')}${m.country?' · '+E(m.country):''}</div>`}h+=fbCard(m)})}
    box.innerHTML='<div class="mc">'+h+'</div>';
    box.querySelectorAll('[data-fb]').forEach(b=>b.onclick=()=>{MC.fbFilter=b.dataset.fb;fbRender()});
  }
  function fbLoad(force){
    if(!force&&MC.fb&&Date.now()-MC.fbAt<60000){fbRender();return}
    if(MC.fbBusy)return;fbRender();
    MC.fbBusy=api({action:'football'},false).then(j=>{MC.fb=Array.isArray(j.matches)?j.matches:[];MC.fbAt=Date.now();if(MC.fbFilter==='live'&&!MC.fb.some(m=>m.phase==='live'))MC.fbFilter='all'}).catch(()=>{MC.fb=MC.fb||[]}).finally(()=>{MC.fbBusy=null;fbRender()});
  }
  function setSport(s){
    document.body.classList.toggle('mcFootball',s==='football');
    document.querySelectorAll('.mcSport button').forEach(b=>b.classList.toggle('on',b.dataset.sport===s));
    if(s==='football')fbLoad(false);
  }
  function mountSport(){
    const home=document.getElementById('home');if(!home||document.querySelector('.mcSport'))return;
    const bar=document.createElement('div');bar.className='mcSport';bar.innerHTML='<button data-sport="cricket" class="on">🏏 CRICKET</button><button data-sport="football">⚽ FOOTBALL</button>';
    home.insertBefore(bar,home.firstChild);
    const box=document.createElement('div');box.id='mcFootball';home.appendChild(box);
    bar.onclick=e=>{const b=e.target.closest('button');if(b)setSport(b.dataset.sport)};
    document.querySelectorAll('.top .tab').forEach(t=>t.addEventListener('click',()=>setSport('cricket')));
    const nav=document.querySelector('.bottom');if(nav)nav.addEventListener('click',e=>{const b=e.target.closest('button');if(b&&b.dataset.nav!=='home')setSport('cricket')});
    setInterval(()=>{if(document.body.classList.contains('mcFootball')&&!document.hidden&&document.getElementById('home').style.display!=='none')fbLoad(true)},90000);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mountSport);else mountSport();
  window.__mcCenter=center;
})();
</script>
"""


def page_assets(brand: str):
    brand = "dura" if str(brand).lower().startswith("dura") else "ibetin"
    css = _CSS % THEMES[brand]
    js = _JS % {"brand": brand}
    return css, js
