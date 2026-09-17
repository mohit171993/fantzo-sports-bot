import logging
import os
from urllib.parse import urlencode

import ibetin_liveline_trial as liveline
import ibetin_liveline_v21_roanuz_clean_ui as v21

logger = logging.getLogger(__name__)

liveline.LIVELINE_PATH = "/admin/liveline-ibetinv22"
liveline.LIVELINE_API_PATH = "/admin/liveline-ibetinv22/api"


def _admin_url() -> str:
    root = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/") or "https://ibetin-app-production.up.railway.app"
    return f"{root}{liveline.LIVELINE_PATH}?{urlencode({'t': liveline._token(), 'v': '20260917-v22-fastfeed'})}"


def _fast_matches(mode: str):
    source = "Roanuz V5 primary"
    try:
        rows = v21.v20._roanuz_matches_mode(mode)
    except Exception as exc:
        logger.warning("IBETIN V22 Roanuz %s list failed: %s", mode, str(exc)[:160])
        rows = []

    valid = [m for m in rows if v21._display_ok(m)]
    if valid:
        logger.info("IBETIN V22 fast feed mode=%s source=Roanuz matches=%s first=%s vs %s", mode, len(valid), valid[0].get("home", {}).get("name"), valid[0].get("away", {}).get("name"))
        return valid[:40], source

    try:
        fallback = v21.v20._OLD_MATCHES_MODE(mode)
        if fallback:
            logger.warning("IBETIN V22 display fallback mode=%s matches=%s", mode, len(fallback))
            return fallback[:40], "Highlightly display fallback"
    except Exception as exc:
        logger.warning("IBETIN V22 fallback failed mode=%s: %s", mode, str(exc)[:160])
    return [], source


v21._matches = _fast_matches


def _page() -> str:
    html = v21._page()
    html = html.replace("/admin/liveline-ibetinv21/api", liveline.LIVELINE_API_PATH)
    html = html.replace("V21 · ROANUZ", "V22 · ROANUZ")
    html = html.replace("20260917-v21-clean-roanuz", "20260917-v22-fastfeed")
    html = html.replace("Refreshing '+mode+' cricket…", "Loading '+mode+' cricket…")
    html = html.replace("setInterval(()=>{if(!document.hidden&&document.getElementById('home').style.display!=='none')load('live')},20000)", "setInterval(()=>{if(!document.hidden&&document.getElementById('home').style.display!=='none')load('live')},30000)")
    return html


liveline.admin_url = _admin_url
liveline._page = _page
liveline._api = v21._api
app = v21.app

logger.info("IBETIN V22 installed: immediate Roanuz fixture render; live detail and BHAV load lazily")

if __name__ == "__main__":
    app.base.ibetin_start.main()
