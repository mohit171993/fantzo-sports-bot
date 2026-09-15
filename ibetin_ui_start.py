import asyncio
import logging

import bot as core
import fantzo_reminders as reminders
import ibetin_start
import ibetin_ui_v2

logger = logging.getLogger(__name__)

ibetin_ui_v2.install(ibetin_start)

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
