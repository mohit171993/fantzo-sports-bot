import logging
import threading
import time
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlencode, urlparse

import ibetin_liveline_trial as liveline
import ibetin_liveline_v13_elite as v13

logger = logging.getLogger(__name__)

# Fresh private route for the efficiency test build.
liveline.LIVELINE_PATH = "/admin/liveline-ibetinv14"
liveline.LIVELINE_API_PATH = "/admin/liveline-ibetinv14/api"


def _v14_admin_url() -> str:
    import os
    root = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/") or "https://ibetin-app-production.up.railway.app"
    return f"{root}{liveline.LIVELINE_PATH}?{urlencode({'t': liveline._token(), 'v': '20260917-v14-efficient'})}"


# Shared in-process provider cache with single-flight protection. This prevents
# a cache-expiry stampede when many Telegram users open the same live match at
# the same time. One Railway replica currently means this cache is shared by all
# users on the service.
_shared_lock = threading.RLock()
_shared_cache = {}
_shared_key_locks = {}
_stats = {
    "highlightly_provider_calls": 0,
    "highlightly_cache_hits": 0,
    "roanuz_provider_calls": 0,
    "roanuz_cache_hits": 0,
}


def _key_lock(key: str):
    with _shared_lock:
        lock = _shared_key_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _shared_key_locks[key] = lock
        return lock


def _shared_get(key: str):
    now = time.time()
    with _shared_lock:
        item = _shared_cache.get(key)
        if not item:
            return None
        expires, value = item
        if expires <= now:
            _shared_cache.pop(key, None)
            return None
        return value


def _shared_put(key: str, value, ttl: int):
    with _shared_lock:
        _shared_cache[key] = (time.time() + max(int(ttl), 1), value)


def _singleflight(key: str, ttl: int, loader, provider: str):
    cached = _shared_get(key)
    if cached is not None:
        with _shared_lock:
            _stats[f"{provider}_cache_hits"] += 1
        return cached
    lock = _key_lock(key)
    with lock:
        cached = _shared_get(key)
        if cached is not None:
            with _shared_lock:
                _stats[f"{provider}_cache_hits"] += 1
            return cached
        value = loader()
        with _shared_lock:
            _stats[f"{provider}_provider_calls"] += 1
        _shared_put(key, value, ttl)
        return value


# Highlightly wrapper: preserve existing behavior while stopping identical
# concurrent requests from reaching the provider more than once.
_raw_highlightly = liveline._highlightly


def _efficient_highlightly(path: str, params=None, ttl: int = 45):
    params = params or {}
    effective = int(ttl or 45)
    lower = path.lower()
    odds_type = str(params.get("oddsType") or params.get("oddstype") or "").lower()
    if "/cricket/odds" in lower:
        if odds_type == "prematch":
            effective = max(effective, 120)
        else:
            effective = max(effective, 30)
    elif lower == "/cricket/matches":
        effective = max(effective, 45)
    elif lower.startswith("/cricket/matches/"):
        effective = max(effective, 30)
    key = "hl:" + path + "?" + repr(sorted((str(k), str(v)) for k, v in params.items()))
    return _singleflight(
        key,
        effective,
        lambda: _raw_highlightly(path, params, ttl=effective),
        "highlightly",
    )


liveline._highlightly = _efficient_highlightly


# Roanuz wrapper: one provider call per path per TTL across all current users,
# with adaptive TTLs. Ball-by-ball remains fast; expensive graphs are cached
# longer; odds TTLs are prepared for when Roanuz enables those entitlements.
admin = v13.v12.app
_raw_roanuz_get = admin._roanuz_get


def _roanuz_effective_ttl(path: str, requested: int) -> int:
    p = path.lower()
    if "ball-by-ball" in p:
        floor = 8
    elif any(x in p for x in ("/worm/", "/manhattan/", "/run-rate/")):
        floor = 90
    elif "live-match-odds" in p or "session-odds" in p:
        floor = 20
    elif "pre-match-odds" in p:
        floor = 120
    elif "featured-matches" in p:
        floor = 60
    elif p.startswith("match/"):
        floor = 30
    else:
        floor = 45
    return max(int(requested or 10), floor)


def _efficient_roanuz_get(path: str, ttl: int = 10):
    effective = _roanuz_effective_ttl(path, ttl)
    key = "rz:" + str(path)
    return _singleflight(
        key,
        effective,
        lambda: _raw_roanuz_get(path, ttl=effective),
        "roanuz",
    )


admin._roanuz_get = _efficient_roanuz_get


_previous_api = liveline._api
_snapshot_lock = threading.Lock()


def _normalize_record(record, odds_type: str):
    if not isinstance(record, dict):
        return []
    odds = record.get("odds") if isinstance(record.get("odds"), list) else []
    preferred = {"bet365": 0, "stake.com": 1, "unibet": 2, "parimatch": 3, "fanduel": 4}
    normalized = []
    for item in odds:
        if not isinstance(item, dict):
            continue
        market = str(item.get("market") or "").strip()
        if market and market.casefold() != "match winner":
            continue
        values = item.get("values") or item.get("odds") or []
        if not isinstance(values, list):
            continue
        clean = []
        for value in values:
            if not isinstance(value, dict):
                continue
            label = str(value.get("value") or value.get("name") or value.get("label") or "").strip()
            odd = value.get("odd")
            if label and odd not in (None, ""):
                clean.append({"label": label, "odd": odd})
        if clean:
            normalized.append({
                "bookmaker": str(item.get("bookmakerName") or item.get("bookmaker") or "Bookmaker"),
                "bookmakerId": item.get("bookmakerId"),
                "type": str(item.get("type") or odds_type),
                "market": market or "Match Winner",
                "values": clean,
            })
    normalized.sort(key=lambda x: preferred.get(x["bookmaker"].casefold(), 50))
    return normalized[:12]


def _odds_snapshot(odds_type: str):
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
            "limit": 100,
            "offset": 0,
        }
        rows = liveline._highlightly("/cricket/odds", params, ttl=ttl)
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


def _snapshot_payload(odds_type: str):
    cache_key = f"v14:odds-snapshot:{odds_type}"
    ttl = 30 if odds_type == "live" else 300
    cached = _shared_get(cache_key)
    if cached is not None:
        return cached
    with _snapshot_lock:
        cached = _shared_get(cache_key)
        if cached is not None:
            return cached
        rows = _odds_snapshot(odds_type)
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
                "entries": _normalize_record(row, odds_type),
            }
        payload = {"ok": True, "oddsType": odds_type, "source": "Highlightly PRO", "byMatch": by_match}
        _shared_put(cache_key, payload, ttl)
        return payload


def _graphs_payload(match_key: str):
    cache_key = f"v14:graphs:{match_key}"
    cached = _shared_get(cache_key)
    if cached is not None:
        return cached
    lock = _key_lock(cache_key)
    with lock:
        cached = _shared_get(cache_key)
        if cached is not None:
            return cached
        graphs = {}
        failures = {}
        for name, endpoint in (
            ("worm", f"match/{match_key}/worm/"),
            ("manhattan", f"match/{match_key}/manhattan/"),
            ("runRate", f"match/{match_key}/run-rate/"),
        ):
            try:
                graphs[name] = admin._roanuz_get(endpoint, ttl=90)
            except Exception as exc:
                failures[name] = str(exc)[:120]
        payload = {
            "ok": True,
            "source": "Roanuz · shared cache",
            "matchKey": match_key,
            "graphs": graphs,
            "failures": failures,
        }
        _shared_put(cache_key, payload, 90)
        return payload


def _v14_api(handler):
    q = parse_qs(urlparse(handler.path).query)
    action = (q.get("action") or [""])[0].strip().lower()

    try:
        if action == "bhavsnapshot":
            requested = (q.get("oddsType") or ["live"])[0].strip().lower()
            odds_type = requested if requested in {"live", "prematch"} else "live"
            liveline._send_json(handler, 200, _snapshot_payload(odds_type))
            return

        if action == "graphs":
            match_key = (q.get("key") or [""])[0].strip()
            if not match_key or not v13._SAFE_MATCH_KEY.match(match_key):
                liveline._send_json(handler, 400, {"ok": False, "error": "Invalid Roanuz match key"})
                return
            liveline._send_json(handler, 200, _graphs_payload(match_key))
            return

        if action == "usage":
            with _shared_lock:
                payload = {"ok": True, "stats": dict(_stats), "sharedCacheEntries": len(_shared_cache)}
            liveline._send_json(handler, 200, payload)
            return

        return _previous_api(handler)
    except Exception as exc:
        logger.exception("IBETIN V14 efficient API failed")
        liveline._send_json(handler, 502, {"ok": False, "error": str(exc)[:180]})


liveline._api = _v14_api


def _v14_page() -> str:
    html = v13._v13_page()
    css = r'''
.liveChip:after{content:'V14 EFFICIENT'!important}
.v14Efficiency{display:inline-flex;align-items:center;gap:5px;font-size:7px;font-weight:950;color:#1b6b4a;background:#eaf8f1;border:1px solid #cbe9da;border-radius:999px;padding:4px 7px;margin-left:6px}
'''
    html = html.replace("</style>", css + "\n</style>", 1)

    js = r'''
<script>
(function(){
  const rawApi=window.api;
  const snapshots=new Map();
  const snapshotAt=new Map();

  // The V13 card decorators still ask for one match at a time. V14 coalesces
  // those browser requests into one shared snapshot promise per odds type.
  window.api=function(params){
    if(params&&params.action==='bhav'){
      const detail=document.getElementById('detail');
      const homeVisible=detail&&detail.style.display==='none';
      if(homeVisible){
        const type=params.oddsType==='prematch'?'prematch':'live';
        const ttl=type==='live'?25000:240000;
        const age=Date.now()-(snapshotAt.get(type)||0);
        if(!snapshots.has(type)||age>ttl){
          const p=rawApi({action:'bhavsnapshot',oddsType:type});
          snapshots.set(type,p);snapshotAt.set(type,Date.now());
          p.catch(()=>{snapshots.delete(type);snapshotAt.delete(type)});
        }
        return snapshots.get(type).then(j=>j?.byMatch?.[String(params.matchId)]||({ok:true,matchId:String(params.matchId),oddsType:type,requestedType:type,market:'Match Winner',source:'Highlightly PRO · shared snapshot',entries:[]}));
      }
    }
    return rawApi(params);
  };

  // Prevent duplicate startup/interval refreshes and stop polling while Telegram
  // is hidden/minimized. The existing V13 30-second timer calls loadMode(), so
  // wrapping it here controls provider pressure without rewriting the UI.
  const rawLoad=window.loadMode;
  const lastByMode=new Map([['live',Date.now()]]);
  window.loadMode=function(mode){
    if(document.hidden&&mode==='live') return Promise.resolve();
    const now=Date.now(),last=lastByMode.get(mode)||0;
    if(mode==='live'&&now-last<12000) return Promise.resolve();
    lastByMode.set(mode,now);
    return rawLoad(mode);
  };
  document.addEventListener('visibilitychange',()=>{
    if(!document.hidden&&window.currentMode==='live'){
      const last=lastByMode.get('live')||0;
      if(Date.now()-last>15000) window.loadMode('live');
    }
  });

  const quick=document.querySelector('.v12QuickStat');
  if(quick&&!quick.querySelector('.v14Efficiency')){
    const tag=document.createElement('span');tag.className='v14Efficiency';tag.textContent='API SAVER ON';quick.appendChild(tag);
  }
})();
</script>
'''
    html = html.replace("</body>", js + "\n</body>")
    html = html.replace("ELITE SPORTS COMMAND CENTER · TEST MODE", "ELITE SPORTS COMMAND CENTER · API-SAVER TEST")
    return html


liveline.admin_url = _v14_admin_url
liveline._page = _v14_page

app = v13.app

logger.info("IBETIN Live Line V14 API-efficient command center installed on private test route")

if __name__ == "__main__":
    app.base.ibetin_start.main()
