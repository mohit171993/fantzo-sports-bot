import hmac
import logging
import os
from html import escape
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse, parse_qs

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import bot as core

logger = logging.getLogger(__name__)

TRACKING_BASE_URL = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/")
TRIAL_TV_TOKEN = os.getenv("TRIAL_TV_TOKEN", "").strip()
PACKAGE_NAME = "com.diamond.diamondlive"
MAIN_ACTIVITY = "com.sherdle.universal.MainActivity"
PLAY_URL = f"https://play.google.com/store/apps/details?id={PACKAGE_NAME}"
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/data/uploads"))
DIAMOND_APK_NAME = os.path.basename(os.getenv("DIAMOND_APK_NAME", "diamond.apk"))


def trial_page_url() -> str:
    if not TRACKING_BASE_URL or not TRIAL_TV_TOKEN:
        return PLAY_URL
    return f"{TRACKING_BASE_URL}/trial-live-tv?{urlencode({'t': TRIAL_TV_TOKEN})}"


def _authorized(path: str) -> bool:
    supplied = parse_qs(urlparse(path).query).get("t", [""])[0]
    return bool(TRIAL_TV_TOKEN) and hmac.compare_digest(supplied, TRIAL_TV_TOKEN)


def _page() -> str:
    fallback = quote(PLAY_URL, safe="")
    intent = (
        "intent://launch#Intent;"
        "action=android.intent.action.MAIN;"
        "category=android.intent.category.LAUNCHER;"
        f"package={PACKAGE_NAME};"
        f"component={PACKAGE_NAME}/{MAIN_ACTIVITY};"
        f"S.browser_fallback_url={fallback};"
        "end"
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fantzo Live TV Trial</title>
<style>
body{{font-family:Arial,sans-serif;background:#0f141c;color:#fff;padding:22px}}
.box{{max-width:620px;margin:35px auto;background:#1a212c;padding:26px;border-radius:18px}}
.btn{{display:block;text-align:center;text-decoration:none;padding:16px;border-radius:12px;margin-top:16px;font-weight:800;background:#fff;color:#111}}
.alt{{background:#2b3442;color:#fff}} .muted{{color:#aeb8c6;line-height:1.45}}
.badge{{display:inline-block;padding:6px 10px;border-radius:999px;background:#2b3442;font-size:12px}}
</style></head>
<body><div class="box">
<span class="badge">ADMIN TRIAL ONLY</span>
<h2>📺 Fantzo Live TV Trial</h2>
<p class="muted">This test only tries to open the installed Diamond Live Android app. It does not expose or rebroadcast any stream.</p>
<a class="btn" href="{escape(intent)}">📺 OPEN DIAMOND LIVE</a>
<a class="btn alt" href="{escape(PLAY_URL)}">Get / Open from Google Play</a>
<p class="muted">If the first button does not open the app from Telegram, tell me exactly what happens and I can adjust the launch method before anything is shown to Fantzo users.</p>
</div></body></html>"""


def _send_html(handler, status: int, html: str) -> None:
    data = html.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(data)


def _stream_diamond_apk(handler) -> None:
    apk = UPLOAD_DIR / DIAMOND_APK_NAME
    if not apk.is_file():
        _send_html(handler, 404, "<h3>Diamond APK is not available.</h3>")
        return

    size = apk.stat().st_size
    handler.send_response(200)
    handler.send_header("Content-Type", "application/vnd.android.package-archive")
    handler.send_header("Content-Disposition", 'attachment; filename="diamond.apk"')
    handler.send_header("Content-Length", str(size))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    with apk.open("rb") as src:
        while True:
            chunk = src.read(1024 * 1024)
            if not chunk:
                break
            handler.wfile.write(chunk)


def install_on_tracking_handler(analytics_module) -> None:
    handler_cls = analytics_module.TrackingHandler
    previous_get = handler_cls.do_GET

    def patched_get(self):
        path = urlparse(self.path).path
        if path == "/trial-live-tv":
            if not _authorized(self.path):
                _send_html(self, 403, "<h3>Trial link expired or invalid.</h3>")
                return
            try:
                core.track(core.ADMIN_USER_ID, "live_tv_trial_open")
            except Exception as exc:
                logger.warning("Could not track Live TV trial open: %s", exc)
            _send_html(self, 200, _page())
            return
        if path == "/trial-diamond-apk":
            if not _authorized(self.path):
                _send_html(self, 403, "<h3>Private test link invalid.</h3>")
                return
            _stream_diamond_apk(self)
            return
        previous_get(self)

    handler_cls.do_GET = patched_get
    logger.info("Admin-only Live TV trial route installed")


async def trial_tv_command(update, context) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return
    if user.id != core.ADMIN_USER_ID:
        await message.reply_text("This command is restricted.")
        return

    core.touch_user(update)
    core.track(user.id, "live_tv_trial_command")
    await message.reply_text(
        "📺 <b>LIVE TV · TRIAL MODE</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Admin-only test. Nothing has been added to the public Fantzo menu.\n\n"
        "Tap below on an Android phone with Diamond Live installed.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("📺 OPEN DIAMOND LIVE · TRIAL", url=trial_page_url())]]
        ),
        disable_web_page_preview=True,
    )
