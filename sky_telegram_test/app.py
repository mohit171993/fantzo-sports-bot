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
            "🔴 FANTZO LIVE · ADMIN TEST\n\n"
            "Private Sky Live test inside Telegram.\n"
            "Tap below → open channels → choose the match.\n\n"
            "Public Fantzo is unchanged."
        ),
        "reply_markup": {
            "inline_keyboard": [[{
                "text": "🔴 OPEN FANTZO LIVE",
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
<title>Fantzo Live</title>
<style>
*{{box-sizing:border-box}}
html,body{{margin:0;min-height:100%;background:#050b14;color:#fff;font-family:Arial,Helvetica,sans-serif}}
body{{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:22px}}
.shell{{width:100%;max-width:460px}}
.hero{{position:relative;overflow:hidden;background:linear-gradient(180deg,#101b2b 0%,#091321 100%);border:1px solid #1f2d42;border-radius:28px;padding:26px 22px;box-shadow:0 24px 70px rgba(0,0,0,.35)}}
.glow{{position:absolute;width:220px;height:220px;border-radius:50%;background:rgba(255,45,61,.12);right:-90px;top:-105px;filter:blur(2px)}}
.top{{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:26px}}
.brand{{font-size:18px;font-weight:900;letter-spacing:.7px}}
.mode{{display:inline-flex;align-items:center;gap:7px;border:1px solid #2a394f;border-radius:999px;padding:8px 10px;color:#9dafc6;font-size:11px;font-weight:800;letter-spacing:.45px}}
.dot{{width:8px;height:8px;border-radius:50%;background:#ff2d3d;box-shadow:0 0 0 5px rgba(255,45,61,.12)}}
h1{{position:relative;margin:0;font-size:36px;line-height:1.02;letter-spacing:-1px}}
.lead{{position:relative;margin:12px 0 22px;color:#a9b7c9;font-size:15px;line-height:1.55}}
.status{{display:flex;gap:10px;margin:0 0 18px}}
.pill{{flex:1;background:#0a1422;border:1px solid #1e2b3e;border-radius:14px;padding:12px 10px;text-align:center}}
.pill strong{{display:block;font-size:13px;margin-bottom:3px}}
.pill span{{font-size:11px;color:#7f91a8}}
.cta{{background:#ff2d3d;border-radius:20px;padding:5px}}
button{{display:block;width:100%;min-height:68px;border:0;border-radius:16px;background:#fff;color:#07101c;font-size:19px;font-weight:900;letter-spacing:.1px;cursor:pointer;touch-action:manipulation;-webkit-tap-highlight-color:transparent}}
button:active{{transform:scale(.99)}}
.flow{{margin:16px 0 0;color:#8799b0;font-size:12px;text-align:center;line-height:1.5}}
.footer{{margin-top:13px;text-align:center;color:#53657c;font-size:11px;line-height:1.45}}
</style>
</head>
<body>
<div class="shell">
  <div class="hero">
    <div class="glow"></div>
    <div class="top">
      <div class="brand">FANTZO</div>
      <div class="mode"><span class="dot"></span> ADMIN TEST</div>
    </div>
    <h1>Live sports,<br>inside Telegram.</h1>
    <p class="lead">Sky is ready for this private compatibility test. Open the live channel list, then choose the match you want to watch.</p>
    <div class="status">
      <div class="pill"><strong>✓ Login ready</strong><span>No typing required</span></div>
      <div class="pill"><strong>✓ In Telegram</strong><span>WebView flow</span></div>
    </div>
    <div class="cta">
      <form action="/handoff?key={key}" method="post">
        <input type="hidden" name="username" value="{user}">
        <input type="hidden" name="password" value="{password}">
        <input type="hidden" name="HWID" value="{hwid}">
        <input type="hidden" name="submit" value="">
        <button type="submit">▶ OPEN LIVE CHANNELS</button>
      </form>
    </div>
    <div class="flow">One tap → Sky opens logged in → select a live channel.</div>
  </div>
  <div class="footer">Private/admin test only · Public Fantzo remains unchanged</div>
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
        self._send_common(b"Fantzo Live private admin test", "text/plain")

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
