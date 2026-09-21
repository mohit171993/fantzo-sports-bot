import csv
import io
import logging
import os
import zipfile
from datetime import datetime, timedelta, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile

import bot as core
import ibetin_phone_verify as phone_verify
import ibetin_leads

logger = logging.getLogger(__name__)

REPORT_PREFIX = "reports:"


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


def lead_status_keyboard(user_id: int) -> InlineKeyboardMarkup:
    uid = int(user_id)
    return InlineKeyboardMarkup(
        [
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
                )
            ],
        ]
    )


def _overview_text() -> str:
    ensure_tables()
    now = datetime.now(timezone.utc)
    cutoff_24h = (now - timedelta(hours=24)).isoformat()
    cutoff_7d = (now - timedelta(days=7)).isoformat()

    with core.db() as conn:
        total_users = _count(conn, "SELECT COUNT(*) FROM users") if _table_exists(conn, "users") else 0
        active_24h = _count(conn, "SELECT COUNT(*) FROM users WHERE last_seen >= ?", (cutoff_24h,)) if _table_exists(conn, "users") else 0
        active_7d = _count(conn, "SELECT COUNT(*) FROM users WHERE last_seen >= ?", (cutoff_7d,)) if _table_exists(conn, "users") else 0
        subscribers = _count(conn, "SELECT COUNT(*) FROM users WHERE subscribed=1") if _table_exists(conn, "users") else 0
        verified_mobile = _count(conn, "SELECT COUNT(*) FROM liveline_verified_users") if _table_exists(conn, "liveline_verified_users") else 0
        dm_users = _count(conn, "SELECT COUNT(DISTINCT customer_id) FROM business_customers") if _table_exists(conn, "business_customers") else 0
        reminder_users = _count(conn, "SELECT COUNT(*) FROM reminder_users") if _table_exists(conn, "reminder_users") else 0
        opted_out = _count(conn, "SELECT COUNT(*) FROM reminder_users WHERE opted_out=1") if _table_exists(conn, "reminder_users") else 0
        actions = _count(conn, "SELECT COUNT(*) FROM clicks") if _table_exists(conn, "clicks") else 0
        web_opens = _count(conn, "SELECT COUNT(*) FROM web_events") if _table_exists(conn, "web_events") else 0
        creatives = _count(conn, "SELECT COUNT(*) FROM creative_assets WHERE active=1") if _table_exists(conn, "creative_assets") else 0
        campaigns = _count(conn, "SELECT COUNT(*) FROM channel_campaigns") if _table_exists(conn, "channel_campaigns") else 0
        lead_total = _count(conn, "SELECT COUNT(*) FROM ibetin_leads") if _table_exists(conn, "ibetin_leads") else 0
        lead_new = _count(conn, "SELECT COUNT(*) FROM ibetin_leads WHERE lead_status='new'") if _table_exists(conn, "ibetin_leads") else 0
        lead_contacted = _count(conn, "SELECT COUNT(*) FROM ibetin_leads WHERE lead_status='contacted'") if _table_exists(conn, "ibetin_leads") else 0
        lead_interested = _count(conn, "SELECT COUNT(*) FROM ibetin_leads WHERE lead_status='interested'") if _table_exists(conn, "ibetin_leads") else 0
        lead_converted = _count(conn, "SELECT COUNT(*) FROM ibetin_leads WHERE lead_status='converted'") if _table_exists(conn, "ibetin_leads") else 0

    return (
        "📊 <b>IBETIN REPORT CENTER</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Bot users: <b>{total_users}</b>\n"
        f"⚡ Active 24h: <b>{active_24h}</b>\n"
        f"📅 Active 7d: <b>{active_7d}</b>\n"
        f"🔔 Subscribers: <b>{subscribers}</b>\n\n"
        f"📱 Verified IBETIN users: <b>{verified_mobile}</b>\n"
        f"💬 Business DM users: <b>{dm_users}</b>\n\n"
        f"⏰ Reminder users: <b>{reminder_users}</b>\n"
        f"🔕 Reminder opt-outs: <b>{opted_out}</b>\n"
        f"🖱 Bot actions: <b>{actions}</b>\n"
        f"🌐 Web opens: <b>{web_opens}</b>\n"
        f"🎨 Active creatives: <b>{creatives}</b>\n"
        f"📣 Channel campaigns: <b>{campaigns}</b>\n\n"
        f"📞 Lead pipeline: <b>{lead_total}</b>\n"
        f"🆕 New: <b>{lead_new}</b> · 📞 Contacted: <b>{lead_contacted}</b>\n"
        f"⭐ Interested: <b>{lead_interested}</b> · ✅ Converted: <b>{lead_converted}</b>"
    )


def report_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📊 OVERVIEW", callback_data="reports:overview")],
            [
                InlineKeyboardButton("👥 BOT USERS", callback_data="reports:users"),
                InlineKeyboardButton("📱 VERIFIED USERS + MOBILE", callback_data="reports:liveline"),
            ],
            [
                InlineKeyboardButton("📞 LEADS", callback_data="reports:leads"),
                InlineKeyboardButton("🎯 AD FUNNEL", callback_data="reports:funnel"),
            ],
            [InlineKeyboardButton("💬 DM USERS", callback_data="reports:business")],
            [
                InlineKeyboardButton("⏰ REMINDERS", callback_data="reports:reminders"),
                InlineKeyboardButton("🖱 ACTIVITY", callback_data="reports:activity"),
            ],
            [
                InlineKeyboardButton("🌐 WEB OPENS", callback_data="reports:web"),
                InlineKeyboardButton("🎨 CAMPAIGNS", callback_data="reports:campaigns"),
            ],
            [InlineKeyboardButton("📦 DOWNLOAD ALL REPORTS", callback_data="reports:all")],
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
        _overview_text(),
        parse_mode="HTML",
        reply_markup=report_menu(),
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
            "User ID", "Username", "First Name", "Mobile Number",
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
        phone = (phones.get(uid) or {}).get("phone_number") or ""
        rows.append([
            uid,
            username,
            first_name,
            phone,
            r["campaign"],
            r["source"],
            r["first_seen_at"],
            r["verified_at"] or "",
            "Yes" if int(r["contact_consent"] or 0) else "No",
            r["lead_status"],
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
            "Campaign", "Source", "First Bot Start", "Verified At",
            "Call + WhatsApp Consent", "Lead Status", "Contacted At",
            "Interested At", "Converted At", "No Answer At", "DNC At",
            "Last Seen",
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
    "leads": ("IBETIN_Lead_Pipeline.csv", _report_leads),
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

    if action.startswith("lead:"):
        parts = action.split(":")
        if len(parts) == 3:
            _, status, uid_s = parts
            try:
                uid = int(uid_s)
            except Exception:
                uid = 0
            if uid and ibetin_leads.set_status(uid, status):
                label = status.replace("_", " ").title()
                await message.reply_text(
                    f"✅ Lead <code>{uid}</code> marked <b>{label}</b>.",
                    parse_mode="HTML",
                    reply_markup=lead_status_keyboard(uid),
                )
            else:
                await message.reply_text("⚠️ Could not update lead status.")
        return True

    if action == "overview":
        await message.reply_text(
            _overview_text(),
            parse_mode="HTML",
            reply_markup=report_menu(),
        )
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
