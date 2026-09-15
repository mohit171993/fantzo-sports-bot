import asyncio
import logging
from datetime import datetime, timedelta, timezone

import bot as core

logger = logging.getLogger(__name__)
REPORT_INTERVAL_SECONDS = 2 * 60 * 60


def ensure_tables():
    with core.db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS growth_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                event TEXT NOT NULL,
                value TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_favourites (
                user_id INTEGER NOT NULL,
                kind TEXT NOT NULL DEFAULT 'team',
                value TEXT NOT NULL,
                alerts_enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                PRIMARY KEY(user_id, kind, value)
            )
        """)


def track(user_id, event, value=''):
    ensure_tables()
    with core.db() as conn:
        conn.execute(
            "INSERT INTO growth_events(user_id,event,value,created_at) VALUES(?,?,?,?)",
            (int(user_id) if user_id else None, str(event), str(value or ''), datetime.now(timezone.utc).isoformat()),
        )


def add_favourite(user_id, team):
    ensure_tables()
    team = str(team or '').strip()
    if not team:
        return False
    with core.db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO user_favourites(user_id,kind,value,alerts_enabled,created_at) VALUES(?,'team',?,1,?)",
            (int(user_id), team, datetime.now(timezone.utc).isoformat()),
        )
    track(user_id, 'favourite_team', team)
    return True


def growth_stats():
    ensure_tables()
    now = datetime.now(timezone.utc)
    day = (now - timedelta(hours=24)).isoformat()
    week = (now - timedelta(days=7)).isoformat()
    with core.db() as conn:
        def count(event, since=None):
            if since:
                return int(conn.execute("SELECT COUNT(*) c FROM growth_events WHERE event=? AND created_at>=?", (event, since)).fetchone()['c'])
            return int(conn.execute("SELECT COUNT(*) c FROM growth_events WHERE event=?", (event,)).fetchone()['c'])
        active_24h = int(conn.execute("SELECT COUNT(DISTINCT user_id) c FROM growth_events WHERE created_at>=? AND user_id IS NOT NULL", (day,)).fetchone()['c'])
        active_7d = int(conn.execute("SELECT COUNT(DISTINCT user_id) c FROM growth_events WHERE created_at>=? AND user_id IS NOT NULL", (week,)).fetchone()['c'])
        favourites = int(conn.execute("SELECT COUNT(*) c FROM user_favourites WHERE alerts_enabled=1").fetchone()['c'])
    return {
        'active_24h': active_24h,
        'active_7d': active_7d,
        'bot_opens_24h': count('bot_open', day),
        'live_tv_24h': count('live_tv_open', day),
        'signup_started_24h': count('signup_started', day),
        'signup_completed_24h': count('signup_completed', day),
        'favourites': favourites,
    }


async def send_growth_report(application):
    s = growth_stats()
    text = (
        "📈 <b>FANTZO GROWTH REPORT</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Active users (24h): <b>{s['active_24h']}</b>\n"
        f"📅 Active users (7d): <b>{s['active_7d']}</b>\n"
        f"🚀 Bot opens (24h): <b>{s['bot_opens_24h']}</b>\n"
        f"📺 Live TV opens (24h): <b>{s['live_tv_24h']}</b>\n"
        f"📝 Signup started (24h): <b>{s['signup_started_24h']}</b>\n"
        f"✅ Signup completed (24h): <b>{s['signup_completed_24h']}</b>\n"
        f"⭐ Favourite-team alerts: <b>{s['favourites']}</b>\n\n"
        "🔄 Automatic report: every 2 hours"
    )
    await application.bot.send_message(chat_id=core.ADMIN_USER_ID, text=text, parse_mode='HTML')


async def report_loop(application):
    await asyncio.sleep(REPORT_INTERVAL_SECONDS)
    while True:
        try:
            await send_growth_report(application)
        except Exception:
            logger.exception('Fantzo growth report failed')
        await asyncio.sleep(REPORT_INTERVAL_SECONDS)


def start(application):
    ensure_tables()
    application.create_task(report_loop(application))
