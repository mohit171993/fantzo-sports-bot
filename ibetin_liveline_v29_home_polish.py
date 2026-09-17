import logging
import re

import ibetin_liveline_v28_scope_hotfix as v28

logger = logging.getLogger(__name__)
v27 = v28.v27
v25 = v27.v25
_ORIGINAL_PAGE = v28._page_v28


def _page_v29() -> str:
    html = _ORIGINAL_PAGE()

    # Home screen is consumer-facing: remove provider/debug command-center hero.
    html = re.sub(r'<section class="hero">.*?</section>', '', html, count=1, flags=re.S)

    # Hide provider/source internals from the home status line while keeping count + freshness.
    old_status = "document.getElementById('status').textContent=`${allMatches.length} matches · ${j.source||'sports feed'} · ${new Date(j.generatedAt).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}`;"
    new_status = "document.getElementById('status').textContent=`${allMatches.length} ${mode==='live'?'live ':''}matches · Updated ${new Date(j.generatedAt).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}`;"
    html = html.replace(old_status, new_status, 1)

    # Home-page spacing/readability. Extra bottom room ensures the fixed nav never traps the last card.
    css = r"""
.main{padding:12px 12px calc(112px + env(safe-area-inset-bottom))!important}
.tools{margin:2px 0 8px!important;gap:8px!important}.search{height:46px!important;border-radius:14px!important;font-size:12px!important;padding:0 14px!important}.refresh{height:46px!important;width:46px!important;border-radius:14px!important}
.status{font-size:9px!important;margin:0 3px 10px!important;color:#7d91a4!important}.list{gap:10px!important;padding-bottom:12px}.league{font-size:10px!important;margin:6px 3px 1px!important}
.match{border-radius:17px!important;box-shadow:0 5px 16px rgba(7,36,68,.06)!important}.mh{padding:10px 12px 5px!important}.team{padding:8px 12px!important}.foot{padding:9px 12px!important}.tn{font-size:13px!important}.sc{font-size:21px!important}.si,.ta{font-size:8px!important}.fmt,.badge{font-size:7px!important}
.bottom{left:12px!important;right:12px!important;bottom:max(10px,env(safe-area-inset-bottom))!important;padding:6px!important}.bottom button{height:44px!important}
"""
    html = html.replace('</style><link rel="icon" href="data:"></head>', css + '</style><link rel="icon" href="data:"></head>', 1)

    return html


v25.v23._page = _page_v29
v25.v23.liveline._page = _page_v29


def _self_test() -> None:
    page = _page_v29()
    checks = {
        'no_command_center': 'Live Cricket Command Center' not in page,
        'no_roanuz_home_label': 'ROANUZ V5 · PRIMARY DATA' not in page,
        'no_direct_match_key': 'DIRECT MATCH KEY' not in page,
        'no_api_saver_badge': 'API SAVER ON' not in page,
        'no_highlightly_badge': 'HIGHLIGHTLY FALLBACK' not in page,
        'provider_hidden_from_status': "j.source||'sports feed'" not in page,
        'freshness_preserved': 'Updated ${new Date(j.generatedAt)' in page,
        'bottom_spacing': '112px + env(safe-area-inset-bottom)' in page,
        'premium_detail_preserved': 'currentPlayersHtml' in page and "['more','MORE']" in page,
        'scope_fix_preserved': '${x.roanuz?.target' not in page.split('function drawDetail()', 1)[0],
        'fast_feed_preserved': 'hydrateScore' in page and '__scoreHydrateBusy' in page,
    }
    ok = all(checks.values())
    (logger.info if ok else logger.error)("IBETIN V29 home polish self-test %s checks=%s", "PASS" if ok else "FAILED", checks)
    if not ok:
        raise RuntimeError(f"V29 home polish self-test failed: {checks}")


_self_test()
logger.info("IBETIN V29 installed: clean consumer home + V28 detail hotfix + V25 fast feed/cache")

app = v25.app

if __name__ == '__main__':
    app.base.ibetin_start.main()
