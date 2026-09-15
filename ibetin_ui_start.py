import asyncio
import logging

import bot as core
import fantzo_reminders as reminders
import ibetin_start
import ibetin_ui_v2

logger = logging.getLogger(__name__)

ibetin_ui_v2.install(ibetin_start)

_original_start_background_loop = reminders.start_background_loop


async def _send_followup_trial(application):
    await asyncio.sleep(5)
    text, markup = reminders._copy_for("general", 1, "bot")
    await application.bot.send_message(
        chat_id=core.ADMIN_USER_ID,
        text="🧪 <b>IBETIN FOLLOW-UP TEST</b>\n\n" + text,
        parse_mode="HTML",
        reply_markup=markup,
        disable_web_page_preview=True,
    )
    logger.info("IBETIN follow-up trial sent to admin=%s", core.ADMIN_USER_ID)


def _start_background_loop_with_trial(application):
    _original_start_background_loop(application)
    if application.bot_data.get("ibetin_followup_trial_scheduled"):
        return
    application.bot_data["ibetin_followup_trial_scheduled"] = True
    asyncio.create_task(_send_followup_trial(application), name="ibetin-followup-trial")


reminders.start_background_loop = _start_background_loop_with_trial

if __name__ == "__main__":
    ibetin_start.main()
