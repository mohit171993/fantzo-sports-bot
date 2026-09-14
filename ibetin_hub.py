import logging
import os
from html import escape
from urllib.parse import parse_qs, quote, urlparse

from telegram import InlineKeyboardButton, WebAppInfo

logger = logging.getLogger(__name__)
HUB_PATH = "/hub"


def _public_base_url() -> str:
    value = (
        os.getenv("TRACKING_BASE_URL", "").strip()
        or os.getenv("RAILWAY_STATIC_URL", "").strip()
        or os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
    )
    if not value:
        value = "https://ibetin-app-production.up.railway.app"
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    return value.rstrip("/")


def hub_url(section: str = "home") -> str:
    section = (section or "home").strip().lower()
    return f"{_public_base_url()}{HUB_PATH}?section={quote(section, safe='')}"


def webapp_button(label: str, section: str = "home") -> InlineKeyboardButton:
    return InlineKeyboardButton(label, web_app=WebAppInfo(url=hub_url(section)))


def _section_copy(section: str) -> tuple[str, str, str]:
    data = {
        "home": (
            "IBETIN Mini App",
            "Everything opens inside Telegram.",
            "Use the bot menu to jump directly to Sports, Live, News, Games, Results, Payments, Support and utilities.",
        ),
        "alerts": (
            "Match Alerts",
            "Control your IBETIN sports notification preference.",
            "This Mini App screen keeps your alert preference on this device. Bot-side match alerts will continue to use your existing Telegram subscription until the next alert-sync upgrade.",
        ),
        "settings": (
            "Settings",
            "Choose how the IBETIN Mini App behaves on this device.",
            "Language and compact-view preferences are stored locally in Telegram's WebView.",
        ),
    }
    return data.get(section, data["home"])


def _page(section: str) -> str:
    title, subtitle, body = _section_copy(section)
    section_js = escape(section, quote=True)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta http-equiv="Cache-Control" content="no-store, no-cache, must-revalidate">
<title>{escape(title)}</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
*{{box-sizing:border-box}}html,body{{margin:0;background:#07101c;color:#f7f9fc;font-family:Arial,Helvetica,sans-serif}}
.wrap{{max-width:720px;margin:0 auto;padding:16px 14px 28px}}
.top{{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}}
.brand{{font-weight:900;letter-spacing:.5px}}.badge{{font-size:11px;color:#9fb0c4;border:1px solid #24364b;border-radius:999px;padding:6px 9px}}
.hero{{background:#0d1928;border:1px solid #203149;border-radius:20px;padding:18px;margin-bottom:14px}}
h1{{font-size:25px;margin:0 0 6px}}p{{color:#aebdce;line-height:1.5;margin:0}}
.card{{background:#0b1624;border:1px solid #1d2d41;border-radius:16px;padding:15px;margin-top:12px}}
label{{display:flex;align-items:center;justify-content:space-between;gap:12px;font-weight:800}}
.switch{{width:54px;height:30px;accent-color:#fff}}
select{{width:100%;margin-top:10px;padding:13px;border-radius:12px;background:#101e2f;color:#fff;border:1px solid #2a3d55;font-size:16px}}
.note{{font-size:12px;color:#8094aa;margin-top:10px}}
.home{{display:block;text-align:center;margin-top:16px;padding:14px;border-radius:14px;background:#fff;color:#07101c;text-decoration:none;font-weight:900}}
</style>
</head>
<body>
<div class="wrap">
  <div class="top"><div class="brand">IBETIN</div><div class="badge">MINI APP</div></div>
  <div class="hero"><h1>{escape(title)}</h1><p>{escape(subtitle)}</p></div>
  <div class="card"><p>{escape(body)}</p></div>
  <div id="controls"></div>
  <a class="home" href="{HUB_PATH}?section=home">IBETIN MINI APP HOME</a>
</div>
<script>
const tg = window.Telegram && window.Telegram.WebApp;
if (tg) {{ tg.ready(); tg.expand(); }}
const section = {section_js!r};
const controls = document.getElementById('controls');
if (section === 'alerts') {{
  const enabled = localStorage.getItem('ibetin_alerts') !== 'off';
  controls.innerHTML = `<div class="card"><label>Sports alerts <input id="alerts" class="switch" type="checkbox" ${{enabled ? 'checked' : ''}}></label><div class="note">Preference saved on this device.</div></div>`;
  document.getElementById('alerts').addEventListener('change', e => localStorage.setItem('ibetin_alerts', e.target.checked ? 'on' : 'off'));
}}
if (section === 'settings') {{
  const lang = localStorage.getItem('ibetin_lang') || 'en';
  controls.innerHTML = `<div class="card"><label for="lang">Language</label><select id="lang"><option value="en">English</option><option value="hi">हिन्दी</option></select><div class="note">Mini App display preference.</div></div>`;
  const el = document.getElementById('lang'); el.value = lang; el.addEventListener('change', e => localStorage.setItem('ibetin_lang', e.target.value));
}}
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
        if parsed.path == HUB_PATH:
            section = parse_qs(parsed.query).get("section", ["home"])[0]
            try:
                _send_html(self, 200, _page(section))
            except Exception:
                logger.exception("Could not render IBETIN Mini App hub")
                _send_html(self, 500, "<h3>IBETIN Mini App could not load.</h3>")
            return
        previous_get(self)

    handler_cls.do_GET = patched_get
    logger.info("IBETIN utility Mini App route installed at %s", HUB_PATH)
