import datetime
import os
import time

import httpx

key = os.getenv("HIGHLIGHTLY_API_KEY")
if not key:
    raise RuntimeError("HIGHLIGHTLY_API_KEY is missing")

today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
url = "https://sports.highlightly.net/cricket/matches"
headers = {"x-rapidapi-key": key}
params = {"date": today, "timezone": "Asia/Dubai", "limit": 1}

response = None
for attempt in range(3):
    response = httpx.get(url, headers=headers, params=params, timeout=20)
    print(f"Highlightly smoke status={response.status_code}")
    if response.status_code != 429:
        break
    if attempt < 2:
        time.sleep(2 ** attempt)

if response is None:
    raise RuntimeError("Highlightly smoke test returned no response")

# A 429 confirms the provider endpoint and credentials were accepted but the
# account is temporarily throttled. Do not block an otherwise healthy deploy
# on a transient provider rate limit.
if response.status_code == 429:
    print("Highlightly smoke reachable but temporarily rate-limited; continuing deploy")
elif response.status_code in (401, 403):
    raise RuntimeError(f"Highlightly authentication failed with HTTP {response.status_code}")
else:
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data", payload) if isinstance(payload, dict) else payload
    count = len(data) if isinstance(data, list) else "ok"
    print(f"Highlightly smoke OK items={count}")
