"""Fantzo feature launcher for Live TV banner queue testing."""
import logging

import bot_tracked as tracked
import fantzo_banner_queue as banner_queue
import fantzo_banner_preview as banner_preview

logger = logging.getLogger(__name__)
_original_configure_telegram_ui = tracked.configure_telegram_ui


async def configure_telegram_ui_with_banners(application) -> None:
    await _original_configure_telegram_ui(application)
    banner_queue.install(application)
    application.create_task(banner_preview.send_once(application))
    logger.info("Fantzo Live TV banner queue installed; private preview scheduled")


tracked.app.configure_telegram_ui = configure_telegram_ui_with_banners


if __name__ == "__main__":
    tracked.private_apk_upload.install_on_tracking_handler(tracked.analytics)
    tracked.trial_live_tv.install_on_tracking_handler(tracked.analytics)
    tracked.fantzo_live_tv.install_on_tracking_handler(tracked.analytics)
    tracked.analytics.start_tracking_server()
    logger.info("Starting Fantzo banner queue test launcher")
    tracked.app.run()
