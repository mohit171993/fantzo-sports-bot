import logging
import os
from urllib.parse import parse_qs, urlencode, urlparse

import ibetin_liveline_trial as liveline
import ibetin_liveline_v14_efficient as v14
import ibetin_liveline_v17_bhavfix as v17fix
import ibetin_liveline_v17_intelligence as v17

logger = logging.getLogger(__name__)
admin = v14.admin

# Fresh private route so Telegram cannot reuse an older cached V17 page.
liveline.LIVELINE_PATH = "/admin/liveline-ibetinv18"
liveline.LIVELINE_API_PATH = "/admin/liveline-ibetinv18/api"


def _v18_admin_url() -> str:
    root = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/") or "https://ibetin-app-production.up.railway.app"
    return f"{root}{liveline.LIVELINE_PATH}?{urlencode({'t': liveline._token(), 'v': '20260917-v18-roanuz-bhav'})}"


_LIVE_STATUS = {
    "live", "inplay", "in play", "in_progress", "in progress",
    "ongoing", "started", "playing", "play", "innings break",
    "drinks", "lunch", "tea", "stumps",
}


def _candidate_is_live(candidate) -> bool:
    if not isinstance(candidate, dict):
        return False
    values = []
    for key in ("play_status", "playStatus", "status", "state", "match_status", "matchStatus"):
        value = candidate.get(key)
        if value not in (None, "", {}, []):
            values.append(str(value).strip().casefold())
    return any(value in _LIVE_STATUS for value in values)


def _live_roanuz_candidates():
    try:
        return [c for c in admin._roanuz_featured_matches() if _candidate_is_live(c)]
    except Exception as exc:
        logger.warning("IBETIN V18 could not read Roanuz live candidates: %s", str(exc)[:160])
        return []


def _match_names(match):
    if not isinstance(match, dict):
        return "", ""
    home = match.get("home") if isinstance(match.get("home"), dict) else {}
    away = match.get("away") if isinstance(match.get("away"), dict) else {}
    return str(home.get("name") or "").strip(), str(away.get("name") or "").strip()


def _find_live_roanuz_key(match, candidates=None) -> str:
    home, away = _match_names(match)
    if not home or not away:
        return ""
    candidates = candidates if candidates is not None else _live_roanuz_candidates()
    best_key, best_score = "", 0.0
    for candidate in candidates:
        names = admin._team_names_from_roanuz(candidate)
        if len(names) < 2:
            continue
        direct = (admin._name_similarity(home, names[0]) + admin._name_similarity(away, names[1])) / 2
        reverse = (admin._name_similarity(home, names[1]) + admin._name_similarity(away, names[0])) / 2
        score = max(direct, reverse)
        if score > best_score:
            best_score = score
            best_key = str(candidate.get("key") or candidate.get("match_key") or candidate.get("matchKey") or "")
    if best_score >= 0.68:
        logger.info("IBETIN V18 mapped live match to Roanuz key=%s confidence=%.2f", best_key, best_score)
        return best_key
    logger.info("IBETIN V18 no safe live Roanuz mapping; confidence=%.2f", best_score)
    return ""


def _roanuz_session_entries(match_key: str):
    """Normalize Roanuz V5 session-odds into the existing BHAV entry shape."""
    try:
        payload = admin._roanuz_get(f"match/{match_key}/session-odds/", ttl=15)
    except Exception as exc:
        logger.warning("IBETIN V18 Roanuz session odds unavailable key=%s: %s", match_key, str(exc)[:160])
        return []

    data = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else payload
    match = data.get("match") if isinstance(data, dict) and isinstance(data.get("match"), dict) else {}
    predictions = match.get("session_predictions") if isinstance(match.get("session_predictions"), list) else []
    innings = match.get("innings")
    current_state = match.get("current_state") if isinstance(match.get("current_state"), dict) else {}

    entries = []
    for row in predictions:
        if not isinstance(row, dict) or row.get("completed") is True:
            continue
        score = row.get("score") if isinstance(row.get("score"), dict) else {}
        low = score.get("min")
        high = score.get("max")
        if low in (None, "") or high in (None, ""):
            continue
        over = row.get("over")
        name = str(row.get("name") or (f"{over} OVER SESSION" if over not in (None, "") else "SESSION MARKET")).strip()
        entries.append({
            "bookmaker": "Roanuz Session",
            "bookmakerId": "roanuz-session",
            "type": "session",
            "market": name,
            "over": over,
            "innings": innings,
            "currentState": current_state,
            "values": [
                {"label": "MIN", "odd": low},
                {"label": "MAX", "odd": high},
            ],
        })
    return entries[:6]


def _roanuz_live_entries(match_key: str):
    """Normalize Roanuz V5 live match odds + session odds into BHAV UI shape."""
    payload = admin._roanuz_get(f"match/{match_key}/live-match-odds/", ttl=20)
    data = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else payload
    match = data.get("match") if isinstance(data, dict) and isinstance(data.get("match"), dict) else {}
    meta = match.get("meta") if isinstance(match.get("meta"), dict) else {}
    status = str(meta.get("status") or "").strip().casefold()
    if status and status not in _LIVE_STATUS:
        return []

    teams = match.get("teams") if isinstance(match.get("teams"), dict) else {}
    bet_odds = match.get("bet_odds") if isinstance(match.get("bet_odds"), dict) else {}
    automatic = bet_odds.get("automatic") if isinstance(bet_odds.get("automatic"), dict) else {}
    decimal = automatic.get("decimal") if isinstance(automatic.get("decimal"), list) else []

    values = []
    for row in decimal:
        if not isinstance(row, dict):
            continue
        team_key = str(row.get("team_key") or "")
        odd = row.get("value")
        if not team_key or odd in (None, ""):
            continue
        team = teams.get(team_key) if isinstance(teams.get(team_key), dict) else {}
        label = str(team.get("name") or team.get("code") or team_key).strip()
        if label:
            values.append({"label": label, "odd": odd})

    entries = []
    if len(values) >= 2:
        entries.append({
            "bookmaker": "Roanuz Live",
            "bookmakerId": "roanuz-live",
            "type": "live",
            "market": "Match Winner",
            "values": values[:2],
        })

    entries.extend(_roanuz_session_entries(match_key))
    return entries


def _highlightly_match_stub(match_id: str):
    raw = liveline._highlightly(f"/cricket/matches/{match_id}", ttl=45)
    item = raw[0] if isinstance(raw, list) and raw else (raw if isinstance(raw, dict) else {})
    if not isinstance(item, dict):
        return {}
    return {
        "id": str(item.get("id") or match_id),
        "home": liveline._team(item, "home"),
        "away": liveline._team(item, "away"),
        "state": liveline._state_text(item),
    }


def _roanuz_primary_for_match(match_id: str):
    match = _highlightly_match_stub(match_id)
    if not match:
        return None
    candidates = _live_roanuz_candidates()
    match_key = _find_live_roanuz_key(match, candidates)
    if not match_key:
        return None
    try:
        entries = _roanuz_live_entries(match_key)
    except Exception as exc:
        logger.warning("IBETIN V18 Roanuz live BHAV unavailable for %s: %s", match_id, str(exc)[:160])
        return None
    if not entries:
        return None
    return {
        "ok": True,
        "matchId": str(match_id),
        "roanuzMatchKey": match_key,
        "oddsType": "live",
        "requestedType": "live",
        "market": "Match Winner",
        "source": "Roanuz Live Odds + Session · primary",
        "entries": entries,
    }


def _roanuz_direct_for_key(match_key: str):
    try:
        entries = _roanuz_live_entries(match_key)
    except Exception as exc:
        logger.warning("IBETIN V18 direct Roanuz BHAV unavailable key=%s: %s", match_key, str(exc)[:160])
        return None
    if not entries:
        return None
    return {
        "ok": True,
        "matchId": match_key,
        "roanuzMatchKey": match_key,
        "oddsType": "live",
        "requestedType": "live",
        "market": "Match Winner",
        "source": "Roanuz Live Odds + Session · direct",
        "entries": entries,
    }


def _roanuz_primary_snapshot():
    cache_key = "v18:roanuz-primary-live-snapshot"
    cached = v14._shared_get(cache_key)
    if cached is not None:
        return cached

    lock = v14._key_lock(cache_key)
    with lock:
        cached = v14._shared_get(cache_key)
        if cached is not None:
            return cached

        fallback = v14._snapshot_payload("live")
        by_match = dict(fallback.get("byMatch") or {}) if isinstance(fallback, dict) else {}
        primary_count = 0
        candidates = _live_roanuz_candidates()

        try:
            live_matches = liveline._matches_mode("live")[:8]
        except Exception as exc:
            logger.warning("IBETIN V18 live match list unavailable for BHAV snapshot: %s", str(exc)[:160])
            live_matches = []

        for match in live_matches:
            if not isinstance(match, dict):
                continue
            match_id = str(match.get("id") or "")
            if not match_id:
                continue
            match_key = _find_live_roanuz_key(match, candidates)
            if not match_key:
                continue
            try:
                entries = _roanuz_live_entries(match_key)
            except Exception as exc:
                logger.warning("IBETIN V18 Roanuz snapshot fallback match=%s: %s", match_id, str(exc)[:140])
                continue
            if not entries:
                continue
            by_match[match_id] = {
                "ok": True,
                "matchId": match_id,
                "roanuzMatchKey": match_key,
                "oddsType": "live",
                "requestedType": "live",
                "market": "Match Winner",
                "source": "Roanuz Live Odds + Session · primary",
                "entries": entries,
            }
            primary_count += 1

        payload = {
            "ok": True,
            "oddsType": "live",
            "source": "Roanuz Live Odds + Session primary · Highlightly fallback",
            "primaryCount": primary_count,
            "byMatch": by_match,
        }
        v14._shared_put(cache_key, payload, 20)
        return payload


_previous_api = liveline._api


def _v18_api(handler):
    query = parse_qs(urlparse(handler.path).query)
    action = (query.get("action") or [""])[0].strip().lower()

    if action == "bhavsnapshot":
        requested = (query.get("oddsType") or ["live"])[0].strip().lower()
        if requested == "live":
            try:
                liveline._send_json(handler, 200, _roanuz_primary_snapshot())
            except Exception:
                logger.exception("IBETIN V18 Roanuz snapshot failed; serving Highlightly fallback")
                liveline._send_json(handler, 200, v14._snapshot_payload("live"))
            return
        return _previous_api(handler)

    if action == "bhav":
        match_id = (query.get("matchId") or query.get("id") or [""])[0].strip()
        requested = (query.get("oddsType") or ["live"])[0].strip().lower()
        if requested == "live" and match_id:
            primary = None
            try:
                if match_id.startswith("a-rz--cricket--"):
                    primary = _roanuz_direct_for_key(match_id)
                elif match_id.isdigit():
                    primary = _roanuz_primary_for_match(match_id)
            except Exception:
                logger.exception("IBETIN V18 Roanuz BHAV primary failed")
                primary = None
            if primary:
                liveline._send_json(handler, 200, primary)
                return
        return _previous_api(handler)

    return _previous_api(handler)


liveline._api = _v18_api


def _v18_page() -> str:
    html = v17._v17_page()
    css = r'''
.liveChip:after{content:'V18'!important}
.v18SourceNote{display:inline-flex;align-items:center;gap:4px;margin-left:5px;padding:3px 6px;border-radius:999px;border:1px solid #cfe5d9;background:#edf9f2;color:#23704b;font-size:5px;font-weight:1000;letter-spacing:.35px}
html[data-v16-theme="dark"] .v18SourceNote{background:#153225;border-color:#28553d;color:#8bdeb1}
'''
    html = html.replace("</style>", css + "\n</style>", 1)
    js = r'''
<script>
(function(){
  const addTag=()=>{
    const q=document.querySelector('.v12QuickStat');
    if(q&&!q.querySelector('.v18SourceNote')){
      const s=document.createElement('span');
      s.className='v18SourceNote';s.textContent='ROANUZ LIVE BHAV · PRIMARY';q.appendChild(s);
    }
  };
  addTag();setTimeout(addTag,400);
})();
</script>
'''
    html = html.replace("</body>", js + "\n</body>")
    return html


liveline.admin_url = _v18_admin_url
liveline._page = _v18_page
app = v17fix.app

logger.info("IBETIN V18 installed: direct Roanuz live BHAV + real session odds + Highlightly fallback")

if __name__ == "__main__":
    app.base.ibetin_start.main()
