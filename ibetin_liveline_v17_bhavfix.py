import logging
from datetime import datetime, timedelta

import ibetin_liveline_trial as liveline
import ibetin_liveline_v14_efficient as v14
import ibetin_liveline_v17_intelligence as v17

logger = logging.getLogger(__name__)


def _safe_odds_snapshot(odds_type: str):
    """Fetch Highlightly odds within the provider's current limit=5 cap.

    Live odds read at most two small pages (10 matches). Prematch reads one
    page per day for the existing four-day window. Every request still goes
    through V14 shared single-flight caching, so concurrent users reuse the
    same provider responses.
    """
    now = datetime.now(liveline.DUBAI_TZ)
    if odds_type == "live":
        dates = [now.date()]
        ttl = 30
        max_pages = 2
    else:
        dates = [now.date() + timedelta(days=i) for i in range(4)]
        ttl = 300
        max_pages = 1

    all_rows = []
    seen = set()

    for day in dates:
        for page in range(max_pages):
            params = {
                "date": day.isoformat(),
                "oddsType": odds_type,
                "limit": 5,
                "offset": page * 5,
            }
            try:
                rows = liveline._highlightly("/cricket/odds", params, ttl=ttl)
            except Exception as exc:
                logger.warning(
                    "IBETIN bhav snapshot page unavailable type=%s date=%s offset=%s: %s",
                    odds_type,
                    day.isoformat(),
                    page * 5,
                    str(exc)[:160],
                )
                break

            if not isinstance(rows, list) or not rows:
                break

            for row in rows:
                if not isinstance(row, dict):
                    continue
                match_id = str(row.get("matchId") or "")
                marker = match_id or repr(row)[:160]
                if marker in seen:
                    continue
                seen.add(marker)
                all_rows.append(row)

            # Fewer than the maximum means there is no next page.
            if len(rows) < 5:
                break

    return all_rows


def _safe_snapshot_payload(odds_type: str):
    cache_key = f"v14:odds-snapshot:{odds_type}"
    ttl = 30 if odds_type == "live" else 300
    cached = v14._shared_get(cache_key)
    if cached is not None:
        return cached

    with v14._snapshot_lock:
        cached = v14._shared_get(cache_key)
        if cached is not None:
            return cached

        try:
            rows = _safe_odds_snapshot(odds_type)
        except Exception as exc:
            # BHAV is optional UI enrichment. Never break the match feed merely
            # because an odds provider is temporarily unavailable.
            logger.warning("IBETIN bhav snapshot degraded safely: %s", str(exc)[:160])
            rows = []

        by_match = {}
        for row in rows:
            match_id = str(row.get("matchId") or "")
            if not match_id:
                continue
            by_match[match_id] = {
                "ok": True,
                "matchId": match_id,
                "oddsType": odds_type,
                "requestedType": odds_type,
                "market": "Match Winner",
                "source": "Highlightly PRO · shared snapshot",
                "entries": v14._normalize_record(row, odds_type),
            }

        payload = {
            "ok": True,
            "oddsType": odds_type,
            "source": "Highlightly PRO · shared snapshot",
            "byMatch": by_match,
        }
        v14._shared_put(cache_key, payload, ttl)
        return payload


# Patch the V14 functions used dynamically by the inherited V14 API router.
v14._odds_snapshot = _safe_odds_snapshot
v14._snapshot_payload = _safe_snapshot_payload

app = v17.app

logger.info(
    "IBETIN V17 BHAV fix installed: Highlightly limit=5 pagination + graceful fallback"
)

if __name__ == "__main__":
    app.base.ibetin_start.main()
