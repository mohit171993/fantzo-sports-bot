import json
import os
from collections import deque

import httpx

BASE = "https://api.sports.roanuz.com/v5"
PROJECT = os.getenv("ROANUZ_PROJECT_KEY", "").strip()
API_KEY = os.getenv("ROANUZ_API_KEY", "").strip()

if not PROJECT or not API_KEY:
    raise SystemExit("Missing Roanuz credentials")

LIVE_WORDS = {
    "live", "inplay", "in play", "in_progress", "in progress",
    "ongoing", "started", "playing", "play", "innings break",
    "drinks", "lunch", "tea", "stumps",
}


def unwrap(payload):
    return payload.get("data") if isinstance(payload, dict) and "data" in payload else payload


def err(payload):
    if not isinstance(payload, dict):
        return ""
    e = payload.get("error")
    if isinstance(e, dict):
        code = e.get("code") or ""
        msg = e.get("msg") or e.get("message") or ""
        return f"{code}:{msg}".strip(":")
    return str(e or "")


def collect_matches(obj):
    out, seen = [], set()
    q = deque([obj])
    while q:
        node = q.popleft()
        if isinstance(node, dict):
            key = node.get("key") or node.get("match_key") or node.get("matchKey")
            if key and key not in seen:
                seen.add(key)
                out.append(node)
            q.extend(v for v in node.values() if isinstance(v, (dict, list)))
        elif isinstance(node, list):
            q.extend(x for x in node if isinstance(x, (dict, list)))
    return out


def status_of(node):
    vals = [
        node.get("play_status"), node.get("playStatus"), node.get("status"),
        node.get("state"), node.get("match_status"), node.get("matchStatus"),
    ] if isinstance(node, dict) else []
    return " | ".join(str(v) for v in vals if v not in (None, "", {}, []))


def is_live(text):
    s = str(text or "").strip().casefold()
    if not s:
        return False
    return any(w in s for w in LIVE_WORDS)


def match_name(node):
    if not isinstance(node, dict):
        return ""
    return str(node.get("name") or node.get("title") or node.get("short_name") or node.get("shortName") or "")


with httpx.Client(timeout=25.0, follow_redirects=True, headers={"Accept": "application/json"}) as client:
    r = client.post(f"{BASE}/core/{PROJECT}/auth/", json={"api_key": API_KEY})
    auth = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    token = None
    if isinstance(auth, dict):
        data = auth.get("data") if isinstance(auth.get("data"), dict) else auth
        token = data.get("token") or data.get("access_token") or data.get("accessToken")
    print("AUTH", r.status_code, bool(token))
    if not token:
        raise SystemExit(2)

    headers = {"rs-token": str(token), "Accept": "application/json"}
    fr = client.get(f"{BASE}/cricket/{PROJECT}/featured-matches-2/", headers=headers)
    featured = fr.json() if fr.headers.get("content-type", "").startswith("application/json") else {}
    candidates = collect_matches(unwrap(featured))
    print("FEATURED", fr.status_code, "CANDIDATES", len(candidates))

    live = []
    for c in candidates:
        key = str(c.get("key") or c.get("match_key") or c.get("matchKey") or "")
        if not key:
            continue
        st = status_of(c)
        name = match_name(c)
        if not is_live(st):
            dr = client.get(f"{BASE}/cricket/{PROJECT}/match/{key}/", headers=headers)
            if 200 <= dr.status_code < 300:
                body = dr.json()
                data = unwrap(body)
                if isinstance(data, dict):
                    st = status_of(data)
                    name = match_name(data) or name
        print("MATCH_STATUS", key, json.dumps(st)[:180], "NAME", json.dumps(name)[:180])
        if is_live(st):
            live.append((key, st, name))

    print("LIVE_MATCHES", len(live))
    if not live:
        print("LIVE_ODDS_RESULT NO_CURRENT_LIVE_MATCH")
        raise SystemExit(0)

    for key, st, name in live[:5]:
        url = f"{BASE}/cricket/{PROJECT}/match/{key}/live-match-odds/"
        rr = client.get(url, headers=headers)
        try:
            body = rr.json()
        except Exception:
            body = {"raw": rr.text[:200]}
        data = unwrap(body)
        present = data not in (None, {}, [])
        print("LIVE_ODDS_RESULT", key, "HTTP", rr.status_code, "DATA", present, "ERROR", err(body), "NAME", json.dumps(name)[:180])
