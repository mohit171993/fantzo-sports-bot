"""Fantzo feature launcher for production feature testing."""
import logging

import bot_tracked as tracked
import fantzo_banner_queue as banner_queue
import fantzo_banner_preview as banner_preview
import fantzo_reminder_report as reminder_report
import fantzo_growth_integration as growth_integration

logger = logging.getLogger(__name__)
growth_integration.install()
_original_configure_telegram_ui = tracked.configure_telegram_ui


async def configure_telegram_ui_with_features(application) -> None:
    await _original_configure_telegram_ui(application)
    banner_queue.install(application)
    application.create_task(banner_preview.send_once(application))
    reminder_report.start(application)
    logger.info("Fantzo banner queue and combined automation report scheduled")


tracked.app.configure_telegram_ui = configure_telegram_ui_with_features


if __name__ == "__main__":
    tracked.private_apk_upload.install_on_tracking_handler(tracked.analytics)
    tracked.trial_live_tv.install_on_tracking_handler(tracked.analytics)
    tracked.fantzo_live_tv.install_on_tracking_handler(tracked.analytics)
    tracked.analytics.start_tracking_server()
    logger.info("Starting Fantzo feature launcher")
    tracked.app.run()
