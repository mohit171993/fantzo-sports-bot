import json
import os
from datetime import date

import httpx

API_KEY = os.getenv("HIGHLIGHTLY_API_KEY", "").strip()
if not API_KEY:
    raise RuntimeError("HIGHLIGHTLY_API_KEY missing")

TODAY = date(2026, 9, 17).isoformat()
DIRECT = "https://sports.highlightly.net"
RAPID = "https://sport-highlights-api.p.rapidapi.com"

common = {
    "x-rapidapi-key": API_KEY,
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 IBETIN Highlightly Odds Probe/1.0",
}


def summarize_payload(payload):
    out = {"type": type(payload).__name__}
    if isinstance(payload, dict):
        out["keys"] = list(payload.keys())[:12]
        plan = payload.get("plan")
        if isinstance(plan, dict):
            out["plan"] = {
                "tier": plan.get("tier"),
                "message": plan.get("message"),
            }
        elif plan is not None:
            out["plan"] = str(plan)[:200]
        data = payload.get("data")
        if isinstance(data, list):
            out["data_count"] = len(data)
            bookmakers = []
            markets = []
            for row in data[:5]:
                if not isinstance(row, dict):
                    continue
                odds = row.get("odds")
                if isinstance(odds, list):
                    for o in odds[:10]:
                        if not isinstance(o, dict):
                            continue
                        bn = o.get("bookmakerName")
                        mk = o.get("market")
                        if bn and bn not in bookmakers:
                            bookmakers.append(str(bn))
                        if mk and mk not in markets:
                            markets.append(str(mk))
                bn = row.get("bookmakerName")
                mk = row.get("market")
                if bn and bn not in bookmakers:
                    bookmakers.append(str(bn))
                if mk and mk not in markets:
                    markets.append(str(mk))
            out["bookmakers"] = bookmakers[:10]
            out["markets"] = markets[:15]
            if data and isinstance(data[0], dict):
                sample = data[0]
                out["sample_keys"] = list(sample.keys())[:12]
                safe_sample = {}
                for k in ("matchId", "bookmakerId", "bookmakerName", "type", "market"):
                    if k in sample:
                        safe_sample[k] = sample.get(k)
                odds = sample.get("odds")
                if isinstance(odds, list) and odds:
                    safe_sample["odds_count"] = len(odds)
                    first = odds[0] if isinstance(odds[0], dict) else None
                    if first:
                        safe_sample["first_odds"] = {
                            k: first.get(k)
                            for k in ("bookmakerId", "bookmakerName", "type", "market")
                            if k in first
                        }
                        vals = first.get("values")
                        if isinstance(vals, list):
                            safe_sample["first_values"] = vals[:3]
                out["sample"] = safe_sample
        elif isinstance(data, dict):
            out["data_keys"] = list(data.keys())[:12]
        for key in ("message", "msg", "error"):
            if key in payload and payload.get(key) is not None:
                val = payload.get(key)
                out[key] = str(val)[:300]
    return out


def request(label, base, path, params, rapid=False):
    headers = dict(common)
    if rapid:
        headers["x-rapidapi-host"] = "sport-highlights-api.p.rapidapi.com"
    url = base + path
    try:
        r = httpx.get(url, params=params, headers=headers, timeout=20.0, follow_redirects=True)
        ct = r.headers.get("content-type", "")
        try:
            payload = r.json() if "json" in ct.lower() else {"raw": r.text[:500]}
        except Exception:
            payload = {"raw": r.text[:500]}
        print("PROBE", json.dumps({
            "label": label,
            "url": url,
            "params": params,
            "http": r.status_code,
            "content_type": ct,
            "summary": summarize_payload(payload),
        }, ensure_ascii=False))
        return r.status_code, payload
    except Exception as exc:
        print("PROBE", json.dumps({
            "label": label,
            "url": url,
            "params": params,
            "http": 0,
            "error": f"{type(exc).__name__}: {exc}",
        }, ensure_ascii=False))
        return 0, None


# Verify ordinary cricket data and obtain a real match ID.
match_status, match_payload = request(
    "matches_direct",
    DIRECT,
    "/cricket/matches",
    {"date": TODAY, "timezone": "Asia/Dubai", "limit": 5, "offset": 0},
)

match_id = None
if isinstance(match_payload, dict):
    rows = match_payload.get("data")
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict) and row.get("id") is not None:
                match_id = row.get("id")
                break
elif isinstance(match_payload, list):
    for row in match_payload:
        if isinstance(row, dict) and row.get("id") is not None:
            match_id = row.get("id")
            break
print("MATCH_ID_PRESENT", bool(match_id))

# Date-scoped odds is enough to reveal plan access even if a particular match has no odds.
for odds_type in ("prematch", "live"):
    params = {
        "date": TODAY,
        "timezone": "Asia/Dubai",
        "oddsType": odds_type,
        "limit": 5,
        "offset": 0,
    }
    request(f"cricket_odds_direct_{odds_type}", DIRECT, "/cricket/odds", params)
    request(f"cricket_odds_rapid_{odds_type}", RAPID, "/cricket/odds", params, rapid=True)

# Match-scoped probe as recommended by Highlightly docs.
if match_id is not None:
    for odds_type in ("prematch", "live"):
        params = {"matchId": match_id, "oddsType": odds_type, "limit": 5, "offset": 0}
        request(f"match_odds_direct_{odds_type}", DIRECT, "/cricket/odds", params)
        request(f"match_odds_rapid_{odds_type}", RAPID, "/cricket/odds", params, rapid=True)
