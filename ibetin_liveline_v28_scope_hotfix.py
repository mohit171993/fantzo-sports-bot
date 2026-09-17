import logging

import ibetin_liveline_v27_premium_ui as v27

logger = logging.getLogger(__name__)
v25 = v27.v25
_ORIGINAL_PAGE = v27._page_v27


def _page_v28() -> str:
    html = _ORIGINAL_PAGE()

    # V27 regression: the scoreboard shell is rendered before the detail payload
    # variable `x` exists. Keep that shell dependent only on the already-loaded
    # match object `m`; detail-only data belongs in drawDetail(), where `x` is in
    # scope.
    html = html.replace(
        "${x.roanuz?.target?chaseInfo(x.roanuz.target,m):''}${lastSixHtml(x.timeline||[])}",
        "",
        1,
    )

    old_match = "if(tab==='match'){const rr=x.roanuz?.runRate;const rv=rateValue(rr);p.innerHTML=ptitle('MATCH SNAPSHOT')+`<div class=\"notice premiumSnapshot\">${rv?`<div class=\"metricRow\"><span class=\"metric\">CRR <b>${esc(rv)}</b></span></div>`:''}${currentPlayersHtml(x)}${lastSixHtml(x.timeline||[])}</div>`}"
    new_match = "if(tab==='match'){const rr=x.roanuz?.runRate;const target=x.roanuz?.target;const rv=rateValue(rr);p.innerHTML=ptitle('MATCH SNAPSHOT')+`<div class=\"notice premiumSnapshot\">${target?chaseInfo(target,m):''}${rv?`<div class=\"metricRow\"><span class=\"metric\">CRR <b>${esc(rv)}</b></span></div>`:''}${currentPlayersHtml(x)}${lastSixHtml(x.timeline||[])}</div>`}"
    html = html.replace(old_match, new_match, 1)

    return html


# UI-only scope hotfix. Feed/cache/API behavior remains the V25 stack underneath.
v25.v23._page = _page_v28
v25.v23.liveline._page = _page_v28


def _self_test() -> None:
    page = _page_v28()
    checks = {
        "scoreboard_scope_safe": "${x.roanuz?.target?chaseInfo(x.roanuz.target,m):''}" not in page,
        "chase_moved_to_detail": "const target=x.roanuz?.target" in page and "target?chaseInfo(target,m)" in page,
        "premium_ui_preserved": "MATCH SNAPSHOT" in page and "currentPlayersHtml(x)" in page and "lastSixHtml(x.timeline||[])" in page,
        "four_tabs_preserved": "['more','MORE']" in page,
        "fast_feed_preserved": "hydrateScore" in page and "__scoreHydrateBusy" in page,
    }
    ok = all(checks.values())
    (logger.info if ok else logger.error)("IBETIN V28 scope hotfix self-test %s checks=%s", "PASS" if ok else "FAILED", checks)
    if not ok:
        raise RuntimeError(f"V28 scope hotfix self-test failed: {checks}")


_self_test()
logger.info("IBETIN V28 installed: V27 premium UI with match-detail scope crash fixed")

app = v25.app

if __name__ == "__main__":
    app.base.ibetin_start.main()
