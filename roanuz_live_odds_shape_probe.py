import json
import os
from collections import deque
import httpx

BASE = "https://api.sports.roanuz.com/v5"
PROJECT = os.getenv("ROANUZ_PROJECT_KEY", "").strip()
API_KEY = os.getenv("ROANUZ_API_KEY", "").strip()

if not PROJECT or not API_KEY:
    raise SystemExit("Missing Roanuz credentials")


def unwrap(payload):
    return payload.get("data") if isinstance(payload, dict) and "data" in payload else payload


def collect_matches(obj):
    out, seen = [], set(); q = deque([obj])
    while q:
        node = q.popleft()
        if isinstance(node, dict):
            key = node.get("key") or node.get("match_key") or node.get("matchKey")
            if key and key not in seen and (node.get("teams") is not None or node.get("play_status") is not None or node.get("status") is not None):
                seen.add(key); out.append(node)
            q.extend(v for v in node.values() if isinstance(v, (dict, list)))
        elif isinstance(node, list):
            q.extend(x for x in node if isinstance(x, (dict, list)))
    return out


def status_of(node):
    if not isinstance(node, dict): return ""
    vals = [node.get("play_status"), node.get("playStatus"), node.get("status"), node.get("state")]
    return " | ".join(str(v) for v in vals if v not in (None, "", {}, []))


def exact_live(text):
    vals = {x.strip().casefold() for x in str(text or "").replace("|", "\n").splitlines() if x.strip()}
    return bool(vals & {"live","inplay","in play","in_progress","in progress","ongoing","started","playing","play","innings break","drinks","lunch","tea","stumps"})


def safe_shape(obj, depth=0):
    if depth > 4:
        return "..."
    if isinstance(obj, dict):
        out = {}
        for k, v in list(obj.items())[:40]:
            if str(k).casefold() in {"token", "rs-token", "api_key", "apikey"}:
                continue
            out[k] = safe_shape(v, depth+1)
        return out
    if isinstance(obj, list):
        return [safe_shape(v, depth+1) for v in obj[:3]]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(type(obj).__name__)

with httpx.Client(timeout=25.0, follow_redirects=True, headers={"Accept":"application/json"}) as client:
    ar = client.post(f"{BASE}/core/{PROJECT}/auth/", json={"api_key": API_KEY})
    auth = ar.json(); data = auth.get("data") if isinstance(auth, dict) else None
    token = data.get("token") if isinstance(data, dict) else None
    print("AUTH", ar.status_code, bool(token))
    if not token: raise SystemExit(2)
    headers = {"rs-token": str(token), "Accept":"application/json"}
    fr = client.get(f"{BASE}/cricket/{PROJECT}/featured-matches-2/", headers=headers)
    candidates = collect_matches(unwrap(fr.json()))
    picked = None
    for c in candidates:
        st = status_of(c)
        if exact_live(st):
            picked = c; break
    if not picked:
        print("NO_LIVE_MATCH"); raise SystemExit(0)
    key = str(picked.get("key") or picked.get("match_key") or picked.get("matchKey"))
    print("MATCH", key, status_of(picked), picked.get("name") or picked.get("title") or "")
    rr = client.get(f"{BASE}/cricket/{PROJECT}/match/{key}/live-match-odds/", headers=headers)
    print("HTTP", rr.status_code)
    body = rr.json()
    print("ODDS_SHAPE", json.dumps(safe_shape(body), ensure_ascii=True)[:12000])
