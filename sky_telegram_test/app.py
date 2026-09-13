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

STATE = {"status": "starting", "message_sent": False}
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
        "text": "🧪 FANTZO SKY TEST\n\nPrivate Telegram WebView compatibility test. Tap below to open Sky inside Telegram.\n\nThis does not change the public Fantzo menu.",
        "reply_markup": {
            "inline_keyboard": [[{
                "text": "🧪 OPEN SKY TEST",
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
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta http-equiv="Cache-Control" content="no-store, no-cache, must-revalidate">
<title>Fantzo Sky Test</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
body{{margin:0;background:#08111d;color:white;font-family:Arial,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;text-align:center}}
.card{{padding:28px;max-width:380px}}.spinner{{width:34px;height:34px;border:4px solid #355;border-top-color:white;border-radius:50%;margin:0 auto 18px;animation:s 1s linear infinite}}@keyframes s{{to{{transform:rotate(360deg)}}}}
.small{{opacity:.72;font-size:13px;line-height:1.45}}
</style>
</head>
<body>
<div class="card"><div class="spinner"></div><h3>Opening Sky test…</h3><div class="small">Private test mode. You will be handed directly to Sky Live Pro inside this WebView.</div></div>
<form id="skyLogin" action="https://skylivepro.com/" method="post" style="display:none">
<input name="username" value="{user}">
<input name="password" value="{password}">
<input name="HWID" value="{hwid}">
<input name="submit" value="">
</form>
<script>
try {{ if (window.Telegram && Telegram.WebApp) {{ Telegram.WebApp.ready(); Telegram.WebApp.expand(); }} }} catch(e) {{}}
setTimeout(function(){{ document.getElementById('skyLogin').submit(); }}, 700);
</script>
</body>
</html>""".encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/health":
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
        elif parsed.path == "/status":
            with LOCK:
                body = json.dumps(STATE, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
        elif parsed.path == "/open":
            key = urllib.parse.parse_qs(parsed.query).get("key", [""])[0]
            if not SKY_TEST_TOKEN or not secrets.compare_digest(key, SKY_TEST_TOKEN):
                body = b"Not found"
                self.send_response(404)
                self.send_header("Content-Type", "text/plain")
            elif not SKY_USERNAME or not SKY_PASSWORD:
                body = b"Test credentials are not configured"
                self.send_response(503)
                self.send_header("Content-Type", "text/plain")
            else:
                body = login_page()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("X-Robots-Tag", "noindex, nofollow")
        else:
            body = b"Fantzo Sky Telegram test"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        return


threading.Thread(target=send_test_message, daemon=True).start()
ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
