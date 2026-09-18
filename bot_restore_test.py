"""Fantzo restored production launcher with Fantzo-first funnel UX.

Keeps the current Live TV reliability layer, restored production features,
Business DM safety and ops protections while making Fantzo.com the dominant
user destination.
"""
import logging

import bot_tracked_livefix  # installs current Live TV reliability layer
import bot_tracked as tracked
import fantzo_banner_queue as banner_queue
import fantzo_banner_preview as banner_preview
import fantzo_reminder_report as reminder_report
import fantzo_growth as growth
import fantzo_growth_integration as growth_integration
import fantzo_business
import fantzo_ops
import fantzo_funnel
import fantzo_business_flow_fix
import fantzo_admin_reports

logger = logging.getLogger(__name__)

# Preserve the restored first-message Business DM behaviour, but make the
# callback return immediately so Telegram RetryAfter sleeps cannot block /start.
_original_business_auto_reply = fantzo_business.business_auto_reply


async def nonblocking_business_auto_reply(update, context):
    context.application.create_task(
        _original_business_auto_reply(update, context)
    )


fantzo_business.business_auto_reply = nonblocking_business_auto_reply

growth_integration.install()
fantzo_funnel.install()
fantzo_business_flow_fix.install()
fantzo_admin_reports.install()
_original_configure_telegram_ui = tracked.configure_telegram_ui


async def configure_telegram_ui_with_restored_features(application) -> None:
    await _original_configure_telegram_ui(application)
    banner_queue.install(application)
    application.create_task(banner_preview.send_once(application))
    reminder_report.start(application)
    growth.start(application)
    fantzo_ops.install(application)
    logger.info(
        "Fantzo production features installed: Business funnel, banner queue, reminder report, favourites tracking, growth reporting, ops safety, admin reports and Fantzo-first main UX"
    )


tracked.app.configure_telegram_ui = configure_telegram_ui_with_restored_features


if __name__ == "__main__":
    tracked.private_apk_upload.install_on_tracking_handler(tracked.analytics)
    tracked.trial_live_tv.install_on_tracking_handler(tracked.analytics)
    tracked.fantzo_live_tv.install_on_tracking_handler(tracked.analytics)
    tracked.analytics.start_tracking_server()
    logger.info("Starting Fantzo with Fantzo-first user funnel")
    tracked.app.run()
