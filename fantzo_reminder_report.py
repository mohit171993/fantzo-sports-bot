import asyncio
import logging
from datetime import datetime, timezone

import bot as core
import fantzo_growth as growth
import fantzo_reminders as reminders

logger = logging.getLogger(__name__)
REPORT_INTERVAL_SECONDS = 2 * 60 * 60


def _report_stats():
    reminders.ensure_tables()
    now = datetime.now(timezone.utc)
    with core.db() as conn:
        users = conn.execute(
            """
            SELECT source,user_id,last_activity,reminder_stage,opted_out,
                   COALESCE(delivery_disabled,0) delivery_disabled
            FROM reminder_users
            """
        ).fetchall()

        active_ids = {
            int(r["user_id"])
            for r in users
            if int(r["opted_out"] or 0) == 0
            and int(r["delivery_disabled"] or 0) == 0
        }
        opted_out_ids = {
            int(r["user_id"])
            for r in users
            if int(r["opted_out"] or 0) == 1
        }
        undeliverable_ids = {
            int(r["user_id"])
            for r in users
            if int(r["opted_out"] or 0) == 0
            and int(r["delivery_disabled"] or 0) == 1
        }

        pending = 0
        for row in users:
            if (
                int(row["opted_out"] or 0) != 0
                or int(row["delivery_disabled"] or 0) != 0
            ):
                continue
            if reminders._due_stage(row, now):
                pending += 1

        status_rows = conn.execute(
            "SELECT status,COUNT(*) AS c FROM reminder_sends GROUP BY status"
        ).fetchall()
        statuses = {str(r["status"]): int(r["c"]) for r in status_rows}
        today = now.date().isoformat()
        sent_today = int(conn.execute(
            "SELECT COUNT(*) AS c FROM reminder_sends "
            "WHERE status='sent' AND substr(sent_at,1,10)=?",
            (today,),
        ).fetchone()["c"])

    return {
        "active": len(active_ids),
        "pending": pending,
        "sent": statuses.get("sent", 0),
        "sent_today": sent_today,
        "failed": statuses.get("failed", 0) + statuses.get("bad_request", 0),
        "blocked": statuses.get("blocked", 0),
        "undeliverable": max(
            len(undeliverable_ids),
            statuses.get("undeliverable", 0),
        ),
        "opted_out": len(opted_out_ids),
    }


async def send_report(application):
    r = _report_stats()
    g = growth.growth_stats()
    text = (
        "📊 <b>FANTZO AUTOMATION & GROWTH REPORT</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "<b>REMINDERS</b>\n"
        f"👥 Reachable users: <b>{r['active']}</b>\n"
        f"⏳ Pending now: <b>{r['pending']}</b>\n"
        f"✅ Sent today: <b>{r['sent_today']}</b>\n"
        f"📨 Total sent: <b>{r['sent']}</b>\n"
        f"⚠️ Failed: <b>{r['failed']}</b> · "
        f"🚫 Undeliverable: <b>{r['undeliverable']}</b>\n"
        f"🔕 User opted out: <b>{r['opted_out']}</b>\n\n"
        "<b>GROWTH · 24H</b>\n"
        f"👥 Active users: <b>{g['active_24h']}</b>\n"
        f"📣 Telegram Ad starts: <b>{g['ad_starts_24h']}</b>\n"
        f"🔥 New verified leads: <b>{g['new_leads_24h']}</b>\n"
        f"✅ Lead conversions: <b>{g['converted_24h']}</b>\n"
        f"📺 Live TV opens: <b>{g['live_tv_24h']}</b>\n"
        f"📝 Signup started: <b>{g['signup_started_24h']}</b>\n"
        f"⭐ Favourite-team alerts: <b>{g['favourites']}</b>\n\n"
        "ℹ️ Signup completion is not shown because Fantzo currently has no "
        "verified completion event from the website.\n"
        "🔄 Automatic report: every 2 hours"
    )
    await application.bot.send_message(
        chat_id=core.ADMIN_USER_ID,
        text=text,
        parse_mode="HTML",
    )


async def report_loop(application):
    # Avoid an extra admin message every time Railway restarts.
    await asyncio.sleep(REPORT_INTERVAL_SECONDS)
    while True:
        try:
            await send_report(application)
        except Exception:
            logger.exception("Fantzo automation/growth report failed")
        await asyncio.sleep(REPORT_INTERVAL_SECONDS)


async def _start_report_when_running(application):
    while not application.running:
        await asyncio.sleep(0.2)
    application.create_task(report_loop(application))


def start(application):
    asyncio.create_task(
        _start_report_when_running(application),
        name="fantzo-automation-growth-report-starter",
    )
