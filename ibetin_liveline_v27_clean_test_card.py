import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

import ibetin_liveline_trial as liveline
import ibetin_liveline_v26_ui_polish as v26

logger = logging.getLogger(__name__)


async def clean_liveline_command(update, context):
    user = update.effective_user
    message = update.effective_message
    chat = update.effective_chat
    if not user or not message or not chat:
        return
    if getattr(chat, "type", "") != "private":
        await message.reply_text("This test preview is available only in a private chat with the bot.")
        return

    logger.info("IBETIN Live Line test preview accepted user_id=%s", user.id)
    await message.reply_text(
        "⚡ <b>IBETIN LIVE LINE · TEST</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Private preview of Live Matches, Match Detail, Scorecard, In-Play data, Upcoming and Results.\n\n"
        "The public IBETIN menu has not been changed.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⚡ OPEN LIVE LINE", web_app=WebAppInfo(url=liveline.admin_url()))]]
        ),
        disable_web_page_preview=True,
    )


# The command registration wrapper in ibetin_liveline_trial resolves this global
# when Telegram UI is configured, so patching it here keeps the route/feed/UI
# unchanged and only cleans the private test launcher copy.
liveline.liveline_command = clean_liveline_command

app = v26.app

if __name__ == "__main__":
    app.base.ibetin_start.main()
