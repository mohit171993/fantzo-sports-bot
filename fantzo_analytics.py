import logging
import os
import re
import threading
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import bot as core

logger = logging.getLogger(__name__)

TRACKING_BASE_URL = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/")
FANTZO_BASE_URL = os.getenv(
    "IBETIN_MINI_APP_URL",
    os.getenv("FANTZO_MINI_APP_URL", "https://ibetin.com"),
).strip().rstrip("/") + "/"
_server_started = False

SOURCE_LABELS = {
    "home_join_cta": "Home Join CTA",
    "join_screen_cta": "Join Screen CTA",
    "join_screen_explore": "Join Screen Explore",
    "explore_home": "Explore IBETIN",
    "explore_join": "Explore Join CTA",
    "telegram_native_menu": "Telegram Menu",
}

ACTION_LABELS = {
    "live_now": "Live Now",
    "trending": "Featured",
    "cricket": "Cricket",
    "football": "Football",
    "upcoming": "Upcoming",
    "results": "Results",
    "find_team": "Find Team",
    "subscribe": "Match Alerts",
    "toggle_sub": "Toggle Alerts",
    "quick_menu": "IBETIN Menu",
    "settings": "Settings",
    "explore": "Explore IBETIN",
    "join_fantzo": "Join IBETIN",
    "back": "Back/Home",
    "dm:message": "Direct DM Messages",
    "dm:autoreply_sent": "Direct Auto Replies",
    "business_dm:message": "Business DM Messages",
    "business_dm:autoreply_sent": "Business Auto Replies",
}


def ensure_tables() -> None:
    with core.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS web_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_web_events_created_at ON web_events(created_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_web_events_source ON web_events(source)"
        )


def _clean_source(source: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "", (source or "unknown"))[:64]
    return cleaned or "unknown"


def destination_url(source: str) -> str:
    source = _clean_source(source)
    return FANTZO_BASE_URL + "?" + urlencode(
        {
            "utm_source": "telegram",
            "utm_medium": "bot",
            "utm_campaign": "ibetin_sports_hub",
            "utm_content": source,
        }
    )


def tracking_url(source: str) -> str:
    source = _clean_source(source)
    if not TRACKING_BASE_URL:
        return destination_url(source)
    return f"{TRACKING_BASE_URL}/go?{urlencode({'source': source})}"


def record_open(source: str) -> None:
    source = _clean_source(source)
    ensure_tables()
    with core.db() as conn:
        conn.execute(
            "INSERT INTO web_events(event, source, created_at) VALUES (?, ?, ?)",
            ("fantzo_open", source, core.now_iso()),
        )


class TrackingHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path.rstrip("/") in {"/meta-ch", "/meta-ch-v2"}:
            from ibetin_meta_landing import page_html
            raw = page_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return

        if parsed.path == "/health":
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path != "/go":
            self.send_response(404)
            self.end_headers()
            return

        source = parse_qs(parsed.query).get("source", ["unknown"])[0]
        source = _clean_source(source)
        try:
            record_open(source)
        except Exception as exc:
            logger.exception("Could not record IBETIN open: %s", exc)

        self.send_response(302)
        self.send_header("Location", destination_url(source))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.end_headers()

    def log_message(self, format: str, *args) -> None:
        return


def start_tracking_server() -> None:
    global _server_started
    if _server_started:
        return

    ensure_tables()
    port = int(os.getenv("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), TrackingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="ibetin-tracker")
    thread.start()
    _server_started = True
    logger.info("IBETIN analytics redirect server listening on port %s", port)


def _action_label(action: str) -> str:
    action = str(action or "unknown")
    if action.startswith("team_upcoming:"):
        return "Team Upcoming"
    if action.startswith("team_recent:"):
        return "Team Results"
    if action.startswith("team:"):
        return "Team Detail"
    return ACTION_LABELS.get(action, action.replace("_", " ").title())


def _source_label(source: str) -> str:
    return SOURCE_LABELS.get(str(source), str(source).replace("_", " ").title())


def _scalar(conn, sql: str, params=()) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row[0] if row else 0)


def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return bool(row)


async def stats_command(update, context) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return
    if user.id != core.ADMIN_USER_ID:
        await message.reply_text("This command is restricted.")
        return

    core.touch_user(update)
    ensure_tables()

    now = datetime.now(timezone.utc)
    cutoff_24h = (now - timedelta(hours=24)).isoformat()
    cutoff_7d = (now - timedelta(days=7)).isoformat()

    with core.db() as conn:
        total_users = _scalar(conn, "SELECT COUNT(*) FROM users")
        new_24h = _scalar(conn, "SELECT COUNT(*) FROM users WHERE created_at >= ?", (cutoff_24h,))
        new_7d = _scalar(conn, "SELECT COUNT(*) FROM users WHERE created_at >= ?", (cutoff_7d,))
        active_24h = _scalar(conn, "SELECT COUNT(*) FROM users WHERE last_seen >= ?", (cutoff_24h,))
        active_7d = _scalar(conn, "SELECT COUNT(*) FROM users WHERE last_seen >= ?", (cutoff_7d,))
        subscribers = _scalar(conn, "SELECT COUNT(*) FROM users WHERE subscribed = 1")

        actions_24h = _scalar(conn, "SELECT COUNT(*) FROM clicks WHERE created_at >= ?", (cutoff_24h,))
        actions_7d = _scalar(conn, "SELECT COUNT(*) FROM clicks WHERE created_at >= ?", (cutoff_7d,))

        dm_messages_all = _scalar(
            conn,
            "SELECT COUNT(*) FROM clicks WHERE action IN ('dm:message','business_dm:message')",
        )
        dm_messages_24h = _scalar(
            conn,
            "SELECT COUNT(*) FROM clicks WHERE action IN ('dm:message','business_dm:message') AND created_at >= ?",
            (cutoff_24h,),
        )
        dm_messages_7d = _scalar(
            conn,
            "SELECT COUNT(*) FROM clicks WHERE action IN ('dm:message','business_dm:message') AND created_at >= ?",
            (cutoff_7d,),
        )
        auto_replies_24h = _scalar(
            conn,
            "SELECT COUNT(*) FROM clicks WHERE action IN ('dm:autoreply_sent','business_dm:autoreply_sent') AND created_at >= ?",
            (cutoff_24h,),
        )
        auto_replies_7d = _scalar(
            conn,
            "SELECT COUNT(*) FROM clicks WHERE action IN ('dm:autoreply_sent','business_dm:autoreply_sent') AND created_at >= ?",
            (cutoff_7d,),
        )
        dm_users_7d = _scalar(
            conn,
            "SELECT COUNT(DISTINCT user_id) FROM clicks WHERE action IN ('dm:message','business_dm:message') AND created_at >= ?",
            (cutoff_7d,),
        )
        business_dm_7d = _scalar(
            conn,
            "SELECT COUNT(*) FROM clicks WHERE action = 'business_dm:message' AND created_at >= ?",
            (cutoff_7d,),
        )

        opens_24h = _scalar(
            conn,
            "SELECT COUNT(*) FROM web_events WHERE event = 'fantzo_open' AND created_at >= ?",
            (cutoff_24h,),
        )
        opens_7d = _scalar(
            conn,
            "SELECT COUNT(*) FROM web_events WHERE event = 'fantzo_open' AND created_at >= ?",
            (cutoff_7d,),
        )
        opens_all = _scalar(conn, "SELECT COUNT(*) FROM web_events WHERE event = 'fantzo_open'")

        reminders_24h = reminders_7d = reminders_all = reminder_users = 0
        if _table_exists(conn, "reminder_sends"):
            reminders_24h = _scalar(
                conn,
                "SELECT COUNT(*) FROM reminder_sends WHERE status = 'sent' AND sent_at >= ?",
                (cutoff_24h,),
            )
            reminders_7d = _scalar(
                conn,
                "SELECT COUNT(*) FROM reminder_sends WHERE status = 'sent' AND sent_at >= ?",
                (cutoff_7d,),
            )
            reminders_all = _scalar(conn, "SELECT COUNT(*) FROM reminder_sends WHERE status = 'sent'")
        if _table_exists(conn, "reminder_users"):
            reminder_users = _scalar(conn, "SELECT COUNT(*) FROM reminder_users WHERE opted_out = 0")

        raw_actions = conn.execute(
            "SELECT action, COUNT(*) c FROM clicks WHERE created_at >= ? GROUP BY action ORDER BY c DESC LIMIT 40",
            (cutoff_7d,),
        ).fetchall()
        raw_sources = conn.execute(
            "SELECT source, COUNT(*) c FROM web_events WHERE event = 'fantzo_open' AND created_at >= ? "
            "GROUP BY source ORDER BY c DESC LIMIT 10",
            (cutoff_7d,),
        ).fetchall()

    action_counts = Counter()
    for row in raw_actions:
        action_counts[_action_label(row["action"])] += int(row["c"])
    top_actions = action_counts.most_common(6)

    top_action_text = "\n".join(
        f"• {escape(label)}: <b>{count}</b>" for label, count in top_actions
    ) or "• No bot activity yet."

    top_source_text = "\n".join(
        f"• {escape(_source_label(row['source']))}: <b>{int(row['c'])}</b>"
        for row in raw_sources[:6]
    ) or "• No IBETIN opens recorded yet."

    await message.reply_text(
        "📊 <b>IBETIN ANALYTICS</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "👥 <b>USERS</b>\n"
        f"Total: <b>{total_users}</b>\n"
        f"New — 24h: <b>{new_24h}</b> | 7d: <b>{new_7d}</b>\n"
        f"Active — 24h: <b>{active_24h}</b> | 7d: <b>{active_7d}</b>\n"
        f"🔔 Alerts ON: <b>{subscribers}</b>\n\n"
        "💬 <b>DM AUTO-REPLY</b>\n"
        f"DM users — 7d: <b>{dm_users_7d}</b>\n"
        f"Messages — 24h: <b>{dm_messages_24h}</b> | 7d: <b>{dm_messages_7d}</b> | All: <b>{dm_messages_all}</b>\n"
        f"Auto replies — 24h: <b>{auto_replies_24h}</b> | 7d: <b>{auto_replies_7d}</b>\n"
        f"Business DM messages — 7d: <b>{business_dm_7d}</b>\n\n"
        "⏰ <b>REMINDERS</b>\n"
        f"Eligible users: <b>{reminder_users}</b>\n"
        f"Sent — 24h: <b>{reminders_24h}</b> | 7d: <b>{reminders_7d}</b> | All: <b>{reminders_all}</b>\n\n"
        "🎯 <b>ENGAGEMENT</b>\n"
        f"Bot actions — 24h: <b>{actions_24h}</b> | 7d: <b>{actions_7d}</b>\n"
        f"IBETIN opens — 24h: <b>{opens_24h}</b> | 7d: <b>{opens_7d}</b> | All: <b>{opens_all}</b>\n\n"
        "🏆 <b>TOP ACTIONS · 7D</b>\n"
        f"{top_action_text}\n\n"
        "🔥 <b>IBETIN OPEN SOURCES · 7D</b>\n"
        f"{top_source_text}",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
