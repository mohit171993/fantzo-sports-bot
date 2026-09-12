import datetime
import os

import httpx

key = os.getenv("HIGHLIGHTLY_API_KEY")
if not key:
    raise RuntimeError("HIGHLIGHTLY_API_KEY is missing")

today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
response = httpx.get(
    "https://sports.highlightly.net/cricket/matches",
    headers={"x-rapidapi-key": key},
    params={"date": today, "timezone": "Asia/Dubai", "limit": 1},
    timeout=20,
)
print(f"Highlightly smoke status={response.status_code}")
response.raise_for_status()
payload = response.json()
data = payload.get("data", payload) if isinstance(payload, dict) else payload
count = len(data) if isinstance(data, list) else "ok"
print(f"Highlightly smoke OK items={count}")
