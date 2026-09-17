import logging
import threading
import time

import ibetin_liveline_v24_detail_contract_hotfix as v24

v23 = v24.v23
logger = logging.getLogger(__name__)

# Keep provider data fresh without making the Telegram Mini App wait on every
# Roanuz round trip. A stale good value is returned immediately while one
# background refresh updates the cache for the next hydrate/request.
_LIST_FRESH_SECONDS = 5.0
_DETAIL_FRESH_SECONDS = 4.0

_list_cache = {}
_detail_cache = {}
_list_refreshing = set()
_detail_refreshing = set()
_lock = threading.RLock()

_ORIGINAL_MATCHES = v23._fast_matches
_ORIGINAL_DETAIL = v24._match_detail_contract
_ORIGINAL_PAGE = v23._page


def _refresh_detail(key: str):
    try:
        detail, source = _ORIGINAL_DETAIL(key)
        if isinstance(detail, dict):
            with _lock:
                _detail_cache[key] = (time.monotonic(), detail, source)
        return detail, source
    finally:
        with _lock:
            _detail_refreshing.discard(key)


def _spawn_detail_refresh(key: str) -> None:
    if not key:
        return
    with _lock:
        if key in _detail_refreshing:
            return
        _detail_refreshing.add(key)
    threading.Thread(target=_safe_refresh_detail, args=(key,), daemon=True, name=f"ibetin-v25-detail-{key[-12:]}").start()


def _safe_refresh_detail(key: str) -> None:
    try:
        _refresh_detail(key)
    except Exception as exc:
        logger.warning("IBETIN V25 background detail refresh failed key=%s: %s", key, str(exc)[:160])


def _prewarm_rows(rows) -> None:
    for row in (rows or [])[:4]:
        if not isinstance(row, dict):
            continue
        key = str(row.get("roanuzMatchKey") or row.get("id") or "")
        if key and v23.v21._valid_key(key):
            _spawn_detail_refresh(key)


def _refresh_matches(mode: str):
    try:
        rows, source = _ORIGINAL_MATCHES(mode)
        with _lock:
            _list_cache[mode] = (time.monotonic(), rows, source)
        if mode == "live":
            _prewarm_rows(rows)
        return rows, source
    finally:
        with _lock:
            _list_refreshing.discard(mode)


def _safe_refresh_matches(mode: str) -> None:
    try:
        _refresh_matches(mode)
    except Exception as exc:
        logger.warning("IBETIN V25 background list refresh failed mode=%s: %s", mode, str(exc)[:160])


def _spawn_matches_refresh(mode: str) -> None:
    with _lock:
        if mode in _list_refreshing:
            return
        _list_refreshing.add(mode)
    threading.Thread(target=_safe_refresh_matches, args=(mode,), daemon=True, name=f"ibetin-v25-list-{mode}").start()


def _fast_matches_cached(mode: str):
    now = time.monotonic()
    with _lock:
        cached = _list_cache.get(mode)
    if cached:
        ts, rows, source = cached
        if now - ts > _LIST_FRESH_SECONDS:
            _spawn_matches_refresh(mode)
        if mode == "live":
            _prewarm_rows(rows)
        return rows, source
    return _refresh_matches(mode)


def _match_detail_cached(key: str):
    now = time.monotonic()
    with _lock:
        cached = _detail_cache.get(key)
    if cached:
        ts, detail, source = cached
        if now - ts > _DETAIL_FRESH_SECONDS:
            _spawn_detail_refresh(key)
        return detail, source
    return _refresh_detail(key)


def _score_summary_cached(key: str):
    now = time.monotonic()
    with _lock:
        cached = _detail_cache.get(key)
    if cached:
        ts, detail, _source = cached
        if now - ts > _DETAIL_FRESH_SECONDS:
            _spawn_detail_refresh(key)
        match = detail.get("match") if isinstance(detail, dict) else None
        if isinstance(match, dict):
            return match

    detail, _source = _match_detail_cached(key)
    match = detail.get("match") if isinstance(detail, dict) else None
    if isinstance(match, dict):
        return match
    return {"id": key, "roanuzMatchKey": key}


def _page_fast() -> str:
    html = _ORIGINAL_PAGE()
    html = html.replace("V23 · STABLE", "V25 · FAST", 1)
    # First hydrate paints immediately from server cache. A second hydrate shortly
    # after picks up the background provider refresh without blocking first paint.
    html = html.replace(
        "if(mode==='live')rows.slice(0,8).forEach(hydrateScore)",
        "if(mode==='live'){rows.slice(0,8).forEach(hydrateScore);setTimeout(()=>rows.slice(0,8).forEach(hydrateScore),1600)}",
        1,
    )
    return html


# Patch the exact runtime call sites used by the V23/V24 API dispatcher.
v23._fast_matches = _fast_matches_cached
v23.v21._matches = _fast_matches_cached
v23.v21._match_detail = _match_detail_cached
v23._score_summary = _score_summary_cached
v23._page = _page_fast
v23.liveline._page = _page_fast


# Warm the first live response while the service starts so the first user does
# not pay the provider latency. The imported V24 startup probe has already
# authenticated Roanuz, so this usually reuses its provider cache.
try:
    rows, source = _refresh_matches("live")
    logger.info("IBETIN V25 warm cache ready source=%s matches=%s", source, len(rows or []))
except Exception:
    logger.exception("IBETIN V25 startup warm cache failed; runtime will fall back to synchronous first fetch")

logger.info("IBETIN V25 installed: stale-while-refresh list/detail cache + background live prewarm + second score hydrate")

app = v23.app

if __name__ == "__main__":
    app.base.ibetin_start.main()
