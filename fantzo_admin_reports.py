"""Fantzo team admin center.

Provides a CRM-first /admin dashboard for the sales/marketing workflow, plus
campaign attribution, operational reports, exports and advanced diagnostics.
CRM status actions intentionally mutate sales_leads; report/export actions are
read-only.
"""

from __future__ import annotations

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
from telegram.ext import ApplicationHandlerStop, CommandHandler, MessageHandler, filters

import bot_tracked as tracked
import fantzo_banner_queue as banner_queue
import fantzo_crm_ops as crm_ops
import fantzo_reminders as reminders

logger = logging.getLogger(__name__)
core = tracked.app.core
_installed = False

REPORT_PREFIX = "rpt:"
DOWNLOAD_PREFIX = "rptdl:"
DUBAI_TZ = ZoneInfo("Asia/Dubai")
CRM_BATCH_SIZE = 10


def _styled_button(label: str, callback_data: str, style: str | None = None) -> InlineKeyboardButton:
    kwargs = {"callback_data": callback_data}
    if style:
        kwargs["api_kwargs"] = {"style": style}
    return InlineKeyboardButton(label, **kwargs)


def _team_admin_ids() -> set[int]:
    """Fantzo-only team/report admins.

    This intentionally uses Fantzo environment variables and never reads
    iBetin authorization settings.
    """
    ids: set[int] = {int(core.ADMIN_USER_ID)}

    single = os.getenv("FANTZO_REPORT_ADMIN_USER_ID", "").strip()
    if single:
        try:
            ids.add(int(single))
        except Exception:
            logger.warning("Invalid FANTZO_REPORT_ADMIN_USER_ID")

    raw = os.getenv("FANTZO_TEAM_ADMIN_USER_IDS", "").strip()
    if raw:
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                ids.add(int(part))
            except Exception:
                logger.warning("Invalid Fantzo team admin ID: %s", part)

    return ids


def _is_owner(update) -> bool:
    user = update.effective_user
    return bool(user and int(user.id) == int(core.ADMIN_USER_ID))


def _is_admin(update) -> bool:
    user = update.effective_user
    return bool(user and int(user.id) in _team_admin_ids())


def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    return bool(row)


def _scalar(conn, sql: str, params=(), default=0):
    row = conn.execute(sql, params).fetchone()
    if not row:
        return default
    value = row[0]
    return default if value is None else value


def _one(conn, sql: str, params=()):
    return conn.execute(sql, params).fetchone()


def _rows(conn, sql: str, params=()):
    return conn.execute(sql, params).fetchall()


def _cutoffs():
    now = datetime.now(timezone.utc)
    return (
        (now - timedelta(hours=24)).isoformat(),
        (now - timedelta(days=7)).isoformat(),
        now,
    )


def _fmt_int(value) -> str:
    try:
        return f"{int(value):,}"
    except Exception:
        return "0"


def _fmt_dt(value) -> str:
    if not value:
        return "—"
    text = str(value)
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%d %b %Y %H:%M UTC")
    except Exception:
        return escape(text[:40])


def _ops_dashboard_text() -> str:
    """Operational Fantzo dashboard modelled on the proven iBetin team screen."""
    crm_ops.ensure_tables()
    day, _, _ = _cutoffs()
    counts = crm_ops.status_counts()
    due = crm_ops.due_count()
    follow_up = int(counts["CONTACTED"]) + int(counts["NO_ANSWER"])

    with core.db() as conn:
        total = _scalar(conn, "SELECT COUNT(*) FROM users") if _table_exists(conn, "users") else 0
        mobile = _scalar(
            conn,
            "SELECT COUNT(DISTINCT mobile_e164) FROM live_tv_mobile_users "
            "WHERE COALESCE(mobile_e164,'')!=''"
        ) if _table_exists(conn, "live_tv_mobile_users") else 0
        verified = _scalar(
            conn,
            "SELECT COUNT(*) FROM live_tv_mobile_users "
            "WHERE capture_method='telegram_contact'"
        ) if _table_exists(conn, "live_tv_mobile_users") else 0
        sent_24 = _scalar(
            conn,
            "SELECT COUNT(*) FROM reminder_sends "
            "WHERE status='sent' AND sent_at>=?",
            (day,),
        ) if _table_exists(conn, "reminder_sends") else 0

    not_verified = max(int(total) - int(verified), 0)
    # Same working logic as iBetin: users not yet verified are still unworked
    # acquisition records; verified NEW leads are immediately contactable.
    new_unworked = not_verified + int(counts["NEW"])
    assigned_new = crm_ops.new_assigned_count()

    reminders_on = not reminders.is_paused()
    channel_on = not banner_queue.is_paused()

    return (
        "📊 <b>FANTZO TEAM DASHBOARD</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "<b>LEADS</b>\n"
        f"👥 Total: <b>{_fmt_int(total)}</b> · "
        f"📱 Mobile: <b>{_fmt_int(mobile)}</b> · "
        f"✅ Verified: <b>{_fmt_int(verified)}</b>\n"
        f"🆕 New/Unworked: <b>{_fmt_int(new_unworked)}</b> · "
        f"⏰ Due: <b>{_fmt_int(due)}</b> · "
        f"📞 Follow-up: <b>{_fmt_int(follow_up)}</b>\n"
        f"⭐ Interested: <b>{_fmt_int(counts['INTERESTED'])}</b> · "
        f"✅ Converted: <b>{_fmt_int(counts['CONVERTED'])}</b>\n\n"
        "<b>AUTOMATION</b>\n"
        f"🔔 Reminders: {'🟢 ON' if reminders_on else '🔴 OFF'} "
        f"· sent 24h: <b>{_fmt_int(sent_24)}</b>\n"
        f"📣 Channel: {'🟢 ON' if channel_on else '🔴 OFF'} "
        f"· daily <b>{escape(banner_queue.schedule_text())}</b>\n\n"
        f"⚠️ Not verified: <b>{_fmt_int(not_verified)}</b> · "
        f"👨‍💼 New already assigned: <b>{_fmt_int(assigned_new)}</b>"
    )


def _ops_dashboard_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _styled_button("🆕 NEW / UNWORKED", "ops:queue:new", "primary"),
            _styled_button("⏰ DUE NOW", "ops:queue:due", "primary"),
        ],
        [
            _styled_button("👥 ALL LEADS", "ops:queue:all", "primary"),
            _styled_button("📱 SAVED MOBILES", "ops:saved", "primary"),
        ],
        [
            _styled_button("📞 FOLLOW-UP", "ops:queue:followup", "primary"),
            _styled_button("⭐ INTERESTED", "ops:queue:interested", "primary"),
        ],
        [
            _styled_button("🔎 SEARCH", "ops:search", "primary"),
            _styled_button("📥 CSV EXPORT", "ops:export", "primary"),
        ],
        [
            _styled_button("✅ CONVERTED", "ops:queue:converted", "success"),
            _styled_button("🎯 AD PERFORMANCE", "ops:adperformance", "primary"),
        ],
        [
            _styled_button("🤖 AUTOMATION", "ops:automation", "primary"),
            _styled_button("📚 TEAM GUIDE", "ops:guide", "primary"),
        ],
    ])


# Backward-compatible aliases: /admin and old admin-home callbacks now use
# the same operational dashboard.
def _admin_dashboard_text() -> str:
    return _ops_dashboard_text()


def _admin_dashboard_menu(user_id: int | None = None) -> InlineKeyboardMarkup:
    del user_id
    return _ops_dashboard_menu()


def _actor(update) -> tuple[int, str]:
    user = update.effective_user
    if not user:
        return 0, ""
    name = str(user.username or user.first_name or user.id)
    return int(user.id), name[:128]


def _fmt_dubai(value) -> str:
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.astimezone(DUBAI_TZ).strftime("%d %b %Y, %H:%M")
    except Exception:
        return str(value)[:18].replace("T", " ")


def _ops_lead_card(user_id: int) -> str:
    lead = crm_ops.get_lead(user_id)
    if not lead:
        return "⚠️ <b>Lead not available.</b>"

    status = str(lead.get("status") or "NEW").upper()
    icon = {
        "NEW": "🆕",
        "CONTACTED": "📞",
        "NO_ANSWER": "📵",
        "INTERESTED": "⭐",
        "CONVERTED": "✅",
        "NOT_INTERESTED": "➖",
        "DO_NOT_CONTACT": "🚫",
    }.get(status, "📌")

    username = str(lead.get("username") or "")
    telegram = f"@{escape(username)}" if username else "—"
    name = escape(str(lead.get("first_name") or "—"))
    mobile = escape(str(lead.get("mobile_e164") or "—"))
    campaign = escape(str(lead.get("campaign") or "direct"))
    source = escape(str(lead.get("verification_source") or "bot"))
    assigned = escape(str(lead.get("assigned_agent") or "UNASSIGNED"))
    note = escape(str(lead.get("last_note") or lead.get("notes") or "")[:180])
    followup = str(lead.get("next_followup_at") or "")
    consent = bool(lead.get("contact_permission_at"))

    lines = [
        f"{icon} <b>{escape(status.replace('_', ' '))}</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"👤 <b>{name}</b> · {telegram}",
        f"📱 <code>{mobile}</code>",
        f"🎯 Campaign: <code>{campaign}</code>",
        f"📥 Source: <b>{source}</b>",
        f"🕒 Verified: <b>{escape(_fmt_dubai(lead.get('verified_at')))}</b>",
        f"👨‍💼 Assigned: <b>{assigned}</b>",
        f"🔐 {'✅ Contact permission recorded' if consent else '⚠️ Contact permission not recorded'}",
    ]
    if followup:
        lines.append(f"⏰ Next follow-up: <b>{escape(_fmt_dubai(followup))}</b>")
    if note:
        lines.append(f"📝 Note: {note}")
    return "\n".join(lines)


def _ops_lead_keyboard(user_id: int) -> InlineKeyboardMarkup:
    lead = crm_ops.get_lead(user_id) or {}
    digits = re.sub(r"\D", "", str(lead.get("mobile_e164") or ""))[:15]
    status = str(lead.get("status") or "NEW").upper()

    rows = [
        [
            InlineKeyboardButton("🙋 ASSIGN TO ME", callback_data=f"ops:assign:{user_id}"),
            InlineKeyboardButton("📝 NOTE", callback_data=f"ops:note:{user_id}"),
        ],
        [
            InlineKeyboardButton("⏰ FOLLOW-UP", callback_data=f"ops:followup:{user_id}"),
            InlineKeyboardButton("🕘 HISTORY", callback_data=f"ops:history:{user_id}"),
        ],
        [
            InlineKeyboardButton("📞 CONTACTED", callback_data=f"ops:set:{user_id}:CONTACTED"),
            InlineKeyboardButton("⭐ INTERESTED", callback_data=f"ops:set:{user_id}:INTERESTED"),
        ],
        [
            InlineKeyboardButton("✅ CONVERTED", callback_data=f"ops:set:{user_id}:CONVERTED"),
            InlineKeyboardButton("📵 NO ANSWER", callback_data=f"ops:set:{user_id}:NO_ANSWER"),
        ],
        [
            InlineKeyboardButton("🚫 DNC", callback_data=f"ops:set:{user_id}:DO_NOT_CONTACT"),
            InlineKeyboardButton("↩️ NEW", callback_data=f"ops:set:{user_id}:NEW"),
        ],
    ]
    if digits and status != "DO_NOT_CONTACT":
        rows.append([
            InlineKeyboardButton(
                "💬 OPEN WHATSAPP",
                url=f"https://wa.me/{digits}",
                api_kwargs={"style": "success"},
            )
        ])
    rows.append([InlineKeyboardButton("⬅️ DASHBOARD", callback_data="ops:home")])
    return InlineKeyboardMarkup(rows)


def _ops_queue_title(queue: str) -> str:
    return {
        "new": "🆕 NEW / UNWORKED",
        "due": "⏰ DUE NOW",
        "all": "👥 ALL CRM LEADS",
        "followup": "📞 FOLLOW-UP",
        "interested": "⭐ INTERESTED",
        "converted": "✅ CONVERTED",
    }.get(queue, "👥 CRM LEADS")


def _ops_queue_intro(queue: str, count: int) -> str:
    text = (
        f"{_ops_queue_title(queue)}\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"Showing <b>{count}</b> contactable lead(s)."
    )
    if queue == "new":
        with core.db() as conn:
            total = _scalar(conn, "SELECT COUNT(*) FROM users") if _table_exists(conn, "users") else 0
            verified = _scalar(
                conn,
                "SELECT COUNT(*) FROM live_tv_mobile_users WHERE capture_method='telegram_contact'"
            ) if _table_exists(conn, "live_tv_mobile_users") else 0
        pending = max(int(total) - int(verified), 0)
        text += (
            f"\n\n⚠️ <b>{_fmt_int(pending)}</b> additional bot user(s) are still "
            "unverified and become contactable only after mobile verification."
        )
    return text


def _automation_text() -> str:
    day, _, _ = _cutoffs()
    with core.db() as conn:
        sent_24 = _scalar(
            conn,
            "SELECT COUNT(*) FROM reminder_sends WHERE status='sent' AND sent_at>=?",
            (day,),
        ) if _table_exists(conn, "reminder_sends") else 0
        queued = _scalar(
            conn,
            "SELECT COUNT(*) FROM live_tv_banners WHERE status='queued'"
        ) if _table_exists(conn, "live_tv_banners") else 0

    return (
        "🤖 <b>FANTZO AUTOMATION</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"🔔 Lead reminders: <b>{'ON' if not reminders.is_paused() else 'OFF'}</b>\n"
        f"📨 Reminders sent 24h: <b>{_fmt_int(sent_24)}</b>\n"
        f"🌙 Quiet hours: <b>22:00–08:00 Dubai</b>\n\n"
        f"📣 Channel automation: <b>{'ON' if not banner_queue.is_paused() else 'OFF'}</b>\n"
        f"🕒 Daily schedule: <b>{escape(banner_queue.schedule_text())}</b>\n"
        f"🖼 Queued channel banners: <b>{_fmt_int(queued)}</b>"
    )


def _automation_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "⏸ REMINDERS" if not reminders.is_paused() else "▶️ REMINDERS",
                callback_data="ops:toggle_reminders",
            ),
            InlineKeyboardButton(
                "⏸ CHANNEL" if not banner_queue.is_paused() else "▶️ CHANNEL",
                callback_data="ops:toggle_channel",
            ),
        ],
        [InlineKeyboardButton("⬅️ DASHBOARD", callback_data="ops:home")],
    ])


def _followup_menu(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏰ +2 HOURS", callback_data=f"ops:fupset:{user_id}:2h"),
            InlineKeyboardButton("🌅 TOMORROW 10AM", callback_data=f"ops:fupset:{user_id}:tom10"),
        ],
        [
            InlineKeyboardButton("📅 +24 HOURS", callback_data=f"ops:fupset:{user_id}:24h"),
            InlineKeyboardButton("📆 +3 DAYS", callback_data=f"ops:fupset:{user_id}:3d"),
        ],
        [InlineKeyboardButton("🧹 CLEAR FOLLOW-UP", callback_data=f"ops:fupset:{user_id}:clear")],
        [InlineKeyboardButton("⬅️ LEAD", callback_data=f"ops:lead:{user_id}")],
    ])


def _followup_iso(option: str) -> str:
    now = datetime.now(timezone.utc)
    if option == "2h":
        return (now + timedelta(hours=2)).isoformat()
    if option == "24h":
        return (now + timedelta(hours=24)).isoformat()
    if option == "3d":
        return (now + timedelta(days=3)).isoformat()
    if option == "tom10":
        local = datetime.now(DUBAI_TZ)
        tomorrow = (local + timedelta(days=1)).date()
        target = datetime(
            tomorrow.year, tomorrow.month, tomorrow.day, 10, 0,
            tzinfo=DUBAI_TZ,
        )
        return target.astimezone(timezone.utc).isoformat()
    return ""


def _history_text(user_id: int) -> str:
    rows = crm_ops.recent_history(user_id)
    if not rows:
        return "🕘 <b>LEAD HISTORY</b>\n\nNo history yet."
    lines = ["🕘 <b>LEAD HISTORY</b>", "━━━━━━━━━━━━━━━━━━", ""]
    for row in rows:
        actor = escape(str(row.get("actor_name") or "system"))
        action = escape(str(row.get("action") or ""))
        value = escape(str(row.get("value") or ""))
        when = escape(_fmt_dubai(row.get("created_at")))
        lines.append(f"• <b>{action}</b>: {value}\n  {actor} · {when}")
    return "\n".join(lines)



def _campaigns_text() -> str:
    with core.db() as conn:
        if not _table_exists(conn, "lead_attribution"):
            return "📣 <b>CAMPAIGNS</b>\n\nNo campaign data yet."

        rows = _rows(
            conn,
            """
            SELECT a.campaign,
                   COUNT(DISTINCT a.user_id) starts,
                   COUNT(DISTINCT m.user_id) verified,
                   COUNT(DISTINCT s.mobile_e164) leads,
                   COUNT(DISTINCT CASE WHEN s.status='INTERESTED' THEN s.mobile_e164 END) interested,
                   COUNT(DISTINCT CASE WHEN s.status='CONVERTED' THEN s.mobile_e164 END) converted
            FROM lead_attribution a
            LEFT JOIN lead_user_map m ON m.user_id=a.user_id
            LEFT JOIN sales_leads s ON s.mobile_e164=m.mobile_e164
            WHERE a.campaign LIKE 'ad_%' OR a.campaign LIKE 'ref_%'
            GROUP BY a.campaign
            ORDER BY starts DESC, verified DESC
            LIMIT 12
            """
        )

    lines = []
    for row in rows:
        starts = int(row["starts"] or 0)
        verified = int(row["verified"] or 0)
        rate = (verified / starts * 100.0) if starts else 0.0
        lines.append(
            f"• <code>{escape(str(row['campaign']))}</code>\n"
            f"  {_fmt_int(starts)} starts → {_fmt_int(verified)} verified "
            f"(<b>{rate:.1f}%</b>) → ⭐ {_fmt_int(row['interested'])} "
            f"→ ✅ {_fmt_int(row['converted'])}"
        )

    body = "\n".join(lines) or "• No paid/referral campaigns tracked yet."
    return (
        "📣 <b>TELEGRAM ADS · CAMPAIGNS</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"{body}\n\n"
        "<b>How the team should use this</b>\n"
        "1. Give every ad its own tracking code.\n"
        "2. Compare start → verified percentage.\n"
        "3. Compare interested and converted leads, not just bot starts.\n"
        "4. Stop spending on campaigns that create starts but weak verified/converted leads.\n\n"
        "Create a link with: <code>/adlink cricket_01</code>"
    )


def _campaigns_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_styled_button("🎯 FULL FUNNEL", "rpt:leads", "success")],
        [InlineKeyboardButton("🏠 ADMIN HOME", callback_data="adm:home")],
    ])


def _tools_text() -> str:
    return (
        "🧰 <b>FANTZO ADMIN TOOLS</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "<b>USE REGULARLY</b>\n"
        "📣 <code>/adlink NAME</code> — create a tracked Telegram Ads link.\n"
        "💼 <code>/lead USER</code> — find a lead directly.\n"
        "👤 <code>/leadassign USER AGENT</code> — assign a salesperson.\n"
        "📝 <code>/leadnote USER NOTE</code> — save sales notes.\n\n"
        "<b>MARKETING / CONTENT</b>\n"
        "📢 <code>/broadcast MESSAGE</code> — send a message to bot users. Use carefully.\n"
        "🖼 <code>/banners</code> — manage the Live TV banner queue.\n"
        "🖼 <code>/setbanner</code> — change the Fantzo home banner.\n\n"
        "<b>TECHNICAL · NOT DAILY TEAM WORK</b>\n"
        "🩺 <code>/apistatus</code> — sports API health.\n"
        "💾 <code>/backupstatus</code> / <code>/backupnow</code> — database backups.\n"
        "📺 <code>/livetvadmin</code> — Live TV admin access.\n"
        "🤖 <code>/autoreply</code>, <code>/stats</code>, <code>/trialtv</code> — diagnostics/testing.\n\n"
        "<i>Technical options are intentionally kept off the main dashboard so the team can focus on leads.</i>"
    )


def _tools_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📈 REPORTS", callback_data="rpt:home")],
        [InlineKeyboardButton("🧪 ADVANCED REPORTS", callback_data="adm:advanced_reports")],
        [InlineKeyboardButton("🏠 ADMIN HOME", callback_data="adm:home")],
    ])


def _team_guide_text() -> str:
    return (
        "❓ <b>FANTZO TEAM WORKFLOW</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "<b>1 · WORK HOT LEADS FIRST</b>\n"
        "Open <b>🆕 NEW</b>, then <b>⭐ INTERESTED</b>. Contact them quickly by phone/WhatsApp.\n\n"
        "<b>2 · UPDATE EVERY CONTACT</b>\n"
        "After every attempt choose CONTACTED, NO ANSWER, INTERESTED, CONVERTED, "
        "NOT INTERESTED or DO NOT CONTACT. This is what makes campaign reporting accurate.\n\n"
        "<b>3 · USE NOTES & ASSIGNMENT</b>\n"
        "Use <code>/leadassign</code> to show who owns the lead and <code>/leadnote</code> "
        "for the latest sales context.\n\n"
        "<b>4 · RESPECT DO NOT CONTACT</b>\n"
        "Never call or WhatsApp a lead marked DO NOT CONTACT.\n\n"
        "<b>5 · CHECK CAMPAIGNS</b>\n"
        "Judge ads on verified leads and conversions, not only clicks/starts.\n\n"
        "<b>6 · END OF SHIFT</b>\n"
        "NEW should be close to zero, NO ANSWER should have a clear follow-up plan, "
        "and every converted lead should be marked CONVERTED."
    )


def _team_guide_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_styled_button("💼 OPEN CRM", "crm:home", "success")],
        [InlineKeyboardButton("🏠 ADMIN HOME", callback_data="adm:home")],
    ])


def _report_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 OVERVIEW", callback_data="rpt:overview")],
        [
            InlineKeyboardButton("👥 BOT USERS", callback_data="rpt:users"),
            InlineKeyboardButton("📱 VERIFIED USERS + MOBILE", callback_data="rpt:mobile"),
        ],
        [_styled_button("💼 CRM / LEADS", "crm:home", "success")],
        [InlineKeyboardButton("💬 DM USERS", callback_data="rpt:business")],
        [
            InlineKeyboardButton("⏰ FOLLOW-UP", callback_data="rpt:reminders"),
            InlineKeyboardButton("🖱 ACTIVITY", callback_data="rpt:daily"),
        ],
        [
            InlineKeyboardButton("🌐 WEB OPENS", callback_data="rpt:web"),
            InlineKeyboardButton("📣 CAMPAIGNS", callback_data="adm:campaigns"),
        ],
        [_styled_button("📦 DOWNLOAD ALL REPORTS", "rptdl:all", "success")],
        [InlineKeyboardButton("🏠 ADMIN HOME", callback_data="adm:home")],
    ])


def _advanced_reports_menu() -> InlineKeyboardMarkup:
    """Lower-frequency diagnostic reports, kept away from the main workflow."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("👥 All Users", callback_data="rpt:users"),
                InlineKeyboardButton("🎯 Raw Engagement", callback_data="rpt:engagement"),
            ],
            [
                InlineKeyboardButton("📺 Live TV", callback_data="rpt:livetv"),
                InlineKeyboardButton("🌐 Fantzo Opens", callback_data="rpt:web"),
            ],
            [
                InlineKeyboardButton("⭐ Favourites", callback_data="rpt:favourites"),
                InlineKeyboardButton("🖼 Banner Queue", callback_data="rpt:banners"),
            ],
            [InlineKeyboardButton("⬅️ REPORTS", callback_data="rpt:home")],
        ]
    )


def _back_menu(download_key: str | None = None) -> InlineKeyboardMarkup:
    rows = []
    if download_key:
        rows.append([_styled_button("⬇️ DOWNLOAD CSV", f"rptdl:{download_key}", "success")])
    rows.append([
        InlineKeyboardButton("⬅️ REPORTS", callback_data="rpt:home"),
        InlineKeyboardButton("🏠 ADMIN", callback_data="adm:home"),
    ])
    return InlineKeyboardMarkup(rows)


def _downloads_menu() -> InlineKeyboardMarkup:
    """Keep the everyday sales exports simple; raw product data is advanced."""
    return InlineKeyboardMarkup(
        [
            [
                _styled_button("🎯 LEADS CSV", "rptdl:leads", "success"),
                _styled_button("📱 VERIFIED CSV", "rptdl:mobile", "success"),
            ],
            [
                InlineKeyboardButton("💬 BUSINESS CSV", callback_data="rptdl:business"),
                InlineKeyboardButton("🔔 FOLLOW-UP CSV", callback_data="rptdl:reminders"),
            ],
            [InlineKeyboardButton("📅 DAILY ACTIVITY CSV", callback_data="rptdl:daily")],
            [_styled_button("📦 COMPLETE BACKUP EXPORT", "rptdl:all", "success")],
            [InlineKeyboardButton("🧪 ADVANCED EXPORTS", callback_data="adm:advanced_exports")],
            [InlineKeyboardButton("⬅️ REPORTS", callback_data="rpt:home")],
            [InlineKeyboardButton("🏠 ADMIN HOME", callback_data="adm:home")],
        ]
    )


def _advanced_downloads_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👥 Users CSV", callback_data="rptdl:users"),
            InlineKeyboardButton("🎯 Engagement CSV", callback_data="rptdl:engagement"),
        ],
        [
            InlineKeyboardButton("📺 Live TV CSV", callback_data="rptdl:livetv"),
            InlineKeyboardButton("🌐 Fantzo Opens CSV", callback_data="rptdl:web"),
        ],
        [
            InlineKeyboardButton("⭐ Favourites CSV", callback_data="rptdl:favourites"),
            InlineKeyboardButton("🖼 Banners CSV", callback_data="rptdl:banners"),
        ],
        [InlineKeyboardButton("⬅️ EXPORTS", callback_data="rpt:downloads")],
    ])


def _overview_text() -> str:
    day, week, now = _cutoffs()
    with core.db() as conn:
        users = _scalar(conn, "SELECT COUNT(*) FROM users") if _table_exists(conn, "users") else 0
        new_24 = _scalar(conn, "SELECT COUNT(*) FROM users WHERE created_at>=?", (day,)) if _table_exists(conn, "users") else 0
        active_24 = _scalar(conn, "SELECT COUNT(*) FROM users WHERE last_seen>=?", (day,)) if _table_exists(conn, "users") else 0
        active_7 = _scalar(conn, "SELECT COUNT(*) FROM users WHERE last_seen>=?", (week,)) if _table_exists(conn, "users") else 0
        subscribers = _scalar(conn, "SELECT COUNT(*) FROM users WHERE subscribed=1") if _table_exists(conn, "users") else 0

        clicks = _scalar(conn, "SELECT COUNT(*) FROM clicks") if _table_exists(conn, "clicks") else 0
        clicks_24 = _scalar(conn, "SELECT COUNT(*) FROM clicks WHERE created_at>=?", (day,)) if _table_exists(conn, "clicks") else 0
        live_tv = _scalar(conn, "SELECT COUNT(*) FROM clicks WHERE action='live_tv_status'") if _table_exists(conn, "clicks") else 0
        live_tv_users = _scalar(conn, "SELECT COUNT(DISTINCT user_id) FROM clicks WHERE action='live_tv_status'") if _table_exists(conn, "clicks") else 0
        business = _scalar(conn, "SELECT COUNT(*) FROM clicks WHERE action LIKE 'business_dm:%'") if _table_exists(conn, "clicks") else 0

        web_opens = _scalar(conn, "SELECT COUNT(*) FROM web_events WHERE event='fantzo_open'") if _table_exists(conn, "web_events") else 0
        reminder_sent = _scalar(conn, "SELECT COUNT(*) FROM reminder_sends WHERE status='sent'") if _table_exists(conn, "reminder_sends") else 0
        favourites = _scalar(conn, "SELECT COUNT(*) FROM user_favourites WHERE alerts_enabled=1") if _table_exists(conn, "user_favourites") else 0
        queued_banners = _scalar(conn, "SELECT COUNT(*) FROM live_tv_banners WHERE status='queued'") if _table_exists(conn, "live_tv_banners") else 0
        mobile_users = _scalar(conn, "SELECT COUNT(*) FROM live_tv_mobile_users WHERE capture_method='telegram_contact'") if _table_exists(conn, "live_tv_mobile_users") else 0
        ad_starts = _scalar(conn, "SELECT COUNT(DISTINCT user_id) FROM lead_attribution WHERE campaign LIKE 'ad_%'") if _table_exists(conn, "lead_attribution") else 0
        sales_leads = _scalar(conn, "SELECT COUNT(*) FROM sales_leads") if _table_exists(conn, "sales_leads") else 0
        converted_leads = _scalar(conn, "SELECT COUNT(*) FROM sales_leads WHERE status='CONVERTED'") if _table_exists(conn, "sales_leads") else 0
        business_verified = 0
        if _table_exists(conn, "live_tv_mobile_users") and _table_exists(conn, "business_welcomes"):
            business_verified = _scalar(
                conn,
                "SELECT COUNT(DISTINCT w.customer_id) "
                "FROM business_welcomes w "
                "JOIN live_tv_mobile_users m ON m.user_id=w.customer_id "
                "WHERE m.capture_method='telegram_contact'"
            )

    return (
        "📊 <b>FANTZO REPORTS · OVERVIEW</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Users: <b>{_fmt_int(users)}</b>\n"
        f"🆕 New users (24h): <b>{_fmt_int(new_24)}</b>\n"
        f"🟢 Active users: <b>{_fmt_int(active_24)}</b> (24h) · <b>{_fmt_int(active_7)}</b> (7d)\n"
        f"🔔 Alert subscribers: <b>{_fmt_int(subscribers)}</b>\n\n"
        f"🎯 Bot actions: <b>{_fmt_int(clicks)}</b> total · <b>{_fmt_int(clicks_24)}</b> in 24h\n"
        f"📺 Live TV opens: <b>{_fmt_int(live_tv)}</b> from <b>{_fmt_int(live_tv_users)}</b> users\n"
        f"📱 Telegram-verified numbers: <b>{_fmt_int(mobile_users)}</b>\n"
        f"📣 Telegram Ad starts: <b>{_fmt_int(ad_starts)}</b>\n"
        f"🎯 Deduplicated leads: <b>{_fmt_int(sales_leads)}</b> · ✅ Converted: <b>{_fmt_int(converted_leads)}</b>\n"
        f"💬 Business DM verified: <b>{_fmt_int(business_verified)}</b>\n"
        f"🌐 Fantzo web opens: <b>{_fmt_int(web_opens)}</b>\n"
        f"💬 Business DM events: <b>{_fmt_int(business)}</b>\n"
        f"📨 Reminders sent: <b>{_fmt_int(reminder_sent)}</b>\n"
        f"⭐ Favourite alerts ON: <b>{_fmt_int(favourites)}</b>\n"
        f"🖼 Banners queued: <b>{_fmt_int(queued_banners)}</b>\n\n"
        f"🕒 Generated: <b>{now.strftime('%d %b %Y %H:%M UTC')}</b>"
    )


def _users_text() -> str:
    day, week, _ = _cutoffs()
    with core.db() as conn:
        if not _table_exists(conn, "users"):
            return "👥 <b>USERS REPORT</b>\n\nNo user table is available."
        total = _scalar(conn, "SELECT COUNT(*) FROM users")
        new_24 = _scalar(conn, "SELECT COUNT(*) FROM users WHERE created_at>=?", (day,))
        new_7 = _scalar(conn, "SELECT COUNT(*) FROM users WHERE created_at>=?", (week,))
        active_24 = _scalar(conn, "SELECT COUNT(*) FROM users WHERE last_seen>=?", (day,))
        active_7 = _scalar(conn, "SELECT COUNT(*) FROM users WHERE last_seen>=?", (week,))
        subs = _scalar(conn, "SELECT COUNT(*) FROM users WHERE subscribed=1")
        langs = _rows(conn, "SELECT COALESCE(language,'unknown') language, COUNT(*) c FROM users GROUP BY language ORDER BY c DESC LIMIT 5")
    lang_text = "\n".join(f"• {escape(str(r['language']))}: <b>{_fmt_int(r['c'])}</b>" for r in langs) or "• No language data"
    return (
        "👥 <b>USERS REPORT</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"Total users: <b>{_fmt_int(total)}</b>\n"
        f"New users: <b>{_fmt_int(new_24)}</b> (24h) · <b>{_fmt_int(new_7)}</b> (7d)\n"
        f"Active users: <b>{_fmt_int(active_24)}</b> (24h) · <b>{_fmt_int(active_7)}</b> (7d)\n"
        f"Alerts ON: <b>{_fmt_int(subs)}</b>\n\n"
        f"<b>Languages</b>\n{lang_text}"
    )


def _engagement_text() -> str:
    day, week, _ = _cutoffs()
    with core.db() as conn:
        if not _table_exists(conn, "clicks"):
            return "🎯 <b>ENGAGEMENT REPORT</b>\n\nNo click data is available."
        total = _scalar(conn, "SELECT COUNT(*) FROM clicks")
        count_24 = _scalar(conn, "SELECT COUNT(*) FROM clicks WHERE created_at>=?", (day,))
        count_7 = _scalar(conn, "SELECT COUNT(*) FROM clicks WHERE created_at>=?", (week,))
        uniq = _scalar(conn, "SELECT COUNT(DISTINCT user_id) FROM clicks")
        uniq_7 = _scalar(conn, "SELECT COUNT(DISTINCT user_id) FROM clicks WHERE created_at>=?", (week,))
        top = _rows(conn, "SELECT action, COUNT(*) c, COUNT(DISTINCT user_id) u FROM clicks GROUP BY action ORDER BY c DESC LIMIT 8")
    top_text = "\n".join(
        f"• {escape(str(r['action']))}: <b>{_fmt_int(r['c'])}</b> · {_fmt_int(r['u'])} users" for r in top
    ) or "• No activity yet"
    return (
        "🎯 <b>ENGAGEMENT REPORT</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"Actions: <b>{_fmt_int(total)}</b> total\n"
        f"Last 24h: <b>{_fmt_int(count_24)}</b>\n"
        f"Last 7d: <b>{_fmt_int(count_7)}</b>\n"
        f"Users with actions: <b>{_fmt_int(uniq)}</b> all-time · <b>{_fmt_int(uniq_7)}</b> in 7d\n\n"
        f"<b>Top actions · all time</b>\n{top_text}"
    )


def _livetv_text() -> str:
    day, week, _ = _cutoffs()
    with core.db() as conn:
        if not _table_exists(conn, "clicks"):
            return "📺 <b>LIVE TV REPORT</b>\n\nNo Live TV tracking data is available."
        total = _scalar(conn, "SELECT COUNT(*) FROM clicks WHERE action='live_tv_status'")
        unique = _scalar(conn, "SELECT COUNT(DISTINCT user_id) FROM clicks WHERE action='live_tv_status'")
        count_24 = _scalar(conn, "SELECT COUNT(*) FROM clicks WHERE action='live_tv_status' AND created_at>=?", (day,))
        count_7 = _scalar(conn, "SELECT COUNT(*) FROM clicks WHERE action='live_tv_status' AND created_at>=?", (week,))
        unique_24 = _scalar(conn, "SELECT COUNT(DISTINCT user_id) FROM clicks WHERE action='live_tv_status' AND created_at>=?", (day,))
        unique_7 = _scalar(conn, "SELECT COUNT(DISTINCT user_id) FROM clicks WHERE action='live_tv_status' AND created_at>=?", (week,))
        first_last = _one(conn, "SELECT MIN(created_at) first_at, MAX(created_at) last_at FROM clicks WHERE action='live_tv_status'")
        callback_opens = _scalar(conn, "SELECT COUNT(*) FROM growth_events WHERE event='live_tv_open'") if _table_exists(conn, "growth_events") else 0
        mobile_users = _scalar(conn, "SELECT COUNT(*) FROM live_tv_mobile_users WHERE capture_method='telegram_contact'") if _table_exists(conn, "live_tv_mobile_users") else 0
    derived_deeplinks = max(int(total) - int(callback_opens), 0)
    return (
        "📺 <b>LIVE TV REPORT</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"Total Live TV entries: <b>{_fmt_int(total)}</b>\n"
        f"Unique users: <b>{_fmt_int(unique)}</b>\n\n"
        f"24h: <b>{_fmt_int(count_24)}</b> opens · <b>{_fmt_int(unique_24)}</b> users\n"
        f"7d: <b>{_fmt_int(count_7)}</b> opens · <b>{_fmt_int(unique_7)}</b> users\n"
        f"📱 Mobile numbers captured: <b>{_fmt_int(mobile_users)}</b>\n\n"
        f"In-bot status-button opens: <b>{_fmt_int(callback_opens)}</b>\n"
        f"Deep-link / other entries (derived): <b>{_fmt_int(derived_deeplinks)}</b>\n\n"
        f"First recorded: <b>{_fmt_dt(first_last['first_at'] if first_last else None)}</b>\n"
        f"Latest recorded: <b>{_fmt_dt(first_last['last_at'] if first_last else None)}</b>\n\n"
        "<i>Live TV totals use clicks.action=live_tv_status as the canonical count.</i>"
    )




def _lead_funnel_text() -> str:
    with core.db() as conn:
        if not _table_exists(conn, "lead_attribution"):
            return "🎯 <b>LEAD FUNNEL</b>\n\nNo paid-ads lead data is available yet."

        starts = _scalar(conn, "SELECT COUNT(DISTINCT user_id) FROM lead_attribution")
        ad_starts = _scalar(
            conn,
            "SELECT COUNT(DISTINCT user_id) FROM lead_attribution WHERE campaign LIKE 'ad_%'"
        )
        prompts = _scalar(
            conn,
            "SELECT COUNT(DISTINCT user_id) FROM lead_events WHERE event='verification_prompt'"
        ) if _table_exists(conn, "lead_events") else 0
        verified_users = _scalar(conn, "SELECT COUNT(DISTINCT user_id) FROM lead_user_map") if _table_exists(conn, "lead_user_map") else 0
        leads = _scalar(conn, "SELECT COUNT(*) FROM sales_leads") if _table_exists(conn, "sales_leads") else 0
        contacted = _scalar(
            conn,
            "SELECT COUNT(*) FROM sales_leads WHERE status!='NEW'"
        ) if _table_exists(conn, "sales_leads") else 0
        interested = _scalar(
            conn,
            "SELECT COUNT(*) FROM sales_leads WHERE status='INTERESTED'"
        ) if _table_exists(conn, "sales_leads") else 0
        converted = _scalar(
            conn,
            "SELECT COUNT(*) FROM sales_leads WHERE status='CONVERTED'"
        ) if _table_exists(conn, "sales_leads") else 0
        reminder_recovered = _scalar(
            conn,
            "SELECT COUNT(DISTINCT user_id) FROM lead_events "
            "WHERE event='verified_mobile' AND value LIKE 'bot_reminder|%'"
        ) if _table_exists(conn, "lead_events") else 0

        ad_verified = 0
        if _table_exists(conn, "lead_user_map"):
            ad_verified = _scalar(
                conn,
                "SELECT COUNT(DISTINCT a.user_id) "
                "FROM lead_attribution a JOIN lead_user_map m ON m.user_id=a.user_id "
                "WHERE a.campaign LIKE 'ad_%'"
            )

        status_rows = _rows(
            conn,
            "SELECT status,COUNT(*) c FROM sales_leads GROUP BY status ORDER BY c DESC"
        ) if _table_exists(conn, "sales_leads") else []

        campaign_rows = _rows(
            conn,
            """
            SELECT a.campaign,
                   COUNT(DISTINCT a.user_id) starts,
                   COUNT(DISTINCT lum.user_id) verified_users,
                   COUNT(DISTINCT s.mobile_e164) leads,
                   COUNT(DISTINCT CASE WHEN s.status='CONVERTED' THEN s.mobile_e164 END) converted
            FROM lead_attribution a
            LEFT JOIN lead_user_map lum ON lum.user_id=a.user_id
            LEFT JOIN sales_leads s ON s.mobile_e164=lum.mobile_e164
            GROUP BY a.campaign
            ORDER BY starts DESC, verified_users DESC
            LIMIT 8
            """
        )

    verification_rate = (float(verified_users) / float(starts) * 100.0) if starts else 0.0
    ad_verification_rate = (float(ad_verified) / float(ad_starts) * 100.0) if ad_starts else 0.0
    lead_conversion = (float(converted) / float(leads) * 100.0) if leads else 0.0

    status_text = "\n".join(
        f"• {escape(str(r['status']).replace('_', ' '))}: <b>{_fmt_int(r['c'])}</b>"
        for r in status_rows
    ) or "• No lead statuses yet"

    campaign_text = "\n".join(
        f"• <code>{escape(str(r['campaign']))}</code>: "
        f"{_fmt_int(r['starts'])} starts → {_fmt_int(r['verified_users'])} verified "
        f"→ {_fmt_int(r['leads'])} leads → {_fmt_int(r['converted'])} converted"
        for r in campaign_rows
    ) or "• No campaign attribution yet"

    return (
        "🎯 <b>PAID ADS · LEAD FUNNEL</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"Bot starts tracked: <b>{_fmt_int(starts)}</b>\n"
        f"Telegram Ad starts: <b>{_fmt_int(ad_starts)}</b>\n"
        f"Verification prompts: <b>{_fmt_int(prompts)}</b>\n"
        f"Verified Telegram users: <b>{_fmt_int(verified_users)}</b>\n"
        f"Deduplicated mobile leads: <b>{_fmt_int(leads)}</b>\n"
        f"Reminder-assisted verifications: <b>{_fmt_int(reminder_recovered)}</b>\n\n"
        f"Overall start → verified: <b>{verification_rate:.1f}%</b>\n"
        f"Ad start → verified: <b>{ad_verification_rate:.1f}%</b>\n"
        f"Lead → converted: <b>{lead_conversion:.1f}%</b>\n\n"
        f"☎️ Contacted/updated: <b>{_fmt_int(contacted)}</b>\n"
        f"🔥 Interested: <b>{_fmt_int(interested)}</b>\n"
        f"✅ Converted: <b>{_fmt_int(converted)}</b>\n\n"
        f"<b>Lead statuses</b>\n{status_text}\n\n"
        f"<b>Campaigns</b>\n{campaign_text}\n\n"
        "<b>Admin lead controls</b>\n"
        "• <code>/lead &lt;user_id | @username | mobile&gt;</code>\n"
        "• <code>/leadstatus &lt;lead&gt; CONTACTED</code>\n"
        "• <code>/leadassign &lt;lead&gt; Agent Name</code>\n"
        "• <code>/leadnote &lt;lead&gt; note</code>\n"
        "• <code>/adlink cricket_01</code>\n\n"
        "<i>Use a different ?start=ad_... code for each paid campaign.</i>"
    )


def _crm_status_label(status: str) -> str:
    labels = {
        "NEW": "🆕 NEW",
        "CONTACTED": "☎️ CONTACTED",
        "NO_ANSWER": "📵 NO ANSWER",
        "INTERESTED": "⭐ INTERESTED",
        "CONVERTED": "✅ CONVERTED",
        "NOT_INTERESTED": "➖ NOT INTERESTED",
        "DO_NOT_CONTACT": "🚫 DO NOT CONTACT",
    }
    return labels.get(str(status or ""), str(status or "UNKNOWN"))


def _crm_home_text() -> str:
    with core.db() as conn:
        if not _table_exists(conn, "sales_leads"):
            return "💼 <b>FANTZO CRM</b>\n\nNo lead data is available yet."

        total = _scalar(conn, "SELECT COUNT(*) FROM sales_leads")
        new = _scalar(conn, "SELECT COUNT(*) FROM sales_leads WHERE status='NEW'")
        contacted = _scalar(conn, "SELECT COUNT(*) FROM sales_leads WHERE status='CONTACTED'")
        no_answer = _scalar(conn, "SELECT COUNT(*) FROM sales_leads WHERE status='NO_ANSWER'")
        interested = _scalar(conn, "SELECT COUNT(*) FROM sales_leads WHERE status='INTERESTED'")
        converted = _scalar(conn, "SELECT COUNT(*) FROM sales_leads WHERE status='CONVERTED'")
        not_interested = _scalar(conn, "SELECT COUNT(*) FROM sales_leads WHERE status='NOT_INTERESTED'")
        dnc = _scalar(conn, "SELECT COUNT(*) FROM sales_leads WHERE status='DO_NOT_CONTACT'")

    conversion = (float(converted) / float(total) * 100.0) if total else 0.0

    return (
        "💼 <b>FANTZO CRM</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"Total leads: <b>{_fmt_int(total)}</b>\n"
        f"🆕 New: <b>{_fmt_int(new)}</b>\n"
        f"☎️ Contacted: <b>{_fmt_int(contacted)}</b>\n"
        f"📵 No answer: <b>{_fmt_int(no_answer)}</b>\n"
        f"⭐ Interested: <b>{_fmt_int(interested)}</b>\n"
        f"✅ Converted: <b>{_fmt_int(converted)}</b>\n"
        f"➖ Not interested: <b>{_fmt_int(not_interested)}</b>\n"
        f"🚫 Do not contact: <b>{_fmt_int(dnc)}</b>\n\n"
        f"Lead conversion: <b>{conversion:.1f}%</b>\n\n"
        "Tap a status to open that lead queue."
    )


def _crm_home_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _styled_button("🆕 NEW", "crm:list:NEW", "primary"),
            _styled_button("☎️ CONTACTED", "crm:list:CONTACTED", "primary"),
        ],
        [
            _styled_button("📵 NO ANSWER", "crm:list:NO_ANSWER", "primary"),
            _styled_button("⭐ INTERESTED", "crm:list:INTERESTED", "success"),
        ],
        [
            _styled_button("✅ CONVERTED", "crm:list:CONVERTED", "success"),
            InlineKeyboardButton("➖ NOT INTERESTED", callback_data="crm:list:NOT_INTERESTED"),
        ],
        [InlineKeyboardButton("🚫 DO NOT CONTACT", callback_data="crm:list:DO_NOT_CONTACT")],
        [_styled_button("📋 ALL LEADS", "crm:list:ALL", "primary")],
        [InlineKeyboardButton("⬅️ REPORTS", callback_data="rpt:home")],
    ])


def _crm_list(status: str):
    status = str(status or "ALL").upper()
    with core.db() as conn:
        if not _table_exists(conn, "sales_leads"):
            return [], 0
        if status == "ALL":
            rows = _rows(
                conn,
                """
                SELECT s.primary_user_id,s.mobile_e164,s.campaign,s.status,
                       s.assigned_agent,s.updated_at,u.username,u.first_name
                FROM sales_leads s
                LEFT JOIN users u ON u.user_id=s.primary_user_id
                ORDER BY s.updated_at DESC
                LIMIT 12
                """
            )
            total = _scalar(conn, "SELECT COUNT(*) FROM sales_leads")
        else:
            rows = _rows(
                conn,
                """
                SELECT s.primary_user_id,s.mobile_e164,s.campaign,s.status,
                       s.assigned_agent,s.updated_at,u.username,u.first_name
                FROM sales_leads s
                LEFT JOIN users u ON u.user_id=s.primary_user_id
                WHERE s.status=?
                ORDER BY s.updated_at DESC
                LIMIT 12
                """,
                (status,),
            )
            total = _scalar(conn, "SELECT COUNT(*) FROM sales_leads WHERE status=?", (status,))
    return rows, int(total)


def _crm_list_text(status: str) -> tuple[str, InlineKeyboardMarkup]:
    rows, total = _crm_list(status)
    label = "ALL LEADS" if status == "ALL" else _crm_status_label(status)

    lines = [
        f"💼 <b>CRM · {escape(label)}</b>",
        "━━━━━━━━━━━━━━━━━━",
        "",
        f"Leads in queue: <b>{_fmt_int(total)}</b>",
        "",
    ]

    buttons = []
    if rows:
        for idx, row in enumerate(rows, start=1):
            username = str(row["username"] or "").strip()
            name = str(row["first_name"] or "").strip()
            display = f"@{username}" if username else (name or f"User {row['primary_user_id']}")
            mobile = _mask_mobile(row["mobile_e164"])
            campaign = str(row["campaign"] or "direct")
            lines.append(
                f"{idx}. <b>{escape(display)}</b> · <code>{mobile}</code>\n"
                f"   {escape(_crm_status_label(row['status']))} · <code>{escape(campaign)}</code>"
            )
            buttons.append([
                InlineKeyboardButton(
                    f"{idx}. {display[:24]}",
                    callback_data=f"crm:lead:{int(row['primary_user_id'])}",
                )
            ])
    else:
        lines.append("No leads in this queue.")

    if total > len(rows):
        lines.extend(["", f"<i>Showing latest {len(rows)} of {total} leads.</i>"])

    buttons.append([InlineKeyboardButton("⬅️ CRM", callback_data="crm:home")])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


def _crm_lead(user_id: int):
    with core.db() as conn:
        if not _table_exists(conn, "sales_leads"):
            return None
        return _one(
            conn,
            """
            SELECT s.*,u.username,u.first_name,
                   a.first_start_arg,a.last_start_arg
            FROM sales_leads s
            LEFT JOIN users u ON u.user_id=s.primary_user_id
            LEFT JOIN lead_attribution a ON a.user_id=s.primary_user_id
            WHERE s.primary_user_id=?
            LIMIT 1
            """,
            (int(user_id),),
        )


def _crm_lead_text(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    row = _crm_lead(user_id)
    if not row:
        return (
            "💼 <b>FANTZO CRM</b>\n\nLead not found.",
            InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ CRM", callback_data="crm:home")]]),
        )

    username = str(row["username"] or "").strip()
    name = str(row["first_name"] or "").strip()
    agent = str(row["assigned_agent"] or "").strip() or "—"
    notes = str(row["notes"] or "").strip() or "—"
    campaign = str(row["campaign"] or "direct")

    text = (
        "💼 <b>FANTZO CRM · LEAD</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"Mobile: <code>{escape(str(row['mobile_e164']))}</code>\n"
        f"Telegram: {('@' + escape(username)) if username else '—'}\n"
        f"Name: {escape(name or '—')}\n"
        f"User ID: <code>{int(row['primary_user_id'])}</code>\n"
        f"Campaign: <code>{escape(campaign)}</code>\n"
        f"Status: <b>{escape(_crm_status_label(row['status']))}</b>\n"
        f"Agent: {escape(agent)}\n"
        f"Created: {_fmt_dt(row['created_at'])}\n"
        f"Updated: {_fmt_dt(row['updated_at'])}\n"
        f"Last contact: {_fmt_dt(row['last_contact_at'])}\n"
        f"Notes: {escape(notes[:500])}\n\n"
        "<i>Use /leadassign or /leadnote for agent and notes.</i>"
    )

    uid = int(row["primary_user_id"])
    mobile_digits = "".join(ch for ch in str(row["mobile_e164"] or "") if ch.isdigit())
    rows = []
    if mobile_digits and str(row["status"] or "") != "DO_NOT_CONTACT":
        rows.append([
            InlineKeyboardButton(
                "💬 OPEN WHATSAPP",
                url=f"https://wa.me/{mobile_digits}",
                api_kwargs={"style": "success"},
            )
        ])

    rows.extend([
        [
            _styled_button("☎️ CONTACTED", callback_data=f"crm:set:{uid}:CONTACTED", style="primary"),
            _styled_button("📵 NO ANSWER", callback_data=f"crm:set:{uid}:NO_ANSWER", style="primary"),
        ],
        [
            _styled_button("⭐ INTERESTED", f"crm:set:{uid}:INTERESTED", "success"),
            _styled_button("✅ CONVERTED", f"crm:set:{uid}:CONVERTED", "success"),
        ],
        [
            InlineKeyboardButton("➖ NOT INTERESTED", callback_data=f"crm:set:{uid}:NOT_INTERESTED"),
        ],
        [
            InlineKeyboardButton("🚫 DO NOT CONTACT", callback_data=f"crm:set:{uid}:DO_NOT_CONTACT"),
        ],
        [InlineKeyboardButton("🆕 RESET TO NEW", callback_data=f"crm:set:{uid}:NEW")],
        [
            InlineKeyboardButton("⬅️ CRM", callback_data="crm:home"),
            InlineKeyboardButton("🏠 ADMIN", callback_data="adm:home"),
        ],
    ])
    buttons = InlineKeyboardMarkup(rows)
    return text, buttons


def _crm_set_status(user_id: int, status: str) -> bool:
    allowed = {
        "NEW", "CONTACTED", "NO_ANSWER", "INTERESTED",
        "CONVERTED", "NOT_INTERESTED", "DO_NOT_CONTACT",
    }
    status = str(status or "").upper()
    if status not in allowed:
        return False

    now = datetime.now(timezone.utc).isoformat()
    with core.db() as conn:
        row = conn.execute(
            "SELECT mobile_e164 FROM sales_leads WHERE primary_user_id=? LIMIT 1",
            (int(user_id),),
        ).fetchone()
        if not row:
            return False

        conn.execute(
            """
            UPDATE sales_leads
            SET status=?,
                updated_at=?,
                last_contact_at=CASE
                    WHEN ? IN ('CONTACTED','NO_ANSWER','INTERESTED','CONVERTED','NOT_INTERESTED','DO_NOT_CONTACT')
                    THEN ? ELSE last_contact_at END,
                converted_at=CASE
                    WHEN ?='CONVERTED' THEN COALESCE(converted_at, ?)
                    WHEN ?!='CONVERTED' THEN NULL
                    ELSE converted_at END
            WHERE primary_user_id=?
            """,
            (status, now, status, now, status, now, status, int(user_id)),
        )
    return True

def _mask_mobile(value: str) -> str:
    text = str(value or "")
    if len(text) >= 7:
        return text[:3] + "••••••" + text[-4:]
    return "—"


def _mobile_text() -> str:
    day, week, _ = _cutoffs()
    with core.db() as conn:
        if not _table_exists(conn, "live_tv_mobile_users"):
            return "📱 <b>TELEGRAM VERIFIED NUMBERS</b>\n\nNo mobile verification data is available yet."

        verified = _scalar(
            conn,
            "SELECT COUNT(*) FROM live_tv_mobile_users WHERE capture_method='telegram_contact'"
        )
        unique_numbers = _scalar(
            conn,
            "SELECT COUNT(DISTINCT mobile_e164) FROM live_tv_mobile_users "
            "WHERE capture_method='telegram_contact'"
        )
        count_24 = _scalar(
            conn,
            "SELECT COUNT(*) FROM live_tv_mobile_users "
            "WHERE capture_method='telegram_contact' AND created_at>=?",
            (day,),
        )
        count_7 = _scalar(
            conn,
            "SELECT COUNT(*) FROM live_tv_mobile_users "
            "WHERE capture_method='telegram_contact' AND created_at>=?",
            (week,),
        )
        legacy_unverified = _scalar(
            conn,
            "SELECT COUNT(*) FROM live_tv_mobile_users "
            "WHERE capture_method!='telegram_contact'"
        )

        welcomed = _scalar(
            conn,
            "SELECT COUNT(DISTINCT customer_id) FROM business_welcomes"
        ) if _table_exists(conn, "business_welcomes") else 0

        business_verified = 0
        if _table_exists(conn, "business_welcomes"):
            business_verified = _scalar(
                conn,
                "SELECT COUNT(DISTINCT w.customer_id) "
                "FROM business_welcomes w "
                "JOIN live_tv_mobile_users m ON m.user_id=w.customer_id "
                "WHERE m.capture_method='telegram_contact'"
            )

        bot_verified = max(int(verified) - int(business_verified), 0)
        verify_opens = 0
        if _table_exists(conn, "mobile_verification_events"):
            verify_opens = _scalar(
                conn,
                "SELECT COUNT(DISTINCT user_id) FROM mobile_verification_events "
                "WHERE source='business_dm' AND event='verify_open'"
            )

        sources = _rows(
            conn,
            "SELECT source, COUNT(*) c FROM live_tv_mobile_users "
            "WHERE capture_method='telegram_contact' "
            "GROUP BY source ORDER BY c DESC LIMIT 8"
        )
        latest = _rows(
            conn,
            "SELECT m.mobile_e164,m.source,m.created_at,"
            "u.username,u.first_name FROM live_tv_mobile_users m "
            "LEFT JOIN users u ON u.user_id=m.user_id "
            "WHERE m.capture_method='telegram_contact' "
            "ORDER BY m.created_at DESC LIMIT 6"
        )

    conversion = (float(business_verified) / float(welcomed) * 100.0) if welcomed else 0.0

    source_text = "\n".join(
        f"• {escape(str(r['source']))}: <b>{_fmt_int(r['c'])}</b>" for r in sources
    ) or "• No source data"

    latest_text = "\n".join(
        f"• <code>{_mask_mobile(r['mobile_e164'])}</code> · "
        f"{escape(str(r['username'] or r['first_name'] or 'user'))} · "
        f"{escape(str(r['source']))}"
        for r in latest
    ) or "• No verified mobile numbers yet"

    return (
        "📱 <b>TELEGRAM VERIFIED NUMBERS</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"Total verified users: <b>{_fmt_int(verified)}</b>\n"
        f"Unique verified numbers: <b>{_fmt_int(unique_numbers)}</b>\n"
        f"New verifications: <b>{_fmt_int(count_24)}</b> (24h) · <b>{_fmt_int(count_7)}</b> (7d)\n\n"
        f"🤖 Bot/direct verified: <b>{_fmt_int(bot_verified)}</b>\n"
        f"💬 Business DM verified: <b>{_fmt_int(business_verified)}</b>\n"
        f"↗️ Business verify opens: <b>{_fmt_int(verify_opens)}</b>\n"
        f"👋 Business DM customers welcomed: <b>{_fmt_int(welcomed)}</b>\n"
        f"📈 Business DM → verified: <b>{conversion:.1f}%</b>\n\n"
        f"Legacy/unverified records: <b>{_fmt_int(legacy_unverified)}</b>\n\n"
        f"<b>Stored verification sources</b>\n{source_text}\n\n"
        f"<b>Latest verified users · masked</b>\n{latest_text}\n\n"
        "<i>Only Telegram self-contact shares count as verified. "
        "Full verified numbers and country codes remain admin-only in the CSV export.</i>"
    )

def _web_text() -> str:
    day, week, _ = _cutoffs()
    with core.db() as conn:
        if not _table_exists(conn, "web_events"):
            return "🌐 <b>FANTZO OPENS REPORT</b>\n\nNo web-open data is available."
        total = _scalar(conn, "SELECT COUNT(*) FROM web_events WHERE event='fantzo_open'")
        count_24 = _scalar(conn, "SELECT COUNT(*) FROM web_events WHERE event='fantzo_open' AND created_at>=?", (day,))
        count_7 = _scalar(conn, "SELECT COUNT(*) FROM web_events WHERE event='fantzo_open' AND created_at>=?", (week,))
        first_last = _one(conn, "SELECT MIN(created_at) first_at, MAX(created_at) last_at FROM web_events WHERE event='fantzo_open'")
        top = _rows(conn, "SELECT source, COUNT(*) c FROM web_events WHERE event='fantzo_open' GROUP BY source ORDER BY c DESC LIMIT 8")
    top_text = "\n".join(f"• {escape(str(r['source']))}: <b>{_fmt_int(r['c'])}</b>" for r in top) or "• No sources yet"
    return (
        "🌐 <b>FANTZO OPENS REPORT</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"Total opens: <b>{_fmt_int(total)}</b>\n"
        f"24h: <b>{_fmt_int(count_24)}</b> · 7d: <b>{_fmt_int(count_7)}</b>\n"
        f"First: <b>{_fmt_dt(first_last['first_at'] if first_last else None)}</b>\n"
        f"Latest: <b>{_fmt_dt(first_last['last_at'] if first_last else None)}</b>\n\n"
        f"<b>Top sources</b>\n{top_text}\n\n"
        "<i>Web redirect tracking records source, not Telegram user ID, so unique users are not inferred here.</i>"
    )


def _business_text() -> str:
    day, week, _ = _cutoffs()
    with core.db() as conn:
        clicks_available = _table_exists(conn, "clicks")
        total = _scalar(conn, "SELECT COUNT(*) FROM clicks WHERE action LIKE 'business_dm:%'") if clicks_available else 0
        unique = _scalar(conn, "SELECT COUNT(DISTINCT user_id) FROM clicks WHERE action LIKE 'business_dm:%'") if clicks_available else 0
        count_24 = _scalar(conn, "SELECT COUNT(*) FROM clicks WHERE action LIKE 'business_dm:%' AND created_at>=?", (day,)) if clicks_available else 0
        count_7 = _scalar(conn, "SELECT COUNT(*) FROM clicks WHERE action LIKE 'business_dm:%' AND created_at>=?", (week,)) if clicks_available else 0
        categories = _rows(conn, "SELECT action, COUNT(*) c FROM clicks WHERE action LIKE 'business_dm:%' GROUP BY action ORDER BY c DESC LIMIT 8") if clicks_available else []
        welcomed = _scalar(conn, "SELECT COUNT(DISTINCT customer_id) FROM business_welcomes") if _table_exists(conn, "business_welcomes") else 0
        connections = _scalar(conn, "SELECT COUNT(*) FROM business_connections WHERE enabled=1") if _table_exists(conn, "business_connections") else 0

        verified = 0
        if _table_exists(conn, "live_tv_mobile_users") and _table_exists(conn, "business_welcomes"):
            verified = _scalar(
                conn,
                "SELECT COUNT(DISTINCT w.customer_id) "
                "FROM business_welcomes w "
                "JOIN live_tv_mobile_users m ON m.user_id=w.customer_id "
                "WHERE m.capture_method='telegram_contact'"
            )

        verify_opens = 0
        if _table_exists(conn, "mobile_verification_events"):
            verify_opens = _scalar(
                conn,
                "SELECT COUNT(DISTINCT user_id) FROM mobile_verification_events "
                "WHERE source='business_dm' AND event='verify_open'"
            )

    conversion = (float(verified) / float(welcomed) * 100.0) if welcomed else 0.0
    cat_text = "\n".join(
        f"• {escape(str(r['action']).replace('business_dm:', ''))}: <b>{_fmt_int(r['c'])}</b>"
        for r in categories
    ) or "• No Business DM activity"

    return (
        "💬 <b>BUSINESS DM REPORT</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"DM events: <b>{_fmt_int(total)}</b>\n"
        f"Unique customers: <b>{_fmt_int(unique)}</b>\n"
        f"24h: <b>{_fmt_int(count_24)}</b> · 7d: <b>{_fmt_int(count_7)}</b>\n\n"
        f"👋 Customers welcomed: <b>{_fmt_int(welcomed)}</b>\n"
        f"↗️ Opened verification: <b>{_fmt_int(verify_opens)}</b>\n"
        f"✅ Telegram verified: <b>{_fmt_int(verified)}</b>\n"
        f"📈 Welcome → verified: <b>{conversion:.1f}%</b>\n"
        f"🔗 Enabled Business connections: <b>{_fmt_int(connections)}</b>\n\n"
        f"<b>Business actions</b>\n{cat_text}"
    )

def _reminders_text() -> str:
    day, week, _ = _cutoffs()
    with core.db() as conn:
        if not _table_exists(conn, "reminder_users"):
            return "🔔 <b>REMINDERS REPORT</b>\n\nReminder tracking is not available."
        tracked_users = _scalar(conn, "SELECT COUNT(*) FROM reminder_users")
        distinct_users = _scalar(conn, "SELECT COUNT(DISTINCT user_id) FROM reminder_users")
        opted_out = _scalar(conn, "SELECT COUNT(*) FROM reminder_users WHERE opted_out=1")
        bot_users = _scalar(conn, "SELECT COUNT(*) FROM reminder_users WHERE source='bot'")
        business_users = _scalar(conn, "SELECT COUNT(*) FROM reminder_users WHERE source='business_dm'")
        sends = _scalar(conn, "SELECT COUNT(*) FROM reminder_sends") if _table_exists(conn, "reminder_sends") else 0
        sent = _scalar(conn, "SELECT COUNT(*) FROM reminder_sends WHERE status='sent'") if _table_exists(conn, "reminder_sends") else 0
        sent_24 = _scalar(conn, "SELECT COUNT(*) FROM reminder_sends WHERE status='sent' AND sent_at>=?", (day,)) if _table_exists(conn, "reminder_sends") else 0
        sent_7 = _scalar(conn, "SELECT COUNT(*) FROM reminder_sends WHERE status='sent' AND sent_at>=?", (week,)) if _table_exists(conn, "reminder_sends") else 0
        failures = _scalar(conn, "SELECT COUNT(*) FROM reminder_sends WHERE status!='sent'") if _table_exists(conn, "reminder_sends") else 0
    return (
        "🔔 <b>REMINDERS REPORT</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"Tracked source/user rows: <b>{_fmt_int(tracked_users)}</b>\n"
        f"Distinct users: <b>{_fmt_int(distinct_users)}</b>\n"
        f"Bot users: <b>{_fmt_int(bot_users)}</b> · Business users: <b>{_fmt_int(business_users)}</b>\n"
        f"Opted out: <b>{_fmt_int(opted_out)}</b>\n\n"
        f"Send attempts: <b>{_fmt_int(sends)}</b>\n"
        f"Sent successfully: <b>{_fmt_int(sent)}</b>\n"
        f"Sent 24h: <b>{_fmt_int(sent_24)}</b> · 7d: <b>{_fmt_int(sent_7)}</b>\n"
        f"Non-sent/failed statuses: <b>{_fmt_int(failures)}</b>"
    )


def _favourites_text() -> str:
    with core.db() as conn:
        if not _table_exists(conn, "user_favourites"):
            return "⭐ <b>FAVOURITES REPORT</b>\n\nNo favourite-team data is available."
        total = _scalar(conn, "SELECT COUNT(*) FROM user_favourites")
        users = _scalar(conn, "SELECT COUNT(DISTINCT user_id) FROM user_favourites")
        enabled = _scalar(conn, "SELECT COUNT(*) FROM user_favourites WHERE alerts_enabled=1")
        top = _rows(conn, "SELECT value, COUNT(*) c FROM user_favourites GROUP BY value ORDER BY c DESC LIMIT 8")
    top_text = "\n".join(f"• {escape(str(r['value']))}: <b>{_fmt_int(r['c'])}</b>" for r in top) or "• No favourites yet"
    return (
        "⭐ <b>FAVOURITES REPORT</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"Favourite records: <b>{_fmt_int(total)}</b>\n"
        f"Users with favourites: <b>{_fmt_int(users)}</b>\n"
        f"Favourite alerts ON: <b>{_fmt_int(enabled)}</b>\n\n"
        f"<b>Most-followed teams</b>\n{top_text}"
    )



def _daily_rows(days: int = 30):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days - 1)).date().isoformat()
    with core.db() as conn:
        def grouped(table, date_col, where="", params=()):
            if not _table_exists(conn, table):
                return {}
            sql = f"SELECT substr({date_col},1,10) d, COUNT(*) c FROM {table} WHERE substr({date_col},1,10)>=?"
            values = [cutoff]
            if where:
                sql += f" AND {where}"
                values.extend(params)
            sql += " GROUP BY substr(" + date_col + ",1,10)"
            return {str(r["d"]): int(r["c"]) for r in _rows(conn, sql, tuple(values))}

        actions = grouped("clicks", "created_at")
        live_tv = grouped("clicks", "created_at", "action='live_tv_status'")
        business = grouped("clicks", "created_at", "action LIKE 'business_dm:%'")
        web = grouped("web_events", "created_at", "event='fantzo_open'")
        reminders = grouped("reminder_sends", "sent_at", "status='sent'")
        mobile = grouped("live_tv_mobile_users", "created_at", "capture_method='telegram_contact'")

        active = {}
        if _table_exists(conn, "users"):
            rows = _rows(
                conn,
                "SELECT substr(last_seen,1,10) d, COUNT(*) c FROM users "
                "WHERE substr(last_seen,1,10)>=? GROUP BY substr(last_seen,1,10)",
                (cutoff,),
            )
            active = {str(r["d"]): int(r["c"]) for r in rows}

    dates = sorted(set(actions) | set(live_tv) | set(business) | set(web) | set(reminders) | set(mobile) | set(active), reverse=True)
    return [
        (d, active.get(d, 0), actions.get(d, 0), live_tv.get(d, 0), mobile.get(d, 0), web.get(d, 0), business.get(d, 0), reminders.get(d, 0))
        for d in dates
    ]


def _daily_text() -> str:
    rows = _daily_rows(14)
    if not rows:
        return "📅 <b>DAILY ACTIVITY</b>\n\nNo daily activity is available yet."
    lines = []
    for d, active, actions, live, mobile, web, business, reminders in rows[:14]:
        lines.append(
            f"<b>{escape(d)}</b> · 👥 {active} · 🎯 {actions} · 📺 {live} · 📱 {mobile} · 🌐 {web} · 💬 {business} · 📨 {reminders}"
        )
    return (
        "📅 <b>DAILY ACTIVITY · LAST 14 DAYS</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "👥 active · 🎯 actions · 📺 Live TV · 📱 mobile · 🌐 opens · 💬 Business · 📨 reminders\n\n"
        + "\n".join(lines)
    )


def _daily_csv() -> bytes:
    return _csv_bytes(
        ["date_utc", "active_users_by_last_seen", "bot_actions", "live_tv_entries", "mobile_captures", "fantzo_web_opens", "business_dm_events", "reminders_sent"],
        _daily_rows(3650),
    )

def _banners_text() -> str:
    with core.db() as conn:
        if not _table_exists(conn, "live_tv_banners"):
            return "🖼 <b>BANNER REPORT</b>\n\nNo banner queue data is available."
        total = _scalar(conn, "SELECT COUNT(*) FROM live_tv_banners")
        queued = _scalar(conn, "SELECT COUNT(*) FROM live_tv_banners WHERE status='queued'")
        posted = _scalar(conn, "SELECT COUNT(*) FROM live_tv_banners WHERE status='posted'")
        latest = _one(conn, "SELECT MAX(posted_at) posted_at FROM live_tv_banners WHERE posted_at IS NOT NULL")
        paused = None
        if _table_exists(conn, "live_tv_banner_settings"):
            row = _one(conn, "SELECT value FROM live_tv_banner_settings WHERE key='paused'")
            paused = str(row[0]) == "1" if row else False
    return (
        "🖼 <b>BANNER REPORT</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"Total banners: <b>{_fmt_int(total)}</b>\n"
        f"Queued: <b>{_fmt_int(queued)}</b>\n"
        f"Posted: <b>{_fmt_int(posted)}</b>\n"
        f"Auto posting: <b>{'PAUSED' if paused else 'ACTIVE'}</b>\n"
        f"Latest post: <b>{_fmt_dt(latest['posted_at'] if latest else None)}</b>"
    )


def _csv_bytes(headers, rows) -> bytes:
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(["" if value is None else value for value in row])
    return out.getvalue().encode("utf-8-sig")


def _query_csv(sql: str, params=(), headers=None) -> bytes:
    with core.db() as conn:
        cur = conn.execute(sql, params)
        names = headers or [d[0] for d in cur.description]
        rows = cur.fetchall()
    return _csv_bytes(names, ([r[i] for i in range(len(names))] for r in rows))


def _table_csv(table: str) -> bytes:
    with core.db() as conn:
        if not _table_exists(conn, table):
            return _csv_bytes(["status"], [[f"table {table} not available"]])
        cur = conn.execute(f'SELECT * FROM "{table}"')
        headers = [d[0] for d in cur.description]
        rows = cur.fetchall()
    return _csv_bytes(headers, ([r[i] for i in range(len(headers))] for r in rows))


def _overview_csv() -> bytes:
    text = _overview_text()
    plain = (
        text.replace("<b>", "").replace("</b>", "")
        .replace("<i>", "").replace("</i>", "")
        .replace("━━━━━━━━━━━━━━━━━━", "")
    )
    rows = [[line.strip()] for line in plain.splitlines() if line.strip()]
    return _csv_bytes(["overview"], rows)


def _report_csv(key: str) -> tuple[str, bytes]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if key == "users":
        return f"fantzo_users_{stamp}.csv", _query_csv(
            "SELECT user_id,username,first_name,language,subscribed,created_at,last_seen FROM users ORDER BY created_at DESC"
        )
    if key == "engagement":
        return f"fantzo_engagement_{stamp}.csv", _query_csv(
            "SELECT c.id,c.user_id,u.username,u.first_name,c.action,c.created_at "
            "FROM clicks c LEFT JOIN users u ON u.user_id=c.user_id ORDER BY c.created_at DESC"
        )
    if key == "livetv":
        return f"fantzo_live_tv_{stamp}.csv", _query_csv(
            "SELECT c.id,c.user_id,u.username,u.first_name,c.action,c.created_at "
            "FROM clicks c LEFT JOIN users u ON u.user_id=c.user_id "
            "WHERE c.action='live_tv_status' ORDER BY c.created_at DESC"
        )
    if key == "leads":
        return f"fantzo_lead_funnel_{stamp}.csv", _query_csv(
            "SELECT s.mobile_e164,s.primary_user_id,u.username,u.first_name,"
            "s.campaign,s.status,s.assigned_agent,s.notes,s.contact_permission_at,"
            "s.created_at,s.updated_at,s.last_contact_at,s.converted_at,"
            "(SELECT COUNT(*) FROM lead_user_map lm WHERE lm.mobile_e164=s.mobile_e164) AS telegram_accounts "
            "FROM sales_leads s LEFT JOIN users u ON u.user_id=s.primary_user_id "
            "ORDER BY s.created_at DESC"
        )
    if key == "mobile":
        return f"fantzo_verified_mobile_numbers_{stamp}.csv", _query_csv(
            "SELECT m.user_id,u.username,u.first_name,m.mobile_e164,m.mobile_national,"
            "CASE WHEN m.capture_method='telegram_contact' THEN 1 ELSE 0 END AS telegram_verified,"
            "m.capture_method,m.source,m.created_at,m.updated_at,m.last_live_tv_at "
            "FROM live_tv_mobile_users m LEFT JOIN users u ON u.user_id=m.user_id "
            "ORDER BY m.created_at DESC"
        )
    if key == "web":
        return f"fantzo_opens_{stamp}.csv", _query_csv(
            "SELECT id,event,source,created_at FROM web_events ORDER BY created_at DESC"
        )
    if key == "business":
        return f"fantzo_business_dm_{stamp}.csv", _query_csv(
            "SELECT c.id,c.user_id,u.username,u.first_name,c.action,c.created_at "
            "FROM clicks c LEFT JOIN users u ON u.user_id=c.user_id "
            "WHERE c.action LIKE 'business_dm:%' ORDER BY c.created_at DESC"
        )
    if key == "reminders":
        return f"fantzo_reminder_sends_{stamp}.csv", _table_csv("reminder_sends")
    if key == "favourites":
        return f"fantzo_favourites_{stamp}.csv", _table_csv("user_favourites")
    if key == "daily":
        return f"fantzo_daily_activity_{stamp}.csv", _daily_csv()
    if key == "banners":
        return f"fantzo_banners_{stamp}.csv", _table_csv("live_tv_banners")
    raise ValueError(f"Unknown report: {key}")


def _all_reports_zip() -> tuple[str, bytes]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    payloads = {
        "00_overview.csv": _overview_csv(),
        "01_users.csv": _table_csv("users"),
        "02_engagement_clicks.csv": _table_csv("clicks"),
        "03_live_tv.csv": _report_csv("livetv")[1],
        "04_live_tv_mobile_numbers.csv": _table_csv("live_tv_mobile_users"),
        "05_mobile_verification_events.csv": _table_csv("mobile_verification_events"),
        "06_lead_attribution.csv": _table_csv("lead_attribution"),
        "07_lead_events.csv": _table_csv("lead_events"),
        "08_lead_user_map.csv": _table_csv("lead_user_map"),
        "09_sales_leads.csv": _table_csv("sales_leads"),
        "10_fantzo_web_opens.csv": _table_csv("web_events"),
        "11_growth_events.csv": _table_csv("growth_events"),
        "12_business_welcomes.csv": _table_csv("business_welcomes"),
        "13_business_connections.csv": _table_csv("business_connections"),
        "14_reminder_users.csv": _table_csv("reminder_users"),
        "15_reminder_sends.csv": _table_csv("reminder_sends"),
        "16_favourites.csv": _table_csv("user_favourites"),
        "17_daily_activity.csv": _daily_csv(),
        "18_live_tv_banners.csv": _table_csv("live_tv_banners"),
        "19_live_tv_banner_settings.csv": _table_csv("live_tv_banner_settings"),
    }
    readme = (
        "FANTZO ADMIN REPORT PACK\n"
        f"Generated: {datetime.now(timezone.utc).isoformat()}\n\n"
        "Definitions:\n"
        "- Live TV canonical opens: clicks.action = live_tv_status\n"
        "- Mobile verification: Telegram self-contact only; all countries accepted\n"
        "- lead_attribution preserves first paid/referral start source per Telegram user\n"
        "- sales_leads is deduplicated by verified mobile number and stores sales status\n"
        "- Business DM verification handoff uses source=business_dm\n"
        "- mobile_verification_events stores verify opens and verification completions\n"
        "- Full mobile numbers are admin-only in live_tv_mobile_users/CSV exports\n"
        "- Fantzo web opens: web_events.event = fantzo_open\n"
        "- Business DM activity: clicks.action starts with business_dm:\n"
        "- Web redirect events do not contain Telegram user_id.\n"
        "- Files are read-only snapshots taken when the ZIP was requested.\n"
    ).encode("utf-8")

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.txt", readme)
        for name, data in payloads.items():
            zf.writestr(name, data)
    return f"fantzo_reports_{stamp}.zip", out.getvalue()


async def _send_document(message, filename: str, data: bytes, caption: str) -> None:
    buf = io.BytesIO(data)
    buf.name = filename
    await message.reply_document(
        document=InputFile(buf, filename=filename),
        caption=caption,
    )


async def _show(query, text: str, markup: InlineKeyboardMarkup) -> None:
    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=markup,
        disable_web_page_preview=True,
    )


async def _handle_report_callback(update, context) -> bool:
    query = update.callback_query
    if not query:
        return False
    data = str(query.data or "")
    if not (
        data.startswith(REPORT_PREFIX)
        or data.startswith(DOWNLOAD_PREFIX)
        or data.startswith("crm:")
        or data.startswith("adm:")
    ):
        return False

    if not _is_admin(update):
        await query.answer("Restricted to Fantzo admin.", show_alert=True)
        return True

    if data.startswith("adm:"):
        action = data.split(":", 1)[1] if ":" in data else "home"
        await query.answer()

        if action == "home":
            await _show(
                query,
                _admin_dashboard_text(),
                _admin_dashboard_menu(update.effective_user.id if update.effective_user else None),
            )
        elif action == "campaigns":
            await _show(query, _campaigns_text(), _campaigns_menu())
        elif action == "tools":
            if not _is_owner(update):
                await query.answer("Owner tools are restricted.", show_alert=True)
                return True
            await _show(query, _tools_text(), _tools_menu())
        elif action == "guide":
            await _show(query, _team_guide_text(), _team_guide_menu())
        elif action == "advanced_reports":
            if not _is_owner(update):
                await query.answer("Advanced reports are owner-only.", show_alert=True)
                return True
            await _show(
                query,
                "🧪 <b>ADVANCED REPORTS</b>\n━━━━━━━━━━━━━━━━━━\n\n"
                "These reports are useful for diagnostics and product analysis, "
                "but they are not part of the team's daily lead workflow.",
                _advanced_reports_menu(),
            )
        elif action == "advanced_exports":
            if not _is_owner(update):
                await query.answer("Advanced exports are owner-only.", show_alert=True)
                return True
            await _show(
                query,
                "🧪 <b>ADVANCED EXPORTS</b>\n━━━━━━━━━━━━━━━━━━\n\n"
                "Raw operational CSVs for analysis or troubleshooting.",
                _advanced_downloads_menu(),
            )
        else:
            await query.answer("Unknown admin action.", show_alert=True)
        return True

    if data.startswith("crm:"):
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else "home"

        if action == "home":
            await query.answer()
            await _show(query, _crm_home_text(), _crm_home_menu())
            return True

        if action == "list":
            status = parts[2] if len(parts) > 2 else "ALL"
            await query.answer()
            text, markup = _crm_list_text(status)
            await _show(query, text, markup)
            return True

        if action == "lead":
            if len(parts) < 3 or not parts[2].isdigit():
                await query.answer("Lead not found.", show_alert=True)
                return True
            await query.answer()
            text, markup = _crm_lead_text(int(parts[2]))
            await _show(query, text, markup)
            return True

        if action == "set":
            if len(parts) < 4 or not parts[2].isdigit():
                await query.answer("Invalid CRM action.", show_alert=True)
                return True
            ok = _crm_set_status(int(parts[2]), parts[3])
            if not ok:
                await query.answer("Could not update lead.", show_alert=True)
                return True
            await query.answer("Lead status updated ✅")
            text, markup = _crm_lead_text(int(parts[2]))
            await _show(query, text, markup)
            return True

        await query.answer("Unknown CRM action.", show_alert=True)
        return True

    if data.startswith(DOWNLOAD_PREFIX):
        key = data[len(DOWNLOAD_PREFIX):]
        await query.answer("Preparing report…")
        try:
            if key == "all":
                filename, payload = _all_reports_zip()
                await _send_document(query.message, filename, payload, "📦 Complete Fantzo reporting pack")
            else:
                filename, payload = _report_csv(key)
                await _send_document(query.message, filename, payload, f"⬇️ Fantzo {key} report")
        except Exception as exc:
            logger.exception("Could not generate Fantzo report %s", key)
            await query.message.reply_text(f"⚠️ Could not generate report: {escape(str(exc))}", parse_mode="HTML")
        return True

    action = data[len(REPORT_PREFIX):]
    await query.answer()
    if action == "home":
        await _show(
            query,
            "📈 <b>FANTZO REPORTS</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            "Daily reports are shown first. Raw diagnostic reports are under Advanced Reports.\n\n"
            "All exports are generated live from the production database and are admin-only.",
            _report_menu(),
        )
    elif action == "overview":
        await _show(query, _overview_text(), _back_menu())
    elif action == "users":
        await _show(query, _users_text(), _back_menu("users"))
    elif action == "engagement":
        await _show(query, _engagement_text(), _back_menu("engagement"))
    elif action == "livetv":
        await _show(query, _livetv_text(), _back_menu("livetv"))
    elif action == "leads":
        await _show(query, _lead_funnel_text(), _back_menu("leads"))
    elif action == "mobile":
        await _show(query, _mobile_text(), _back_menu("mobile"))
    elif action == "web":
        await _show(query, _web_text(), _back_menu("web"))
    elif action == "business":
        await _show(query, _business_text(), _back_menu("business"))
    elif action == "reminders":
        await _show(query, _reminders_text(), _back_menu("reminders"))
    elif action == "favourites":
        await _show(query, _favourites_text(), _back_menu("favourites"))
    elif action == "daily":
        await _show(query, _daily_text(), _back_menu("daily"))
    elif action == "banners":
        await _show(query, _banners_text(), _back_menu("banners"))
    elif action == "downloads":
        await _show(
            query,
            "⬇️ <b>DOWNLOAD REPORTS</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            "Choose a CSV report, or download the complete ZIP pack.",
            _downloads_menu(),
        )
    else:
        await query.answer("Unknown report", show_alert=True)
    return True


async def send_reports_panel(message, user_id: int | None = None) -> None:
    await message.reply_text(
        _admin_dashboard_text(),
        parse_mode="HTML",
        reply_markup=_admin_dashboard_menu(user_id),
        disable_web_page_preview=True,
    )



async def reports_command(update, context) -> None:
    if not _is_admin(update) or not update.effective_message:
        if update.effective_message:
            await update.effective_message.reply_text("This command is restricted.")
        return
    await update.effective_message.reply_text(
        _overview_text(),
        parse_mode="HTML",
        reply_markup=_report_menu(),
        disable_web_page_preview=True,
    )


async def crm_command(update, context) -> None:
    if not _is_admin(update) or not update.effective_message:
        if update.effective_message:
            await update.effective_message.reply_text("This command is restricted.")
        return
    await update.effective_message.reply_text(
        _crm_home_text(),
        parse_mode="HTML",
        reply_markup=_crm_home_menu(),
        disable_web_page_preview=True,
    )


def register_handlers(application) -> None:
    application.add_handler(CommandHandler("reports", reports_command))
    application.add_handler(CommandHandler("crm", crm_command))
    logger.info("Fantzo /reports and /crm admin shortcuts registered")


def install() -> None:
    global _installed
    if _installed:
        return
    _installed = True

    original_admin = tracked.app.core.admin
    original_router = tracked.app.core.callback_router

    async def admin_with_reports(update, context):
        if not _is_admin(update):
            await original_admin(update, context)
            return
        if update.effective_message:
            await send_reports_panel(
                update.effective_message,
                update.effective_user.id if update.effective_user else None,
            )

    async def router_with_reports(update, context):
        if await _handle_report_callback(update, context):
            return
        await original_router(update, context)

    tracked.app.core.admin = admin_with_reports
    tracked.app.core.callback_router = router_with_reports
    logger.info("Fantzo team admin dashboard installed: CRM-first workflow, campaigns, reports and advanced tools")
