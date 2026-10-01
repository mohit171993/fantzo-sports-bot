"""Live Line Match Centre for the Full-mode /liveline Mini App.

Adds what the Roanuz V5 match feed already returns but the page never showed:
full batting/bowling scorecards, extras, fall of wickets, partnerships, live
batters/bowler, CRR/RRR/target/projected score, win probability, recent overs,
ball-by-ball commentary, squads/playing XI, toss/venue/officials, series points
table, plus live football scores from Highlightly.

Shared by IBETIN and DURA; ``brand`` only switches the theme.  It is installed
on top of the existing V40 page and /liveline/api contract:

* new API actions ``center``, ``points`` and ``football``; every other action is
  passed through unchanged (BHAV / session markets keep working exactly as now);
* the page gets extra CSS + JS, existing markup and wording are untouched.

Provider usage is cost-aware.  The match centre re-uses the cached
``match/{key}/`` and ``live-match-odds/`` responses that the page and BHAV
already fetch (no new per-match Roanuz endpoints), ``tournament/{key}/points/``
(free on Roanuz plans) is cached for 30 minutes and Highlightly football for
two minutes.  Failures are negative-cached so a missing entitlement never
hammers a provider, and every renderer copes with missing data.
"""
from __future__ import annotations

import html as _html
import logging
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

VERSION = "match-centre-2026-10-01"
logger = logging.getLogger(__name__)

CENTER_TTL = 12
ODDS_TTL = 20
POINTS_TTL = 30 * 60
FOOTBALL_TTL = 120
NEGATIVE_TTL = 5 * 60

_cache: dict = {}
_cache_lock = threading.Lock()
_key_locks: dict = {}
_TAG_RE = re.compile(r"<[^>]+>")
_KEY_RE = re.compile(r"^[A-Za-z0-9_.:-]{3,120}$")
_IST = timezone(timedelta(hours=5, minutes=30))


# ---------------------------------------------------------------- caching ---

def _cache_get(key):
    with _cache_lock:
        item = _cache.get(key)
        if not item:
            return None
        expires, value = item
        if expires < time.monotonic():
            _cache.pop(key, None)
            return None
        return value


def _cache_put(key, value, ttl):
    with _cache_lock:
        _cache[key] = (time.monotonic() + max(1, int(ttl)), value)
        if len(_cache) > 600:
            now = time.monotonic()
            for k in [k for k, (exp, _) in _cache.items() if exp < now]:
                _cache.pop(k, None)


def _lock_for(key):
    with _cache_lock:
        lock = _key_locks.get(key)
        if lock is None:
            lock = _key_locks[key] = threading.Lock()
        return lock


class _Negative:
    __slots__ = ("error",)

    def __init__(self, error):
        self.error = error


def _cached(key, ttl, loader, negative_ttl=NEGATIVE_TTL):
    """Single-flight cache; errors are remembered for ``negative_ttl``."""
    hit = _cache_get(key)
    if hit is None:
        with _lock_for(key):
            hit = _cache_get(key)
            if hit is None:
                try:
                    hit = loader()
                    _cache_put(key, hit, ttl)
                except Exception as exc:  # remember the failure, do not retry-storm
                    hit = _Negative(str(exc)[:160])
                    _cache_put(key, hit, negative_ttl)
    if isinstance(hit, _Negative):
        raise RuntimeError(hit.error)
    return hit


# ---------------------------------------------------------------- helpers ---

def _d(value):
    return value if isinstance(value, dict) else {}


def _l(value):
    return value if isinstance(value, list) else []


def _num(value, default=None):
    try:
        if value is None or value == "" or isinstance(value, bool):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value, default=None):
    n = _num(value)
    return default if n is None else int(round(n))


def _clean(value, limit=400):
    text = _html.unescape(_TAG_RE.sub("", str(value or "")))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _overs(value):
    if isinstance(value, (list, tuple)):
        if len(value) >= 2:
            return f"{_int(value[0], 0)}.{_int(value[1], 0)}"
        if len(value) == 1:
            return str(_int(value[0], 0))
        return ""
    if value in (None, ""):
        return ""
    return str(value)


def _balls_from_overs(value):
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return _int(value[0], 0) * 6 + _int(value[1], 0)
    n = _num(value)
    if n is None:
        return None
    whole = int(n)
    return whole * 6 + int(round((n - whole) * 10))


def _rate(runs, balls):
    if not balls:
        return None
    return round(float(runs) * 6.0 / float(balls), 2)


def _sr(runs, balls):
    if not balls:
        return None
    return round(float(runs) * 100.0 / float(balls), 1)


def _pretty_key(key):
    text = str(key or "")
    for prefix in ("c__player__", "c__team__", "a-rz--cricket--", "w_", "m_"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    text = re.sub(r"__[0-9a-f]{4,}$", "", text)
    text = re.sub(r"[-_]+", " ", text).strip()
    return text.title() if text else str(key or "")


def _first(*values):
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


# ------------------------------------------------------- match context ---

class _Match:
    def __init__(self, node):
        self.node = _d(node)
        self.teams = _d(self.node.get("teams"))
        self.players = _d(self.node.get("players"))
        self.squad = _d(self.node.get("squad"))
        self.play = _d(self.node.get("play"))
        self.live = _d(self.play.get("live"))
        self.innings_map = _d(self.play.get("innings"))
        self._names = {}
        recent = _d(self.live.get("recent_players"))
        for item in recent.values():
            item = _d(item)
            if item.get("key") and item.get("name"):
                self._names[str(item["key"])] = str(item["name"])
        for ball in self.balls_raw():
            # "Bowler to Batter: ..." gives a name for the two keys involved.
            comment = _clean(ball.get("comment"), 160)
            match = re.match(r"^(.+?) to (.+?):", comment)
            if match:
                bowler = _d(ball.get("bowler")).get("player_key")
                batter = _d(ball.get("batsman")).get("player_key")
                if bowler and bowler not in self._names:
                    self._names[str(bowler)] = match.group(1).strip()
                if batter and batter not in self._names:
                    self._names[str(batter)] = match.group(2).strip()

    # names / sides -----------------------------------------------------
    def name(self, key):
        if not key:
            return ""
        key = str(key)
        player = _d(_d(self.players.get(key)).get("player"))
        return str(player.get("name") or player.get("jersey_name") or self._names.get(key) or _pretty_key(key))

    def role(self, key):
        player = _d(_d(self.players.get(str(key))).get("player"))
        role = player.get("seasonal_role") or _first(*_l(player.get("roles"))) or ""
        return str(role).replace("_", " ").replace("batsman", "batter").strip()

    def team(self, side):
        team = _d(self.teams.get(side))
        return {
            "side": side,
            "key": team.get("key") or side,
            "name": team.get("name") or team.get("alternate_name") or side.upper(),
            "code": team.get("code") or team.get("alternate_code") or (team.get("name") or side)[:3].upper(),
        }

    def side_for_team_key(self, team_key):
        for side, team in self.teams.items():
            if str(_d(team).get("key")) == str(team_key):
                return side
        return None

    def squad_keys(self, side, playing=True):
        team = _d(self.squad.get(side))
        keys = _l(team.get("playing_xi")) if playing else []
        if not keys:
            keys = _l(team.get("player_keys"))
        return [str(k) for k in keys if k]

    def side_of(self, key):
        key = str(key)
        for side in self.squad:
            team = _d(self.squad.get(side))
            if key in {str(k) for k in _l(team.get("player_keys")) + _l(team.get("playing_xi"))}:
                return side
        return None

    def score_block(self, key, number, kind):
        score = _d(_d(self.players.get(str(key))).get("score"))
        block = _d(_d(score.get(str(number))).get(kind))
        return block

    # innings -------------------------------------------------------------
    def ordered_innings(self):
        order = [str(x) for x in _l(self.play.get("innings_order"))]
        for idx in self.innings_map:
            if str(idx) not in order:
                order.append(str(idx))
        rows = []
        for idx in order:
            row = _d(self.innings_map.get(idx))
            if not row:
                continue
            score = _d(row.get("score"))
            started = bool(_int(score.get("balls"), 0) or _l(row.get("batting_order")))
            if started or idx == self.live.get("innings"):
                rows.append((idx, row))
        return rows

    def balls_raw(self):
        related = self.play.get("related_balls")
        if not isinstance(related, (dict, list)):
            related = self.node.get("related_balls")
        values = list(related.values()) if isinstance(related, dict) else _l(related)
        return [b for b in values if isinstance(b, dict)]


def _ball_token(repr_value, ball=None):
    """Roanuz ball repr ("r1", "b4", "w", "e1,wd", ...) -> (label, runs, kind)."""
    parts = [p.strip().lower() for p in str(repr_value or "").split(",") if p.strip()]
    runs, extra, label, kind = 0, 0, "", "run"
    wicket = False
    for part in parts:
        if part == "w" or part.startswith("w") and part[1:].isdigit():
            wicket = True
        elif part in ("wd", "nb", "lb", "b", "bye", "lb", "pen"):
            label = part
        elif part[:1] == "r" and part[1:].isdigit():
            runs += int(part[1:])
        elif part[:1] == "b" and part[1:].isdigit():
            runs += int(part[1:])
            kind = "six" if part[1:] == "6" else "four" if part[1:] == "4" else kind
        elif part[:1] == "e" and part[1:].isdigit():
            extra += int(part[1:])
    if ball:
        batsman = _d(ball.get("batsman"))
        if batsman.get("is_six"):
            kind = "six"
        elif batsman.get("is_four"):
            kind = "four"
        if ball.get("wicket"):
            wicket = True
        ball_type = str(ball.get("ball_type") or "").lower()
        if ball_type in ("wide", "no_ball", "noball", "leg_bye", "bye") and not label:
            label = {"wide": "wd", "no_ball": "nb", "noball": "nb", "leg_bye": "lb", "bye": "b"}[ball_type]
        team_score = _d(ball.get("team_score"))
        if not parts and team_score:
            runs = _int(team_score.get("runs"), 0) - _int(team_score.get("extras"), 0)
            extra = _int(team_score.get("extras"), 0)
    total = runs + extra
    if wicket:
        return "W", total, "wicket"
    if label in ("wd", "nb"):
        shown = f"{total}{label}" if total > 1 else label
        return shown, total, "extra"
    if label in ("lb", "b") and total:
        return f"{total}{label}", total, "extra"
    if kind in ("four", "six"):
        return str(runs), total, kind
    return ("•" if total == 0 else str(total)), total, "dot" if total == 0 else "run"


# ------------------------------------------------------------- builders ---

def _batting(ctx, idx, row, live_innings):
    side, _, number = idx.partition("_")
    number = number or "1"
    order = [str(k) for k in _l(row.get("batting_order"))]
    out_keys = [str(k) for k in _l(row.get("wicket_order"))]
    partnerships = _l(row.get("partnerships"))
    totals = {}
    for part in partnerships:
        part = _d(part)
        for pk_name, sc_name in (("player_a_key", "player_a_score"), ("player_b_key", "player_b_score")):
            pk = part.get(pk_name)
            sc = _d(part.get(sc_name))
            if not pk:
                continue
            agg = totals.setdefault(str(pk), {"runs": 0, "balls": 0, "fours": 0, "sixes": 0})
            for k in agg:
                agg[k] += _int(sc.get(k), 0)
    for pk in totals:
        if pk not in order:
            order.append(pk)
    recent = _d(ctx.live.get("recent_players")) if idx == live_innings else {}
    striker = _d(recent.get("striker")).get("key") or (ctx.live.get("striker_key") if idx == live_innings else None)
    non_striker = _d(recent.get("non_striker")).get("key") or (ctx.live.get("non_striker_key") if idx == live_innings else None)
    rows = []
    for pk in order:
        block = ctx.score_block(pk, number, "batting")
        score = _d(block.get("score"))
        if not score:
            for who in ("striker", "non_striker"):
                item = _d(recent.get(who))
                if str(item.get("key")) == pk:
                    score = _d(item.get("stats"))
        if not score:
            score = totals.get(pk, {})
        runs = _int(score.get("runs"), 0)
        balls = _int(score.get("balls"), 0)
        dismissal = _d(block.get("dismissal"))
        is_out = pk in out_keys or bool(dismissal)
        batting_now = pk in (striker, non_striker) and not is_out
        if dismissal.get("msg"):
            how = _clean(dismissal.get("msg"), 90)
        elif is_out:
            how = "out"
        elif batting_now:
            how = "batting"
        else:
            how = "not out"
        rows.append({
            "key": pk,
            "name": ctx.name(pk),
            "how": how,
            "out": is_out,
            "onStrike": pk == striker and not is_out,
            "batting": batting_now,
            "r": runs,
            "b": balls,
            "4s": _int(score.get("fours"), 0),
            "6s": _int(score.get("sixes"), 0),
            "sr": _num(score.get("strike_rate")) if _num(score.get("strike_rate")) is not None else _sr(runs, balls),
        })
    yet = [ctx.name(k) for k in ctx.squad_keys(side) if k not in order]
    return rows, yet


def _bowling(ctx, idx, row):
    side, _, number = idx.partition("_")
    number = number or "1"
    bowl_side = next((s for s in ctx.teams if s != side), None)
    candidates = []
    for source in ([_d(ctx.innings_map.get(f"{bowl_side}_{number}")).get("bowling_order")] if bowl_side else []) + [row.get("bowling_order")]:
        for pk in _l(source):
            if pk and str(pk) not in candidates:
                candidates.append(str(pk))
    if bowl_side:
        for pk in ctx.squad_keys(bowl_side, playing=False):
            if pk not in candidates and ctx.score_block(pk, number, "bowling"):
                candidates.append(pk)
    rows = []
    recent = _d(ctx.live.get("recent_players")) if idx == ctx.live.get("innings") else {}
    current = _d(recent.get("bowler")).get("key")
    for pk in candidates:
        member = ctx.side_of(pk)
        if member and bowl_side and member != bowl_side:
            continue
        score = _d(ctx.score_block(pk, number, "bowling").get("score"))
        if not score:
            for who in ("bowler", "prev_over_bowler"):
                item = _d(recent.get(who))
                if str(item.get("key")) == pk:
                    score = _d(item.get("stats"))
        if not score:
            continue
        balls = _int(score.get("balls"))
        if balls is None:
            balls = _balls_from_overs(score.get("overs")) or 0
        runs = _int(score.get("runs"), 0)
        rows.append({
            "key": pk,
            "name": ctx.name(pk),
            "o": _overs(score.get("overs")) or f"{balls // 6}.{balls % 6}",
            "m": _int(score.get("maiden_overs"), 0),
            "r": runs,
            "w": _int(score.get("wickets"), 0),
            "eco": _num(score.get("economy")) if _num(score.get("economy")) is not None else _rate(runs, balls),
            "bowling": pk == current,
        })
    return rows


def _fall_of_wickets(ctx, idx, row):
    number = idx.partition("_")[2] or "1"
    partnerships = [_d(p) for p in _l(row.get("partnerships"))]
    by_ball = {}
    for ball in ctx.balls_raw():
        wicket = _d(ball.get("wicket"))
        if ball.get("innings") == idx and wicket.get("player_key"):
            by_ball[str(wicket["player_key"])] = ball
    fow = []
    running = 0
    for i, pk in enumerate(_l(row.get("wicket_order"))):
        pk = str(pk)
        dismissal = _d(ctx.score_block(pk, number, "batting").get("dismissal"))
        runs = _int(dismissal.get("team_runs"))
        overs = _overs(dismissal.get("overs"))
        if runs is None and i < len(partnerships):
            running = sum(_int(_d(p.get("score")).get("runs"), 0) for p in partnerships[: i + 1])
            runs = running
            overs = overs or _overs(partnerships[i].get("end_overs"))
        if runs is None and pk in by_ball:
            m = re.match(r"\s*(\d+)/(\d+)", str(by_ball[pk].get("display_score") or ""))
            if m:
                runs = int(m.group(1))
            overs = overs or _overs(by_ball[pk].get("overs"))
        fow.append({"wicket": i + 1, "score": f"{runs if runs is not None else '?'}-{i + 1}", "overs": overs, "name": ctx.name(pk)})
    return fow


def _partnerships(ctx, row):
    rows = []
    for i, part in enumerate(_l(row.get("partnerships"))):
        part = _d(part)
        score = _d(part.get("score"))
        a, b = _d(part.get("player_a_score")), _d(part.get("player_b_score"))
        rows.append({
            "wicket": i + 1,
            "runs": _int(score.get("runs"), 0),
            "balls": _int(score.get("balls"), 0),
            "a": {"name": ctx.name(part.get("player_a_key")), "r": _int(a.get("runs"), 0), "b": _int(a.get("balls"), 0)},
            "b": {"name": ctx.name(part.get("player_b_key")), "r": _int(b.get("runs"), 0), "b": _int(b.get("balls"), 0)},
            "active": not part.get("is_completed"),
        })
    return rows


def _extras(row):
    ex = _d(row.get("extra_runs"))
    total = _int(ex.get("extra"))
    parts = {"b": _int(ex.get("bye"), 0), "lb": _int(ex.get("leg_bye"), 0), "w": _int(ex.get("wide"), 0), "nb": _int(ex.get("no_ball"), 0), "p": _int(ex.get("penalty"), 0)}
    if total is None:
        total = sum(parts.values())
    return {"total": total, **parts}


def _innings(ctx):
    live_innings = ctx.live.get("innings")
    out = []
    for idx, row in ctx.ordered_innings():
        side, _, number = idx.partition("_")
        score = _d(row.get("score"))
        batting, yet = _batting(ctx, idx, row, live_innings)
        balls = _int(score.get("balls"), 0)
        out.append({
            "index": idx,
            "number": number or "1",
            "team": ctx.team(side),
            "runs": _int(score.get("runs"), 0),
            "wickets": _int(row.get("wickets"), 0),
            "overs": _overs(row.get("overs")) or (f"{balls // 6}.{balls % 6}" if balls else ""),
            "rr": _num(score.get("run_rate")) if _num(score.get("run_rate")) is not None else _rate(_int(score.get("runs"), 0), balls),
            "fours": _int(score.get("fours")),
            "sixes": _int(score.get("sixes")),
            "dots": _int(score.get("dot_balls")),
            "complete": bool(row.get("is_completed")),
            "live": idx == live_innings,
            "batting": batting,
            "yetToBat": yet,
            "extras": _extras(row),
            "bowling": _bowling(ctx, idx, row),
            "fow": _fall_of_wickets(ctx, idx, row),
            "partnerships": _partnerships(ctx, row),
        })
    return out


def _recent_overs(ctx):
    overs = []
    for item in _l(ctx.live.get("recent_overs_repr")):
        item = _d(item)
        balls = [_ball_token(x) for x in _l(item.get("ball_repr"))]
        number = _int(item.get("overnumber"))
        overs.append({
            "over": (number + 1) if number is not None else None,
            "balls": [{"t": t, "k": k} for t, _, k in balls],
            "runs": sum(r for _, r, _ in balls),
            "wickets": sum(1 for _, _, k in balls if k == "wicket"),
        })
    return overs


def _commentary(ctx, extra_balls=()):
    seen, rows = set(), []
    for ball in list(ctx.balls_raw()) + [b for b in extra_balls if isinstance(b, dict)]:
        marker = str(ball.get("key") or f"{ball.get('innings')}:{ball.get('overs')}:{ball.get('comment')}")
        if marker in seen:
            continue
        seen.add(marker)
        overs = ball.get("overs")
        label, runs, kind = _ball_token(ball.get("repr"), ball)
        over_no = _int(overs[0]) if isinstance(overs, (list, tuple)) and overs else None
        rows.append({
            "ball": _overs(overs) or str(ball.get("over_str") or ""),
            "over": (over_no + 1) if over_no is not None else None,
            "innings": ball.get("innings") or "",
            "text": _clean(ball.get("comment") or ball.get("commentary"), 320),
            "score": str(ball.get("display_score") or "").replace(" overs", " ov"),
            "t": label,
            "k": kind,
            "runs": runs,
            "_sort": _num(ball.get("entry_time")) or _num(ball.get("updated_time")) or 0,
        })
    rows.sort(key=lambda r: r["_sort"], reverse=True)
    for row in rows:
        row.pop("_sort", None)
    return rows[:150]


def _toss_text(ctx):
    toss = _d(ctx.node.get("toss"))
    winner = toss.get("winner")
    if not winner:
        return ""
    team = ctx.team(str(winner)) if str(winner) in ctx.teams else {"name": _pretty_key(winner)}
    elected = str(toss.get("elected") or "").lower()
    choice = "bat" if elected.startswith("bat") else "bowl" if elected in ("bowl", "field", "bowling", "fielding") else elected
    return f"{team['name']} won the toss and chose to {choice}" if choice else f"{team['name']} won the toss"


def _people(value, ctx):
    if isinstance(value, str):
        return [ctx.name(value) if value in ctx.players else _clean(value, 60)]
    if isinstance(value, dict):
        name = value.get("name")
        if name:
            return [_clean(name, 60)]
        out = []
        for v in value.values():
            out.extend(_people(v, ctx))
        return out
    if isinstance(value, list):
        out = []
        for v in value:
            out.extend(_people(v, ctx))
        return out
    return []


def _officials(ctx):
    raw = ctx.node.get("umpires")
    rows = []
    if isinstance(raw, dict):
        labels = {"match_umpires": "Umpires", "tv_umpires": "TV umpire", "third_umpire": "TV umpire", "reserve_umpires": "Reserve umpire", "match_referee": "Match referee", "referee": "Match referee"}
        for key, value in raw.items():
            names = [n for n in _people(value, ctx) if n]
            if names:
                rows.append([labels.get(key, _pretty_key(key)), ", ".join(dict.fromkeys(names))])
    elif isinstance(raw, list):
        names = [n for n in _people(raw, ctx) if n]
        if names:
            rows.append(["Umpires", ", ".join(dict.fromkeys(names))])
    return rows


def _squads(ctx):
    out = []
    for side in ("a", "b"):
        if side not in ctx.teams:
            continue
        team = _d(ctx.squad.get(side))
        xi = [str(k) for k in _l(team.get("playing_xi"))]
        allp = [str(k) for k in _l(team.get("player_keys"))]
        captain, keeper = str(team.get("captain") or ""), str(team.get("keeper") or "")

        def row(k):
            return {"name": ctx.name(k), "role": ctx.role(k), "c": k == captain, "wk": k == keeper}

        out.append({
            "team": ctx.team(side),
            "announced": bool(xi),
            "xi": [row(k) for k in (xi or allp)],
            "bench": [row(k) for k in allp if xi and k not in xi],
        })
    return out


def _win_probability(ctx, odds_payload):
    data = _d(_d(odds_payload).get("data")) or _d(odds_payload)
    match = _d(data.get("match"))
    pred = _d(_d(match.get("result_prediction")).get("automatic"))
    rows = []
    for item in _l(pred.get("percentage")):
        item = _d(item)
        side = ctx.side_for_team_key(item.get("team_key"))
        value = _num(item.get("value"))
        if side and value is not None:
            team = ctx.team(side)
            rows.append({"side": side, "name": team["name"], "code": team["code"], "pct": round(value, 1)})
    if len(rows) < 2:
        return None
    rows.sort(key=lambda r: r["side"])
    draw = _num(_d(_d(match.get("result_prediction_with_draw")).get("draw")).get("value"))
    return {"teams": rows, "draw": draw}


def _live_block(ctx, innings, winprob):
    live = ctx.live
    if not live:
        return None
    idx = live.get("innings")
    side = str(idx or "").partition("_")[0]
    score = _d(live.get("score"))
    runs, balls = _int(score.get("runs"), 0), _int(score.get("balls"), 0)
    crr = _num(score.get("run_rate")) if _num(score.get("run_rate")) is not None else _rate(runs, balls)
    target = _d(ctx.play.get("target"))
    required = _d(live.get("required_score"))
    t_runs = _int(_first(target.get("runs"), required.get("target")))
    need = _int(required.get("runs"))
    balls_left = _int(_first(required.get("balls"), required.get("balls_remaining")))
    if t_runs and need is None:
        need = max(t_runs - runs, 0)
    if t_runs and balls_left is None:
        total_balls = _int(target.get("balls"))
        if total_balls:
            balls_left = max(total_balls - balls, 0)
    rrr = _num(required.get("run_rate") or required.get("required_run_rate"))
    if rrr is None and need is not None and balls_left:
        rrr = _rate(need, balls_left)
    overs_cfg = [x for x in (_int(v) for v in _l(ctx.play.get("overs_per_innings"))) if x]
    max_overs = max(overs_cfg) if overs_cfg else None
    fmt = str(ctx.node.get("format") or "").lower()
    projected = []
    if not t_runs and max_overs and fmt != "test" and balls and crr:
        left = max(max_overs * 6 - balls, 0)
        for rate in sorted({round(crr, 1), round(crr) + 1.0, round(crr) + 2.0}):
            projected.append({"rate": rate, "score": int(round(runs + rate * left / 6.0))})
    recent = _d(live.get("recent_players"))

    def bat(item, strike):
        item = _d(item)
        st = _d(item.get("stats"))
        if not item.get("key"):
            return None
        r, b = _int(st.get("runs"), 0), _int(st.get("balls"), 0)
        return {"name": item.get("name") or ctx.name(item.get("key")), "r": r, "b": b, "4s": _int(st.get("fours"), 0), "6s": _int(st.get("sixes"), 0),
                "sr": _num(st.get("strike_rate")) if _num(st.get("strike_rate")) is not None else _sr(r, b), "strike": strike}

    def bowl(item):
        item = _d(item)
        st = _d(item.get("stats"))
        if not item.get("key"):
            return None
        bl = _int(st.get("balls"), 0)
        r = _int(st.get("runs"), 0)
        return {"name": item.get("name") or ctx.name(item.get("key")), "o": _overs(st.get("overs")) or f"{bl // 6}.{bl % 6}", "m": _int(st.get("maiden_overs"), 0), "r": r,
                "w": _int(st.get("wickets"), 0), "eco": _num(st.get("economy")) if _num(st.get("economy")) is not None else _rate(r, bl)}

    current = next((i for i in innings if i["index"] == idx), None)
    partnership = None
    last_wicket = None
    if current:
        active = [p for p in current["partnerships"] if p["active"]]
        partnership = active[-1] if active else None
        if current["fow"]:
            fw = current["fow"][-1]
            out_row = next((b for b in current["batting"] if b["name"] == fw["name"]), None)
            last_wicket = {"name": fw["name"], "score": fw["score"], "overs": fw["overs"],
                           "r": out_row["r"] if out_row else None, "b": out_row["b"] if out_row else None, "how": out_row["how"] if out_row else ""}
    batters = [x for x in (bat(recent.get("striker"), True), bat(recent.get("non_striker"), False)) if x]
    return {
        "innings": idx,
        "team": ctx.team(side) if side in ctx.teams else None,
        "runs": runs,
        "wickets": _int(score.get("wickets"), 0),
        "overs": _overs(score.get("overs")),
        "crr": crr,
        "target": t_runs,
        "need": need,
        "ballsLeft": balls_left,
        "rrr": rrr,
        "requiredText": _clean(required.get("title") or ""),
        "projected": projected,
        "batters": batters,
        "bowler": bowl(recent.get("bowler")),
        "prevBowler": bowl(recent.get("prev_over_bowler")),
        "partnership": partnership,
        "lastWicket": last_wicket,
        "recentOvers": _recent_overs(ctx),
        "lead": _clean(score.get("msg_lead_by") or ""),
        "trail": _clean(score.get("msg_trail_by") or ""),
        "matchBreak": _clean(live.get("match_break") or ""),
        "winProbability": winprob,
    }


def _result(ctx):
    result = _d(ctx.play.get("result"))
    pom = []
    for key in _l(result.get("pom")):
        pom.append(ctx.name(key))
    msg = _clean(result.get("msg") or result.get("result_str") or "")
    if not msg and ctx.node.get("winner") and str(ctx.node.get("winner")) in ctx.teams:
        msg = f"{ctx.team(str(ctx.node.get('winner')))['name']} won"
    return {"text": msg, "pom": pom}


def build_center(node, odds_payload=None, extra_balls=()):
    """Pure function: Roanuz match node (+ optional live odds) -> centre JSON."""
    ctx = _Match(node)
    innings = _innings(ctx)
    winprob = _win_probability(ctx, odds_payload) if odds_payload else None
    venue = _d(ctx.node.get("venue"))
    country = _d(venue.get("country"))
    tournament = _d(ctx.node.get("tournament"))
    status = str(ctx.node.get("status") or "").lower()
    weather = ctx.node.get("weather")
    if isinstance(weather, dict):
        weather = ", ".join(str(v) for v in weather.values() if isinstance(v, (str, int, float)) and str(v).strip())
    info = [
        ["Series", tournament.get("name")],
        ["Match", ctx.node.get("sub_title") or ctx.node.get("short_name")],
        ["Format", str(ctx.node.get("format") or "").upper()],
        ["Venue", venue.get("name")],
        ["City", ", ".join(x for x in (venue.get("city"), country.get("name")) if x)],
        ["Toss", _toss_text(ctx)],
    ]
    for label, value in _officials(ctx):
        info.append([label, value])
    if weather:
        info.append(["Weather", _clean(weather, 80)])
    result = _result(ctx)
    if result["pom"]:
        info.append(["Player of the match", ", ".join(result["pom"])])
    return {
        "version": VERSION,
        "key": ctx.node.get("key"),
        "title": ctx.node.get("title") or ctx.node.get("name"),
        "status": status,
        "playStatus": str(ctx.node.get("play_status") or ""),
        "isLive": status == "started" or str(ctx.node.get("play_status") or "").lower() == "in_play",
        "startAt": _num(ctx.node.get("start_at")),
        "format": str(ctx.node.get("format") or ""),
        "teams": [ctx.team(s) for s in ("a", "b") if s in ctx.teams],
        "tournament": {"key": tournament.get("key"), "name": tournament.get("name")},
        "toss": _toss_text(ctx),
        "result": result,
        "messages": [_clean(m, 200) for m in _l(ctx.node.get("messages")) if isinstance(m, str)][:3],
        "info": [[k, v] for k, v in info if v],
        "innings": innings,
        "live": _live_block(ctx, innings, winprob) if ctx.live else None,
        "commentary": _commentary(ctx, extra_balls),
        "squads": _squads(ctx),
    }


# ----------------------------------------------------------- points table ---

def build_points(payload):
    data = _d(_d(payload).get("data")) or _d(payload)
    names = {}

    def collect(node):
        if isinstance(node, dict):
            if node.get("key") and node.get("name") and ("code" in node or "alternate_name" in node):
                names[str(node["key"])] = (str(node["name"]), str(node.get("code") or ""))
            for v in node.values():
                collect(v)
        elif isinstance(node, list):
            for v in node:
                collect(v)

    collect(data)
    groups = []

    def team_row(item):
        team = item.get("team")
        key = item.get("team_key") or (team.get("key") if isinstance(team, dict) else team)
        name, code = names.get(str(key), (None, None))
        if isinstance(team, dict):
            name = name or team.get("name")
            code = code or team.get("code")
        stats = _d(item.get("stats")) or item
        return {
            "team": name or _pretty_key(key),
            "code": code or "",
            "p": _int(_first(stats.get("played"), stats.get("matches_played"), stats.get("matches")), 0),
            "w": _int(_first(stats.get("won"), stats.get("wins")), 0),
            "l": _int(_first(stats.get("lost"), stats.get("losses")), 0),
            "nr": _int(_first(stats.get("no_result"), stats.get("nr")), 0) + _int(stats.get("tied"), 0),
            "pts": _num(_first(stats.get("points"), stats.get("pts")), 0),
            "nrr": _num(_first(stats.get("net_run_rate"), stats.get("nrr"))),
            "pos": _int(_first(item.get("position"), item.get("rank"))),
        }

    def walk(node, title):
        if isinstance(node, dict):
            label = node.get("name") if isinstance(node.get("name"), str) else title
            for v in node.values():
                walk(v, label)
        elif isinstance(node, list):
            rows = [x for x in node if isinstance(x, dict) and (x.get("team_key") or x.get("team")) and any(k in (_d(x.get("stats")) or x) for k in ("points", "played", "matches_played", "won"))]
            if rows and len(rows) >= 2:
                table = [team_row(x) for x in rows]
                table.sort(key=lambda r: (r["pos"] if r["pos"] else 999, -(r["pts"] or 0), -(r["nrr"] or -99)))
                groups.append({"name": title or "Standings", "rows": table})
                return
            for v in node:
                walk(v, title)

    walk(data, "")
    tour = _d(data.get("tournament"))
    return {"tournament": tour.get("name") or "", "groups": groups[:8]}


# --------------------------------------------------------------- football ---

_FB_LIVE = {"first half", "second half", "half time", "halftime", "extra time", "break time", "penalties", "in progress", "live"}
_FB_DONE = {"finished", "finished after extra time", "finished after penalties", "full time", "ft", "aet", "after penalties"}


def build_football(rows):
    out = []
    for item in _l(rows):
        item = _d(item)
        state = _d(item.get("state"))
        desc = str(state.get("description") or "").strip()
        low = desc.lower()
        phase = "live" if low in _FB_LIVE or "half" in low or "extra" in low else "done" if low in _FB_DONE or low.startswith("finished") else "upcoming"
        if low in ("postponed", "cancelled", "canceled", "abandoned", "suspended", "interrupted"):
            phase = "other"
        score = _d(state.get("score"))
        current = score.get("current")
        home_goals = away_goals = None
        if isinstance(current, str) and "-" in current:
            left, _, right = current.partition("-")
            home_goals, away_goals = _int(left.strip()), _int(right.strip())
        elif isinstance(current, dict):
            home_goals, away_goals = _int(current.get("home")), _int(current.get("away"))
        home, away = _d(item.get("homeTeam")), _d(item.get("awayTeam"))
        league = _d(item.get("league"))
        out.append({
            "id": item.get("id"),
            "home": {"name": home.get("name") or "Home", "logo": home.get("logo") or ""},
            "away": {"name": away.get("name") or "Away", "logo": away.get("logo") or ""},
            "hg": home_goals,
            "ag": away_goals,
            "pens": _clean(score.get("penalties") or ""),
            "status": desc or "Scheduled",
            "clock": _int(state.get("clock")),
            "phase": phase,
            "league": league.get("name") or "",
            "leagueLogo": league.get("logo") or "",
            "country": _d(item.get("country")).get("name") or "",
            "start": item.get("startDate") or "",
        })
    order = {"live": 0, "upcoming": 1, "done": 2, "other": 3}
    out.sort(key=lambda m: (order.get(m["phase"], 9), str(m["start"]), m["league"]))
    return out[:80]


# ------------------------------------------------------------ runtime glue ---

class _Runtime:
    def __init__(self, runtime):
        self.runtime = runtime
        self.v23 = runtime.v23
        self.liveline = runtime.v23.liveline
        self.admin = runtime.v23.v20.admin

    def match_node(self, key):
        _payload, node = self.v23._match_payload(key)
        return node if isinstance(node, dict) else {}

    def odds(self, key):
        # Same path + TTL as the BHAV feed, so this is normally a cache hit.
        return _cached(f"mc:odds:{key}", ODDS_TTL, lambda: self.admin._roanuz_get(f"match/{key}/live-match-odds/", ttl=ODDS_TTL))

    def center(self, key):
        def load():
            node = self.match_node(key)
            if not node:
                raise RuntimeError("match not available")
            odds = None
            status = str(node.get("status") or "").lower()
            if status == "started":
                try:
                    odds = self.odds(key)
                except Exception:
                    odds = None
            return build_center(node, odds)
        return _cached(f"mc:center:{key}", CENTER_TTL, load, negative_ttl=8)

    def points(self, key):
        node = self.match_node(key)
        tkey = str(_d(node.get("tournament")).get("key") or "")
        if not tkey or not _KEY_RE.match(tkey):
            return {"tournament": "", "groups": []}
        payload = _cached(f"mc:points-raw:{tkey}", POINTS_TTL, lambda: self.admin._roanuz_get(f"tournament/{tkey}/points/", ttl=POINTS_TTL), negative_ttl=10 * 60)
        table = build_points(payload)
        table["tournament"] = table["tournament"] or _d(node.get("tournament")).get("name") or ""
        return table

    def football(self):
        today = datetime.now(_IST).date().isoformat()

        def load():
            rows = self.liveline._highlightly(
                "/football/matches",
                {"date": today, "timezone": "Asia/Kolkata", "limit": 100},
                ttl=FOOTBALL_TTL,
            )
            return build_football(rows)
        return _cached(f"mc:football:{today}", FOOTBALL_TTL, load, negative_ttl=NEGATIVE_TTL)


def _send(rt, handler, status, payload):
    rt.liveline._send_json(handler, status, payload)


def _handle(rt, handler, action, key):
    if action in ("center", "points") and (not key or not _KEY_RE.match(key)):
        _send(rt, handler, 400, {"ok": False, "error": "Invalid match key"})
        return
    if action == "center":
        if key.isdigit():
            # Highlightly-only fallback match: the page keeps its old panels.
            _send(rt, handler, 200, {"ok": True, "center": None, "reason": "fallback"})
            return
        try:
            _send(rt, handler, 200, {"ok": True, "center": rt.center(key)})
        except Exception as exc:
            logger.warning("Live Line match centre unavailable key=%s: %s", key, str(exc)[:160])
            _send(rt, handler, 200, {"ok": True, "center": None, "reason": "unavailable"})
        return
    if action == "points":
        try:
            _send(rt, handler, 200, {"ok": True, "points": rt.points(key) if not key.isdigit() else {"groups": []}})
        except Exception as exc:
            logger.info("Live Line points table unavailable key=%s: %s", key, str(exc)[:160])
            _send(rt, handler, 200, {"ok": True, "points": {"groups": []}})
        return
    if action == "football":
        try:
            _send(rt, handler, 200, {"ok": True, "matches": rt.football()})
        except Exception as exc:
            logger.warning("Live Line football feed unavailable: %s", str(exc)[:160])
            _send(rt, handler, 200, {"ok": True, "matches": [], "unavailable": True})
        return


_ACTIONS = {"center", "points", "football"}


def inject_page(page: str, brand: str) -> str:
    if "__LIVELINE_MATCH_CENTRE__" in page:
        return page
    from liveline_match_center_ui import page_assets
    css, js = page_assets(brand)
    page = page.replace("</style>", css + "\n</style>", 1)
    page = page.replace("</body>", js + "\n</body>", 1)
    return page


def install(runtime, brand: str = "ibetin") -> bool:
    """Install the match centre on the V40 runtime module. Never raises."""
    brand = "dura" if str(brand).lower().startswith("dura") else "ibetin"
    try:
        if getattr(runtime, "_liveline_match_centre_installed", False):
            return True
        rt = _Runtime(runtime)
        previous_api = rt.liveline._api

        def api(handler):
            try:
                q = parse_qs(urlparse(handler.path).query)
                action = (q.get("action") or [""])[0].strip().lower()
            except Exception:
                action = ""
            if action in _ACTIONS:
                key = (q.get("id") or q.get("matchId") or q.get("key") or [""])[0].strip()
                return _handle(rt, handler, action, key)
            return previous_api(handler)

        rt.liveline._api = api
        rt.v23.liveline._api = api

        base_public = runtime._page_v40_public
        base_visual = runtime._page_v40_visual_polish
        runtime._page_v40_public = lambda: inject_page(base_public(), brand)
        admin_page = lambda: inject_page(base_visual(), brand)  # noqa: E731
        rt.v23._page = admin_page
        rt.liveline._page = admin_page
        runtime._liveline_match_centre_installed = True
        runtime._liveline_match_centre_runtime = rt
        _self_test(runtime, brand)
        logger.info("Live Line Match Centre installed version=%s brand=%s actions=%s", VERSION, brand, sorted(_ACTIONS))
        return True
    except Exception as exc:
        logger.exception("Live Line Match Centre install failed; page keeps the previous UI: %s", exc)
        return False


_SELF_TEST_NODE = {
    "key": "selftest", "status": "started", "format": "t20", "play_status": "in_play",
    "teams": {"a": {"key": "ta", "name": "Team A", "code": "TA"}, "b": {"key": "tb", "name": "Team B", "code": "TB"}},
    "toss": {"winner": "a", "elected": "bowl"},
    "play": {"overs_per_innings": [20, 20], "innings_order": ["b_1"], "innings": {"b_1": {
        "index": "b_1", "overs": [2, 3], "score": {"runs": 21, "balls": 15, "run_rate": 8.4}, "wickets": 1,
        "extra_runs": {"extra": 2, "wide": 2}, "batting_order": ["p1", "p2", "p3"], "wicket_order": ["p1"],
        "partnerships": [{"player_a_key": "p1", "player_a_score": {"runs": 6, "balls": 5}, "player_b_key": "p2", "player_b_score": {"runs": 5, "balls": 4}, "score": {"runs": 12, "balls": 9}, "is_completed": True, "end_overs": [1, 3]},
                         {"player_a_key": "p3", "player_a_score": {"runs": 4, "balls": 3}, "player_b_key": "p2", "player_b_score": {"runs": 5, "balls": 3}, "score": {"runs": 9, "balls": 6}, "is_completed": False}]}},
        "live": {"innings": "b_1", "score": {"runs": 21, "balls": 15, "wickets": 1, "run_rate": 8.4, "overs": [2, 3]},
                 "recent_overs_repr": [{"overnumber": 1, "ball_repr": ["r1", "b4", "w", "e1,wd", "r0", "b6", "r2"]}],
                 "recent_players": {"striker": {"key": "p2", "name": "Player Two", "stats": {"runs": 10, "balls": 7}}}}},
}


def _self_test(runtime, brand):
    center = build_center(_SELF_TEST_NODE, {"data": {"match": {"result_prediction": {"automatic": {"percentage": [{"team_key": "ta", "value": 40}, {"team_key": "tb", "value": 60}]}}}}})
    page = runtime._page_v40_public()
    checks = {
        "scorecard": bool(center["innings"] and center["innings"][0]["batting"]),
        "fow": center["innings"][0]["fow"][0]["score"] == "12-1",
        "win_probability": bool(center["live"] and center["live"]["winProbability"]),
        "recent_overs": center["live"]["recentOvers"][0]["runs"] == 14,
        "page_assets": "__LIVELINE_MATCH_CENTRE__" in page,
        "bhav_kept": "LIVE BHAV" in page,
        "brand_theme": (f'data-mc-brand="{brand}"' in page) or (f"mcBrand='{brand}'" in page),
    }
    ok = all(checks.values())
    (logger.info if ok else logger.error)("Live Line Match Centre self-test %s checks=%s", "PASS" if ok else "FAILED", checks)
    return ok
