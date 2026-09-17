import json
import os
from collections import deque

import httpx

BASE = "https://api.sports.roanuz.com/v5"
PROJECT = os.getenv("ROANUZ_PROJECT_KEY", "").strip()
API_KEY = os.getenv("ROANUZ_API_KEY", "").strip()

if not PROJECT or not API_KEY:
    raise SystemExit("Missing ROANUZ_PROJECT_KEY or ROANUZ_API_KEY")


def safe_keys(value):
    if isinstance(value, dict):
        return list(value.keys())[:30]
    if isinstance(value, list):
        if value and isinstance(value[0], dict):
            return list(value[0].keys())[:30]
        return [f"list[{len(value)}]"]
    return [type(value).__name__]


def unwrap(payload):
    if isinstance(payload, dict) and "data" in payload:
        return payload.get("data")
    return payload


def err_info(payload):
    if not isinstance(payload, dict):
        return ""
    err = payload.get("error")
    if isinstance(err, dict):
        return ":".join(str(x) for x in (err.get("code"), err.get("msg")) if x)
    if err:
        return str(err)
    return ""


def deep_find(obj, names, limit=25):
    names = {n.casefold() for n in names}
    out = []
    q = deque([obj])
    while q and len(out) < limit:
        node = q.popleft()
        if isinstance(node, dict):
            for k, v in node.items():
                if k.casefold() in names and v not in (None, "", [], {}):
                    out.append((k, v))
                if isinstance(v, (dict, list)):
                    q.append(v)
        elif isinstance(node, list):
            q.extend(x for x in node if isinstance(x, (dict, list)))
    return out


def first_scalar(obj, names):
    for _, v in deep_find(obj, names, limit=50):
        if isinstance(v, (str, int, float)) and str(v).strip():
            return str(v)
    return ""


def first_match_node(obj):
    q = deque([obj])
    while q:
        node = q.popleft()
        if isinstance(node, dict):
            key = node.get("key") or node.get("match_key") or node.get("matchKey")
            teams = node.get("teams")
            if key and (teams is not None or node.get("play_status") is not None or node.get("playStatus") is not None):
                return node
            q.extend(v for v in node.values() if isinstance(v, (dict, list)))
        elif isinstance(node, list):
            q.extend(x for x in node if isinstance(x, (dict, list)))
    return {}


def find_context_key(obj, candidates):
    wanted = {x.casefold() for x in candidates}
    q = deque([obj])
    while q:
        node = q.popleft()
        if isinstance(node, dict):
            for k, v in node.items():
                if k.casefold() in wanted and isinstance(v, (str, int, float)) and str(v).strip():
                    return str(v)
                if isinstance(v, (dict, list)):
                    q.append(v)
        elif isinstance(node, list):
            q.extend(x for x in node if isinstance(x, (dict, list)))
    return ""


def summarize_features(data):
    feature_names = {
        "scorecard": ["scorecard", "innings", "batting", "bowling"],
        "playing_xi": ["playing_xi", "playingXi", "playing11", "lineup", "lineups"],
        "squads_players": ["squad", "squads", "players", "player"],
        "partnerships": ["partnership", "partnerships"],
        "fall_of_wickets": ["fall_of_wickets", "fallOfWickets", "fow"],
        "recent_balls": ["recent_balls", "recentBalls", "balls", "ball"],
        "overs": ["overs", "over"],
        "run_rate": ["run_rate", "runRate", "required_run_rate", "requiredRunRate", "crr", "rrr"],
        "target": ["target", "target_runs", "targetRuns"],
        "venue": ["venue"],
        "toss": ["toss"],
        "player_of_match": ["player_of_match", "playerOfMatch", "man_of_match"],
        "winner": ["winner", "result"],
        "odds_prediction": ["odds", "betodds", "result_prediction", "prediction", "win_probability", "winProbability"],
    }
    present = []
    for label, keys in feature_names.items():
        if deep_find(data, keys, limit=1):
            present.append(label)
    return present


results = []

def record(label, path, status, payload, note=""):
    data = unwrap(payload)
    result = {
        "label": label,
        "path": path,
        "http": status,
        "ok": 200 <= status < 300,
        "data": data not in (None, {}, []),
        "keys": safe_keys(data),
        "features": summarize_features(data),
        "error": err_info(payload),
        "note": note,
    }
    results.append(result)
    print("PROBE_RESULT " + json.dumps(result, ensure_ascii=True))


with httpx.Client(timeout=25.0, follow_redirects=True, headers={"Accept": "application/json"}) as client:
    auth_url = f"{BASE}/core/{PROJECT}/auth/"
    r = client.post(auth_url, json={"api_key": API_KEY})
    try:
        auth_payload = r.json()
    except Exception:
        auth_payload = {"raw": r.text[:200]}
    auth_data = auth_payload.get("data") if isinstance(auth_payload, dict) else None
    token = auth_data.get("token") if isinstance(auth_data, dict) else None
    print("AUTH_STATUS", r.status_code, "TOKEN_PRESENT", bool(token))
    if not token:
        record("auth", "/core/{project}/auth/", r.status_code, auth_payload)
        raise SystemExit(2)

    headers = {"rs-token": str(token), "Accept": "application/json"}

    def get(label, path, note=""):
        url = f"{BASE}/cricket/{PROJECT}/{path.lstrip('/')}"
        try:
            resp = client.get(url, headers=headers)
            try:
                body = resp.json()
            except Exception:
                body = {"raw": resp.text[:200]}
            record(label, path, resp.status_code, body, note)
            return resp.status_code, body
        except Exception as exc:
            record(label, path, 0, {"error": {"msg": type(exc).__name__ + ": " + str(exc)}}, note)
            return 0, {}

    _, featured = get("featured_matches", "featured-matches-2/")
    _, fixtures = get("fixtures", "fixtures/")

    match_node = first_match_node(unwrap(featured))
    match_key = str(match_node.get("key") or match_node.get("match_key") or match_node.get("matchKey") or "") if match_node else ""
    if not match_key:
        match_key = first_scalar(unwrap(featured), ["match_key", "matchKey"])
    print("MATCH_KEY_PRESENT", bool(match_key))

    tournament_key = ""
    if match_node:
        tournament_key = find_context_key(match_node, ["tournament_key", "tournamentKey", "competition_key", "competitionKey"])
    if not tournament_key:
        tournament_key = find_context_key(unwrap(featured), ["tournament_key", "tournamentKey", "competition_key", "competitionKey"])
    print("TOURNAMENT_KEY_PRESENT", bool(tournament_key))

    if match_key:
        _, match_detail = get("match_detail", f"match/{match_key}/")
        get("ball_by_ball", f"match/{match_key}/ball-by-ball/")
        get("live_match_odds", f"match/{match_key}/live-match-odds/")
        get("pre_match_odds_match", f"match/{match_key}/pre-match-odds/")
        get("session_odds_match", f"match/{match_key}/session-odds/")
        get("worm_chart", f"match/{match_key}/worm/")
        get("manhattan_chart", f"match/{match_key}/manhattan/")
        get("run_rate_chart", f"match/{match_key}/run-rate/")
        get("match_stats", f"match/{match_key}/stats/")

        detail_data = unwrap(match_detail)
        if not tournament_key:
            tournament_key = find_context_key(detail_data, ["tournament_key", "tournamentKey", "competition_key", "competitionKey"])

        player_key = find_context_key(detail_data, ["player_key", "playerKey"])
        team_key = find_context_key(detail_data, ["team_key", "teamKey"])
        if player_key:
            get("player_profile", f"player/{player_key}/")
            get("player_stats", f"player/{player_key}/stats/")
        if team_key:
            get("team_profile", f"team/{team_key}/")
            get("team_stats", f"team/{team_key}/stats/")

    if tournament_key:
        get("tournament_detail", f"tournament/{tournament_key}/")
        get("tournament_points", f"tournament/{tournament_key}/points/")
        get("tournament_fixtures", f"tournament/{tournament_key}/fixtures/")
        get("tournament_stats", f"tournament/{tournament_key}/stats/")
        get("tournament_featured", f"tournament/{tournament_key}/featured-matches-2/")

    # Some Roanuz market feeds are exposed at project scope on newer deployments.
    get("live_odds_project_scope", "live-match-odds/")
    get("pre_match_odds_project_scope", "pre-match-odds/")
    get("session_odds_project_scope", "session-odds/")

print("CAPABILITY_SUMMARY_START")
for r in results:
    print(json.dumps(r, ensure_ascii=True))
print("CAPABILITY_SUMMARY_END")
