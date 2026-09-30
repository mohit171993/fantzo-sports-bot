import asyncio
import hashlib
import hmac
import json
import logging
import os
from html import escape
from urllib.parse import parse_qs, quote, urlencode, urlparse

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import CommandHandler

import bot as core
import fantzo_reminders as reminders
import ibetin_start
import ibetin_ui_v2

logger = logging.getLogger(__name__)

ibetin_ui_v2.install(ibetin_start)

# The light v2 router intentionally owns /hub, but its home page must never
# become an intermediate menu for JOIN IBETIN.  Home should hand off straight
# to the real IBETIN app while Alerts/Settings keep their Telegram-native pages.
_original_hub_page = ibetin_start.hub._page


def _hub_page_without_home_shell(section: str):
    requested = (section or "home").strip().lower()
    if requested == "home":
        target = json.dumps(ibetin_start.hub.IBETIN_HOME_URL)
        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta http-equiv="Cache-Control" content="no-store, no-cache, must-revalidate"><title>IBETIN</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>html,body{{margin:0;background:#fff;color:#172033;font-family:Arial,sans-serif}}main{{display:flex;min-height:70vh;align-items:center;justify-content:center;text-align:center;padding:24px}}.spin{{width:28px;height:28px;margin:16px auto 0;border:3px solid #e5e7eb;border-top-color:#172033;border-radius:50%;animation:s .7s linear infinite}}@keyframes s{{to{{transform:rotate(360deg)}}}}</style>
</head><body><main><div><b>IBETIN</b><div style="margin-top:8px;color:#64748b;font-size:13px">Opening IBETIN…</div><div class="spin"></div></div></main>
<script>const tg=window.Telegram&&window.Telegram.WebApp;if(tg){{try{{tg.ready();tg.expand();}}catch(e){{}}}}window.location.replace({target});</script></body></html>"""
    return _original_hub_page(requested)


ibetin_start.hub._page = _hub_page_without_home_shell
logger.info("IBETIN JOIN/home passthrough installed: home opens real IBETIN app")

# The production reminder now intentionally has two CTA types:
# - OPEN LIVE LINE / JOIN IBETIN = Telegram Mini App launchers
# - JOIN CHANNEL = normal Telegram channel URL
# Keep every existing navigation check, but allow only the three legacy
# self-test complaints caused by this intentional new channel button.
_original_navigation_self_test = ibetin_start.run_navigation_self_test


def _navigation_self_test_with_channel_cta():
    try:
        _original_navigation_self_test()
        return
    except RuntimeError as exc:
        prefix = "IBETIN navigation self-test FAILED: "
        message = str(exc)
        if not message.startswith(prefix):
            raise
        actual = set(message[len(prefix):].split(" | "))
        allowed = {
            "business-reminder: expected 1 launcher, got 3",
            "direct-reminder/📢 JOIN CHANNEL: not a web_app button",
            "direct-reminder/📢 JOIN CHANNEL: unexpected url button",
        }
        if actual != allowed:
            raise
        logger.info(
            "IBETIN navigation self-test PASS with JOIN CHANNEL CTA: "
            "JOIN IBETIN remains Mini App; channel remains Telegram URL"
        )


ibetin_start.run_navigation_self_test = _navigation_self_test_with_channel_cta

# =========================================================
# ADMIN-ONLY CRICKET MAZZA SCREEN MIRROR TRIAL
# =========================================================

MAZZA_PACKAGE = "com.crics.cricket11"
MAZZA_PLAY_URL = f"https://play.google.com/store/apps/details?id={MAZZA_PACKAGE}"
MAZZA_MIRROR_PATH = "/admin/mazza-mirror"
MAZZA_MIRROR_SOURCE = os.getenv("MAZZA_MIRROR_URL", "").strip()
MAZZA_BASE_URL = (
    os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/")
    or "https://ibetin-app-production.up.railway.app"
)


def _mazza_token() -> str:
    secret = os.getenv("BOT_TOKEN", "").strip()
    if not secret:
        return ""
    payload = f"ibetin-mazza-mirror:{core.ADMIN_USER_ID}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _mazza_admin_url() -> str:
    token = _mazza_token()
    if not token:
        return MAZZA_PLAY_URL
    return f"{MAZZA_BASE_URL}{MAZZA_MIRROR_PATH}?{urlencode({'t': token})}"


def _mazza_authorized(path: str) -> bool:
    expected = _mazza_token()
    supplied = (parse_qs(urlparse(path).query).get("t") or [""])[0]
    return bool(expected) and hmac.compare_digest(expected, supplied)


def _mazza_launch_intent() -> str:
    fallback = quote(MAZZA_PLAY_URL, safe="")
    return (
        "intent://launch#Intent;"
        "action=android.intent.action.MAIN;"
        "category=android.intent.category.LAUNCHER;"
        f"package={MAZZA_PACKAGE};"
        f"S.browser_fallback_url={fallback};"
        "end"
    )


def _mazza_mirror_page() -> str:
    source = MAZZA_MIRROR_SOURCE
    source_json = json.dumps(source)
    source_html = escape(source, quote=True)
    intent_html = escape(_mazza_launch_intent(), quote=True)
    play_html = escape(MAZZA_PLAY_URL, quote=True)

    remote_panel = ""
    if source:
        if source.lower().split("?", 1)[0].endswith((".mp4", ".m3u8")):
            remote_panel = (
                f'<video id="remote" class="mirror" src="{source_html}" '
                'controls autoplay muted playsinline></video>'
            )
        else:
            remote_panel = (
                f'<iframe id="remote" class="mirror" src="{source_html}" '
                'allow="autoplay; fullscreen; picture-in-picture" allowfullscreen></iframe>'
            )
    else:
        remote_panel = (
            '<div class="empty" id="remote-empty"><b>No remote mirror source connected yet.</b>'
            '<span>This admin trial can first test direct device screen capture. '
            'A relay URL can be connected later without changing the public bot.</span></div>'
        )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta http-equiv="Cache-Control" content="no-store, no-cache, must-revalidate">
<meta name="referrer" content="no-referrer">
<title>IBETIN · Cricket Mazza Mirror Trial</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
*{{box-sizing:border-box}}
html,body{{margin:0;min-height:100%;background:#07101c;color:#f8fafc;font-family:Arial,Helvetica,sans-serif}}
body{{padding:14px}}
.wrap{{max-width:760px;margin:0 auto}}
.top{{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:12px}}
.brand{{font-size:18px;font-weight:900;letter-spacing:.4px}}
.badge{{font-size:10px;font-weight:900;padding:7px 9px;border:1px solid #334155;border-radius:999px;color:#cbd5e1}}
.card{{background:#0f1d2e;border:1px solid #24364d;border-radius:20px;padding:16px;margin-bottom:12px}}
h1{{font-size:23px;margin:0 0 7px}}
p{{margin:0;color:#a9b9ca;font-size:13px;line-height:1.5}}
.preview{{position:relative;width:100%;aspect-ratio:9/16;max-height:68vh;background:#000;border-radius:18px;overflow:hidden;border:1px solid #26384d;margin-top:14px}}
.mirror,.preview video{{width:100%;height:100%;border:0;object-fit:contain;background:#000}}
.empty{{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:28px;color:#e2e8f0}}
.empty span{{display:block;margin-top:8px;color:#8fa3b8;font-size:12px;line-height:1.5}}
.status{{margin-top:10px;padding:10px 12px;border-radius:12px;background:#0a1523;color:#9fb0c2;font-size:12px;line-height:1.4}}
.actions{{display:grid;grid-template-columns:1fr;gap:9px;margin-top:12px}}
.btn{{display:block;width:100%;border:0;border-radius:13px;padding:14px 15px;text-align:center;text-decoration:none;font-weight:900;font-size:13px;cursor:pointer}}
.primary{{background:#fff;color:#07101c}}
.green{{background:#17834f;color:#fff}}
.soft{{background:#1a2b40;color:#eef5fb;border:1px solid #30455f}}
.small{{font-size:11px;color:#7f94aa;margin-top:10px;line-height:1.45}}
</style>
</head>
<body>
<div class="wrap">
  <div class="top"><div class="brand">IBETIN · MIRROR LAB</div><div class="badge">ADMIN ONLY</div></div>
  <section class="card">
    <h1>🏏 Cricket Mazza Screen Mirror · Trial</h1>
    <p>This is isolated from the public IBETIN menu. First we test whether this device/Telegram client can capture its screen. Nothing is rebroadcast to users in this trial.</p>
    <div class="preview" id="preview">{remote_panel}<video id="local" autoplay muted playsinline style="display:none"></video></div>
    <div class="status" id="status">Ready for admin test.</div>
    <div class="actions">
      <button class="btn green" id="capture">📱 TRY DEVICE SCREEN MIRROR</button>
      <a class="btn primary" href="{intent_html}">🏏 OPEN CRICKET MAZZA APP</a>
      <a class="btn soft" href="{play_html}" target="_blank" rel="noopener noreferrer">GOOGLE PLAY</a>
    </div>
    <div class="small">Suggested test: tap TRY DEVICE SCREEN MIRROR → allow full-screen sharing if Telegram/Android offers it → open Cricket Mazza → return here and check whether the preview kept capturing. If screen capture is unsupported, this page will say so clearly.</div>
  </section>
</div>
<script>
const tg = window.Telegram && window.Telegram.WebApp;
if (tg) {{ try {{ tg.ready(); tg.expand(); tg.setHeaderColor('#07101c'); tg.setBackgroundColor('#07101c'); }} catch(e) {{}} }}
const local = document.getElementById('local');
const status = document.getElementById('status');
const capture = document.getElementById('capture');
const configuredSource = {source_json};
let stream = null;
function setStatus(text) {{ status.textContent = text; }}
capture.addEventListener('click', async () => {{
  if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {{
    setStatus('Screen capture is not supported by this Telegram/Android WebView. We will need a remote mirror source/relay instead.');
    return;
  }}
  try {{
    if (stream) stream.getTracks().forEach(track => track.stop());
    stream = await navigator.mediaDevices.getDisplayMedia({{video:true,audio:false}});
    local.srcObject = stream;
    local.style.display = 'block';
    const remote = document.getElementById('remote');
    const empty = document.getElementById('remote-empty');
    if (remote) remote.style.display = 'none';
    if (empty) empty.style.display = 'none';
    setStatus('Screen capture started. Now open Cricket Mazza, then return here to see whether Android kept the capture active.');
    const track = stream.getVideoTracks()[0];
    if (track) track.addEventListener('ended', () => setStatus('Screen capture stopped.'));
  }} catch (err) {{
    setStatus('Screen capture was not started: ' + (err && err.message ? err.message : String(err)));
  }}
}});
if (configuredSource) setStatus('Remote mirror source is configured. You can also test direct device capture below.');
</script>
</body>
</html>"""


def _send_mazza_html(handler, status: int, html: str) -> None:
    data = html.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
    handler.send_header("Pragma", "no-cache")
    handler.send_header("X-Robots-Tag", "noindex, nofollow")
    handler.end_headers()
    handler.wfile.write(data)


def _install_mazza_mirror_route() -> None:
    handler_cls = ibetin_start.ibetin_entry.analytics.TrackingHandler
    if getattr(handler_cls, "_ibetin_mazza_mirror_installed", False):
        return

    previous_get = handler_cls.do_GET

    def patched_get(self):
        if urlparse(self.path).path == MAZZA_MIRROR_PATH:
            if not _mazza_authorized(self.path):
                _send_mazza_html(self, 403, "<h3>Admin mirror link is invalid.</h3>")
                return
            try:
                core.track(core.ADMIN_USER_ID, "mazza_mirror_admin_open")
            except Exception:
                logger.exception("Could not track Cricket Mazza mirror admin open")
            _send_mazza_html(self, 200, _mazza_mirror_page())
            return
        previous_get(self)

    handler_cls.do_GET = patched_get
    handler_cls._ibetin_mazza_mirror_installed = True
    logger.info("IBETIN admin-only Cricket Mazza mirror trial installed at %s", MAZZA_MIRROR_PATH)


async def _mazza_mirror_command(update, context) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message or user.id != core.ADMIN_USER_ID:
        return
    await message.reply_text(
        "🏏 <b>CRICKET MAZZA MIRROR · ADMIN TRIAL</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "This is private and is not visible in the public IBETIN menu.\n\n"
        "First we will test screen capture directly from your device. If Android blocks it, the same admin page is ready for a remote mirror source.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🏏 OPEN MIRROR TRIAL", web_app=WebAppInfo(url=_mazza_admin_url()))]]
        ),
        disable_web_page_preview=True,
    )


_install_mazza_mirror_route()

# Put the trial inside the existing admin experience as well as /mazzamirror.
_runtime = ibetin_start.ibetin_entry.runtime
_original_admin = _runtime.app.core.admin


async def _admin_with_mazza_trial(update, context) -> None:
    await _original_admin(update, context)
    user = update.effective_user
    message = update.effective_message
    if not user or not message or user.id != core.ADMIN_USER_ID:
        return
    await message.reply_text(
        "🏏 <b>CRICKET MAZZA MIRROR · TRIAL</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🏏 OPEN MIRROR TRIAL", web_app=WebAppInfo(url=_mazza_admin_url()))]]
        ),
        disable_web_page_preview=True,
    )


_runtime.app.core.admin = _admin_with_mazza_trial

_original_configure_telegram_ui = _runtime.configure_telegram_ui


async def _configure_telegram_ui_with_mazza(application) -> None:
    await _original_configure_telegram_ui(application)
    application.add_handler(CommandHandler("mazzamirror", _mazza_mirror_command))
    logger.info("IBETIN /mazzamirror admin command registered")


_runtime.configure_telegram_ui = _configure_telegram_ui_with_mazza

# Keep the app-level pointer aligned too; ibetin_start will restore this wrapper
# again after the hub router installs.
_runtime.app.configure_telegram_ui = _configure_telegram_ui_with_mazza

_original_start_background_loop = reminders.start_background_loop


async def _send_followup_trial(application):
    await asyncio.sleep(5)
    text, markup = reminders._copy_for("general", 1, "bot")
    try:
        await application.bot.send_message(
            chat_id=core.ADMIN_USER_ID,
            text="🧪 <b>IBETIN FOLLOW-UP TEST</b>\n\n" + text,
            parse_mode="HTML",
            reply_markup=markup,
            disable_web_page_preview=True,
        )
        logger.info("IBETIN follow-up trial sent to admin=%s", core.ADMIN_USER_ID)
    except Exception:
        logger.exception("IBETIN follow-up trial FAILED for admin=%s", core.ADMIN_USER_ID)


def _start_background_loop_with_trial(application):
    _original_start_background_loop(application)
    if application.bot_data.get("ibetin_followup_trial_scheduled"):
        return
    application.bot_data["ibetin_followup_trial_scheduled"] = True
    asyncio.create_task(_send_followup_trial(application), name="ibetin-followup-trial")


reminders.start_background_loop = _start_background_loop_with_trial

if __name__ == "__main__":
    ibetin_start.main()
