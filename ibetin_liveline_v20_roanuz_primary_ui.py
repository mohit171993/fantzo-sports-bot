import logging
import os
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode, urlparse

import ibetin_liveline_trial as liveline
import ibetin_liveline_v14_efficient as v14
import ibetin_liveline_v18_roanuz_bhav as v18
import ibetin_liveline_v19_trust_intel as v19

logger = logging.getLogger(__name__)
admin = v14.admin

liveline.LIVELINE_PATH = "/admin/liveline-ibetinv20"
liveline.LIVELINE_API_PATH = "/admin/liveline-ibetinv20/api"

_SAFE_KEY = re.compile(r"^[A-Za-z0-9_.:\-]{3,180}$")

LIVE_STATES = {
    "live", "inplay", "in play", "in_progress", "in progress", "ongoing",
    "started", "playing", "play", "innings break", "drinks", "lunch", "tea",
    "stumps", "match delayed", "delay", "delayed"
}
UPCOMING_STATES = {
    "not_started", "not started", "scheduled", "upcoming", "fixture", "created",
    "confirmed", "to be announced", "tba"
}
FINISHED_STATES = {
    "completed", "complete", "finished", "result", "ended", "closed", "abandoned",
    "cancelled", "canceled", "no result"
}


def _v20_admin_url() -> str:
    root = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/") or "https://ibetin-app-production.up.railway.app"
    return f"{root}{liveline.LIVELINE_PATH}?{urlencode({'t': liveline._token(), 'v': '20260917-v20-roanuz-primary-ui'})}"


def _deep_first(node, names):
    if isinstance(node, dict):
        for name in names:
            value = node.get(name)
            if value not in (None, "", {}, []):
                return value
        for value in node.values():
            found = _deep_first(value, names)
            if found not in (None, "", {}, []):
                return found
    elif isinstance(node, list):
        for value in node:
            found = _deep_first(value, names)
            if found not in (None, "", {}, []):
                return found
    return None


def _match_key(node) -> str:
    if not isinstance(node, dict):
        return ""
    return str(node.get("key") or node.get("match_key") or node.get("matchKey") or "").strip()


def _team_obj(raw, fallback: str):
    if isinstance(raw, dict):
        name = raw.get("name") or raw.get("short_name") or raw.get("shortName") or raw.get("code") or fallback
        abbr = raw.get("short_name") or raw.get("shortName") or raw.get("code") or ""
        logo = raw.get("logo") or raw.get("logo_url") or raw.get("image") or ""
        return {"id": str(raw.get("key") or raw.get("id") or ""), "name": str(name), "abbr": str(abbr), "logo": str(logo)}
    if raw:
        return {"id": "", "name": str(raw), "abbr": "", "logo": ""}
    return {"id": "", "name": fallback, "abbr": "", "logo": ""}


def _teams(node):
    teams = node.get("teams") if isinstance(node, dict) else None
    if isinstance(teams, dict):
        a = teams.get("a") or teams.get("home") or teams.get("team_a") or teams.get("teamA")
        b = teams.get("b") or teams.get("away") or teams.get("team_b") or teams.get("teamB")
        if a is None or b is None:
            vals = [v for v in teams.values() if isinstance(v, (dict, str))]
            if len(vals) >= 2:
                a = a or vals[0]
                b = b or vals[1]
        return _team_obj(a, "Team A"), _team_obj(b, "Team B")
    if isinstance(teams, list) and len(teams) >= 2:
        return _team_obj(teams[0], "Team A"), _team_obj(teams[1], "Team B")
    return _team_obj(None, "Team A"), _team_obj(None, "Team B")


def _status(node) -> str:
    if not isinstance(node, dict):
        return ""
    values = []
    for key in ("play_status", "playStatus", "status", "state", "match_status", "matchStatus"):
        value = node.get(key)
        if isinstance(value, dict):
            value = value.get("status") or value.get("name") or value.get("description")
        if value not in (None, ""):
            values.append(str(value).strip())
    meta = node.get("meta") if isinstance(node.get("meta"), dict) else {}
    for key in ("status", "play_status", "playStatus"):
        value = meta.get(key)
        if value not in (None, ""):
            values.append(str(value).strip())
    return values[0] if values else ""


def _start_time(node) -> str:
    if not isinstance(node, dict):
        return ""
    for key in ("start_at", "startAt", "start_time", "startTime", "start_date", "startDate", "scheduled_at", "scheduledAt"):
        value = node.get(key)
        if value not in (None, ""):
            return str(value)
    meta = node.get("meta") if isinstance(node.get("meta"), dict) else {}
    for key in ("start_at", "startAt", "start_time", "startTime"):
        value = meta.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _league(node):
    if not isinstance(node, dict):
        return {"id": "", "name": "Cricket", "season": None, "logo": ""}
    obj = None
    for key in ("tournament", "competition", "league", "season"):
        if isinstance(node.get(key), dict):
            obj = node.get(key)
            break
    obj = obj or {}
    return {
        "id": str(obj.get("key") or obj.get("id") or ""),
        "name": str(obj.get("name") or obj.get("title") or node.get("title") or "Cricket"),
        "season": obj.get("season") or obj.get("year"),
        "logo": str(obj.get("logo") or obj.get("image") or ""),
    }


def _score_text(team_raw):
    if not isinstance(team_raw, dict):
        return "", ""
    score = team_raw.get("score") or team_raw.get("runs")
    wickets = team_raw.get("wickets")
    overs = team_raw.get("overs") or team_raw.get("over")
    if isinstance(score, dict):
        runs = score.get("runs") or score.get("score")
        wickets = score.get("wickets") if wickets is None else wickets
        overs = score.get("overs") if overs is None else overs
        score = runs
    if score in (None, ""):
        return "", str(overs or "")
    text = str(score)
    if wickets not in (None, ""):
        text += f"/{wickets}"
    return text, str(overs or "")


def _normalize_roanuz_match(node):
    if not isinstance(node, dict):
        return {}
    key = _match_key(node)
    home, away = _teams(node)
    teams = node.get("teams") if isinstance(node.get("teams"), dict) else {}
    a_raw = teams.get("a") or teams.get("home") or teams.get("team_a") or teams.get("teamA") or {}
    b_raw = teams.get("b") or teams.get("away") or teams.get("team_b") or teams.get("teamB") or {}
    home_score, home_info = _score_text(a_raw)
    away_score, away_info = _score_text(b_raw)
    state = _status(node)
    report = str(node.get("status_note") or node.get("statusNote") or node.get("note") or node.get("result") or state or "")
    fmt = str(node.get("format") or node.get("match_format") or node.get("matchFormat") or node.get("type") or "")
    start = _start_time(node)
    return {
        "id": key,
        "roanuzMatchKey": key,
        "source": "Roanuz",
        "format": fmt,
        "dayType": "",
        "startDate": start,
        "startTime": start,
        "endDate": "",
        "country": node.get("country") if isinstance(node.get("country"), dict) else {},
        "league": _league(node),
        "home": home,
        "away": away,
        "state": state,
        "report": report,
        "homeScore": home_score,
        "homeInfo": home_info,
        "awayScore": away_score,
        "awayInfo": away_info,
    }


def _extract_matches(payload):
    found, seen = [], set()
    def walk(node):
        if isinstance(node, dict):
            key = _match_key(node)
            if key and node.get("teams") is not None:
                if key not in seen:
                    seen.add(key)
                    found.append(node)
                return
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
    walk(payload)
    return found


def _is_state(node, states):
    return _status(node).strip().casefold() in states


def _roanuz_featured_raw():
    return admin._roanuz_featured_matches()


def _roanuz_fixtures_raw():
    payload = admin._roanuz_get("fixtures/", ttl=120)
    return _extract_matches(payload)


def _roanuz_matches_mode(mode: str):
    if mode == "live":
        rows = _roanuz_featured_raw()
        live = [x for x in rows if _is_state(x, LIVE_STATES)]
        return [_normalize_roanuz_match(x) for x in live[:40]]

    try:
        rows = _roanuz_fixtures_raw()
    except Exception as exc:
        logger.warning("IBETIN V20 Roanuz fixtures unavailable; using Highlightly fallback for %s: %s", mode, str(exc)[:160])
        return _OLD_MATCHES_MODE(mode)

    if mode == "upcoming":
        selected = [x for x in rows if _is_state(x, UPCOMING_STATES)]
    elif mode == "results":
        selected = [x for x in rows if _is_state(x, FINISHED_STATES)]
    else:
        raise ValueError("Unknown matches mode")

    selected.sort(key=_start_time, reverse=(mode == "results"))
    return [_normalize_roanuz_match(x) for x in selected[:40]]


def _find_match_dict(payload, key: str):
    best = None
    def walk(node):
        nonlocal best
        if best is not None:
            return
        if isinstance(node, dict):
            if _match_key(node) == key and node.get("teams") is not None:
                best = node
                return
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
    walk(payload)
    if best is not None:
        return best
    rows = _extract_matches(payload)
    return rows[0] if rows else (payload if isinstance(payload, dict) else {})


def _list_value(node, names):
    value = _deep_first(node, names)
    return value if isinstance(value, list) else []


def _dict_value(node, names):
    value = _deep_first(node, names)
    return value if isinstance(value, dict) else {}


def _roanuz_match_detail(match_key: str):
    if not match_key or not _SAFE_KEY.match(match_key):
        raise ValueError("Invalid Roanuz match key")
    payload = admin._roanuz_get(f"match/{match_key}/", ttl=20)
    node = _find_match_dict(payload, match_key)
    normalized = _normalize_roanuz_match(node)
    if not normalized.get("id"):
        normalized["id"] = match_key
        normalized["roanuzMatchKey"] = match_key
    try:
        timeline = admin._roanuz_timeline(match_key)
    except Exception as exc:
        logger.warning("IBETIN V20 ball-by-ball unavailable for %s: %s", match_key, str(exc)[:120])
        timeline = []

    venue = _dict_value(node, ("venue", "ground")) or _dict_value(payload, ("venue", "ground"))
    playing_xi = _list_value(node, ("playing_xi", "playingXI", "playing11")) or _list_value(payload, ("playing_xi", "playingXI", "playing11"))
    squads = _list_value(node, ("squads_players", "squad", "squads", "players")) or _list_value(payload, ("squads_players", "squad", "squads", "players"))
    scorecard = _list_value(node, ("scorecard", "score_card", "innings")) or _list_value(payload, ("scorecard", "score_card", "innings"))
    recent_balls = _list_value(node, ("recent_balls", "recentBalls")) or _list_value(payload, ("recent_balls", "recentBalls"))
    inplay = _dict_value(node, ("inplay_data", "inplayData", "live")) or _dict_value(payload, ("inplay_data", "inplayData", "live"))
    if recent_balls and isinstance(inplay, dict):
        inplay = dict(inplay)
        inplay.setdefault("recentBalls", recent_balls)

    return {
        "match": normalized,
        "venue": venue,
        "forecast": {},
        "statistics": scorecard,
        "squad": playing_xi or squads,
        "bestBatsmen": _list_value(payload, ("best_batsmen", "bestBatsmen", "top_batsmen")),
        "bestBowlers": _list_value(payload, ("best_bowlers", "bestBowlers", "top_bowlers")),
        "inplayData": inplay,
        "timeline": timeline,
        "roanuz": {
            "matchKey": match_key,
            "source": "Roanuz V5 primary",
            "target": _deep_first(payload, ("target",)),
            "runRate": _deep_first(payload, ("run_rate", "runRate")),
            "toss": _deep_first(payload, ("toss",)),
            "winner": _deep_first(payload, ("winner",)),
        },
    }


_OLD_MATCHES_MODE = liveline._matches_mode
_OLD_MATCH_DETAIL = liveline._match_detail
liveline._matches_mode = _roanuz_matches_mode
liveline._match_detail = _roanuz_match_detail


_PREVIOUS_API = liveline._api


def _valid_key(value: str) -> bool:
    return bool(value and _SAFE_KEY.match(value))


def _v20_bhav(match_key: str):
    entries = []
    try:
        entries = v18._roanuz_live_entries(match_key)
    except Exception as exc:
        logger.warning("IBETIN V20 Roanuz BHAV unavailable for %s: %s", match_key, str(exc)[:140])
    payload = {
        "ok": True,
        "matchId": match_key,
        "roanuzMatchKey": match_key,
        "oddsType": "live",
        "requestedType": "live",
        "market": "Match Winner",
        "source": "Roanuz Live Odds · primary",
        "observedAt": v19._now_iso(),
        "entries": entries,
    }
    v19._record_bhav(payload)
    return payload


def _v20_snapshot():
    cache_key = "v20:roanuz-live-bhav-snapshot"
    cached = v14._shared_get(cache_key)
    if cached is not None:
        return cached
    by_match = {}
    matches = _roanuz_matches_mode("live")[:8]
    for match in matches:
        key = str(match.get("roanuzMatchKey") or match.get("id") or "")
        if not _valid_key(key):
            continue
        payload = _v20_bhav(key)
        if payload.get("entries"):
            by_match[key] = payload
    out = {
        "ok": True,
        "oddsType": "live",
        "source": "Roanuz V5 direct match keys",
        "primaryCount": len(by_match),
        "byMatch": by_match,
    }
    v14._shared_put(cache_key, out, 20)
    return out


def _v20_api(handler):
    q = parse_qs(urlparse(handler.path).query)
    action = (q.get("action") or [""])[0].strip().lower()
    key = (q.get("matchId") or q.get("id") or q.get("key") or [""])[0].strip()

    if action == "bhav":
        if not _valid_key(key):
            liveline._send_json(handler, 400, {"ok": False, "error": "Invalid Roanuz match key"})
            return
        liveline._send_json(handler, 200, _v20_bhav(key))
        return

    if action == "bhavsnapshot":
        liveline._send_json(handler, 200, _v20_snapshot())
        return

    if action == "bhavhistory":
        if not _valid_key(key):
            liveline._send_json(handler, 400, {"ok": False, "error": "Invalid Roanuz match key"})
            return
        liveline._send_json(handler, 200, v19._history_payload(key))
        return

    if action == "trust":
        with v14._shared_lock:
            stats = dict(v14._stats)
            cache_entries = len(v14._shared_cache)
        calls = int(stats.get("highlightly_provider_calls", 0)) + int(stats.get("roanuz_provider_calls", 0))
        hits = int(stats.get("highlightly_cache_hits", 0)) + int(stats.get("roanuz_cache_hits", 0))
        total = calls + hits
        liveline._send_json(handler, 200, {
            "ok": True,
            "generatedAt": v19._now_iso(),
            "latestBhav": v19._latest_bhav(key),
            "roanuz": {"role": "primary fixtures + match + live odds", "liveOdds": "enabled", "directMatchKey": True},
            "highlightly": {"role": "fallback only"},
            "apiSaver": {
                "providerCalls": calls,
                "cacheHits": hits,
                "cacheHitRate": round((hits / total) * 100, 1) if total else None,
                "sharedCacheEntries": cache_entries,
            },
        })
        return

    return _PREVIOUS_API(handler)


liveline._api = _v20_api


def _v20_page() -> str:
    html = v19._v19_page()
    # Fix the old lexical currentDetail/window.currentDetail mismatch in inherited layers.
    html = html.replace("window.currentDetail", "currentDetail")
    for old in (
        "/admin/liveline-ibetinv19/api", "/admin/liveline-ibetinv18/api",
        "/admin/liveline-ibetinv17/api", "/admin/liveline/api"
    ):
        html = html.replace(old, liveline.LIVELINE_API_PATH)

    css = r'''
/* =============================================================
   IBETIN V20 — PREMIUM SPORTS TERMINAL RESET
   Cleaner hierarchy: score first, situation second, BHAV third.
   ============================================================= */
:root{
  --v20-bg:#eef2f6;--v20-card:#fff;--v20-navy:#06172f;--v20-navy2:#0b315f;
  --v20-blue:#0d5fbd;--v20-gold:#f2c94c;--v20-ink:#112b49;--v20-muted:#73879a;
  --v20-line:#dce4ec;--v20-live:#e73d53;--v20-green:#0b9461;
}
html,body{background:var(--v20-bg)!important;color:var(--v20-ink)!important}
body{padding-bottom:76px!important}
.topShell{background:linear-gradient(118deg,#041326,#092b55 72%,#0a3f78)!important;box-shadow:0 6px 22px rgba(4,23,47,.20)!important}
.topShell:before{height:2px!important;background:var(--v20-gold)!important}
.brandRow{height:60px!important}.brandMark{width:36px!important;height:36px!important;border-radius:11px!important}.brandText b{font-size:17px!important}.brandText span{font-size:6px!important;letter-spacing:1.5px!important}.liveChip:after{content:'V20'!important;background:var(--v20-gold)!important;color:#132c48!important}
.navCard{top:60px!important;background:rgba(238,242,246,.96)!important;border-bottom:0!important;box-shadow:none!important}.navTabs{padding:8px 10px 6px!important}.tab{height:36px!important;border:0!important;background:#fff!important;border-radius:10px!important;color:#75879a!important}.tab.active{background:#0a315f!important;color:#fff!important;box-shadow:0 4px 12px rgba(10,49,95,.15)!important}
.content,.detailWrap{padding:8px 9px 14px!important;background:var(--v20-bg)!important}
.v15ArenaHero{display:none!important}.v12Command{border:0!important;box-shadow:none!important;background:transparent!important;margin:0 0 8px!important}.v12Sports{padding:2px 0 7px!important}.v12Sport{background:#fff!important;border:0!important;border-radius:9px!important;height:31px!important}.v12Sport.active{background:#0a315f!important;color:#fff!important}.v12SearchRow{padding:0!important}.v12SearchBox{background:#fff!important;border:0!important;min-height:40px!important;border-radius:11px!important;box-shadow:0 2px 8px rgba(7,35,67,.045)!important}.v12Filters{padding:7px 0 0!important}.v12Filter{border:0!important;background:#fff!important}.v12QuickStat{background:transparent!important;border:0!important;padding:6px 1px!important}
.v20Hero{position:relative;overflow:hidden;border-radius:17px;background:linear-gradient(130deg,#06172f,#0b315f 65%,#0e579f);padding:15px 14px 13px;color:#fff;margin-bottom:9px;box-shadow:0 12px 28px rgba(6,35,72,.17)}
.v20Hero:after{content:'';position:absolute;width:150px;height:150px;border-radius:50%;right:-72px;top:-74px;background:rgba(255,255,255,.07)}.v20Hero small{display:block;font-size:6px;font-weight:1000;letter-spacing:1.2px;color:#9fc0e5}.v20Hero h2{font-size:18px;margin:4px 0 4px;letter-spacing:-.25px}.v20Hero p{font-size:7px;color:#c4d7eb;margin:0;line-height:1.5}.v20HeroRow{display:flex;gap:6px;margin-top:11px}.v20HeroPill{font-size:6px;font-weight:1000;padding:5px 7px;border-radius:999px;background:rgba(255,255,255,.09);border:1px solid rgba(255,255,255,.12)}.v20HeroPill.primary{background:#f2c94c;color:#18314e;border-color:#f2c94c}
.dayBlock{margin-bottom:11px!important}.dayHead{margin:0 0 6px!important}.leagueBlock{border:0!important;border-radius:13px!important;box-shadow:none!important;background:transparent!important;margin-bottom:8px!important}.leagueSectionHead{border:0!important;border-radius:10px 10px 0 0!important;padding:7px 8px!important;background:#e6ebf1!important}.leagueSectionName{font-size:8px!important}.leagueMatches{background:transparent!important;padding:5px 0!important;gap:6px!important}.leagueMatches .match{border:0!important;border-radius:13px!important;box-shadow:0 3px 11px rgba(7,36,68,.055)!important;background:#fff!important}.match:before{width:3px!important;background:#d9e3ed!important}.match.liveCard:before{background:var(--v20-live)!important}.leagueMatches .matchHead{padding:7px 9px 5px 11px!important;background:#fff!important;border-bottom:0!important}.badgeLive{background:#fff0f2!important;color:#d72d45!important;border:0!important}.badgeState,.badgeResult{border:0!important}.leagueMatches .matchBody{padding:3px 9px 3px 11px!important}.leagueMatches .team{min-height:39px!important}.leagueMatches .teamBadge{width:30px!important;height:30px!important;border:0!important;background:#f2f5f8!important}.teamname{font-size:12px!important;font-weight:950!important;color:#142d49!important}.abbr{font-size:6px!important}.score{font-size:18px!important;color:#083f7f!important;letter-spacing:-.3px!important}.info{font-size:6px!important}.leagueMatches .matchFoot{min-height:31px!important;padding:5px 8px 7px 11px!important;background:#fff!important;border-top:1px solid #f0f3f6!important}.report{font-size:7px!important}.arrow{background:#edf3f8!important;border-radius:8px!important}.v13CardBhav{padding:6px 8px 7px 11px!important;background:#f9fbfd!important}.v13BhavLabel{font-size:6px!important}.v13BhavOdd{background:#eef5fc!important;border:0!important;color:#0a559f!important;border-radius:8px!important}
.back{border:0!important;background:#fff!important;border-radius:10px!important}.v13MiniScore{top:60px!important;background:linear-gradient(115deg,#06172f,#0b315f)!important;border-radius:13px!important;box-shadow:none!important}.scoreHero{border:0!important;border-radius:15px!important;box-shadow:none!important}.scoreTop,.scoreMain{background:#fff!important}.heroScore{font-size:23px!important;color:#083f7f!important}.detailTabs{top:108px!important;background:var(--v20-bg)!important;padding:6px 0!important}.detailTab{border:0!important;background:#fff!important;border-radius:9px!important;height:33px!important}.detailTab.active{background:#0a315f!important;color:#fff!important}.panel{border:0!important;border-radius:13px!important;box-shadow:none!important;background:#fff!important}.v12Pulse{background:linear-gradient(130deg,#06172f,#0b3f78)!important;border-radius:14px!important;box-shadow:none!important}.v19Trust{gap:5px!important}.v19Trust>div{border:0!important;border-radius:9px!important;background:#fff!important;box-shadow:none!important}.v17IntelStrip>div,.v17Card,.v19Lab,.v19History{border:0!important;box-shadow:none!important;border-radius:11px!important}
.v20Bottom{position:fixed;left:8px;right:8px;bottom:8px;z-index:10040;max-width:720px;margin:auto;display:grid;grid-template-columns:repeat(5,1fr);gap:3px;background:rgba(5,22,45,.96);backdrop-filter:blur(14px);border-radius:15px;padding:6px;box-shadow:0 10px 28px rgba(4,23,48,.22)}.v20Bottom button{border:0;background:transparent;color:#9fb2c8;height:42px;border-radius:10px;font-size:6px;font-weight:950}.v20Bottom button b{display:block;font-size:15px;line-height:16px;margin-bottom:2px}.v20Bottom button.on{background:rgba(255,255,255,.10);color:#fff}.v20Bottom button.liveBtn b{color:#ff5b6f}
html[data-v16-theme="dark"] body{background:#07111e!important}.v20Bottom{border:1px solid rgba(255,255,255,.06)}
'''
    html = html.replace("</style>", css + "\n</style>", 1)

    js = r'''
<script>
(function(){
  function installHero(){
    const content=document.querySelector('.content');
    if(!content||content.querySelector('.v20Hero'))return;
    const hero=document.createElement('section');hero.className='v20Hero';
    hero.innerHTML='<small>IBETIN · ROANUZ V5 PRIMARY</small><h2>Live Cricket Command Center</h2><p>Direct Roanuz match keys · live score intelligence · BHAV · ball-by-ball · graphs</p><div class="v20HeroRow"><span class="v20HeroPill primary">DIRECT MATCH KEY</span><span class="v20HeroPill">API SAVER ON</span><span class="v20HeroPill">LIVE TRUST</span></div>';
    content.insertBefore(hero,content.firstChild);
  }
  function installBottom(){
    if(document.querySelector('.v20Bottom'))return;
    const n=document.createElement('nav');n.className='v20Bottom';n.innerHTML='<button class="on" data-v20="home"><b>⌂</b>HOME</button><button class="liveBtn" data-v20="live"><b>●</b>LIVE</button><button data-v20="cricket"><b>🏏</b>CRICKET</button><button data-v20="alerts"><b>🔔</b>ALERTS</button><button data-v20="more"><b>•••</b>MORE</button>';document.body.appendChild(n);
    n.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;const x=b.dataset.v20; if(x==='live'||x==='cricket'||x==='home'){const tab=[...document.querySelectorAll('.tab')].find(t=>(t.dataset.mode||'').toLowerCase()==='live');if(tab)tab.click();document.getElementById('home')?.scrollIntoView({behavior:'smooth'});}else if(x==='alerts'){const a=document.querySelector('[data-v19-alerts],.v19AlertsBtn');if(a)a.click();}else{document.querySelector('.v12Command')?.scrollIntoView({behavior:'smooth'});}n.querySelectorAll('button').forEach(q=>q.classList.toggle('on',q===b));});
  }
  function tagSource(){document.querySelectorAll('.match').forEach(m=>{if(m.dataset.v20tag)return;m.dataset.v20tag='1';m.title='Roanuz primary fixture / match key';});}
  installHero();installBottom();tagSource();
  new MutationObserver(()=>{installHero();installBottom();tagSource();}).observe(document.body,{childList:true,subtree:true});
})();
</script>
'''
    html = html.replace("</body>", js + "\n</body>", 1)
    return html


liveline.admin_url = _v20_admin_url
liveline._page = _v20_page
app = v19.app


def _startup_probe():
    try:
        featured = _roanuz_featured_raw()
        live = sum(1 for x in featured if _is_state(x, LIVE_STATES))
        logger.info("IBETIN V20 Roanuz featured probe OK candidates=%s live=%s", len(featured), live)
    except Exception as exc:
        logger.warning("IBETIN V20 Roanuz featured probe failed: %s", str(exc)[:160])
    try:
        fixtures = _roanuz_fixtures_raw()
        logger.info("IBETIN V20 Roanuz fixtures probe OK matches=%s", len(fixtures))
    except Exception as exc:
        logger.warning("IBETIN V20 Roanuz fixtures probe unavailable: %s", str(exc)[:160])


_startup_probe()
logger.info("IBETIN V20 installed: Roanuz primary matches/fixtures + direct match keys + premium UI reset")

if __name__ == "__main__":
    app.base.ibetin_start.main()
