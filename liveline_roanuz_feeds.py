"""Roanuz paid live feeds for the Live Line match centre.

Adds the three per-match Roanuz feeds to the Full-mode /liveline Mini App:

* Ball-by-ball  ``match/{key}/ball-by-ball/`` (+ ``/{over_key}/`` for older overs)
* Over summary  ``match/{key}/over-summary/`` (+ ``/{page_key}/`` for older pages)
* Live odds     ``match/{key}/live-match-odds/`` (already fetched for BHAV; reused)

Both bots share ONE Roanuz subscription, so every call is budgeted:

* Feeds are only requested when a user opens COMMENTARY / OVERS for a match,
  and only for matches that have started (never for fixtures).  The page polls
  only while the tab is visible and the match is live.
* One server-side single-flight cache per match and path.  The latest over is
  refreshed at most every ``BALL_LIVE_TTL`` s and the latest summary page every
  ``SUMMARY_LIVE_TTL`` s however many users watch.  Completed overs and older
  summary pages never change, so they are fetched once and kept for hours.
* Older overs are back-filled a few per request (``*_BUDGET``) under a per-match
  lock, so a cold start never bursts and concurrent viewers never duplicate it.
* Cross-bot de-duplication: DURA asks the iBetin relay first for these paths,
  so iBetin's shared cache serves both bots.  If the relay is unavailable DURA
  falls back to its own direct Roanuz credentials (relay is paused for a while).
* Failures are negative-cached; every renderer degrades to the commentary and
  overs already embedded in ``match/{key}/``.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time

logger = logging.getLogger(__name__)

FEEDS_VERSION = "roanuz-feeds-2026-10-01"

BALL_LIVE_TTL = 10            # latest over while the match is live
SUMMARY_LIVE_TTL = 30         # latest over-summary page while live
DONE_TTL = 6 * 60 * 60        # completed overs / older pages are immutable
FINISHED_TTL = 30 * 60        # latest page of a match that is no longer live
FEED_NEGATIVE_TTL = 90        # remember provider failures
BALL_BUDGET = 12              # older overs fetched per request (back-fill)
SUMMARY_BUDGET = 3            # older summary pages fetched per request
MAX_OVERS = 120               # hard cap per match (Tests: latest 120 overs)
MAX_PAGES = 15
RELAY_PAUSE = 5 * 60

_SUB_KEY_RE = re.compile(r"^[A-Za-z0-9]{1,4}_[0-9]{1,2}_[0-9]{1,3}$")


def feed_path_ttl(path: str):
    """TTL policy for the paid feed paths (None for any other path)."""
    parts = [p for p in str(path or "").strip("/").split("/") if p]
    if len(parts) < 3 or parts[0] != "match" or parts[2] not in ("ball-by-ball", "over-summary"):
        return None
    if len(parts) == 4 and _SUB_KEY_RE.match(parts[3]):
        return DONE_TTL
    if len(parts) == 3:
        return BALL_LIVE_TTL if parts[2] == "ball-by-ball" else SUMMARY_LIVE_TTL
    return None


def relay_path_allowed(path: str) -> bool:
    """Extra paths the iBetin relay may serve for DURA (feeds only)."""
    parts = [p for p in str(path or "").strip().strip("/").split("/") if p]
    if len(parts) not in (3, 4) or parts[0] != "match":
        return False
    key = parts[1]
    if not key or len(key) > 180 or not all(ch.isalnum() or ch in "._:-" for ch in key):
        return False
    if parts[2] not in ("ball-by-ball", "over-summary"):
        return False
    return len(parts) == 3 or bool(_SUB_KEY_RE.match(parts[3]))


# ------------------------------------------------------------- pure parsing ---

def _d(v):
    return v if isinstance(v, dict) else {}


def _l(v):
    return v if isinstance(v, list) else []


def _num(v, default=None):
    try:
        if v is None or v == "":
            return default
        n = float(v)
        return n if n == n else default
    except (TypeError, ValueError):
        return default


def _int(v, default=None):
    n = _num(v)
    return int(n) if n is not None else default


def _data(payload):
    payload = _d(payload)
    return _d(payload.get("data")) or payload


def _innings_label(idx, teams):
    side, _, num = str(idx or "").partition("_")
    team = _d(teams.get(side))
    name = team.get("code") or team.get("name") or side.upper()
    return f"{name} {'1st' if num == '1' else '2nd' if num == '2' else num} inns" if num and num != "1" else str(name)


def parse_ball(ball, tokenizer, cleaner, namer):
    ball = _d(ball)
    overs = ball.get("overs")
    over_no = _int(overs[0]) if isinstance(overs, (list, tuple)) and overs else None
    ball_no = _int(overs[1]) if isinstance(overs, (list, tuple)) and len(overs) > 1 else None
    label, runs, kind = tokenizer(ball.get("repr"), ball)
    bat = _d(ball.get("batsman"))
    bowl = _d(ball.get("bowler"))
    wicket = _d(ball.get("wicket"))
    return {
        "key": str(ball.get("key") or ""),
        "innings": str(ball.get("innings") or ""),
        "over": (over_no + 1) if over_no is not None else None,
        "ball": f"{over_no}.{ball_no}" if over_no is not None and ball_no is not None else "",
        "t": label,
        "k": kind,
        "runs": runs,
        "text": cleaner(ball.get("comment"), 360),
        "score": str(ball.get("display_score") or "").replace(" overs", " ov"),
        "batter": namer(bat.get("player_key")) if bat.get("player_key") else "",
        "bowler": namer(bowl.get("player_key")) if bowl.get("player_key") else "",
        "out": namer(wicket.get("player_key")) if wicket.get("player_key") else "",
        "how": str(wicket.get("wicket_type") or "").replace("_", " "),
        "milestone": bool(bat.get("milestone")) or bool(ball.get("team_batting_milestone")),
        "_t": _num(ball.get("entry_time")) or _num(ball.get("updated_time")) or 0,
    }


def build_ball_feed(over_payloads, teams, tokenizer, cleaner, namer, complete=True):
    """Roanuz ball-by-ball over payloads -> innings -> overs (latest first)."""
    overs = {}
    for payload in over_payloads:
        over = _d(_data(payload).get("over")) or _d(payload.get("over") if isinstance(payload, dict) else None)
        index = _d(over.get("index"))
        balls = [parse_ball(b, tokenizer, cleaner, namer) for b in _l(over.get("balls"))]
        balls = [b for b in balls if b["key"] or b["text"]]
        if not balls:
            continue
        inn = str(index.get("innings") or balls[0]["innings"] or "")
        num = balls[0]["over"] or _int(index.get("over_number"))
        if num is None:
            continue
        seen, uniq = set(), []
        for b in sorted(balls, key=lambda x: (x["_t"], x["ball"])):
            mark = b["key"] or f"{b['ball']}:{b['text']}"
            if mark in seen:
                continue
            seen.add(mark)
            b.pop("_t", None)
            uniq.append(b)
        overs[(inn, num)] = {
            "innings": inn,
            "over": num,
            "balls": uniq,
            "runs": sum(int(b["runs"] or 0) for b in uniq),
            "wickets": sum(1 for b in uniq if b["k"] == "wicket"),
            "fours": sum(1 for b in uniq if b["k"] == "four"),
            "sixes": sum(1 for b in uniq if b["k"] == "six"),
            "score": uniq[-1]["score"] if uniq else "",
            "bowler": next((b["bowler"] for b in uniq if b["bowler"]), ""),
        }
    order = []
    for inn, num in overs:
        if inn not in order:
            order.append(inn)
    order.sort(key=lambda i: (i.partition("_")[2], i))
    innings = []
    for inn in order:
        rows = sorted((o for (i, _), o in overs.items() if i == inn), key=lambda o: o["over"], reverse=True)
        innings.append({
            "innings": inn,
            "label": _innings_label(inn, teams),
            "overs": rows,
            "balls": sum(len(o["balls"]) for o in rows),
            "firstOver": rows[-1]["over"] if rows else None,
        })
    return {"innings": innings, "complete": bool(complete)}


def _over_offset_from_balls(ball_payloads):
    """CricketOverIndex.over_number minus the 0-based over in ``ball.overs``."""
    for payload in ball_payloads:
        over = _d(_data(payload).get("over"))
        n = _int(_d(over.get("index")).get("over_number"))
        balls = _l(over.get("balls"))
        if n is None or not balls:
            continue
        ov = _d(balls[0]).get("overs")
        if isinstance(ov, (list, tuple)) and ov:
            zero = _int(ov[0])
            if zero is not None and n - zero in (0, 1):
                return n - zero
    return None


def _over_offset_from_rates(summaries):
    votes = {0: 0, 1: 0}
    for s in summaries:
        s = _d(s)
        n = _int(_d(s.get("index")).get("over_number"))
        ms = _d(s.get("match_score"))
        runs, rr = _num(ms.get("runs")), _num(ms.get("run_rate"))
        if n is None or not runs or not rr:
            continue
        overs_done = runs / rr
        for off in (0, 1):
            if abs(overs_done - (n + 1 - off)) < 0.35:
                votes[off] += 1
    if votes[0] == votes[1]:
        return None
    return 0 if votes[0] > votes[1] else 1


def build_over_summary(pages, teams, namer, offset=None):
    """Roanuz over-summary pages -> innings -> overs (ascending) for charts."""
    summaries = []
    for payload in pages:
        summaries.extend(_l(_data(payload).get("summaries")))
    if offset is None:
        offset = _over_offset_from_rates(summaries)
    if offset is None:
        offset = 1  # page/over keys (b_1_11) are 1-based
    rows = {}
    for s in summaries:
        s = _d(s)
        index = _d(s.get("index"))
        inn = str(index.get("innings") or "")
        n = _int(index.get("over_number"))
        if not inn or n is None:
            continue
        over = n + (1 - offset)
        ms = _d(s.get("match_score"))
        rows[(inn, over)] = {
            "innings": inn,
            "over": over,
            "runs": _int(s.get("runs"), 0),
            "wickets": _int(s.get("wickets"), 0),
            "total": _int(ms.get("runs")),
            "totalWickets": _int(ms.get("wickets")),
            "rr": _num(ms.get("run_rate")),
            "rrr": _num(ms.get("req_run_rate")),
            "need": _int(ms.get("req_runs")),
            "ballsLeft": _int(ms.get("req_balls")),
            "fours": _int(ms.get("fours")),
            "sixes": _int(ms.get("sixes")),
            "extras": _int(ms.get("extras")),
            "batters": [
                {
                    "name": namer(_d(b).get("player_key")),
                    "r": _int(_d(_d(b).get("score")).get("runs"), 0),
                    "b": _int(_d(_d(b).get("score")).get("balls"), 0),
                    "out": bool(_d(_d(b).get("score")).get("is_dismissed") or _d(b).get("is_dismissed")),
                }
                for b in _l(s.get("strikers"))[:2]
            ],
            "bowlers": [
                {
                    "name": namer(_d(b).get("player_key")),
                    "o": ".".join(str(x) for x in _l(_d(_d(b).get("score")).get("overs"))) or "",
                    "r": _int(_d(_d(b).get("score")).get("runs"), 0),
                    "w": _int(_d(_d(b).get("score")).get("wickets"), 0),
                }
                for b in _l(s.get("bowlers"))[:1]
            ],
        }
    order = sorted({i for i, _ in rows}, key=lambda i: (i.partition("_")[2], i))
    innings = []
    for inn in order:
        overs = sorted((r for (i, _), r in rows.items() if i == inn), key=lambda r: r["over"])
        cum = None
        for r in overs:
            if r["total"] is None:
                cum = (cum or 0) + r["runs"]
                r["total"] = cum
            cum = r["total"]
        innings.append({
            "innings": inn,
            "label": _innings_label(inn, teams),
            "overs": overs,
            "runs": overs[-1]["total"] if overs else 0,
            "wickets": overs[-1]["totalWickets"] if overs else 0,
            "maxOver": max((r["runs"] for r in overs), default=0),
        })
    return {"innings": innings}


def build_odds(odds_payload, teams):
    """Roanuz live-match-odds -> match winner decimal/fractional + probability."""
    match = _d(_data(odds_payload).get("match"))
    if not match:
        return None
    side_for = {}
    for side, t in _d(teams).items():
        t = _d(t)
        if t.get("key"):
            side_for[str(t["key"])] = side
    names = {str(k): _d(v) for k, v in _d(match.get("teams")).items()}
    fmt = str(_d(match.get("meta")).get("format") or "").lower()
    with_draw = fmt in ("test", "first_class", "multi_day") or fmt.startswith("test")
    bet = _d(match.get("bet_odds_with_draw") if with_draw else match.get("bet_odds")) or _d(match.get("bet_odds"))
    auto = _d(bet.get("automatic"))
    pred = _d(match.get("result_prediction_with_draw") if with_draw else match.get("result_prediction")) or _d(match.get("result_prediction"))
    pct = {str(_d(p).get("team_key")): _num(_d(p).get("value")) for p in _l(_d(pred.get("automatic")).get("percentage"))}
    frac = {str(_d(p).get("team_key")): _d(p) for p in _l(auto.get("fractional"))}
    rows = []
    for item in _l(auto.get("decimal")):
        item = _d(item)
        tk = str(item.get("team_key") or "")
        dec = _num(item.get("value"))
        if not tk or dec is None:
            continue
        info = names.get(tk) or _d(_d(teams).get(side_for.get(tk, "")))
        f = frac.get(tk) or {}
        rows.append({
            "side": side_for.get(tk, ""),
            "name": info.get("name") or tk,
            "code": info.get("code") or info.get("name") or tk,
            "decimal": round(dec, 2),
            "fractional": f"{f['numerator']}/{f['denominator']}" if f.get("numerator") and f.get("denominator") else "",
            "implied": round(100.0 / dec, 1) if dec > 0 else None,
            "pct": round(pct[tk], 1) if pct.get(tk) is not None else None,
        })
    if len(rows) < 2:
        return None
    rows.sort(key=lambda r: (r["side"] or "z", r["name"]))
    fav = min(rows, key=lambda r: r["decimal"])
    draw = None
    if with_draw:
        dd = _num(_d(_d(_d(match.get("bet_odds_with_draw")).get("draw")).get("decimal")).get("value"))
        dp = _num(_d(_d(match.get("result_prediction_with_draw")).get("draw")).get("value"))
        if dd or dp:
            draw = {"decimal": round(dd, 2) if dd else None, "pct": round(dp, 1) if dp is not None else None}
    return {"teams": rows, "favourite": fav["code"], "draw": draw, "status": str(_d(match.get("meta")).get("status") or "")}


# ------------------------------------------------------------ runtime feeds ---

class Feeds:
    """Budgeted, cached access to the paid feeds for one bot."""

    def __init__(self, admin, brand, cached, cache_get, lock_for, tokenizer, cleaner):
        self.admin = admin
        self.brand = brand
        self._cached = cached
        self._cache_get = cache_get
        self._lock_for = lock_for
        self._tok = tokenizer
        self._clean = cleaner
        self.stats = {"calls": 0}
        self._stats_lock = threading.Lock()

    def fetch(self, path, ttl):
        """One call through the bot's shared Roanuz cache (V14 single-flight).

        On DURA the raw transport underneath asks the iBetin relay first, see
        ``install_dura_relay``.
        """
        with self._stats_lock:
            self.stats["calls"] = self.stats.get("calls", 0) + 1
        return self.admin._roanuz_get(path, ttl=ttl)

    def _get(self, cache_key, path, ttl):
        return self._cached(cache_key, ttl, lambda: self.fetch(path, ttl), negative_ttl=FEED_NEGATIVE_TTL)

    # -- ball by ball -----------------------------------------------------
    def ball_payloads(self, key, live):
        latest_ttl = BALL_LIVE_TTL if live else FINISHED_TTL
        latest = self._get(f"rf:bb:{key}:latest:{int(bool(live))}", f"match/{key}/ball-by-ball/", latest_ttl)
        payloads = [latest]
        prev = _data(latest).get("previous_over_key")
        budget, more, seen = BALL_BUDGET, False, set()
        with self._lock_for(f"rf:bbwalk:{key}"):
            while prev and len(payloads) < MAX_OVERS and prev not in seen:
                seen.add(prev)
                if not _SUB_KEY_RE.match(str(prev)):
                    break
                ck = f"rf:bb:{key}:{prev}"
                hit = self._cache_get(ck)
                if hit is None:
                    if budget <= 0:
                        more = True
                        break
                    budget -= 1
                    try:
                        hit = self._get(ck, f"match/{key}/ball-by-ball/{prev}/", DONE_TTL)
                    except Exception:
                        more = True
                        break
                elif not isinstance(hit, dict):
                    more = True  # negative-cached over; try again later
                    break
                payloads.append(hit)
                prev = _data(hit).get("previous_over_key")
        return payloads, (not more)

    def balls(self, key, live, teams, namer):
        payloads, complete = self.ball_payloads(key, live)
        feed = build_ball_feed(payloads, teams, self._tok, self._clean, namer, complete)
        feed["offset"] = _over_offset_from_balls(payloads)
        return feed

    # -- over summary -----------------------------------------------------
    def summary_pages(self, key, live):
        latest_ttl = SUMMARY_LIVE_TTL if live else FINISHED_TTL
        latest = self._get(f"rf:os:{key}:latest:{int(bool(live))}", f"match/{key}/over-summary/", latest_ttl)
        pages = [latest]
        prev = _data(latest).get("previous_page_key")
        budget, more, seen = SUMMARY_BUDGET, False, set()
        with self._lock_for(f"rf:oswalk:{key}"):
            while prev and len(pages) < MAX_PAGES and prev not in seen:
                seen.add(prev)
                if not _SUB_KEY_RE.match(str(prev)):
                    break
                ck = f"rf:os:{key}:{prev}"
                hit = self._cache_get(ck)
                if hit is None:
                    if budget <= 0:
                        more = True
                        break
                    budget -= 1
                    try:
                        hit = self._get(ck, f"match/{key}/over-summary/{prev}/", DONE_TTL)
                    except Exception:
                        more = True
                        break
                elif not isinstance(hit, dict):
                    more = True
                    break
                pages.append(hit)
                prev = _data(hit).get("previous_page_key")
        return pages, (not more)

    def summary(self, key, live, teams, namer, offset=None):
        pages, complete = self.summary_pages(key, live)
        out = build_over_summary(pages, teams, namer, offset)
        out["complete"] = complete
        return out


def install_shared_ttl(v14_module) -> bool:
    """Teach the shared Roanuz cache (V14) the feed TTLs. Never raises."""
    try:
        base = v14_module._roanuz_effective_ttl
        if getattr(base, "_feeds_ttl", False):
            return True

        def effective(path, requested):
            ttl = feed_path_ttl(path)
            if ttl is not None:
                return max(int(requested or 0), ttl) if ttl == DONE_TTL else max(min(int(requested or ttl), FINISHED_TTL), ttl)
            return base(path, requested)

        effective._feeds_ttl = True
        v14_module._roanuz_effective_ttl = effective
        return True
    except Exception as exc:
        logger.warning("Live Line feeds: shared TTL policy not installed: %s", exc)
        return False


def install_relay_paths(v30_module) -> bool:
    """iBetin only: let the existing DURA relay serve the feed paths too."""
    try:
        base = getattr(v30_module, "_allowed_dura_roanuz_proxy_path", None)
        if base is None or getattr(base, "_feeds_relay", False):
            return base is not None

        def allowed(value):
            return bool(base(value)) or relay_path_allowed(value)

        allowed._feeds_relay = True
        v30_module._allowed_dura_roanuz_proxy_path = allowed
        return True
    except Exception as exc:
        logger.warning("Live Line feeds: relay paths not installed: %s", exc)
        return False


_RELAY_STATE = {"paused_until": 0.0, "relay": 0, "direct": 0, "fail": 0}


def _relay_configured():
    return bool(os.getenv("IBETIN_ROANUZ_PROXY_URL", "").strip() and os.getenv("DURA_FEED_RELAY_SECRET", "").strip())


def _relay_get(path):
    import httpx  # provided by the bot runtime

    with httpx.Client(timeout=12.0, follow_redirects=True) as client:
        response = client.get(
            os.getenv("IBETIN_ROANUZ_PROXY_URL", "").strip(),
            params={"path": path},
            headers={"x-dura-relay-key": os.getenv("DURA_FEED_RELAY_SECRET", "").strip(), "Accept": "application/json"},
        )
    if response.status_code < 200 or response.status_code >= 300:
        raise RuntimeError(f"relay HTTP {response.status_code}")
    data = response.json()
    if not isinstance(data, dict) or not data.get("ok"):
        raise RuntimeError("relay returned no payload")
    return data.get("payload")


def shared_feed_path(path) -> bool:
    """Paths both bots request for the same match (cross-bot de-duplicated)."""
    parts = [p for p in str(path or "").strip("/").split("/") if p]
    if len(parts) == 3 and parts[0] == "match" and parts[2] == "live-match-odds":
        return True
    return relay_path_allowed(path)


def install_dura_relay(v14_module, relay_get=None) -> bool:
    """DURA only: fetch the paid per-match feeds through the iBetin relay first.

    iBetin then serves both bots from one cached Roanuz response.  Any relay
    failure pauses the relay for ``RELAY_PAUSE`` seconds and DURA uses its own
    direct credentials, so the feeds never depend on iBetin being up.
    """
    try:
        raw = v14_module._raw_roanuz_get
        if getattr(raw, "_feeds_relay", False):
            return True
        getter = relay_get or _relay_get

        def transport(path, ttl=10):
            if shared_feed_path(path) and _relay_configured() and time.time() >= _RELAY_STATE["paused_until"]:
                try:
                    payload = getter(path)
                    _RELAY_STATE["relay"] += 1
                    return payload
                except Exception as exc:
                    _RELAY_STATE["paused_until"] = time.time() + RELAY_PAUSE
                    _RELAY_STATE["fail"] += 1
                    logger.warning("Live Line feeds: shared relay unavailable (%s); direct Roanuz for %ss", str(exc)[:80], RELAY_PAUSE)
            _RELAY_STATE["direct"] += 1
            return raw(path, ttl=ttl)

        transport._feeds_relay = True
        v14_module._raw_roanuz_get = transport
        return True
    except Exception as exc:
        logger.warning("Live Line feeds: DURA relay not installed: %s", exc)
        return False
