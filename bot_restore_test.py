"""Fantzo restored production launcher with Fantzo-first funnel UX.

Keeps the current Live TV reliability layer, restored production features,
Business DM safety and ops protections while making Fantzo.com the dominant
user destination.
"""
import asyncio
import logging

import bot_tracked_livefix  # installs current Live TV reliability layer
import bot_tracked as tracked
import fantzo_banner_queue as banner_queue
import fantzo_banner_preview as banner_preview
import fantzo_reminder_report as reminder_report
import fantzo_growth_integration as growth_integration
import fantzo_business
import fantzo_ops
import fantzo_funnel
import fantzo_business_flow_fix
import fantzo_admin_reports
import fantzo_live_tv_mobile_gate
import fantzo_lead_funnel
import fantzo_native_ui

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
fantzo_native_ui.install()
fantzo_funnel.install()
fantzo_business_flow_fix.install()
fantzo_lead_funnel.install()
fantzo_admin_reports.install()
fantzo_live_tv_mobile_gate.install()
_original_configure_telegram_ui = tracked.configure_telegram_ui


async def _send_banner_preview_when_running(application) -> None:
    while not application.running:
        await asyncio.sleep(0.2)
    await banner_preview.send_once(application)


async def configure_telegram_ui_with_restored_features(application) -> None:
    await _original_configure_telegram_ui(application)

    try:
        await application.bot.set_my_short_description(
            "Cricket & football scores, fixtures, Live TV and sports updates."
        )
        await application.bot.set_my_description(
            "Fantzo Sports brings cricket and football live scores, fixtures, "
            "match alerts, Live TV access and sports updates inside Telegram. "
            "One-time Telegram mobile verification is required to continue."
        )
    except Exception:
        logger.exception("Could not update Fantzo Telegram bot descriptions")

    banner_queue.install(application)
    asyncio.create_task(
        _send_banner_preview_when_running(application),
        name="fantzo-banner-preview-starter",
    )
    reminder_report.start(application)
    fantzo_ops.install(application)
    fantzo_live_tv_mobile_gate.register_handlers(application)
    fantzo_lead_funnel.register_handlers(application)
    fantzo_native_ui.register_handlers(application)
    fantzo_admin_reports.register_handlers(application)
    logger.info(
        "Fantzo production features installed: isolated Fantzo native UI, iBetin-style compact admin/report navigation, Fantzo CRM, paid-ad attribution, banner queue, reminders, growth, ops safety, global mobile verification and Fantzo sports UX"
    )


tracked.app.configure_telegram_ui = configure_telegram_ui_with_restored_features


def _force_fantzo_test_unverified_once() -> None:
    """Make only Mohit_97saxena unverified while preserving saved mobile/CRM."""
    marker = "fantzo_test_unverified:2026-09-23-manual"
    username = "mohit_97saxena"
    core = tracked.app.core

    with core.db() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT)"
        )
        if conn.execute(
            "SELECT 1 FROM settings WHERE key=?",
            (marker,),
        ).fetchone():
            return

        rows = conn.execute(
            "SELECT user_id FROM users WHERE lower(COALESCE(username,''))=?",
            (username,),
        ).fetchall()
        ids = {int(row["user_id"]) for row in rows}
        if len(ids) != 1:
            logger.warning(
                "Fantzo test unverify skipped: username match count=%s",
                len(ids),
            )
            return

        uid = next(iter(ids))
        row = conn.execute(
            """
            SELECT mobile_e164,capture_method
            FROM live_tv_mobile_users
            WHERE user_id=?
            """,
            (uid,),
        ).fetchone()
        if not row:
            logger.warning("Fantzo test unverify skipped: verification row unavailable")
            return

        saved_mobile = bool(str(row["mobile_e164"] or "").strip())
        was_verified = str(row["capture_method"] or "") == "telegram_contact"

        conn.execute(
            """
            UPDATE live_tv_mobile_users
            SET capture_method='test_unverified',
                source='manual_test_reset',
                updated_at=?
            WHERE user_id=?
            """,
            (core.now_iso(), uid),
        )
        conn.execute(
            "INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
            (marker, "applied"),
        )

        verified_after = bool(conn.execute(
            """
            SELECT 1 FROM live_tv_mobile_users
            WHERE user_id=? AND capture_method='telegram_contact'
            """,
            (uid,),
        ).fetchone())

    logger.info(
        "FANTZO test account forced unverified was_verified=%s verified_after=%s saved_mobile=%s",
        was_verified,
        verified_after,
        saved_mobile,
    )


if __name__ == "__main__":
    _force_fantzo_test_unverified_once()
    tracked.private_apk_upload.install_on_tracking_handler(tracked.analytics)
    tracked.trial_live_tv.install_on_tracking_handler(tracked.analytics)
    tracked.fantzo_live_tv.install_on_tracking_handler(tracked.analytics)
    tracked.analytics.start_tracking_server()
    logger.info("Starting Fantzo with Fantzo-first user funnel")
    tracked.app.run()
