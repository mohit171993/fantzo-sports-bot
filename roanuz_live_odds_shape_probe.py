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
    if isinstance(payload, dict) and "data" in payload:
        return payload.get("data")
    return payload


def compact(obj, limit=12000):
    try:
        text = json.dumps(obj, ensure_ascii=True, default=str, separators=(",", ":"))
    except Exception:
        text = str(obj)
    return text[:limit]


def collect_matches(obj):
    out, seen = [], set()
    q = deque([obj])
    while q:
        node = q.popleft()
        if isinstance(node, dict):
            key = node.get("key") or node.get("match_key") or node.get("matchKey")
            if key and key not in seen:
                seen.add(str(key))
                out.append(node)
            q.extend(v for v in node.values() if isinstance(v, (dict, list)))
        elif isinstance(node, list):
            q.extend(x for x in node if isinstance(x, (dict, list)))
    return out


def status_of(node):
    vals = []
    if isinstance(node, dict):
        for k in ("play_status", "playStatus", "status", "state", "match_status", "matchStatus"):
            v = node.get(k)
            if v not in (None, "", {}, []):
                vals.append(str(v))
    return " | ".join(vals)


def liveish(text):
    s = str(text or "").casefold().replace("_", " ")
    return any(x in s for x in ("live", "in play", "inplay", "playing", "started", "ongoing", "innings break"))


with httpx.Client(timeout=25.0, follow_redirects=True, headers={"Accept": "application/json"}) as client:
    ar = client.post(f"{BASE}/core/{PROJECT}/auth/", json={"api_key": API_KEY})
    try:
        auth_body = ar.json()
    except Exception:
        auth_body = {"raw": ar.text[:1000]}
    data = auth_body.get("data") if isinstance(auth_body, dict) else None
    token = data.get("token") if isinstance(data, dict) else None
    print("AUTH_HTTP", ar.status_code, "TOKEN", bool(token))
    if not token:
        print("AUTH_BODY", compact(auth_body, 4000))
        raise SystemExit(2)

    headers = {"rs-token": str(token), "Accept": "application/json"}
    fr = client.get(f"{BASE}/cricket/{PROJECT}/featured-matches-2/", headers=headers)
    try:
        featured_body = fr.json()
    except Exception:
        featured_body = {"raw": fr.text[:4000]}
    matches = collect_matches(unwrap(featured_body))
    print("FEATURED_HTTP", fr.status_code, "MATCHES", len(matches))

    picked = None
    for m in matches:
        if liveish(status_of(m)):
            picked = m
            break
    if not picked and matches:
        picked = matches[0]
    if not picked:
        print("NO_MATCH_AVAILABLE")
        raise SystemExit(0)

    key = str(picked.get("key") or picked.get("match_key") or picked.get("matchKey") or "")
    print("MATCH_KEY", key)
    print("MATCH_STATUS", status_of(picked))
    print("MATCH_NAME", picked.get("name") or picked.get("title") or "")

    endpoints = [
        ("LIVE_MATCH_ODDS", f"match/{key}/live-match-odds/"),
        ("SESSION_ODDS", f"match/{key}/session-odds/"),
    ]

    for label, path in endpoints:
        url = f"{BASE}/cricket/{PROJECT}/{path}"
        rr = client.get(url, headers=headers)
        try:
            body = rr.json()
        except Exception:
            body = {"raw": rr.text[:12000]}
        print("\n===", label, "===")
        print("HTTP", rr.status_code)
        print("BODY", compact(body, 16000))

print("\nPROBE_COMPLETE")
