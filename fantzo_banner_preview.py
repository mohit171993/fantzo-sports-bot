import asyncio
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import bot as core
import fantzo_banner_queue as banners

logger = logging.getLogger(__name__)

async def send_once(application):
    await asyncio.sleep(8)
    try:
        if banners._setting("private_preview_sent", "0") == "1":
            return
        row = banners.next_banner()
        if not row:
            logger.info("Banner preview skipped: queue empty")
            return
        caption = str(row["caption"] or "").strip() or banners.DEFAULT_CAPTION
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("📺 OPEN FANTZO SPORTS", url="https://t.me/fantzoofficialbot?start=livetv_banner")
        ]])
        await application.bot.send_photo(
            chat_id=core.ADMIN_USER_ID,
            photo=str(row["file_id"]),
            caption="🧪 <b>PRIVATE TEST PREVIEW</b>\n\n" + caption,
            parse_mode="HTML",
            reply_markup=markup,
        )
        banners._set_setting("private_preview_sent", "1")
        logger.info("Private banner preview sent to admin")
    except Exception:
        logger.exception("Automatic private banner preview failed")
