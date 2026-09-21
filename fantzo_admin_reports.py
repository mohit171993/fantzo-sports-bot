"""Admin reporting center for Fantzo.

Adds a read-only Reports section beneath the existing /admin panel. Reports can
be viewed in Telegram or downloaded as CSV files. A complete ZIP export is also
available. No report action mutates Fantzo production data.
"""

from __future__ import annotations

import csv
import io
import logging
import zipfile
from datetime import datetime, timedelta, timezone
from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile

import bot_tracked as tracked

logger = logging.getLogger(__name__)
core = tracked.app.core
_installed = False

REPORT_PREFIX = "rpt:"
DOWNLOAD_PREFIX = "rptdl:"


def _styled_button(label: str, callback_data: str, style: str | None = None) -> InlineKeyboardButton:
    kwargs = {"callback_data": callback_data}
    if style:
        kwargs["api_kwargs"] = {"style": style}
    return InlineKeyboardButton(label, **kwargs)


def _is_admin(update) -> bool:
    user = update.effective_user
    return bool(user and user.id == core.ADMIN_USER_ID)


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


def _report_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                _styled_button("📊 OVERVIEW", "rpt:overview", "primary"),
                _styled_button("👥 USERS", "rpt:users", "primary"),
            ],
            [
                _styled_button("🎯 ENGAGEMENT", "rpt:engagement", "primary"),
                _styled_button("📺 LIVE TV", "rpt:livetv", "success"),
            ],
            [
                _styled_button("🌐 FANTZO OPENS", "rpt:web", "primary"),
                _styled_button("💬 BUSINESS DMs", "rpt:business", "primary"),
            ],
            [
                _styled_button("🔔 REMINDERS", "rpt:reminders", "primary"),
                _styled_button("⭐ FAVOURITES", "rpt:favourites", "primary"),
            ],
            [_styled_button("🎯 LEAD FUNNEL", "rpt:leads", "success")],
            [_styled_button("📱 VERIFIED NUMBERS", "rpt:mobile", "success")],
            [
                _styled_button("📅 DAILY", "rpt:daily", "primary"),
                _styled_button("🖼 BANNERS", "rpt:banners", "primary"),
            ],
            [_styled_button("⬇️ DOWNLOADS", "rpt:downloads", "success")],
            [_styled_button("📦 DOWNLOAD ALL REPORTS", "rptdl:all", "success")],
        ]
    )


def _back_menu(download_key: str | None = None) -> InlineKeyboardMarkup:
    rows = []
    if download_key:
        rows.append([_styled_button("⬇️ DOWNLOAD CSV", f"rptdl:{download_key}", "success")])
    rows.append([InlineKeyboardButton("⬅️ REPORTS", callback_data="rpt:home")])
    return InlineKeyboardMarkup(rows)


def _downloads_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("👥 Users CSV", callback_data="rptdl:users"),
                InlineKeyboardButton("🎯 Engagement CSV", callback_data="rptdl:engagement"),
            ],
            [
                InlineKeyboardButton("📺 Live TV CSV", callback_data="rptdl:livetv"),
                InlineKeyboardButton("📱 Verified Numbers CSV", callback_data="rptdl:mobile"),
            ],
            [InlineKeyboardButton("🎯 Lead Funnel CSV", callback_data="rptdl:leads")],
            [InlineKeyboardButton("🌐 Fantzo Opens CSV", callback_data="rptdl:web")],
            [
                InlineKeyboardButton("💬 Business CSV", callback_data="rptdl:business"),
                InlineKeyboardButton("🔔 Reminders CSV", callback_data="rptdl:reminders"),
            ],
            [
                InlineKeyboardButton("⭐ Favourites CSV", callback_data="rptdl:favourites"),
                InlineKeyboardButton("📅 Daily CSV", callback_data="rptdl:daily"),
            ],
            [InlineKeyboardButton("🖼 Banners CSV", callback_data="rptdl:banners")],
            [_styled_button("📦 COMPLETE ZIP", "rptdl:all", "success")],
            [InlineKeyboardButton("⬅️ REPORTS", callback_data="rpt:home")],
        ]
    )


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
    if not (data.startswith(REPORT_PREFIX) or data.startswith(DOWNLOAD_PREFIX)):
        return False

    if not _is_admin(update):
        await query.answer("Restricted to Fantzo admin.", show_alert=True)
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
            "📊 <b>FANTZO ADMIN · REPORTS</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            "View operational reports or download the underlying data.\n\n"
            "All downloads are generated live from the production database and are admin-only.",
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


async def send_reports_panel(message) -> None:
    await message.reply_text(
        "📊 <b>FANTZO ADMIN · REPORTS</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "View live summaries or download detailed CSV reports.\n"
        "Use <b>Download All Reports</b> for one complete ZIP.",
        parse_mode="HTML",
        reply_markup=_report_menu(),
    )


def install() -> None:
    global _installed
    if _installed:
        return
    _installed = True

    original_admin = tracked.app.core.admin
    original_router = tracked.app.core.callback_router

    async def admin_with_reports(update, context):
        await original_admin(update, context)
        if _is_admin(update) and update.effective_message:
            await send_reports_panel(update.effective_message)

    async def router_with_reports(update, context):
        if await _handle_report_callback(update, context):
            return
        await original_router(update, context)

    tracked.app.core.admin = admin_with_reports
    tracked.app.core.callback_router = router_with_reports
    logger.info("Fantzo admin reports installed: view summaries, CSV downloads and complete ZIP")
