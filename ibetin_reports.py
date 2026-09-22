import csv
import io
import logging
import os
import re
import zipfile
from datetime import datetime, timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile

import bot as core
import ibetin_phone_verify as phone_verify
import ibetin_leads

logger = logging.getLogger(__name__)

REPORT_PREFIX = "reports:"
DUBAI_TZ = ZoneInfo("Asia/Dubai")
CRM_BATCH_SIZE = 5


def _setting_user_id(key: str):
    try:
        with core.db() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"
            )
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?",
                (key,),
            ).fetchone()
        return int(row["value"]) if row and row["value"] else None
    except Exception:
        return None


def is_authorized_admin(user_id: int) -> bool:
    try:
        uid = int(user_id or 0)
    except Exception:
        return False
    if not uid:
        return False

    if uid == int(core.ADMIN_USER_ID):
        return True

    env_admin = 0
    try:
        env_admin = int(os.getenv("IBETIN_REPORT_ADMIN_USER_ID", "0").strip() or "0")
    except Exception:
        env_admin = 0

    if env_admin and uid == env_admin:
        return True

    # Backward-compatible persisted authorization.
    return uid in {
        x for x in (
            _setting_user_id("creative_admin_user_id"),
            _setting_user_id("report_admin_user_id"),
        )
        if x
    }


def notification_admin_user_id() -> int:
    """Prefer the currently unlocked report/admin account for lead alerts."""
    try:
        env_admin = int(
            os.getenv("IBETIN_REPORT_ADMIN_USER_ID", "0").strip() or "0"
        )
    except Exception:
        env_admin = 0

    for candidate in (
        env_admin,
        _setting_user_id("report_admin_user_id"),
        int(core.ADMIN_USER_ID),
    ):
        try:
            uid = int(candidate or 0)
        except Exception:
            uid = 0
        if uid:
            return uid
    return int(core.ADMIN_USER_ID)


def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row)


def _count(conn, sql: str, params=()) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row[0] if row else 0)


def ensure_tables() -> None:
    phone_verify.ensure_tables()
    ibetin_leads.ensure_tables()
    with core.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS live_tv_users (
                user_id INTEGER PRIMARY KEY,
                first_opened_at TEXT NOT NULL,
                last_opened_at TEXT NOT NULL,
                open_count INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        # Best-effort historical backfill if any earlier implementation logged
        # Live TV opens as bot click actions.
        if _table_exists(conn, "clicks"):
            rows = conn.execute(
                """
                SELECT user_id, MIN(created_at) first_at, MAX(created_at) last_at, COUNT(*) c
                FROM clicks
                WHERE user_id IS NOT NULL
                  AND lower(action) IN (
                    'live_tv', 'live_tv_open', 'livetv', 'watch_live_tv',
                    'open_live_tv', 'live_tv_status'
                  )
                GROUP BY user_id
                """
            ).fetchall()
            for row in rows:
                conn.execute(
                    """
                    INSERT INTO live_tv_users(user_id, first_opened_at, last_opened_at, open_count)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        first_opened_at = CASE
                            WHEN excluded.first_opened_at < live_tv_users.first_opened_at
                            THEN excluded.first_opened_at ELSE live_tv_users.first_opened_at END,
                        last_opened_at = CASE
                            WHEN excluded.last_opened_at > live_tv_users.last_opened_at
                            THEN excluded.last_opened_at ELSE live_tv_users.last_opened_at END,
                        open_count = CASE
                            WHEN excluded.open_count > live_tv_users.open_count
                            THEN excluded.open_count ELSE live_tv_users.open_count END
                    """,
                    (
                        int(row["user_id"]),
                        str(row["first_at"] or core.now_iso()),
                        str(row["last_at"] or core.now_iso()),
                        int(row["c"] or 1),
                    ),
                )


def record_live_tv_open(user_id: int) -> None:
    if not user_id:
        return
    ensure_tables()
    now = core.now_iso()
    with core.db() as conn:
        conn.execute(
            """
            INSERT INTO live_tv_users(user_id, first_opened_at, last_opened_at, open_count)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(user_id) DO UPDATE SET
                last_opened_at = excluded.last_opened_at,
                open_count = live_tv_users.open_count + 1
            """,
            (int(user_id), now, now),
        )
        # Also keep the general activity table useful for reporting.
        if _table_exists(conn, "clicks"):
            conn.execute(
                "INSERT INTO clicks(user_id, action, created_at) VALUES (?, ?, ?)",
                (int(user_id), "live_tv_open", now),
            )


def _user_maps(conn):
    users = {}
    if _table_exists(conn, "users"):
        for row in conn.execute(
            "SELECT user_id, username, first_name, language, subscribed, created_at, last_seen FROM users"
        ).fetchall():
            users[int(row["user_id"])] = dict(row)

    business = {}
    if _table_exists(conn, "business_customers"):
        for row in conn.execute(
            """
            SELECT customer_id, username, first_name, MAX(last_seen) last_seen
            FROM business_customers
            GROUP BY customer_id
            """
        ).fetchall():
            business[int(row["customer_id"])] = dict(row)

    phones = {}
    if _table_exists(conn, "liveline_verified_users"):
        for row in conn.execute(
            "SELECT * FROM liveline_verified_users"
        ).fetchall():
            phones[int(row["user_id"])] = dict(row)
    return users, business, phones


def _identity(uid: int, users, business):
    u = users.get(uid) or {}
    b = business.get(uid) or {}
    username = str(u.get("username") or b.get("username") or "")
    first_name = str(u.get("first_name") or b.get("first_name") or "")
    return username, first_name


def _actor_name(user) -> str:
    if not user:
        return "Admin"
    username = str(getattr(user, "username", "") or "").strip()
    if username:
        return "@" + username
    name = str(getattr(user, "first_name", "") or "").strip()
    return name or "Admin"


def _fmt_admin_time(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "—"
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(DUBAI_TZ).strftime("%d %b %Y, %H:%M")
    except Exception:
        return raw[:16].replace("T", " ")


def _lead_view(user_id: int):
    ensure_tables()
    uid = int(user_id)
    with core.db() as conn:
        users, business, phones = _user_maps(conn)
        row = conn.execute(
            "SELECT * FROM ibetin_leads WHERE user_id=?",
            (uid,),
        ).fetchone()
    if not row:
        return None
    lead = dict(row)
    username, first_name = _identity(uid, users, business)
    current_phone = (phones.get(uid) or {}).get("phone_number") or ""
    phone = str(lead.get("mobile_number") or current_phone or "")
    lead["username"] = username
    lead["first_name"] = first_name
    lead["phone_number"] = phone
    lead["is_currently_verified"] = uid in phones
    return lead


def _phone_digits(value: str) -> str:
    return re.sub(r"\D", "", str(value or ""))[:15]


def lead_status_keyboard(user_id: int) -> InlineKeyboardMarkup:
    uid = int(user_id)
    lead = _lead_view(uid) or {}
    phone_digits = _phone_digits(lead.get("phone_number") or "")
    consent = bool(int(lead.get("contact_consent") or 0))

    rows = [
        [
            InlineKeyboardButton(
                "🙋 ASSIGN TO ME",
                callback_data=f"reports:assign:{uid}",
            ),
            InlineKeyboardButton(
                "📝 NOTE",
                callback_data=f"reports:note:{uid}",
            ),
        ],
        [
            InlineKeyboardButton(
                "⏰ FOLLOW-UP",
                callback_data=f"reports:followup:{uid}",
            ),
            InlineKeyboardButton(
                "🕘 HISTORY",
                callback_data=f"reports:history:{uid}",
            ),
        ],
        [
            InlineKeyboardButton(
                "📞 CONTACTED",
                callback_data=f"reports:lead:contacted:{uid}",
            ),
            InlineKeyboardButton(
                "⭐ INTERESTED",
                callback_data=f"reports:lead:interested:{uid}",
            ),
        ],
        [
            InlineKeyboardButton(
                "✅ CONVERTED",
                callback_data=f"reports:lead:converted:{uid}",
            ),
            InlineKeyboardButton(
                "📵 NO ANSWER",
                callback_data=f"reports:lead:no_answer:{uid}",
            ),
        ],
        [
            InlineKeyboardButton(
                "🚫 DNC",
                callback_data=f"reports:lead:dnc:{uid}",
            ),
            InlineKeyboardButton(
                "↩️ NEW",
                callback_data=f"reports:lead:new:{uid}",
            ),
        ],
    ]
    if phone_digits and consent:
        rows.append(
            [InlineKeyboardButton("💬 OPEN WHATSAPP", url=f"https://wa.me/{phone_digits}")]
        )
    rows.append(
        [InlineKeyboardButton("⬅️ WORK QUEUE", callback_data="reports:crm")]
    )
    return InlineKeyboardMarkup(rows)


def _lead_card_text(lead: dict) -> str:
    status = str(lead.get("lead_status") or "new").replace("_", " ").upper()
    status_icon = {
        "NEW": "🆕",
        "CONTACTED": "📞",
        "INTERESTED": "⭐",
        "CONVERTED": "✅",
        "NO ANSWER": "📵",
        "DNC": "🚫",
    }.get(status, "📌")
    username = str(lead.get("username") or "")
    telegram = f"@{escape(username)}" if username else "—"
    first_name = escape(str(lead.get("first_name") or "—"))
    phone_raw = str(lead.get("phone_number") or "").strip()
    phone = escape(phone_raw) if phone_raw else "Not captured"
    telegram_user_id = int(lead.get("user_id") or 0)
    campaign = escape(str(lead.get("campaign") or "direct"))
    source = escape(str(lead.get("source") or "bot"))
    assigned = escape(str(lead.get("assigned_name") or "UNASSIGNED"))
    first_seen = escape(_fmt_admin_time(str(lead.get("first_seen_at") or "")))
    verified_raw = str(lead.get("verified_at") or "")
    verified = bool(lead.get("is_currently_verified"))
    followup = _fmt_admin_time(str(lead.get("next_followup_at") or ""))
    note = escape(str(lead.get("last_note") or "")[:180])
    consent = bool(int(lead.get("contact_consent") or 0))

    if verified:
        verification_text = (
            f"✅ <b>VERIFIED</b> · "
            f"{escape(_fmt_admin_time(verified_raw))}"
        )
        consent_text = (
            "✅ Call + WhatsApp consent recorded"
            if consent
            else "⚠️ Legacy verified record · contact consent not recorded"
        )
    else:
        verification_text = "⚠️ <b>NOT VERIFIED</b>"
        consent_text = "ℹ️ Contact consent not available · verification incomplete"

    lines = [
        f"{status_icon} <b>{status}</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"👤 <b>{first_name}</b> · {telegram}",
        f"🆔 Telegram ID: <code>{telegram_user_id}</code>",
        f"📱 Mobile: <code>{phone}</code>" if phone_raw else "📱 Mobile: <b>Not captured</b>",
        f"🔐 Verification: {verification_text}",
        f"🕒 First seen: <b>{first_seen}</b>",
        f"🎯 Campaign: <code>{campaign}</code>",
        f"📥 Source: <b>{source}</b>",
        f"👨‍💼 Assigned: <b>{assigned}</b>",
        consent_text,
    ]
    if str(lead.get("next_followup_at") or ""):
        lines.append(f"⏰ Next follow-up: <b>{escape(followup)}</b>")
    if note:
        lines.append(f"📝 Note: {note}")
    return "\n".join(lines)


def _crm_status_counts() -> dict:
    ensure_tables()
    counts = {
        "new": 0,
        "contacted": 0,
        "no_answer": 0,
        "interested": 0,
        "converted": 0,
        "dnc": 0,
    }
    with core.db() as conn:
        rows = conn.execute(
            """
            SELECT lead_status, COUNT(*) c
            FROM ibetin_leads
            GROUP BY lead_status
            """
        ).fetchall()
    for row in rows:
        key = str(row["lead_status"] or "new")
        if key in counts:
            counts[key] = int(row["c"] or 0)
    return counts


def _crm_text() -> str:
    counts = _crm_status_counts()
    follow_up = counts["contacted"] + counts["no_answer"]
    with core.db() as conn:
        unassigned = _count(
            conn,
            """
            SELECT COUNT(*) FROM ibetin_leads
            WHERE lead_status='new'
              AND assigned_to IS NULL
            """,
        )
        unassigned_verified = _count(
            conn,
            """
            SELECT COUNT(*)
            FROM ibetin_leads l
            WHERE l.lead_status='new'
              AND l.assigned_to IS NULL
              AND EXISTS (
                  SELECT 1 FROM liveline_verified_users v
                  WHERE v.user_id=l.user_id
              )
            """,
        )
        unassigned_unverified = _count(
            conn,
            """
            SELECT COUNT(*)
            FROM ibetin_leads l
            WHERE l.lead_status='new'
              AND l.assigned_to IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM liveline_verified_users v
                  WHERE v.user_id=l.user_id
              )
            """,
        )
        legacy = _count(
            conn,
            """
            SELECT COUNT(*) FROM ibetin_leads
            WHERE verified_at IS NOT NULL
              AND contact_consent=0
              AND lead_status='new'
            """,
        )
        due = _count(
            conn,
            """
            SELECT COUNT(*) FROM ibetin_leads
            WHERE next_followup_at IS NOT NULL
              AND next_followup_at <= ?
              AND lead_status NOT IN ('converted','dnc')
            """,
            (datetime.now(timezone.utc).isoformat(),),
        )

    active = unassigned + follow_up + counts["interested"]
    return (
        "📞 <b>IBETIN TEAM WORK QUEUE</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"🆕 Unassigned / New · ALL TIME: <b>{unassigned}</b>\n"
        f"   ✅ Verified: <b>{unassigned_verified}</b> · "
        f"⚠️ Not verified: <b>{unassigned_unverified}</b>\n"
        f"🗂 Legacy verified awaiting review: <b>{legacy}</b>\n"
        f"📞 Follow-up: <b>{follow_up}</b> · ⏰ Due now: <b>{due}</b>\n"
        f"⭐ Interested: <b>{counts['interested']}</b>\n"
        f"✅ Converted: <b>{counts['converted']}</b>\n\n"
        f"📌 Active work: <b>{active}</b>\n\n"
        "Unassigned now includes every historical bot/DM record still in New status, "
        "whether verified or not. Open it to review one record at a time."
    )


def crm_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🆕 NEW / UNWORKED", callback_data="reports:queue:new")],
            [
                InlineKeyboardButton("📞 FOLLOW-UP", callback_data="reports:queue:followup"),
                InlineKeyboardButton("⭐ INTERESTED", callback_data="reports:queue:interested"),
            ],
            [
                InlineKeyboardButton("🔎 SEARCH", callback_data="reports:search"),
                InlineKeyboardButton("📥 CSV EXPORT", callback_data="reports:exportleads"),
            ],
            [
                InlineKeyboardButton("✅ CONVERTED", callback_data="reports:queue:converted"),
                InlineKeyboardButton("🎯 AD PERFORMANCE", callback_data="reports:adperformance"),
            ],
            [
                InlineKeyboardButton("📚 TEAM GUIDE", callback_data="reports:guide"),
                InlineKeyboardButton("🧰 MORE ADMIN TOOLS", callback_data="reports:advanced"),
            ],
        ]
    )


def _queue_statuses(queue: str):
    mapping = {
        "new": ("new",),
        "followup": ("contacted", "no_answer"),
        "due": ("new", "contacted", "no_answer", "interested"),
        "interested": ("interested",),
        "converted": ("converted",),
    }
    return mapping.get(str(queue or ""), ())


def _queue_title(queue: str) -> str:
    return {
        "new": "🆕 NEW / UNWORKED · ALL TIME",
        "followup": "📞 FOLLOW-UP QUEUE",
        "due": "⏰ FOLLOW-UP DUE NOW",
        "interested": "⭐ INTERESTED LEADS",
        "converted": "✅ CONVERTED LEADS",
    }.get(queue, "📞 CRM LEADS")


def _queue_ids(queue: str):
    statuses = _queue_statuses(queue)
    if not statuses:
        return []
    placeholders = ",".join("?" for _ in statuses)
    ensure_tables()
    now = datetime.now(timezone.utc).isoformat()
    params = list(statuses)

    if queue == "new":
        where_extra = " AND assigned_to IS NULL"
        order = "COALESCE(verified_at, first_seen_at) DESC"
    elif queue == "due":
        where_extra = " AND next_followup_at IS NOT NULL AND next_followup_at <= ?"
        params.append(now)
        order = "next_followup_at ASC"
    elif queue == "followup":
        where_extra = ""
        order = "COALESCE(next_followup_at, updated_at) ASC"
    else:
        where_extra = ""
        order = "updated_at DESC"

    with core.db() as conn:
        rows = conn.execute(
            f"""
            SELECT user_id
            FROM ibetin_leads
            WHERE lead_status IN ({placeholders})
              {where_extra}
            ORDER BY {order}
            """,
            tuple(params),
        ).fetchall()
    return [int(row["user_id"]) for row in rows]


def _queue_item(queue: str, index: int):
    ids = _queue_ids(queue)
    total = len(ids)
    if not total:
        return None, 0, 0
    safe_index = max(0, min(int(index), total - 1))
    return _lead_view(ids[safe_index]), safe_index, total


def _queue_card_keyboard(
    user_id: int,
    queue: str,
    index: int,
    total: int,
) -> InlineKeyboardMarkup:
    rows = list(lead_status_keyboard(int(user_id)).inline_keyboard)
    nav = []
    if index > 0:
        nav.append(
            InlineKeyboardButton(
                "◀️ PREVIOUS",
                callback_data=f"reports:qitem:{queue}:{index-1}",
            )
        )
    if index < total - 1:
        nav.append(
            InlineKeyboardButton(
                "NEXT ▶️",
                callback_data=f"reports:qitem:{queue}:{index+1}",
            )
        )
    if nav:
        # Keep navigation above the final CRM-back row.
        insert_at = max(0, len(rows) - 1)
        rows.insert(insert_at, nav)
    rows.insert(
        max(0, len(rows) - 1),
        [
            InlineKeyboardButton(
                f"📋 {index+1} OF {total}",
                callback_data="reports:no_op",
            )
        ],
    )
    return InlineKeyboardMarkup(rows)


def queue_menu(queue: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔄 REFRESH", callback_data=f"reports:queue:{queue}")],
            [InlineKeyboardButton("⬅️ CRM", callback_data="reports:crm")],
        ]
    )


def advanced_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("👥 BOT USERS", callback_data="reports:users"),
                InlineKeyboardButton("📱 VERIFIED MOBILES", callback_data="reports:liveline"),
            ],
            [
                InlineKeyboardButton("💬 DM USERS", callback_data="reports:business"),
                InlineKeyboardButton("⏰ REMINDERS", callback_data="reports:reminders"),
            ],
            [
                InlineKeyboardButton("🖱 ACTIVITY", callback_data="reports:activity"),
                InlineKeyboardButton("🌐 WEB OPENS", callback_data="reports:web"),
            ],
            [
                InlineKeyboardButton("🎨 TECH/CAMPAIGNS", callback_data="reports:campaigns"),
                InlineKeyboardButton("📦 ALL REPORTS", callback_data="reports:all"),
            ],
            [InlineKeyboardButton("⬅️ BACK TO CRM", callback_data="reports:overview")],
        ]
    )


def _team_guide_text() -> str:
    return (
        "📚 <b>IBETIN CRM · TEAM GUIDE</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "<b>1. NEW LEAD</b>\n"
        "A user has verified their Telegram-linked mobile and agreed to "
        "IBETIN follow-up by call and WhatsApp. Contact them as soon as possible.\n\n"
        "<b>2. CONTACTED</b>\n"
        "Mark this immediately after your first genuine call/WhatsApp attempt.\n\n"
        "<b>3. NO ANSWER</b>\n"
        "Use when the user did not respond. These leads stay in Follow-up.\n\n"
        "<b>4. INTERESTED</b>\n"
        "Use when the user has responded positively and needs conversion follow-up.\n\n"
        "<b>5. CONVERTED</b>\n"
        "Use only after the team's conversion goal has actually been completed.\n\n"
        "<b>6. DNC</b>\n"
        "Use immediately if the user asks not to be contacted. Do not call or "
        "WhatsApp them again.\n\n"
        "<b>Daily routine:</b> New Leads → Follow-up → Interested → Ad Performance.\n"
        "Always update status after every contact attempt so another team member "
        "can understand the lead instantly."
    )


def _ad_performance_text() -> str:
    headers, rows = _report_funnel()
    del headers
    if not rows:
        return (
            "🎯 <b>AD PERFORMANCE</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "No campaign data yet. Use a unique Telegram start code for every ad."
        )

    lines = [
        "🎯 <b>AD PERFORMANCE</b>",
        "━━━━━━━━━━━━━━━━━━",
        "",
        "Shows which Telegram start code produces verified and converted leads.",
        "",
    ]
    for row in rows[:8]:
        campaign, starts, verified, verify_rate, contacted, interested, converted, conversion_rate = row
        lines.extend(
            [
                f"<b>{escape(str(campaign))}</b>",
                f"Starts <b>{starts}</b> → Verified <b>{verified}</b> ({escape(str(verify_rate))}) "
                f"→ Converted <b>{converted}</b> ({escape(str(conversion_rate))})",
                f"Contacted <b>{contacted}</b> · Interested <b>{interested}</b>",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def ad_performance_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📥 EXPORT AD FUNNEL", callback_data="reports:exportfunnel")],
            [InlineKeyboardButton("⬅️ DASHBOARD", callback_data="reports:overview")],
        ]
    )


def _overview_text() -> str:
    ensure_tables()
    now = datetime.now(timezone.utc)
    cutoff_24h = (now - timedelta(hours=24)).isoformat()
    cutoff_7d = (now - timedelta(days=7)).isoformat()

    with core.db() as conn:
        starts_24h = _count(
            conn,
            "SELECT COUNT(*) FROM ibetin_leads WHERE first_seen_at >= ?",
            (cutoff_24h,),
        )
        verified_from_24h_starts = _count(
            conn,
            """
            SELECT COUNT(*)
            FROM ibetin_leads
            WHERE first_seen_at >= ?
              AND verified_at IS NOT NULL
                          """,
            (cutoff_24h,),
        )
        verified_24h = _count(
            conn,
            """
            SELECT COUNT(*)
            FROM ibetin_leads
            WHERE verified_at >= ?
                          """,
            (cutoff_24h,),
        )
        converted_24h = _count(
            conn,
            "SELECT COUNT(*) FROM ibetin_leads WHERE converted_at >= ?",
            (cutoff_24h,),
        )
        starts_7d = _count(
            conn,
            "SELECT COUNT(*) FROM ibetin_leads WHERE first_seen_at >= ?",
            (cutoff_7d,),
        )
        verified_7d = _count(
            conn,
            """
            SELECT COUNT(*)
            FROM ibetin_leads
            WHERE first_seen_at >= ?
              AND verified_at IS NOT NULL
                          """,
            (cutoff_7d,),
        )
        converted_7d = _count(
            conn,
            "SELECT COUNT(*) FROM ibetin_leads WHERE converted_at >= ?",
            (cutoff_7d,),
        )

    counts = _crm_status_counts()
    follow_up = counts["contacted"] + counts["no_answer"]
    verification_rate = (
        round(verified_from_24h_starts * 100.0 / starts_24h, 1)
        if starts_24h else 0.0
    )
    verify_rate_7d = (
        round(verified_7d * 100.0 / starts_7d, 1)
        if starts_7d else 0.0
    )

    return (
        "📊 <b>IBETIN SALES DASHBOARD</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "<b>Last 24 hours</b>\n"
        f"👥 Bot starts: <b>{starts_24h}</b>\n"
        f"📱 New verified leads: <b>{verified_24h}</b>\n"
        f"🔐 Start → verification: <b>{verification_rate}%</b>\n"
        f"✅ Converted: <b>{converted_24h}</b>\n\n"
        "<b>Team work queue</b>\n"
        f"🆕 New to contact: <b>{counts['new']}</b>\n"
        f"📞 Follow-up: <b>{follow_up}</b>\n"
        f"⭐ Interested: <b>{counts['interested']}</b>\n"
        f"✅ Total converted: <b>{counts['converted']}</b>\n\n"
        "<b>Last 7 days</b>\n"
        f"👥 Starts: <b>{starts_7d}</b> · 📱 Verified: <b>{verified_7d}</b> "
        f"(<b>{verify_rate_7d}%</b>) · ✅ Converted: <b>{converted_7d}</b>\n\n"
        "Open <b>CRM / LEAD PIPELINE</b> to work leads. "
        "Technical reports are kept under Advanced."
    )


def report_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📞 OPEN TEAM WORK QUEUE", callback_data="reports:crm")],
            [
                InlineKeyboardButton("🔎 SEARCH", callback_data="reports:search"),
                InlineKeyboardButton("📥 CSV EXPORT", callback_data="reports:exportleads"),
            ],
            [
                InlineKeyboardButton("🎯 AD PERFORMANCE", callback_data="reports:adperformance"),
                InlineKeyboardButton("📚 HELP", callback_data="reports:guide"),
            ],
        ]
    )


async def send_menu(update, context) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message or not is_authorized_admin(user.id):
        if message:
            await message.reply_text("This command is restricted.")
        return
    ensure_tables()
    await message.reply_text(
        _crm_text(),
        parse_mode="HTML",
        reply_markup=crm_menu(),
        disable_web_page_preview=True,
    )


def _csv_safe(value):
    if value is None:
        return ""
    text = str(value)
    if text[:1] in {"=", "+", "-", "@"}:
        return "'" + text
    return text


def _csv_bytes(headers, rows) -> bytes:
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([_csv_safe(v) for v in row])
    return ("\ufeff" + out.getvalue()).encode("utf-8")


def _report_users():
    with core.db() as conn:
        if not _table_exists(conn, "users"):
            return ["User ID"], []
        rows = conn.execute(
            """
            SELECT user_id, username, first_name, language, subscribed, created_at, last_seen
            FROM users ORDER BY last_seen DESC
            """
        ).fetchall()
    return (
        ["User ID", "Username", "First Name", "Language", "Subscribed", "Created At", "Last Seen"],
        [
            [
                r["user_id"], r["username"], r["first_name"], r["language"],
                "Yes" if int(r["subscribed"] or 0) else "No", r["created_at"], r["last_seen"],
            ]
            for r in rows
        ],
    )


def _report_liveline():
    phone_verify.ensure_tables()
    ibetin_leads.ensure_tables()
    with core.db() as conn:
        users, business, phones = _user_maps(conn)
        leads = {
            int(r["user_id"]): dict(r)
            for r in conn.execute("SELECT * FROM ibetin_leads").fetchall()
        }
    rows = []
    for uid, p in sorted(
        phones.items(),
        key=lambda item: str(
            item[1].get("first_verified_at")
            or item[1].get("verified_at")
            or ""
        ),
        reverse=True,
    ):
        username, first_name = _identity(uid, users, business)
        lead = leads.get(uid) or {}
        rows.append([
            uid,
            username,
            first_name,
            p.get("phone_number") or "",
            p.get("first_verified_at") or p.get("verified_at") or "",
            p.get("verification_source") or lead.get("source") or "",
            p.get("campaign") or lead.get("campaign") or "direct",
            "Yes" if int(p.get("contact_consent") or 0) else "No",
            lead.get("lead_status") or "new",
            lead.get("contacted_at") or "",
            lead.get("interested_at") or "",
            lead.get("converted_at") or "",
            users.get(uid, {}).get("last_seen")
            or business.get(uid, {}).get("last_seen")
            or "",
        ])
    return (
        [
            "Telegram User ID", "Username", "First Name", "Mobile Number",
            "First Verified At", "Verification Source", "Campaign",
            "Call + WhatsApp Consent", "Lead Status", "Contacted At",
            "Interested At", "Converted At", "Last Seen",
        ],
        rows,
    )


def _report_livetv():
    ensure_tables()
    with core.db() as conn:
        users, business, phones = _user_maps(conn)
        tv = conn.execute(
            "SELECT user_id, first_opened_at, last_opened_at, open_count FROM live_tv_users ORDER BY last_opened_at DESC"
        ).fetchall()
    rows = []
    for r in tv:
        uid = int(r["user_id"])
        username, first_name = _identity(uid, users, business)
        p = phones.get(uid) or {}
        rows.append([
            uid,
            username,
            first_name,
            p.get("phone_number") or "",
            "Verified" if p.get("phone_number") else "Not verified",
            r["first_opened_at"],
            r["last_opened_at"],
            r["open_count"],
        ])
    return (
        [
            "User ID", "Username", "First Name", "Mobile Number", "Mobile Status",
            "First Live TV Open", "Last Live TV Open", "Live TV Open Count",
        ],
        rows,
    )


def _report_business():
    with core.db() as conn:
        if not _table_exists(conn, "business_customers"):
            return ["User ID"], []
        phones = {}
        if _table_exists(conn, "liveline_verified_users"):
            phones = {
                int(r["user_id"]): dict(r)
                for r in conn.execute(
                    "SELECT user_id, phone_number, verified_at FROM liveline_verified_users"
                ).fetchall()
            }
        rows = conn.execute(
            """
            SELECT customer_id, MAX(username) username, MAX(first_name) first_name, MAX(last_seen) last_seen
            FROM business_customers
            GROUP BY customer_id
            ORDER BY last_seen DESC
            """
        ).fetchall()
    return (
        ["User ID", "Username", "First Name", "Mobile Number", "Mobile Verified At", "Last Seen"],
        [
            [
                r["customer_id"], r["username"], r["first_name"],
                (phones.get(int(r["customer_id"])) or {}).get("phone_number") or "",
                (phones.get(int(r["customer_id"])) or {}).get("verified_at") or "",
                r["last_seen"],
            ]
            for r in rows
        ],
    )


def _report_reminders():
    with core.db() as conn:
        if not _table_exists(conn, "reminder_users"):
            return ["Source", "User ID"], []
        rows = conn.execute(
            """
            SELECT source, user_id, interest, last_activity, last_reminder,
                   reminder_stage, opted_out, updated_at
            FROM reminder_users
            ORDER BY updated_at DESC
            """
        ).fetchall()
    return (
        ["Source", "User ID", "Interest", "Last Activity", "Last Reminder", "Stage", "Opted Out", "Updated At"],
        [
            [
                r["source"], r["user_id"], r["interest"], r["last_activity"], r["last_reminder"],
                r["reminder_stage"], "Yes" if int(r["opted_out"] or 0) else "No", r["updated_at"],
            ]
            for r in rows
        ],
    )


def _report_activity():
    with core.db() as conn:
        if not _table_exists(conn, "clicks"):
            return ["User ID", "Action", "Created At"], []
        users, business, phones = _user_maps(conn)
        rows = conn.execute(
            "SELECT user_id, action, created_at FROM clicks ORDER BY id DESC"
        ).fetchall()
    result = []
    for r in rows:
        uid = int(r["user_id"] or 0)
        username, first_name = _identity(uid, users, business) if uid else ("", "")
        p = phones.get(uid) or {}
        result.append([uid or "", username, first_name, p.get("phone_number") or "", r["action"], r["created_at"]])
    return (
        ["User ID", "Username", "First Name", "Mobile Number", "Action", "Created At"],
        result,
    )


def _report_web():
    with core.db() as conn:
        if not _table_exists(conn, "web_events"):
            return ["Event", "Source", "Created At"], []
        rows = conn.execute(
            "SELECT event, source, created_at FROM web_events ORDER BY id DESC"
        ).fetchall()
    return (
        ["Event", "Source", "Created At"],
        [[r["event"], r["source"], r["created_at"]] for r in rows],
    )


def _report_campaigns():
    rows = []
    with core.db() as conn:
        if _table_exists(conn, "channel_campaigns"):
            for r in conn.execute(
                "SELECT campaign_key, sent_at, message_id, status FROM channel_campaigns ORDER BY sent_at DESC"
            ).fetchall():
                rows.append(["channel_campaign", r["campaign_key"], r["status"], r["sent_at"], r["message_id"], "", ""])
        if _table_exists(conn, "creative_assets"):
            for r in conn.execute(
                "SELECT id, pool, media_type, filename, created_at, active FROM creative_assets ORDER BY id DESC"
            ).fetchall():
                rows.append([
                    "creative", r["id"], "active" if int(r["active"] or 0) else "inactive",
                    r["created_at"], "", r["pool"], r["filename"] or r["media_type"],
                ])
    return (
        ["Type", "Key / ID", "Status", "Created / Sent At", "Message ID", "Pool", "Name / Media"],
        rows,
    )


def _report_leads():
    phone_verify.ensure_tables()
    ibetin_leads.ensure_tables()
    with core.db() as conn:
        users, business, phones = _user_maps(conn)
        rows_db = conn.execute(
            """
            SELECT *
            FROM ibetin_leads
            ORDER BY COALESCE(verified_at, first_seen_at) DESC
            """
        ).fetchall()

    rows = []
    for r in rows_db:
        uid = int(r["user_id"])
        username, first_name = _identity(uid, users, business)
        phone = str(
            r["mobile_number"]
            or (phones.get(uid) or {}).get("phone_number")
            or ""
        )
        verified = uid in phones
        consent = bool(int(r["contact_consent"] or 0))
        if verified and consent:
            consent_status = "Recorded"
        elif verified:
            consent_status = "Legacy / Not Recorded"
        else:
            consent_status = "Not Available / Not Verified"

        rows.append([
            uid,
            username,
            first_name,
            phone,
            "Verified" if verified else "Not Verified",
            r["campaign"],
            r["source"],
            r["first_seen_at"],
            r["verified_at"] or "",
            consent_status,
            r["lead_status"],
            r["assigned_name"] or "",
            r["next_followup_at"] or "",
            r["last_note"] or "",
            r["updated_by_name"] or "",
            r["contacted_at"] or "",
            r["interested_at"] or "",
            r["converted_at"] or "",
            r["no_answer_at"] or "",
            r["dnc_at"] or "",
            r["last_seen_at"],
        ])
    return (
        [
            "User ID", "Username", "First Name", "Mobile Number",
            "Verification Status", "Campaign", "Source", "First Seen",
            "Verified At", "Contact Consent Status", "Lead Status",
            "Assigned To", "Next Follow-up", "Latest Note", "Last Updated By",
            "Contacted At", "Interested At", "Converted At", "No Answer At",
            "DNC At", "Last Seen",
        ],
        rows,
    )


def _report_funnel():
    ibetin_leads.ensure_tables()
    with core.db() as conn:
        rows_db = conn.execute(
            """
            SELECT
                campaign,
                COUNT(*) starts,
                SUM(CASE WHEN verified_at IS NOT NULL THEN 1 ELSE 0 END) verified,
                SUM(CASE WHEN lead_status IN ('contacted','interested','converted') THEN 1 ELSE 0 END) contacted,
                SUM(CASE WHEN lead_status='interested' THEN 1 ELSE 0 END) interested,
                SUM(CASE WHEN lead_status='converted' THEN 1 ELSE 0 END) converted
            FROM ibetin_leads
            GROUP BY campaign
            ORDER BY starts DESC, campaign ASC
            """
        ).fetchall()

    rows = []
    for r in rows_db:
        starts = int(r["starts"] or 0)
        verified = int(r["verified"] or 0)
        converted = int(r["converted"] or 0)
        verify_rate = round((verified * 100.0 / starts), 2) if starts else 0
        conversion_rate = round((converted * 100.0 / verified), 2) if verified else 0
        rows.append([
            r["campaign"],
            starts,
            verified,
            f"{verify_rate}%",
            int(r["contacted"] or 0),
            int(r["interested"] or 0),
            converted,
            f"{conversion_rate}%",
        ])
    return (
        [
            "Campaign", "Bot Starts", "Verified Mobiles", "Verification Rate",
            "Contacted", "Interested", "Converted",
            "Verified-to-Converted Rate",
        ],
        rows,
    )


REPORT_BUILDERS = {
    "users": ("IBETIN_Bot_Users.csv", _report_users),
    "liveline": ("IBETIN_Verified_Users_With_Mobile.csv", _report_liveline),
    "leads": ("IBETIN_CRM_Leads.csv", _report_leads),
    "funnel": ("IBETIN_Ad_Funnel_By_Campaign.csv", _report_funnel),
    "business": ("IBETIN_Business_DM_Users.csv", _report_business),
    "reminders": ("IBETIN_Reminder_Users.csv", _report_reminders),
    "activity": ("IBETIN_Activity_Report.csv", _report_activity),
    "web": ("IBETIN_Web_Opens.csv", _report_web),
    "campaigns": ("IBETIN_Campaigns_Creatives.csv", _report_campaigns),
}


async def _send_report(message, key: str) -> None:
    filename, builder = REPORT_BUILDERS[key]
    headers, rows = builder()
    data = _csv_bytes(headers, rows)
    await message.reply_document(
        document=InputFile(io.BytesIO(data), filename=filename),
        caption=f"📄 {filename}\nRows: {len(rows)}",
    )


async def _send_all(message) -> None:
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        overview = _overview_text().replace("<b>", "").replace("</b>", "")
        zf.writestr("IBETIN_Report_Overview.txt", overview)
        for _, (filename, builder) in REPORT_BUILDERS.items():
            headers, rows = builder()
            zf.writestr(filename, _csv_bytes(headers, rows))
    memory.seek(0)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    await message.reply_document(
        document=InputFile(memory, filename=f"IBETIN_All_Reports_{stamp}.zip"),
        caption="📦 IBETIN complete report pack",
    )


async def admin_text_handler(update, context) -> bool:
    user = update.effective_user
    message = update.effective_message
    if not user or not message or not message.text:
        return False
    if not is_authorized_admin(user.id):
        return False

    mode = str(context.user_data.get("ibetin_admin_input_mode") or "")
    if not mode:
        return False

    actor = _actor_name(user)
    text = message.text.strip()
    context.user_data.pop("ibetin_admin_input_mode", None)

    if mode == "search":
        ids = ibetin_leads.search_leads(text, limit=8)
        if not ids:
            await message.reply_text(
                "🔎 <b>No CRM lead found.</b>\n\n"
                "Search by mobile number, Telegram username or user ID.",
                parse_mode="HTML",
                reply_markup=crm_menu(),
            )
            return True
        await message.reply_text(
            f"🔎 <b>SEARCH RESULTS</b> · {len(ids)} found",
            parse_mode="HTML",
        )
        for uid in ids:
            lead = _lead_view(uid)
            if lead:
                await message.reply_text(
                    _lead_card_text(lead),
                    parse_mode="HTML",
                    reply_markup=lead_status_keyboard(uid),
                    disable_web_page_preview=True,
                )
        return True

    if mode.startswith("note:"):
        try:
            uid = int(mode.split(":", 1)[1])
        except Exception:
            uid = 0
        if uid and ibetin_leads.add_note(uid, text, user.id, actor):
            lead = _lead_view(uid)
            await message.reply_text(
                "✅ <b>Note saved.</b>",
                parse_mode="HTML",
            )
            if lead:
                await message.reply_text(
                    _lead_card_text(lead),
                    parse_mode="HTML",
                    reply_markup=lead_status_keyboard(uid),
                    disable_web_page_preview=True,
                )
        return True

    return False


async def reports_command(update, context) -> None:
    await send_menu(update, context)


async def handle_callback(update, context) -> bool:
    query = update.callback_query
    if not query or not str(query.data or "").startswith(REPORT_PREFIX):
        return False

    user = update.effective_user
    if not user or not is_authorized_admin(user.id):
        try:
            await query.answer("Restricted", show_alert=True)
        except Exception:
            pass
        return True

    try:
        await query.answer()
    except Exception:
        pass

    action = str(query.data).split(":", 1)[1]
    message = query.message or update.effective_message
    if not message:
        return True

    if action == "search":
        context.user_data["ibetin_admin_input_mode"] = "search"
        await message.reply_text(
            "🔎 <b>CRM SEARCH</b>\n\n"
            "Send a mobile number, Telegram username or Telegram user ID.",
            parse_mode="HTML",
        )
        return True

    if action.startswith("assign:"):
        try:
            uid = int(action.split(":", 1)[1])
        except Exception:
            uid = 0
        actor = _actor_name(user)
        if uid and ibetin_leads.assign_lead(uid, user.id, actor):
            lead = _lead_view(uid)
            if lead:
                await query.edit_message_text(
                    _lead_card_text(lead),
                    parse_mode="HTML",
                    reply_markup=lead_status_keyboard(uid),
                    disable_web_page_preview=True,
                )
        return True

    if action.startswith("note:"):
        try:
            uid = int(action.split(":", 1)[1])
        except Exception:
            uid = 0
        if uid:
            context.user_data["ibetin_admin_input_mode"] = f"note:{uid}"
            await message.reply_text(
                "📝 <b>ADD NOTE</b>\n\nSend the note in your next message.",
                parse_mode="HTML",
            )
        return True

    if action.startswith("followup:"):
        try:
            uid = int(action.split(":", 1)[1])
        except Exception:
            uid = 0
        if uid:
            await message.reply_text(
                "⏰ <b>SET NEXT FOLLOW-UP</b>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("1 HOUR", callback_data=f"reports:setfu:1h:{uid}"),
                            InlineKeyboardButton("3 HOURS", callback_data=f"reports:setfu:3h:{uid}"),
                        ],
                        [
                            InlineKeyboardButton("TOMORROW", callback_data=f"reports:setfu:1d:{uid}"),
                            InlineKeyboardButton("CLEAR", callback_data=f"reports:setfu:clear:{uid}"),
                        ],
                    ]
                ),
            )
        return True

    if action.startswith("setfu:"):
        parts = action.split(":")
        if len(parts) == 3:
            _, choice, uid_s = parts
            try:
                uid = int(uid_s)
            except Exception:
                uid = 0
            actor = _actor_name(user)
            now = datetime.now(timezone.utc)
            if choice == "1h":
                target = now + timedelta(hours=1)
            elif choice == "3h":
                target = now + timedelta(hours=3)
            elif choice == "1d":
                target = now + timedelta(days=1)
            else:
                target = None
            if uid and ibetin_leads.set_followup(
                uid,
                target.isoformat() if target else "",
                user.id,
                actor,
            ):
                lead = _lead_view(uid)
                if lead:
                    await message.reply_text(
                        _lead_card_text(lead),
                        parse_mode="HTML",
                        reply_markup=lead_status_keyboard(uid),
                        disable_web_page_preview=True,
                    )
        return True

    if action.startswith("history:"):
        try:
            uid = int(action.split(":", 1)[1])
        except Exception:
            uid = 0
        rows = ibetin_leads.recent_history(uid, 6) if uid else []
        if not rows:
            await message.reply_text("🕘 No CRM history yet.")
            return True
        lines = ["🕘 <b>LEAD HISTORY</b>", "━━━━━━━━━━━━━━━━━━", ""]
        for row in rows:
            when = escape(_fmt_admin_time(str(row.get("created_at") or "")))
            actor = escape(str(row.get("actor_name") or "System"))
            action_name = escape(str(row.get("action") or "").replace("_", " ").title())
            value = escape(str(row.get("value") or "")[:160])
            lines.append(f"• <b>{action_name}</b> · {actor} · {when}")
            if value:
                lines.append(f"  {value}")
        await message.reply_text("\n".join(lines), parse_mode="HTML")
        return True

    if action.startswith("lead:"):
        parts = action.split(":")
        if len(parts) == 3:
            _, status, uid_s = parts
            try:
                uid = int(uid_s)
            except Exception:
                uid = 0
            actor = _actor_name(user)
            if uid and ibetin_leads.set_status(uid, status, user.id, actor):
                if status == "dnc":
                    try:
                        import fantzo_reminders as reminders
                        reminders.set_opt_out("bot", uid, True)
                        reminders.set_opt_out("business_dm", uid, True)
                    except Exception:
                        logger.exception("Could not apply DNC reminder opt-out")

                lead = _lead_view(uid)
                if lead:
                    try:
                        await query.edit_message_text(
                            _lead_card_text(lead),
                            parse_mode="HTML",
                            reply_markup=lead_status_keyboard(uid),
                            disable_web_page_preview=True,
                        )
                    except Exception:
                        label = status.replace("_", " ").title()
                        await message.reply_text(
                            f"✅ Lead status updated to <b>{escape(label)}</b>.",
                            parse_mode="HTML",
                        )
            else:
                await message.reply_text("⚠️ Could not update lead status.")
        return True

    if action == "overview":
        await message.reply_text(
            _crm_text(),
            parse_mode="HTML",
            reply_markup=crm_menu(),
            disable_web_page_preview=True,
        )
        return True

    if action == "crm":
        await message.reply_text(
            _crm_text(),
            parse_mode="HTML",
            reply_markup=crm_menu(),
            disable_web_page_preview=True,
        )
        return True

    if action == "no_op":
        return True

    if action.startswith("queue:"):
        queue = action.split(":", 1)[1]
        lead, index, total = _queue_item(queue, 0)
        title = _queue_title(queue)
        if not lead:
            await message.reply_text(
                f"{title}\n\n✅ No records in this queue right now.",
                parse_mode="HTML",
                reply_markup=queue_menu(queue),
            )
            return True

        await message.reply_text(
            f"{title}\n"
            f"<b>Record {index+1} of {total}</b>\n\n"
            + _lead_card_text(lead),
            parse_mode="HTML",
            reply_markup=_queue_card_keyboard(
                int(lead["user_id"]), queue, index, total
            ),
            disable_web_page_preview=True,
        )
        return True

    if action.startswith("qitem:"):
        parts = action.split(":")
        if len(parts) == 3:
            _, queue, index_s = parts
            try:
                wanted = int(index_s)
            except Exception:
                wanted = 0
            lead, index, total = _queue_item(queue, wanted)
            if lead:
                await query.edit_message_text(
                    f"{_queue_title(queue)}\n"
                    f"<b>Record {index+1} of {total}</b>\n\n"
                    + _lead_card_text(lead),
                    parse_mode="HTML",
                    reply_markup=_queue_card_keyboard(
                        int(lead["user_id"]), queue, index, total
                    ),
                    disable_web_page_preview=True,
                )
        return True

    if action == "adperformance":
        await message.reply_text(
            _ad_performance_text(),
            parse_mode="HTML",
            reply_markup=ad_performance_menu(),
            disable_web_page_preview=True,
        )
        return True

    if action == "guide":
        await message.reply_text(
            _team_guide_text(),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ WORK QUEUE", callback_data="reports:crm")]]
            ),
            disable_web_page_preview=True,
        )
        return True

    if action == "advanced":
        await message.reply_text(
            "🧰 <b>MORE ADMIN TOOLS</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Useful reports and operational tools kept separate from the daily CRM "
            "so the main sales screen stays simple.",
            parse_mode="HTML",
            reply_markup=advanced_menu(),
        )
        return True

    if action == "exportleads":
        await _send_report(message, "leads")
        return True

    if action == "exportfunnel":
        await _send_report(message, "funnel")
        return True

    if action == "all":
        await _send_all(message)
        return True

    if action in REPORT_BUILDERS:
        await _send_report(message, action)
        return True

    return True


def log_admin_diagnostics() -> None:
    """Temporary startup diagnostic for admin authorization mismatch."""
    try:
        with core.db() as conn:
            rows = conn.execute(
                """
                SELECT user_id, username, last_seen
                FROM users
                ORDER BY last_seen DESC
                LIMIT 8
                """
            ).fetchall() if _table_exists(conn, "users") else []
            creative_admin = _setting_user_id("creative_admin_user_id")
            report_admin = _setting_user_id("report_admin_user_id")
        logger.info(
            "IBETIN admin diagnostic original_admin=%s creative_admin=%s report_admin=%s recent=%s",
            core.ADMIN_USER_ID,
            creative_admin,
            report_admin,
            [
                {
                    "user_id": int(r["user_id"]),
                    "username": str(r["username"] or ""),
                    "last_seen": str(r["last_seen"] or ""),
                }
                for r in rows
            ],
        )
    except Exception:
        logger.exception("IBETIN admin diagnostic failed")


async def push_report_center_to_unlocked_admin(application) -> None:
    """Send the report center once to the persistently unlocked operator."""
    admin_id = _setting_user_id("creative_admin_user_id")
    if not admin_id:
        return

    marker = f"report_center_push_v1:{admin_id}"
    try:
        with core.db() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"
            )
            sent = conn.execute(
                "SELECT value FROM settings WHERE key = ?",
                (marker,),
            ).fetchone()
        if sent:
            return

        await application.bot.send_message(
            chat_id=int(admin_id),
            text=(
                "✅ <b>IBETIN ADMIN ACCESS ENABLED</b>\n\n"
                + _overview_text()
            ),
            parse_mode="HTML",
            reply_markup=report_menu(),
            disable_web_page_preview=True,
        )

        with core.db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)",
                (marker, core.now_iso()),
            )
        logger.info("IBETIN report center pushed to unlocked admin")
    except Exception:
        logger.exception("Could not push IBETIN report center to unlocked admin")
