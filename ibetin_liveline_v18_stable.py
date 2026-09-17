import logging
import os
from datetime import datetime, timedelta
from urllib.parse import urlencode

import ibetin_liveline_trial as liveline
import ibetin_liveline_v14_efficient as v14
import ibetin_liveline_v17_intelligence as v17

logger = logging.getLogger(__name__)

# Fresh route so Telegram/WebView cannot reuse the V17 page after the odds fix.
liveline.LIVELINE_PATH = "/admin/liveline-ibetinv18"
liveline.LIVELINE_API_PATH = "/admin/liveline-ibetinv18/api"


def _v18_admin_url() -> str:
    root = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/") or "https://ibetin-app-production.up.railway.app"
    return f"{root}{liveline.LIVELINE_PATH}?{urlencode({'t': liveline._token(), 'v': '20260917-v18-stable'})}"


def _safe_odds_snapshot(odds_type: str):
    """Use Highlightly's current max page size and fail soft on odds only.

    Scores/match data must keep working even when the optional odds feed is
    temporarily unavailable. V14's shared cache/singleflight still wraps these
    calls, so this does not undo the API-saving architecture.
    """
    now = datetime.now(liveline.DUBAI_TZ)
    if odds_type == "live":
        dates = [now.date()]
        ttl = 30
    else:
        dates = [now.date() + timedelta(days=i) for i in range(4)]
        ttl = 300

    all_rows = []
    seen = set()
    for day in dates:
        params = {
            "date": day.isoformat(),
            "oddsType": odds_type,
            # Highlightly currently rejects values above 5.
            "limit": 5,
            "offset": 0,
        }
        try:
            rows = liveline._highlightly("/cricket/odds", params, ttl=ttl)
        except Exception as exc:
            logger.warning(
                "IBETIN V18 odds snapshot skipped %s/%s: %s",
                odds_type,
                day.isoformat(),
                str(exc)[:160],
            )
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            match_id = str(row.get("matchId") or "")
            marker = match_id or repr(row)[:160]
            if marker in seen:
                continue
            seen.add(marker)
            all_rows.append(row)
    return all_rows


# Patch V14's snapshot loader in-place. _snapshot_payload resolves this global
# at request time, so every V17/V18 card benefits without duplicating backend.
v14._odds_snapshot = _safe_odds_snapshot


def _v18_page() -> str:
    html = v17._v17_page()
    html = html.replace("content:'V17'!important", "content:'V18'!important")
    html = html.replace(
        "IBETIN SPORTS INTELLIGENCE · V17 PRIVATE TEST",
        "IBETIN SPORTS INTELLIGENCE · V18 STABLE TEST",
    )
    html = html.replace(
        "SPORTS INTELLIGENCE · PRIVATE TEST",
        "SPORTS INTELLIGENCE · V18 STABLE TEST",
    )
    return html


liveline.admin_url = _v18_admin_url
liveline._page = _v18_page

app = v17.app

logger.info("IBETIN Live Line V18 stable odds snapshot fix installed on private test route")

if __name__ == "__main__":
    app.base.ibetin_start.main()
