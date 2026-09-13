import html
import json
import os
import secrets
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.getenv("PORT", "8080"))
SKY_USERNAME = os.getenv("SKY_USERNAME", "").strip()
SKY_PASSWORD = os.getenv("SKY_PASSWORD", "").strip()
SKY_TEST_TOKEN = os.getenv("SKY_TEST_TOKEN", "").strip()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID", "").strip()
TEST_BASE_URL = os.getenv("TEST_BASE_URL", "").strip().rstrip("/")

STATE = {"status": "starting", "message_sent": False, "handoff_count": 0}
LOCK = threading.Lock()


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
            "Production Fantzo remains unchanged."
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
  <div class="badge">PRIVATE TEST MODE</div>
  <h1>🔴 FANTZO LIVE</h1>
  <p class="sub">Your Sky account is prepared. Open the live channel list inside Telegram, then choose the match you want to test.</p>
  <div class="panel">
    <form action="/handoff?key={key}" method="post">
      <input type="hidden" name="username" value="{user}">
      <input type="hidden" name="password" value="{password}">
      <input type="hidden" name="HWID" value="{hwid}">
      <input type="hidden" name="submit" value="">
      <button type="submit">▶ OPEN LIVE CHANNELS</button>
    </form>
    <div class="steps">1 tap here → Sky opens logged in → tap the match/channel.</div>
  </div>
  <div class="private">Isolated test only. Public Fantzo is unchanged.</div>
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

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/health":
            self._send_common(b"ok", "text/plain")
            return
        if parsed.path == "/status":
            with LOCK:
                body = json.dumps(STATE, indent=2).encode("utf-8")
            self._send_common(body, "application/json")
            return
        if parsed.path == "/open":
            key = urllib.parse.parse_qs(parsed.query).get("key", [""])[0]
            if not SKY_TEST_TOKEN or not secrets.compare_digest(key, SKY_TEST_TOKEN):
                self._send_common(b"Not found", "text/plain", 404)
                return
            if not SKY_USERNAME or not SKY_PASSWORD:
                self._send_common(b"Test credentials are not configured", "text/plain", 503)
                return
            body = login_page()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Robots-Tag", "noindex, nofollow")
            self.end_headers()
            self.wfile.write(body)
            return
        self._send_common(b"Fantzo Live private test", "text/plain")

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
