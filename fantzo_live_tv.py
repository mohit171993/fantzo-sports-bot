import logging
import os
from html import escape
from urllib.parse import parse_qs, urlencode, urlparse

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

import ibetin_phone_verify as phone_verify
import ibetin_reports as reports

logger = logging.getLogger(__name__)

LIVE_TV_URL = os.getenv(
    "IBETIN_LIVE_TV_URL",
    os.getenv("FANTZO_LIVE_TV_URL", "https://skylivepro.com/"),
).strip()
TRACKING_BASE_URL = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/")
LIVE_TV_MODE = os.getenv("LIVE_TV_MODE", "admin").strip().lower()
if LIVE_TV_MODE not in {"off", "admin", "public"}:
    LIVE_TV_MODE = "admin"
MINITV_PATH = "/minitv"


def minitv_url(user_id: int = 0) -> str:
    """Return the IBETIN MiniTV URL, signed to a Telegram user when known."""
    base = f"{TRACKING_BASE_URL}{MINITV_PATH}" if TRACKING_BASE_URL else LIVE_TV_URL
    if user_id and TRACKING_BASE_URL:
        token = phone_verify.issue_access_token(int(user_id))
        return f"{base}?{urlencode({'viewer': token})}"
    return base


def live_tv_button(label: str = "📺 Live TV", user_id: int = 0) -> InlineKeyboardButton:
    return InlineKeyboardButton(label, web_app=WebAppInfo(url=minitv_url(user_id)))


def live_tv_keyboard(user_id: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [live_tv_button("📺 OPEN LIVE TV", user_id)],
            [InlineKeyboardButton("⬅️ Back to IBETIN", callback_data="back")],
        ]
    )


def is_public_enabled() -> bool:
    return LIVE_TV_MODE == "public" and bool(LIVE_TV_URL)


def is_enabled() -> bool:
    """Backward-compatible alias for public MiniTV availability."""
    return is_public_enabled()


def _page() -> str:
    target = escape(LIVE_TV_URL, quote=True)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta http-equiv="Cache-Control" content="no-store, no-cache, must-revalidate">
<title>IBETIN MiniTV</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
*{{box-sizing:border-box}}
html,body{{margin:0;width:100%;height:100%;background:#050b14;color:#fff;font-family:Arial,Helvetica,sans-serif;overflow:hidden}}
.shell{{height:100%;display:flex;flex-direction:column;background:#050b14}}
.top{{height:54px;display:flex;align-items:center;justify-content:space-between;padding:0 14px;background:#0b1320;border-bottom:1px solid #1b2a3d;flex:0 0 auto}}
.brand{{font-size:15px;font-weight:900;letter-spacing:.5px}}
.badge{{font-size:11px;font-weight:800;color:#8ea2bb;border:1px solid #27384e;border-radius:999px;padding:6px 9px}}
.frame-wrap{{position:relative;flex:1;min-height:0;background:#000}}
iframe{{width:100%;height:100%;border:0;background:#000}}
.fallback{{position:absolute;inset:0;display:none;align-items:center;justify-content:center;padding:24px;background:#07101c;text-align:center}}
.card{{max-width:360px}}
.card h2{{margin:0 0 10px;font-size:23px}}
.card p{{color:#9cadc2;line-height:1.5;font-size:14px}}
.btn{{display:block;margin-top:16px;padding:15px 18px;border-radius:14px;background:#fff;color:#07101c;text-decoration:none;font-weight:900}}
</style>
</head>
<body>
<div class="shell">
  <div class="top"><div class="brand">IBETIN · MINITV</div><div class="badge">LIVE TV</div></div>
  <div class="frame-wrap">
    <iframe id="sky" src="{target}" allow="autoplay; fullscreen; picture-in-picture" allowfullscreen referrerpolicy="no-referrer"></iframe>
    <div class="fallback" id="fallback">
      <div class="card">
        <h2>📺 Open Live TV</h2>
        <p>The provider did not load inside MiniTV. You can open the normal provider page and sign in with your own account.</p>
        <a class="btn" href="{target}" target="_blank" rel="noopener noreferrer">OPEN LIVE TV</a>
      </div>
    </div>
  </div>
</div>
<script>
const tg = window.Telegram && window.Telegram.WebApp;
if (tg) {{ tg.ready(); tg.expand(); }}
const frame = document.getElementById('sky');
const fallback = document.getElementById('fallback');
let loaded = false;
frame.addEventListener('load', () => {{ loaded = true; }});
setTimeout(() => {{ if (!loaded) fallback.style.display = 'flex'; }}, 7000);
</script>
</body>
</html>"""


def _send_html(handler, status: int, html: str) -> None:
    data = html.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
    handler.send_header("Pragma", "no-cache")
    handler.send_header("X-Robots-Tag", "noindex, nofollow")
    handler.end_headers()
    handler.wfile.write(data)


def install_on_tracking_handler(analytics_module) -> None:
    handler_cls = analytics_module.TrackingHandler
    previous_get = handler_cls.do_GET

    def patched_get(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == MINITV_PATH:
            if not is_public_enabled():
                _send_html(self, 503, "<h3>IBETIN Live TV is temporarily unavailable.</h3>")
                return
            try:
                viewer_token = (parse_qs(parsed.query).get("viewer") or [""])[0]
                viewer_id = phone_verify.verify_access_token(viewer_token) if viewer_token else 0
                if viewer_id:
                    reports.record_live_tv_open(viewer_id)
                _send_html(self, 200, _page())
            except Exception:
                logger.exception("Could not render IBETIN MiniTV")
                _send_html(self, 500, "<h3>IBETIN MiniTV could not load.</h3>")
            return
        previous_get(self)

    handler_cls.do_GET = patched_get
    logger.info("IBETIN MiniTV WebApp route installed at %s (mode=%s)", MINITV_PATH, LIVE_TV_MODE)
