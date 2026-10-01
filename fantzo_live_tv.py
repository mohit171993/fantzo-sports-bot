import logging
import os
from html import escape
from urllib.parse import urlparse

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

logger = logging.getLogger(__name__)

LIVE_TV_URL = os.getenv("FANTZO_LIVE_TV_URL", "https://skylivepro.com/").strip()
TRACKING_BASE_URL = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/")
LIVE_TV_MODE = os.getenv("LIVE_TV_MODE", "admin").strip().lower()
if LIVE_TV_MODE not in {"off", "admin", "public"}:
    LIVE_TV_MODE = "admin"
MINITV_PATH = "/minitv"


def minitv_url() -> str:
    """Return the public Fantzo MiniTV URL used by Telegram WebApp buttons."""
    if TRACKING_BASE_URL:
        return f"{TRACKING_BASE_URL}{MINITV_PATH}"
    return LIVE_TV_URL


def live_tv_button(label: str = "📺 Live TV") -> InlineKeyboardButton:
    return InlineKeyboardButton(label, web_app=WebAppInfo(url=minitv_url()))


def live_tv_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [live_tv_button("📺 OPEN LIVE TV")],
            [InlineKeyboardButton("⬅️ Back to Fantzo", callback_data="back")],
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
<title>Fantzo MiniTV</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700;800;900&family=Manrope:wght@400;500;600;700;800&display=swap');
*{{box-sizing:border-box}}
html,body{{margin:0;width:100%;height:100%;background:#0a0806;color:#f6ecd6;font-family:'Manrope','Inter',Arial,Helvetica,sans-serif;overflow:hidden}}
.shell{{height:100%;display:flex;flex-direction:column;background:#0a0806}}
.top{{position:relative;height:58px;display:flex;align-items:center;justify-content:space-between;padding:0 14px;flex:0 0 auto;background:radial-gradient(120% 160% at 0 0,rgba(226,184,90,.16),transparent 55%),linear-gradient(180deg,#16110a,#0b0806);box-shadow:0 10px 24px rgba(0,0,0,.55)}}
.top:after{{content:"";position:absolute;left:0;right:0;bottom:-1px;height:1px;background:linear-gradient(90deg,transparent,#a8792a 15%,#f5d27a 50%,#a8792a 85%,transparent)}}
.brand{{display:flex;align-items:center;gap:10px;font-size:15px;font-weight:900;letter-spacing:1.2px;font-family:'Cinzel','Times New Roman',serif;background:linear-gradient(180deg,#f5d27a,#e2b85a 55%,#a8792a);-webkit-background-clip:text;background-clip:text;color:transparent}}
.brand:before{{content:"F";display:grid;place-items:center;width:32px;height:32px;border-radius:10px;font:900 18px/1 'Cinzel','Times New Roman',serif;color:#1a1206;-webkit-text-fill-color:#1a1206;background:linear-gradient(145deg,#f5d27a,#e2b85a 40%,#a8792a 75%,#6d4c14);box-shadow:inset 0 1px 0 rgba(255,255,255,.55),0 4px 12px rgba(226,184,90,.3)}}
.badge{{display:inline-flex;align-items:center;gap:7px;font-size:10px;font-weight:800;letter-spacing:1.4px;color:#1a1206;background:linear-gradient(180deg,#f5d27a,#e2b85a 60%,#a8792a);border-radius:999px;padding:6px 11px;box-shadow:inset 0 1px 0 rgba(255,255,255,.5),0 0 12px rgba(226,184,90,.35)}}
.badge:before{{content:"";width:7px;height:7px;border-radius:50%;background:#c4271c;box-shadow:0 0 0 2px rgba(196,39,28,.25);animation:pulse 1.2s ease-in-out infinite}}
@keyframes pulse{{0%,100%{{opacity:1;transform:scale(1)}}50%{{opacity:.35;transform:scale(.65)}}}}
.frame-wrap{{position:relative;flex:1;min-height:0;background:radial-gradient(80% 50% at 50% 40%,rgba(226,184,90,.08),transparent 70%),#0a0806}}
iframe{{width:100%;height:100%;border:0;background:#0a0806}}
.fallback{{position:absolute;inset:0;display:none;align-items:center;justify-content:center;padding:24px;text-align:center;background:radial-gradient(90% 50% at 50% 30%,rgba(226,184,90,.14),transparent 70%),repeating-linear-gradient(45deg,rgba(255,255,255,.012) 0 2px,transparent 2px 7px),linear-gradient(180deg,#120e08,#0a0806)}}
.card{{position:relative;max-width:360px;width:100%;padding:28px 22px 22px;border-radius:22px;overflow:hidden;background:linear-gradient(160deg,#211a0f,#0f0b07 60%,#080604);box-shadow:inset 0 0 0 1px rgba(226,184,90,.42),0 22px 40px -16px rgba(0,0,0,.9)}}
.card:before{{content:"";position:absolute;inset:0 0 auto;height:2px;background:linear-gradient(90deg,#6d4c14,#a8792a 20%,#f5d27a 55%,#a8792a 85%,#6d4c14)}}
.card h2{{margin:0 0 10px;font-size:22px;font-family:'Cinzel','Times New Roman',serif;letter-spacing:.6px;color:#f5d27a}}
.card p{{margin:0;color:#cdbf9f;line-height:1.6;font-size:14px}}
.btn{{display:block;margin-top:20px;padding:15px 18px;border-radius:14px;background:linear-gradient(180deg,#f5d27a 0%,#e2b85a 50%,#a8792a 100%);color:#1a1206;text-decoration:none;font-weight:900;letter-spacing:1.2px;box-shadow:inset 0 1px 0 rgba(255,255,255,.55),0 10px 24px -8px rgba(226,184,90,.5)}}
</style>
</head>
<body>
<div class="shell">
  <div class="top"><div class="brand">FANTZO · MINITV</div><div class="badge">LIVE TV</div></div>
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
if (tg) {{ tg.ready(); tg.expand(); try {{ tg.setHeaderColor('#16110a'); tg.setBackgroundColor('#0a0806'); }} catch (e) {{}} }}
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
        path = urlparse(self.path).path
        if path == MINITV_PATH:
            if not is_public_enabled():
                _send_html(self, 503, "<h3>Fantzo Live TV is temporarily unavailable.</h3>")
                return
            try:
                _send_html(self, 200, _page())
            except Exception:
                logger.exception("Could not render Fantzo MiniTV")
                _send_html(self, 500, "<h3>Fantzo MiniTV could not load.</h3>")
            return
        previous_get(self)

    handler_cls.do_GET = patched_get
    logger.info("Fantzo MiniTV WebApp route installed at %s (mode=%s)", MINITV_PATH, LIVE_TV_MODE)
