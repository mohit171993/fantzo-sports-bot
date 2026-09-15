import asyncio
import json
import logging

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
# - JOIN IBETIN = Telegram Mini App
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
            "business-reminder: expected 1 launcher, got 2",
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
