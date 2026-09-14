import html
import json
import os
import secrets
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

PORT = int(os.getenv("PORT", "8080"))
SKY_USERNAME = os.getenv("SKY_USERNAME", "").strip()
SKY_PASSWORD = os.getenv("SKY_PASSWORD", "").strip()
SKY_TEST_TOKEN = os.getenv("SKY_TEST_TOKEN", "").strip()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID", "").strip()
TEST_BASE_URL = os.getenv("TEST_BASE_URL", "").strip().rstrip("/")
HIGHLIGHTLY_API_KEY = os.getenv("HIGHLIGHTLY_API_KEY", "").strip()

# Public Live TV is intentionally separate from the private/admin Sky login.
# Public matches must be supplied as authorized URLs, for example:
# [{"title":"India vs Australia","url":"https://authorized.example/match"}]
SKY_PUBLIC_STATUS = os.getenv("SKY_PUBLIC_STATUS", "off").strip().lower()
SKY_PUBLIC_MATCHES_JSON = os.getenv("SKY_PUBLIC_MATCHES_JSON", "[]").strip()

HIGHLIGHTLY_API_BASE = "https://sports.highlightly.net"
APP_TIMEZONE = ZoneInfo("Asia/Dubai")
LIVE_CACHE_TTL_SECONDS = 45

CRICKET_LIVE_STATES = {
    "in play",
    "stumps",
    "lunch",
    "innings break",
    "drinks",
    "timeout",
    "tea",
    "match delayed",
}

FOOTBALL_LIVE_STATES = {
    "first half",
    "second half",
    "extra time",
    "break time",
    "half time",
    "penalties",
    "interrupted",
}

STATE = {
    "status": "starting",
    "message_sent": False,
    "handoff_count": 0,
    "live_gate": "unknown",
    "public_live_status": SKY_PUBLIC_STATUS,
}
LOCK = threading.Lock()
LIVE_CACHE = {
    "checked_at": 0.0,
    "status": "unknown",
    "count": 0,
}
LIVE_CACHE_LOCK = threading.Lock()


def set_state(**kwargs):
    with LOCK:
        STATE.update(kwargs)


def safe_ready():
    missing = [
        name for name, value in (
            ("SKY_USERNAME", SKY_USERNAME),
            ("SKY_PASSWORD", SKY_PASSWORD),
            ("SKY_TEST_TOKEN", SKY_TEST_TOKEN),
            ("BOT_TOKEN", BOT_TOKEN),
            ("ADMIN_USER_ID", ADMIN_USER_ID),
            ("TEST_BASE_URL", TEST_BASE_URL),
        ) if not value
    ]
    return missing


def send_test_message():
    missing = safe_ready()
    if missing:
        set_state(status="waiting_for_variables", missing_variables=missing)
        return

    open_url = TEST_BASE_URL + "/open?" + urllib.parse.urlencode({"key": SKY_TEST_TOKEN})
    payload = {
        "chat_id": ADMIN_USER_ID,
        "text": (
            "🔴 FANTZO LIVE · PRIVATE TEST\n\n"
            "Tap below to open the isolated Sky Live compatibility test inside Telegram.\n\n"
            "Public Fantzo uses the separate authorized /public screen."
        ),
        "reply_markup": {
            "inline_keyboard": [[{
                "text": "🔴 OPEN FANTZO LIVE TEST",
                "web_app": {"url": open_url}
            }]]
        }
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8", "replace"))
        if body.get("ok"):
            set_state(status="ready", message_sent=True)
        else:
            set_state(status="send_failed", error="Telegram API returned ok=false")
    except Exception as exc:
        set_state(status="send_failed", error=str(exc)[:300])


# -------------------------------------------------------------------------
# SAFE PUBLIC LIVE TV SCREEN
# -------------------------------------------------------------------------

def _safe_http_url(value: str) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    try:
        parsed = urllib.parse.urlparse(value)
    except Exception:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return value


def public_matches():
    try:
        payload = json.loads(SKY_PUBLIC_MATCHES_JSON or "[]")
    except Exception:
        payload = []

    if not isinstance(payload, list):
        return []

    clean = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = _safe_http_url(item.get("url"))
        subtitle = str(item.get("subtitle") or "").strip()
        if title and url:
            clean.append({
                "title": title[:120],
                "subtitle": subtitle[:160],
                "url": url,
            })
    return clean[:12]


def public_live_page():
    matches = public_matches() if SKY_PUBLIC_STATUS == "on" else []
    has_matches = bool(matches)

    if has_matches:
        cards = []
        for item in matches:
            title = html.escape(item["title"])
            subtitle = html.escape(item["subtitle"])
            url = html.escape(item["url"], quote=True)
            sub_html = f'<div class="match-sub">{subtitle}</div>' if subtitle else ""
            cards.append(
                f'<a class="match" href="{url}" target="_blank" rel="noopener noreferrer">'
                f'<div class="live-dot"></div>'
                f'<div class="match-copy"><div class="match-title">{title}</div>{sub_html}</div>'
                f'<div class="arrow">›</div>'
                f'</a>'
            )
        matches_html = "".join(cards)
        headline = "LIVE MATCHES"
        helper = "Choose a match below to continue."
        state_badge = "LIVE NOW"
    else:
        matches_html = (
            '<div class="empty-icon">😴</div>'
            '<div class="empty-title">No live matches right now</div>'
            '<div class="empty-text">There are currently no authorized live matches available. '
            'Please check again later.</div>'
            '<button class="retry" onclick="location.reload()">🔄 CHECK AGAIN</button>'
        )
        headline = "NO LIVE MATCHES"
        helper = "Live TV will appear here when an authorized match is available."
        state_badge = "OFF AIR"

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta http-equiv="Cache-Control" content="no-store, no-cache, must-revalidate">
<title>Fantzo Live</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
*{{box-sizing:border-box}}
html,body{{margin:0;min-height:100%;background:#050505;color:#fff;font-family:Arial,Helvetica,sans-serif}}
body{{min-height:100vh;padding:18px}}
.shell{{width:100%;max-width:460px;margin:0 auto}}
.hero{{min-height:245px;position:relative;display:flex;align-items:center;justify-content:center;overflow:hidden;background:linear-gradient(145deg,#151515 0%,#050505 48%,#111 100%);border:1px solid #292929;border-radius:22px}}
.hero:before,.hero:after{{content:"";position:absolute;width:250px;height:70px;background:rgba(255,255,255,.025);transform:rotate(-45deg)}}
.hero:before{{left:-80px;top:35px}}.hero:after{{right:-100px;bottom:35px}}
.logo{{position:relative;z-index:1;text-align:center;font-weight:900;letter-spacing:2px}}
.logo-top{{font-size:18px;color:#f4f4f4}}
.logo-sky{{font-size:43px;line-height:.92;margin:4px 0 7px;text-shadow:0 0 18px rgba(44,151,255,.18)}}
.logo-pro{{font-size:12px;color:#a9a9a9;letter-spacing:1px}}
.panel{{margin-top:16px;background:#111;border:1px solid #333;border-radius:20px;padding:18px;box-shadow:0 16px 45px rgba(0,0,0,.35)}}
.toprow{{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:8px}}
h1{{margin:0;font-size:21px;letter-spacing:.2px}}
.badge{{font-size:10px;font-weight:900;letter-spacing:.7px;padding:7px 9px;border-radius:999px;background:#191919;border:1px solid #333;color:#aaa}}
.helper{{margin:0 0 16px;color:#969696;font-size:13px;line-height:1.45}}
.match{{display:flex;align-items:center;gap:12px;text-decoration:none;color:#fff;background:#191919;border:1px solid #333;border-radius:15px;padding:15px 14px;margin-top:10px}}
.match:active{{transform:scale(.99)}}
.live-dot{{width:10px;height:10px;flex:0 0 10px;border-radius:50%;background:#ff334d;box-shadow:0 0 0 6px rgba(255,51,77,.1)}}
.match-copy{{flex:1;min-width:0}}
.match-title{{font-size:15px;font-weight:900;line-height:1.25}}
.match-sub{{font-size:11px;color:#989898;margin-top:4px;line-height:1.35}}
.arrow{{font-size:26px;color:#858585}}
.empty-icon{{text-align:center;font-size:46px;margin:18px 0 8px}}
.empty-title{{text-align:center;font-size:20px;font-weight:900}}
.empty-text{{text-align:center;color:#9d9d9d;font-size:14px;line-height:1.5;margin:10px auto 18px;max-width:330px}}
.retry{{display:block;width:100%;min-height:54px;border:0;border-radius:14px;background:#1687ff;color:#fff;font-size:15px;font-weight:900;cursor:pointer}}
.footer{{text-align:center;color:#5f5f5f;font-size:11px;margin:14px 0 4px;line-height:1.4}}
</style>
</head>
<body>
<div class="shell">
  <div class="hero">
    <div class="logo">
      <div class="logo-top">THE</div>
      <div class="logo-sky">SKY</div>
      <div class="logo-pro">LIVE PRO</div>
    </div>
  </div>
  <div class="panel">
    <div class="toprow">
      <h1>{headline}</h1>
      <div class="badge">{state_badge}</div>
    </div>
    <p class="helper">{helper}</p>
    {matches_html}
  </div>
  <div class="footer">Fantzo public Live TV · Authorized links only</div>
</div>
<script>
const tg = window.Telegram && window.Telegram.WebApp;
if (tg) {{ tg.ready(); tg.expand(); }}
</script>
</body>
</html>""".encode("utf-8")


# -------------------------------------------------------------------------
# PRIVATE/ADMIN LIVE STATUS GATE
# -------------------------------------------------------------------------

def _state_description(match):
    state = (match or {}).get("state") or {}
    if isinstance(state, dict):
        return str(state.get("description") or "").strip().casefold()
    return str(state or "").strip().casefold()


def _fetch_sport_matches(sport: str):
    today = datetime.now(APP_TIMEZONE).date().isoformat()
    params = urllib.parse.urlencode({
        "date": today,
        "timezone": "Asia/Dubai",
        "limit": 100,
    })
    req = urllib.request.Request(
        f"{HIGHLIGHTLY_API_BASE}/{sport}/matches?{params}",
        headers={
            "x-rapidapi-key": HIGHLIGHTLY_API_KEY,
            "User-Agent": "FantzoLiveGate/1.0",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read().decode("utf-8", "replace"))

    if isinstance(payload, dict) and "data" in payload:
        payload = payload["data"]

    return payload if isinstance(payload, list) else []


def live_gate_status(force: bool = False):
    """Return ('live'|'none'|'unavailable', count) for private/admin testing."""
    now = time.monotonic()

    with LIVE_CACHE_LOCK:
        if (
            not force
            and LIVE_CACHE["status"] in {"live", "none"}
            and now - float(LIVE_CACHE["checked_at"]) < LIVE_CACHE_TTL_SECONDS
        ):
            return LIVE_CACHE["status"], int(LIVE_CACHE["count"])

    if not HIGHLIGHTLY_API_KEY:
        set_state(live_gate="unavailable", live_gate_error="HIGHLIGHTLY_API_KEY missing")
        return "unavailable", 0

    failures = []
    live_count = 0

    for sport, live_states in (
        ("cricket", CRICKET_LIVE_STATES),
        ("football", FOOTBALL_LIVE_STATES),
    ):
        try:
            matches = _fetch_sport_matches(sport)
        except Exception as exc:
            failures.append(f"{sport}:{type(exc).__name__}")
            continue

        for match in matches:
            if isinstance(match, dict) and _state_description(match) in live_states:
                live_count += 1

    if live_count > 0:
        status = "live"
    elif failures:
        set_state(live_gate="unavailable", live_gate_error=",".join(failures)[:200])
        return "unavailable", 0
    else:
        status = "none"

    with LIVE_CACHE_LOCK:
        LIVE_CACHE["checked_at"] = now
        LIVE_CACHE["status"] = status
        LIVE_CACHE["count"] = live_count

    set_state(live_gate=status, live_match_count=live_count)
    return status, live_count


def gate_page(kind: str):
    if kind == "none":
        icon = "😴"
        title = "No live match right now"
        text = (
            "Live TV is paused so you do not enter an empty channel screen. "
            "Please check again when a cricket or football match is live."
        )
        badge = "NO LIVE MATCH"
    else:
        icon = "⚠️"
        title = "Live status unavailable"
        text = (
            "Fantzo cannot verify a live match at the moment, so Live TV has not been opened. "
            "Please try again shortly."
        )
        badge = "PLEASE TRY AGAIN"

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta http-equiv="Cache-Control" content="no-store, no-cache, must-revalidate">
<title>Fantzo Live</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
*{{box-sizing:border-box}}
html,body{{margin:0;min-height:100%;background:#07111f;color:#fff;font-family:Arial,sans-serif}}
body{{display:flex;align-items:center;justify-content:center;min-height:100vh;padding:22px}}
.card{{width:100%;max-width:440px;text-align:center;background:#0d1929;border:1px solid #1b2a40;border-radius:24px;padding:28px 22px}}
.badge{{display:inline-block;padding:8px 12px;border-radius:999px;background:#172235;color:#aeb9c9;font-size:12px;font-weight:800;letter-spacing:.5px;margin-bottom:20px}}
.icon{{font-size:44px;margin-bottom:12px}}
h1{{margin:0 0 12px;font-size:28px;line-height:1.1}}
p{{margin:0 auto 22px;max-width:350px;color:#aeb9c9;font-size:15px;line-height:1.55}}
button{{display:block;width:100%;min-height:58px;border:0;border-radius:15px;font-size:16px;font-weight:900;cursor:pointer;margin-top:10px}}
.retry{{background:#fff;color:#07111f}}
.back{{background:#172235;color:#fff;border:1px solid #263750}}
.small{{margin-top:18px;color:#65758b;font-size:11px}}
</style>
</head>
<body>
<div class="card">
  <div class="badge">{badge}</div>
  <div class="icon">{icon}</div>
  <h1>{title}</h1>
  <p>{text}</p>
  <button class="retry" onclick="location.reload()">🔄 CHECK AGAIN</button>
  <button class="back" onclick="closeFantzo()">← BACK TO FANTZO</button>
  <div class="small">Private/admin test gate.</div>
</div>
<script>
const tg = window.Telegram && window.Telegram.WebApp;
if (tg) {{ tg.ready(); tg.expand(); }}
function closeFantzo() {{
  if (tg && tg.close) {{ tg.close(); }}
  else if (history.length > 1) {{ history.back(); }}
}}
</script>
</body>
</html>""".encode("utf-8")


def login_page():
    user = html.escape(SKY_USERNAME, quote=True)
    password = html.escape(SKY_PASSWORD, quote=True)
    hwid = html.escape(secrets.token_urlsafe(15)[:20] + "_web", quote=True)
    key = html.escape(SKY_TEST_TOKEN, quote=True)
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta http-equiv="Cache-Control" content="no-store, no-cache, must-revalidate">
<title>Fantzo Live Test</title>
<style>
html,body{{margin:0;min-height:100%;background:#07111f;color:#fff;font-family:Arial,sans-serif}}
body{{display:flex;align-items:center;justify-content:center;min-height:100vh}}
.card{{box-sizing:border-box;width:100%;max-width:440px;padding:30px 22px;text-align:center}}
.badge{{display:inline-block;padding:8px 12px;border-radius:999px;background:#172235;font-size:12px;font-weight:800;letter-spacing:.5px;margin-bottom:20px}}
h1{{margin:0 0 10px;font-size:32px;line-height:1.05}}
.sub{{margin:0 auto 24px;max-width:340px;color:#aeb9c9;font-size:15px;line-height:1.5}}
.panel{{background:#0d1929;border:1px solid #1b2a40;border-radius:22px;padding:20px}}
button{{display:block;width:100%;min-height:66px;padding:18px 20px;border:0;border-radius:16px;background:#fff;color:#07111f;font-size:19px;font-weight:900;cursor:pointer;touch-action:manipulation;-webkit-tap-highlight-color:rgba(0,0,0,0)}}
.steps{{margin-top:16px;color:#8fa0b6;font-size:13px;line-height:1.5}}
.private{{margin-top:18px;color:#68788e;font-size:12px}}
</style>
</head>
<body>
<div class="card">
  <div class="badge">LIVE MATCH CONFIRMED</div>
  <h1>🔴 FANTZO LIVE · ADMIN</h1>
  <p class="sub">Private compatibility test. Open the live channel list and choose the match.</p>
  <div class="panel">
    <form action="/handoff?key={key}" method="post">
      <input type="hidden" name="username" value="{user}">
      <input type="hidden" name="password" value="{password}">
      <input type="hidden" name="HWID" value="{hwid}">
      <input type="hidden" name="submit" value="">
      <button type="submit">▶ OPEN LIVE CHANNELS</button>
    </form>
    <div class="steps">Private/admin test only.</div>
  </div>
  <div class="private">Public users never use this route.</div>
</div>
</body>
</html>""".encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def _send_common(self, body: bytes, content_type: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _send_html(self, body: bytes, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/health":
            self._send_common(b"ok", "text/plain")
            return

        if parsed.path == "/status":
            with LOCK:
                data = dict(STATE)
            data["public_live_status"] = SKY_PUBLIC_STATUS
            data["public_match_count"] = len(public_matches()) if SKY_PUBLIC_STATUS == "on" else 0
            body = json.dumps(data, indent=2).encode("utf-8")
            self._send_common(body, "application/json")
            return

        if parsed.path == "/public":
            self._send_html(public_live_page())
            return

        if parsed.path == "/open":
            key = urllib.parse.parse_qs(parsed.query).get("key", [""])[0]
            if not SKY_TEST_TOKEN or not secrets.compare_digest(key, SKY_TEST_TOKEN):
                self._send_common(b"Not found", "text/plain", 404)
                return
            if not SKY_USERNAME or not SKY_PASSWORD:
                self._send_common(b"Test credentials are not configured", "text/plain", 503)
                return

            gate, _ = live_gate_status()
            if gate == "none":
                self._send_html(gate_page("none"))
                return
            if gate != "live":
                self._send_html(gate_page("unavailable"))
                return

            self._send_html(login_page())
            return

        self._send_common(b"Fantzo Live", "text/plain")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/handoff":
            self._send_common(b"Not found", "text/plain", 404)
            return

        key = urllib.parse.parse_qs(parsed.query).get("key", [""])[0]
        if not SKY_TEST_TOKEN or not secrets.compare_digest(key, SKY_TEST_TOKEN):
            self._send_common(b"Not found", "text/plain", 404)
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0 or length > 16384:
            self._send_common(b"Invalid handoff", "text/plain", 400)
            return

        gate, _ = live_gate_status(force=True)
        if gate == "none":
            self._send_html(gate_page("none"))
            return
        if gate != "live":
            self._send_html(gate_page("unavailable"))
            return

        with LOCK:
            STATE["handoff_count"] = int(STATE.get("handoff_count", 0)) + 1
            STATE["status"] = "handoff_redirected"

        self.send_response(307)
        self.send_header("Location", "https://skylivepro.com/")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        return


threading.Thread(target=send_test_message, daemon=True).start()
ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
