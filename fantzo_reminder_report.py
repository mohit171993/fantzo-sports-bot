import asyncio
import logging
from datetime import datetime, timezone

import bot as core
import fantzo_reminders as reminders

logger = logging.getLogger(__name__)
REPORT_INTERVAL_SECONDS = 2 * 60 * 60


def _report_stats():
    reminders.ensure_tables()
    now = datetime.now(timezone.utc)
    with core.db() as conn:
        users = conn.execute("SELECT source, user_id, last_activity, reminder_stage, opted_out FROM reminder_users").fetchall()
        total_active = sum(1 for r in users if int(r["opted_out"] or 0) == 0)
        opted_out = sum(1 for r in users if int(r["opted_out"] or 0) == 1)
        pending = 0
        for row in users:
            if int(row["opted_out"] or 0) != 0:
                continue
            if reminders._due_stage(row, now):
                pending += 1

        status_rows = conn.execute("SELECT status, COUNT(*) AS c FROM reminder_sends GROUP BY status").fetchall()
        statuses = {str(r["status"]): int(r["c"]) for r in status_rows}
        today = now.date().isoformat()
        sent_today = int(conn.execute("SELECT COUNT(*) AS c FROM reminder_sends WHERE status='sent' AND substr(sent_at,1,10)=?", (today,)).fetchone()["c"])
        sent_last_2h = int(conn.execute("SELECT COUNT(*) AS c FROM reminder_sends WHERE status='sent' AND sent_at >= ?", ((now.timestamp() - REPORT_INTERVAL_SECONDS),)).fetchone()["c"] if False else 0)

    return {
        "active": total_active,
        "pending": pending,
        "sent": statuses.get("sent", 0),
        "sent_today": sent_today,
        "failed": statuses.get("failed", 0) + statuses.get("bad_request", 0),
        "blocked": statuses.get("blocked", 0),
        "opted_out": opted_out,
    }


async def send_report(application):
    s = _report_stats()
    text = (
        "⏰ <b>FANTZO REMINDER REPORT</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Active users: <b>{s['active']}</b>\n"
        f"⏳ Pending now: <b>{s['pending']}</b>\n"
        f"✅ Sent today: <b>{s['sent_today']}</b>\n"
        f"📨 Total sent: <b>{s['sent']}</b>\n"
        f"⚠️ Failed: <b>{s['failed']}</b>\n"
        f"🚫 Blocked: <b>{s['blocked']}</b>\n"
        f"🔕 Opted out: <b>{s['opted_out']}</b>\n\n"
        "🔄 Automatic report: every 2 hours"
    )
    await application.bot.send_message(chat_id=core.ADMIN_USER_ID, text=text, parse_mode="HTML")


async def report_loop(application):
    # Wait two hours before the first report so deployment does not create an immediate extra DM.
    await asyncio.sleep(REPORT_INTERVAL_SECONDS)
    while True:
        try:
            await send_report(application)
        except Exception:
            logger.exception("Fantzo reminder report failed")
        await asyncio.sleep(REPORT_INTERVAL_SECONDS)


def start(application):
    application.create_task(report_loop(application))
