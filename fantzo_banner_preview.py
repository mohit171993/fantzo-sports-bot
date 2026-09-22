import asyncio
import logging
import bot as core
import fantzo_banner_queue as banners

logger = logging.getLogger(__name__)

async def send_once(application):
    await asyncio.sleep(8)
    try:
        row = banners.next_banner()
        if not row:
            logger.info("Banner preview skipped: queue empty")
            return
        banner_id = str(row["id"])
        if banners._setting("private_preview_banner_id", "") == banner_id:
            logger.info("Banner preview skipped: next queued banner already previewed")
            return
        await banners.send_banner(
            application.bot,
            core.ADMIN_USER_ID,
            row,
            caption_prefix="🧪 <b>PRIVATE TEST PREVIEW</b>\n\n",
        )
        banners._set_setting("private_preview_banner_id", banner_id)
        logger.info("Private banner preview sent to admin")
    except Exception:
        logger.exception("Automatic private banner preview failed")
