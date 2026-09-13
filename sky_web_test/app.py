import json
import os
import secrets
import threading
import urllib.parse
import urllib.request
import http.cookiejar
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html.parser import HTMLParser

PORT = int(os.getenv("PORT", "8080"))
SKY_USERNAME = os.getenv("SKY_USERNAME", "").strip()
SKY_PASSWORD = os.getenv("SKY_PASSWORD", "").strip()
BASE = "https://skylivepro.com"

STATE = {"status": "starting", "target": "Sky Live Pro web login/player"}
LOCK = threading.Lock()


def update(**kwargs):
    with LOCK:
        STATE.update(kwargs)


class PageInspector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inputs = []
        self.scripts = []
        self.buttons = []
        self.links = []
        self._button_text = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "input":
            self.inputs.append({k: a.get(k) for k in ("id", "name", "type", "value")})
        elif tag == "script" and a.get("src"):
            self.scripts.append(a.get("src"))
        elif tag == "button":
            self._button_text = []
        elif tag == "a" and a.get("href"):
            self.links.append(a.get("href"))

    def handle_data(self, data):
        if self._button_text is not None:
            self._button_text.append(data)

    def handle_endtag(self, tag):
        if tag == "button" and self._button_text is not None:
            txt = " ".join("".join(self._button_text).split())
            if txt:
                self.buttons.append(txt[:120])
            self._button_text = None


def fetch(opener, url, data=None, headers=None, timeout=30):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with opener.open(req, timeout=timeout) as resp:
        return resp.geturl(), resp.status, resp.read(2_000_000).decode("utf-8", "replace"), dict(resp.headers)


def worker():
    if not SKY_USERNAME or not SKY_PASSWORD:
        update(status="waiting_for_credentials")
        return
    try:
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        ua = "Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36 Chrome/140 Mobile Safari/537.36"
        headers = {"User-Agent": ua, "Accept": "text/html,application/xhtml+xml"}

        # Prime cookies and verify the public login page.
        login_url, login_status, login_html, _ = fetch(opener, BASE + "/", headers=headers)
        has_login_form = 'name="username"' in login_html and 'name="password"' in login_html
        update(public_login_page_ok=bool(login_status == 200 and has_login_form))

        hwid = secrets.token_urlsafe(15)[:20] + "_web"
        form = urllib.parse.urlencode({
            "username": SKY_USERNAME,
            "password": SKY_PASSWORD,
            "HWID": hwid,
            "submit": "",
        }).encode()
        post_headers = dict(headers)
        post_headers["Content-Type"] = "application/x-www-form-urlencoded"
        post_headers["Origin"] = BASE
        post_headers["Referer"] = BASE + "/"
        final_url, status, html, resp_headers = fetch(opener, BASE + "/", data=form, headers=post_headers, timeout=45)

        parser = PageInspector()
        parser.feed(html)
        html_lower = html.lower()
        login_still_present = 'name="username"' in html_lower and 'name="password"' in html_lower
        player_markers = {
            "livekit_client": "livekit" in html_lower,
            "button_container": "button-container" in html_lower,
            "video_container": "video-container" in html_lower,
            "access_token_field": ('id="token"' in html_lower or 'name="token"' in html_lower),
            "flashphoner": "flashphoner" in html_lower,
        }
        authenticated = status == 200 and not login_still_present and any(player_markers.values())

        # Check the authenticated FP button metadata endpoint without exposing IDs/URLs.
        fp_count = None
        fp_endpoint_ok = False
        if authenticated:
            try:
                _, fp_status, fp_body, _ = fetch(
                    opener,
                    BASE + "/deps/getFPData.php",
                    data=b"",
                    headers={"User-Agent": ua, "Referer": final_url, "Content-Type": "application/json"},
                    timeout=20,
                )
                if fp_status == 200:
                    obj = json.loads(fp_body)
                    if isinstance(obj, list):
                        fp_count = len(obj)
                        fp_endpoint_ok = True
            except Exception:
                pass

        # Only safe metadata; never return cookies, tokens, username/password, HWID, or stream identifiers.
        update(
            status="done",
            authenticated=authenticated,
            http_status=status,
            final_path=urllib.parse.urlparse(final_url).path or "/",
            session_cookie_count=len(list(jar)),
            player_markers=player_markers,
            fp_metadata_endpoint_ok=fp_endpoint_ok,
            fp_button_count=fp_count,
            script_count=len(parser.scripts),
            button_count=len(parser.buttons),
        )
    except Exception as exc:
        update(status="failed", error=str(exc)[:500])


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/health"):
            payload = b"ok"; ctype = "text/plain"
        elif self.path.startswith("/status"):
            with LOCK:
                payload = json.dumps(STATE, indent=2).encode()
            ctype = "application/json"
        else:
            payload = b"Sky Live Pro private compatibility test"; ctype = "text/plain"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        return


threading.Thread(target=worker, daemon=True).start()
ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
