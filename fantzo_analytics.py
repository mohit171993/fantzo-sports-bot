import logging
import os
import re
import threading
import json
import hmac
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse
from zoneinfo import ZoneInfo

import bot as core

logger = logging.getLogger(__name__)

TRACKING_BASE_URL = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/")
FANTZO_BASE_URL = os.getenv("FANTZO_MINI_APP_URL", "https://www.fantzo.com").strip().rstrip("/") + "/"
_server_started = False
REPORT_TZ = ZoneInfo("Asia/Dubai")

DESTINATION_PATHS = {
    "home": "",
    "live": "en/live",
    "register": "en/registration",
}

SOURCE_LABELS = {
    "home_join_cta": "Home Join CTA",
    "join_screen_cta": "Join Screen CTA",
    "join_screen_explore": "Join Screen Explore",
    "explore_home": "Explore Fantzo",
    "explore_join": "Explore Join CTA",
    "telegram_native_menu": "Telegram Menu",
    "home_open_fantzo": "Home Open Fantzo",
    "business_play_fantzo": "Business Play Fantzo",
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
    "quick_menu": "Fantzo Menu",
    "settings": "Settings",
    "explore": "Explore Fantzo",
    "join_fantzo": "Join Fantzo",
    "back": "Back/Home",
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


def _clean_destination(destination: str) -> str:
    value = str(destination or "home").strip().lower()
    return value if value in DESTINATION_PATHS else "home"


def destination_url(source: str, destination: str = "home") -> str:
    source = _clean_source(source)
    destination = _clean_destination(destination)
    path = DESTINATION_PATHS[destination]
    base = FANTZO_BASE_URL if not path else FANTZO_BASE_URL + path
    return base + "?" + urlencode(
        {
            "utm_source": "telegram",
            "utm_medium": "bot",
            "utm_campaign": "fantzo_sports_hub",
            "utm_content": source,
        }
    )


def tracking_url(source: str, destination: str = "home") -> str:
    source = _clean_source(source)
    destination = _clean_destination(destination)
    if not TRACKING_BASE_URL:
        return destination_url(source, destination)
    query = {"source": source}
    if destination != "home":
        query["dest"] = destination
    return f"{TRACKING_BASE_URL}/go?{urlencode(query)}"


def record_open(source: str) -> None:
    source = _clean_source(source)
    ensure_tables()
    with core.db() as conn:
        conn.execute(
            "INSERT INTO web_events(event, source, created_at) VALUES (?, ?, ?)",
            ("fantzo_open", source, core.now_iso()),
        )


def _table_exists(conn, name: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone())


def _column_exists(conn, table: str, column: str) -> bool:
    if not _table_exists(conn, table):
        return False
    return any(str(r[1]) == column for r in conn.execute(f"PRAGMA table_info({table})").fetchall())


def _metric_count(conn, sql: str, params=()) -> int:
    try:
        row = conn.execute(sql, params).fetchone()
        return int(row[0] if row else 0)
    except Exception:
        return 0


def _report_day_windows(days: int = 3):
    now_local = datetime.now(timezone.utc).astimezone(REPORT_TZ)
    today = now_local.date()
    windows = []
    for offset in range(days):
        day = today - timedelta(days=offset)
        start_local = datetime(day.year, day.month, day.day, tzinfo=REPORT_TZ)
        end_local = start_local + timedelta(days=1)
        windows.append(
            (
                day.isoformat(),
                start_local.astimezone(timezone.utc).isoformat(),
                end_local.astimezone(timezone.utc).isoformat(),
            )
        )
    return windows


def _report_metrics_payload() -> dict:
    cutoff_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    day_windows = _report_day_windows(3)
    verified_by_date = {day: 0 for day, _, _ in day_windows}

    with core.db() as conn:
        bot_users = _metric_count(conn, "SELECT COUNT(*) FROM users") if _table_exists(conn, "users") else 0

        leads = 0
        leads_24h = 0
        verified = 0
        verified_24h = 0

        if _table_exists(conn, "sales_leads"):
            leads = _metric_count(conn, "SELECT COUNT(*) FROM sales_leads")
            if _column_exists(conn, "sales_leads", "created_at"):
                leads_24h = _metric_count(conn, "SELECT COUNT(*) FROM sales_leads WHERE created_at>=?", (cutoff_24h,))
            if _table_exists(conn, "lead_user_map"):
                verified = _metric_count(conn, "SELECT COUNT(DISTINCT user_id) FROM lead_user_map")
                verified_time_col = None
                for candidate in ("linked_at", "created_at"):
                    if _column_exists(conn, "lead_user_map", candidate):
                        verified_time_col = candidate
                        break
                if verified_time_col:
                    verified_24h = _metric_count(
                        conn,
                        f"SELECT COUNT(DISTINCT user_id) FROM lead_user_map WHERE {verified_time_col}>=?",
                        (cutoff_24h,),
                    )
                    for day, start_utc, end_utc in day_windows:
                        verified_by_date[day] = _metric_count(
                            conn,
                            f"SELECT COUNT(DISTINCT user_id) FROM lead_user_map "
                            f"WHERE {verified_time_col}>=? AND {verified_time_col}<?",
                            (start_utc, end_utc),
                        )
        elif _table_exists(conn, "ibetin_leads"):
            leads = _metric_count(conn, "SELECT COUNT(*) FROM ibetin_leads")
            if _column_exists(conn, "ibetin_leads", "first_seen_at"):
                leads_24h = _metric_count(conn, "SELECT COUNT(*) FROM ibetin_leads WHERE first_seen_at>=?", (cutoff_24h,))
            elif _column_exists(conn, "ibetin_leads", "created_at"):
                leads_24h = _metric_count(conn, "SELECT COUNT(*) FROM ibetin_leads WHERE created_at>=?", (cutoff_24h,))
            if _table_exists(conn, "liveline_verified_users"):
                verified = _metric_count(conn, "SELECT COUNT(DISTINCT user_id) FROM liveline_verified_users")
                if _column_exists(conn, "liveline_verified_users", "verified_at"):
                    verified_24h = _metric_count(conn, "SELECT COUNT(DISTINCT user_id) FROM liveline_verified_users WHERE verified_at>=?", (cutoff_24h,))
                    for day, start_utc, end_utc in day_windows:
                        verified_by_date[day] = _metric_count(
                            conn,
                            "SELECT COUNT(DISTINCT user_id) FROM liveline_verified_users "
                            "WHERE verified_at>=? AND verified_at<?",
                            (start_utc, end_utc),
                        )

        registration_clicks = 0
        registration_clicks_24h = 0
        if _table_exists(conn, "clicks") and _column_exists(conn, "clicks", "action"):
            registration_clicks = _metric_count(
                conn,
                "SELECT COUNT(*) FROM clicks WHERE lower(action) IN ('join_fantzo','join_ibetin','join_dura','register','registration','signup','sign_up')"
            )
            if _column_exists(conn, "clicks", "created_at"):
                registration_clicks_24h = _metric_count(
                    conn,
                    "SELECT COUNT(*) FROM clicks WHERE lower(action) IN ('join_fantzo','join_ibetin','join_dura','register','registration','signup','sign_up') AND created_at>=?",
                    (cutoff_24h,),
                )

        return {
            "bot_users": bot_users,
            "leads": leads,
            "leads_24h": leads_24h,
            "registration_clicks": registration_clicks,
            "registration_clicks_24h": registration_clicks_24h,
            "completed_registrations": None,
            "verified": verified,
            "verified_24h": verified_24h,
            "verified_by_date": verified_by_date,
            "verified_timezone": "Asia/Dubai",
            "registration_note": "Completed external-site registrations are not available unless the destination sends a conversion event back.",
        }


class TrackingHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/report-metrics":
            secret = os.getenv("REPORT_METRICS_SECRET", "").strip()
            supplied = self.headers.get("X-Report-Key", "")
            if not secret or not hmac.compare_digest(secret, supplied):
                self.send_response(403)
                self.end_headers()
                return
            raw = json.dumps(_report_metrics_payload(), separators=(",", ":")).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
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

        params = parse_qs(parsed.query)
        source = _clean_source(params.get("source", ["unknown"])[0])
        destination = _clean_destination(params.get("dest", ["home"])[0])
        try:
            record_open(source)
        except Exception as exc:
            logger.exception("Could not record Fantzo open: %s", exc)

        self.send_response(302)
        self.send_header("Location", destination_url(source, destination))
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
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="fantzo-tracker")
    thread.start()
    _server_started = True
    logger.info("Fantzo analytics redirect server listening on port %s", port)


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
    ) or "• No Fantzo opens recorded yet."

    await message.reply_text(
        "📊 <b>FANTZO ANALYTICS</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "👥 <b>USERS</b>\n"
        f"Total: <b>{total_users}</b>\n"
        f"New — 24h: <b>{new_24h}</b> | 7d: <b>{new_7d}</b>\n"
        f"Active — 24h: <b>{active_24h}</b> | 7d: <b>{active_7d}</b>\n"
        f"🔔 Alerts ON: <b>{subscribers}</b>\n\n"
        "🎯 <b>ENGAGEMENT</b>\n"
        f"Bot actions — 24h: <b>{actions_24h}</b> | 7d: <b>{actions_7d}</b>\n"
        f"Fantzo opens — 24h: <b>{opens_24h}</b> | 7d: <b>{opens_7d}</b> | All: <b>{opens_all}</b>\n\n"
        "🏆 <b>TOP BOT ACTIONS · 7D</b>\n"
        f"{top_action_text}\n\n"
        "🔥 <b>FANTZO OPEN SOURCES · 7D</b>\n"
        f"{top_source_text}\n\n"
        "ℹ️ Completed registrations cannot be measured from the bot because the Fantzo site is white-label and does not send a registration event back.",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
