"""Paid-ads lead attribution and lightweight sales CRM for Fantzo.

This module is intentionally additive:
- keeps the existing Fantzo bot / Live TV flows intact;
- records acquisition source before verification;
- deduplicates sales leads by verified mobile number;
- provides a focused post-verification conversion screen;
- exposes admin-only lead commands.

It does not contact leads automatically.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import CommandHandler

import bot_tracked as tracked

logger = logging.getLogger(__name__)
core = tracked.app.core

_installed = False

INTERNAL_START_ARGS = {
    "",
    "livetv_business",
    "livetv_banner",
    "verify_business_dm",
    "reminder",
    "stopreminders",
}

LEAD_STATUSES = (
    "NEW",
    "CONTACTED",
    "NO_ANSWER",
    "INTERESTED",
    "CONVERTED",
    "NOT_INTERESTED",
    "DO_NOT_CONTACT",
)

STATUS_ALIASES = {
    "NEW": "NEW",
    "CONTACTED": "CONTACTED",
    "CONTACT": "CONTACTED",
    "NOANSWER": "NO_ANSWER",
    "NO_ANSWER": "NO_ANSWER",
    "NO-ANSWER": "NO_ANSWER",
    "INTERESTED": "INTERESTED",
    "CONVERTED": "CONVERTED",
    "CONVERT": "CONVERTED",
    "NOTINTERESTED": "NOT_INTERESTED",
    "NOT_INTERESTED": "NOT_INTERESTED",
    "DNC": "DO_NOT_CONTACT",
    "DO_NOT_CONTACT": "DO_NOT_CONTACT",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_tables() -> None:
    with core.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lead_attribution (
                user_id INTEGER PRIMARY KEY,
                campaign TEXT NOT NULL DEFAULT 'direct',
                first_start_arg TEXT NOT NULL DEFAULT '',
                first_seen_at TEXT NOT NULL,
                last_start_arg TEXT NOT NULL DEFAULT '',
                last_seen_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lead_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                event TEXT NOT NULL,
                value TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_lead_events_user "
            "ON lead_events(user_id, created_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_lead_events_event "
            "ON lead_events(event, created_at)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lead_user_map (
                user_id INTEGER PRIMARY KEY,
                mobile_e164 TEXT NOT NULL,
                linked_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_lead_user_map_mobile "
            "ON lead_user_map(mobile_e164)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sales_leads (
                mobile_e164 TEXT PRIMARY KEY,
                primary_user_id INTEGER NOT NULL,
                campaign TEXT NOT NULL DEFAULT 'direct',
                status TEXT NOT NULL DEFAULT 'NEW',
                assigned_agent TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                contact_permission_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_contact_at TEXT,
                converted_at TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sales_leads_status "
            "ON sales_leads(status, updated_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sales_leads_campaign "
            "ON sales_leads(campaign, created_at)"
        )


def _clean_start_arg(arg: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]", "", str(arg or ""))[:64]
    return value


def campaign_from_start_arg(arg: str) -> str:
    arg = _clean_start_arg(arg)
    if not arg:
        return "direct"
    low = arg.lower()
    if low.startswith("ad_"):
        return low
    if low in INTERNAL_START_ARGS:
        return "internal"
    return f"ref_{low}"[:64]


def record_event(user_id: int, event: str, value: str = "") -> None:
    if not user_id:
        return
    ensure_tables()
    with core.db() as conn:
        conn.execute(
            "INSERT INTO lead_events(user_id,event,value,created_at) VALUES(?,?,?,?)",
            (
                int(user_id),
                str(event or "unknown")[:64],
                str(value or "")[:160],
                _now_iso(),
            ),
        )


def record_start(user_id: int, arg: str = "") -> str:
    """Persist the first acquisition campaign before any verification gate."""
    if not user_id:
        return "direct"

    ensure_tables()
    now = _now_iso()
    start_arg = _clean_start_arg(arg)
    candidate = campaign_from_start_arg(start_arg)

    with core.db() as conn:
        existing = conn.execute(
            "SELECT campaign FROM lead_attribution WHERE user_id=?",
            (int(user_id),),
        ).fetchone()

        if existing:
            current = str(existing["campaign"] or "direct")
            # Do not overwrite a genuine ad/referrer with later internal starts.
            chosen = current
            if current in {"direct", "internal"} and candidate not in {"direct", "internal"}:
                chosen = candidate
            conn.execute(
                """
                UPDATE lead_attribution
                SET campaign=?, last_start_arg=?, last_seen_at=?
                WHERE user_id=?
                """,
                (chosen, start_arg, now, int(user_id)),
            )
            campaign = chosen
        else:
            campaign = candidate
            conn.execute(
                """
                INSERT INTO lead_attribution(
                    user_id,campaign,first_start_arg,first_seen_at,
                    last_start_arg,last_seen_at
                ) VALUES(?,?,?,?,?,?)
                """,
                (int(user_id), campaign, start_arg, now, start_arg, now),
            )

    if campaign not in {"direct", "internal"}:
        with core.db() as conn:
            mapped = conn.execute(
                "SELECT mobile_e164 FROM lead_user_map WHERE user_id=?",
                (int(user_id),),
            ).fetchone()
            if mapped:
                conn.execute(
                    """
                    UPDATE sales_leads
                    SET campaign=CASE
                        WHEN campaign IN ('direct','internal') THEN ?
                        ELSE campaign END,
                        updated_at=?
                    WHERE mobile_e164=?
                    """,
                    (campaign, _now_iso(), str(mapped["mobile_e164"])),
                )

    record_event(user_id, "bot_start", campaign)
    return campaign


def campaign_for_user(user_id: int) -> str:
    ensure_tables()
    with core.db() as conn:
        row = conn.execute(
            "SELECT campaign FROM lead_attribution WHERE user_id=?",
            (int(user_id),),
        ).fetchone()
    return str(row["campaign"]) if row and row["campaign"] else "direct"


def on_verification_prompt(user_id: int, source: str) -> None:
    record_event(user_id, "verification_prompt", str(source or "unknown"))


def on_verified(user_id: int, mobile_e164: str, source: str) -> bool:
    """Create/update one sales lead per verified mobile number.

    Returns True only when this mobile number becomes a new deduplicated lead.
    """
    if not user_id or not mobile_e164:
        return False

    ensure_tables()
    now = _now_iso()
    campaign = campaign_for_user(user_id)

    with core.db() as conn:
        conn.execute(
            """
            INSERT INTO lead_user_map(user_id,mobile_e164,linked_at)
            VALUES(?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET
                mobile_e164=excluded.mobile_e164,
                linked_at=excluded.linked_at
            """,
            (int(user_id), str(mobile_e164), now),
        )

        existing = conn.execute(
            "SELECT primary_user_id,campaign,status,created_at "
            "FROM sales_leads WHERE mobile_e164=?",
            (str(mobile_e164),),
        ).fetchone()

        is_new_lead = not bool(existing)

        if existing:
            existing_campaign = str(existing["campaign"] or "direct")
            chosen_campaign = existing_campaign
            if existing_campaign in {"direct", "internal"} and campaign not in {"direct", "internal"}:
                chosen_campaign = campaign
            conn.execute(
                """
                UPDATE sales_leads
                SET campaign=?, updated_at=?,
                    contact_permission_at=COALESCE(contact_permission_at, ?)
                WHERE mobile_e164=?
                """,
                (chosen_campaign, now, now, str(mobile_e164)),
            )
        else:
            conn.execute(
                """
                INSERT INTO sales_leads(
                    mobile_e164,primary_user_id,campaign,status,
                    assigned_agent,notes,contact_permission_at,
                    created_at,updated_at,last_contact_at,converted_at
                ) VALUES(?,?,?,'NEW','','',?,?,?,NULL,NULL)
                """,
                (str(mobile_e164), int(user_id), campaign, now, now, now),
            )

    record_event(user_id, "verified_mobile", f"{source}|{campaign}")
    return is_new_lead



async def notify_admin_verified(application, user_id: int, mobile_e164: str, source: str, is_new_lead: bool) -> None:
    """Notify the Fantzo admin immediately when a new deduplicated lead verifies."""
    if not is_new_lead:
        return

    campaign = campaign_for_user(user_id)
    ensure_tables()
    with core.db() as conn:
        user = conn.execute(
            "SELECT username,first_name FROM users WHERE user_id=?",
            (int(user_id),),
        ).fetchone()

    username = str(user["username"] or "") if user else ""
    first_name = str(user["first_name"] or "") if user else ""

    try:
        await application.bot.send_message(
            chat_id=core.ADMIN_USER_ID,
            text=(
                "🔥 <b>NEW VERIFIED FANTZO LEAD</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                f"Mobile: <code>{escape(str(mobile_e164))}</code>\n"
                f"Telegram: @{escape(username) if username else '—'}\n"
                f"Name: {escape(first_name or '—')}\n"
                f"Campaign: <code>{escape(campaign)}</code>\n"
                f"Verification source: <code>{escape(str(source or 'unknown'))}</code>\n"
                f"User ID: <code>{int(user_id)}</code>\n\n"
                f"Lead status: <b>NEW</b>\n"
                f"Open: <code>/lead {int(user_id)}</code>\n"
                f"After contact: <code>/leadstatus {int(user_id)} CONTACTED</code>"
            ),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception:
        logger.exception("Could not send Fantzo new-lead admin alert")


def record_post_verify_view(user_id: int) -> None:
    record_event(user_id, "post_verify_view", campaign_for_user(user_id))


def record_post_verify_action(user_id: int, action: str) -> None:
    record_event(user_id, "post_verify_action", str(action or "")[:120])


def _styled_button(label: str, *, style: str | None = None, **kwargs):
    if style:
        kwargs["api_kwargs"] = {"style": style}
    return InlineKeyboardButton(label, **kwargs)


def _campaign_primary(campaign: str) -> tuple[str, str]:
    value = str(campaign or "").lower()
    if "cricket" in value:
        return "🏏 CRICKET NOW", "cricket"
    if "football" in value or "soccer" in value:
        return "⚽ FOOTBALL NOW", "football"
    if "fixture" in value:
        return "📅 TODAY'S FIXTURES", "upcoming"
    if "live" in value or "score" in value:
        return "🔴 LIVE SCORES", "live_now"
    return "🔴 LIVE SCORES", "live_now"


def post_verify_keyboard(user_id: int) -> InlineKeyboardMarkup:
    campaign = campaign_for_user(user_id)
    label, action = _campaign_primary(campaign)
    source = re.sub(r"[^a-zA-Z0-9_-]", "", campaign)[:40] or "direct"

    return InlineKeyboardMarkup(
        [
            [_styled_button(label, style="primary", callback_data=action)],
            [
                _styled_button(
                    "✨ OPEN FANTZO",
                    style="success",
                    web_app=WebAppInfo(
                        url=tracked.analytics.tracking_url(
                            f"verified_{source}",
                            "home",
                        )
                    ),
                )
            ],
            [InlineKeyboardButton("🏟 FULL SPORTS MENU", callback_data="back")],
        ]
    )


def post_verify_text(user_id: int) -> str:
    campaign = campaign_for_user(user_id)
    if "cricket" in campaign:
        hook = "🏏 Cricket is ready for you."
    elif "football" in campaign or "soccer" in campaign:
        hook = "⚽ Football is ready for you."
    elif "fixture" in campaign:
        hook = "📅 Today's fixtures are ready."
    else:
        hook = "🔥 Your Fantzo sports experience is ready."

    return (
        "✅ <b>VERIFICATION COMPLETE</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"{hook}\n\n"
        "Live scores, fixtures, Live TV and Fantzo are now unlocked.\n\n"
        "Choose where you want to go 👇"
    )


async def send_post_verify(message, user_id: int) -> None:
    record_post_verify_view(user_id)
    text = post_verify_text(user_id)
    markup = post_verify_keyboard(user_id)

    # Reuse the existing Fantzo home banner when one is configured, so the
    # conversion screen feels visual without creating another asset workflow.
    try:
        banner_file_id = tracked.app.get_banner_file_id()
    except Exception:
        banner_file_id = ""

    if banner_file_id:
        try:
            await message.reply_photo(
                photo=banner_file_id,
                caption=text,
                parse_mode="HTML",
                reply_markup=markup,
            )
            return
        except Exception:
            logger.exception("Could not send Fantzo post-verification hero banner")

    await message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=markup,
        disable_web_page_preview=True,
    )


def _resolve_mobile(identifier: str) -> str | None:
    ensure_tables()
    raw = str(identifier or "").strip()
    digits = re.sub(r"\D", "", raw)

    with core.db() as conn:
        if raw.isdigit():
            row = conn.execute(
                "SELECT mobile_e164 FROM lead_user_map WHERE user_id=?",
                (int(raw),),
            ).fetchone()
            if row:
                return str(row["mobile_e164"])

        if digits:
            e164 = f"+{digits}"
            row = conn.execute(
                "SELECT mobile_e164 FROM sales_leads WHERE mobile_e164=?",
                (e164,),
            ).fetchone()
            if row:
                return str(row["mobile_e164"])

        row = conn.execute(
            """
            SELECT m.mobile_e164
            FROM users u
            JOIN lead_user_map m ON m.user_id=u.user_id
            WHERE lower(u.username)=lower(?)
            LIMIT 1
            """,
            (raw.lstrip("@"),),
        ).fetchone()
        if row:
            return str(row["mobile_e164"])

    return None


def _admin_only(update) -> bool:
    user = update.effective_user
    return bool(user and int(user.id) == int(core.ADMIN_USER_ID))


def _lead_row(mobile: str):
    ensure_tables()
    with core.db() as conn:
        return conn.execute(
            """
            SELECT s.*,u.username,u.first_name,a.first_start_arg,a.last_start_arg
            FROM sales_leads s
            LEFT JOIN users u ON u.user_id=s.primary_user_id
            LEFT JOIN lead_attribution a ON a.user_id=s.primary_user_id
            WHERE s.mobile_e164=?
            """,
            (mobile,),
        ).fetchone()


async def lead_command(update, context) -> None:
    if not _admin_only(update) or not update.effective_message:
        return
    if not context.args:
        await update.effective_message.reply_text(
            "Usage: <code>/lead &lt;user_id | @username | mobile&gt;</code>",
            parse_mode="HTML",
        )
        return

    mobile = _resolve_mobile(context.args[0])
    if not mobile:
        await update.effective_message.reply_text("Lead not found.")
        return

    row = _lead_row(mobile)
    if not row:
        await update.effective_message.reply_text("Lead not found.")
        return

    await update.effective_message.reply_text(
        "🎯 <b>FANTZO LEAD</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"Mobile: <code>{escape(str(row['mobile_e164']))}</code>\n"
        f"Telegram: @{escape(str(row['username'] or '—'))}\n"
        f"Name: {escape(str(row['first_name'] or '—'))}\n"
        f"Campaign: <code>{escape(str(row['campaign'] or 'direct'))}</code>\n"
        f"Status: <b>{escape(str(row['status']))}</b>\n"
        f"Agent: {escape(str(row['assigned_agent'] or '—'))}\n"
        f"Created: {escape(str(row['created_at']))}\n"
        f"Last contact: {escape(str(row['last_contact_at'] or '—'))}\n"
        f"Notes: {escape(str(row['notes'] or '—'))}",
        parse_mode="HTML",
    )


async def leadstatus_command(update, context) -> None:
    if not _admin_only(update) or not update.effective_message:
        return
    if len(context.args) < 2:
        await update.effective_message.reply_text(
            "Usage: <code>/leadstatus &lt;lead&gt; &lt;NEW|CONTACTED|NO_ANSWER|INTERESTED|CONVERTED|NOT_INTERESTED|DO_NOT_CONTACT&gt;</code>",
            parse_mode="HTML",
        )
        return

    mobile = _resolve_mobile(context.args[0])
    status = STATUS_ALIASES.get(str(context.args[1]).upper())
    if not mobile or not status:
        await update.effective_message.reply_text("Lead or status not recognised.")
        return

    now = _now_iso()
    with core.db() as conn:
        conn.execute(
            """
            UPDATE sales_leads
            SET status=?, updated_at=?,
                last_contact_at=CASE
                    WHEN ? IN ('CONTACTED','NO_ANSWER','INTERESTED','CONVERTED','NOT_INTERESTED','DO_NOT_CONTACT')
                    THEN ? ELSE last_contact_at END,
                converted_at=CASE WHEN ?='CONVERTED' THEN ? ELSE converted_at END
            WHERE mobile_e164=?
            """,
            (status, now, status, now, status, now, mobile),
        )

    await update.effective_message.reply_text(
        f"✅ Lead <code>{escape(mobile)}</code> → <b>{escape(status)}</b>",
        parse_mode="HTML",
    )


async def leadassign_command(update, context) -> None:
    if not _admin_only(update) or not update.effective_message:
        return
    if len(context.args) < 2:
        await update.effective_message.reply_text(
            "Usage: <code>/leadassign &lt;lead&gt; &lt;agent name&gt;</code>",
            parse_mode="HTML",
        )
        return

    mobile = _resolve_mobile(context.args[0])
    agent = " ".join(context.args[1:]).strip()[:120]
    if not mobile:
        await update.effective_message.reply_text("Lead not found.")
        return

    with core.db() as conn:
        conn.execute(
            "UPDATE sales_leads SET assigned_agent=?,updated_at=? WHERE mobile_e164=?",
            (agent, _now_iso(), mobile),
        )
    await update.effective_message.reply_text(
        f"✅ Assigned <code>{escape(mobile)}</code> to <b>{escape(agent)}</b>",
        parse_mode="HTML",
    )


async def leadnote_command(update, context) -> None:
    if not _admin_only(update) or not update.effective_message:
        return
    if len(context.args) < 2:
        await update.effective_message.reply_text(
            "Usage: <code>/leadnote &lt;lead&gt; &lt;note&gt;</code>",
            parse_mode="HTML",
        )
        return

    mobile = _resolve_mobile(context.args[0])
    note = " ".join(context.args[1:]).strip()[:1000]
    if not mobile:
        await update.effective_message.reply_text("Lead not found.")
        return

    with core.db() as conn:
        conn.execute(
            "UPDATE sales_leads SET notes=?,updated_at=? WHERE mobile_e164=?",
            (note, _now_iso(), mobile),
        )
    await update.effective_message.reply_text("✅ Lead note saved.")



def _backfill_existing_verified_users() -> None:
    """Seed CRM rows for already-verified users without fabricating consent."""
    ensure_tables()
    with core.db() as conn:
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='live_tv_mobile_users' LIMIT 1"
        ).fetchone()
        if not table:
            return
        rows = conn.execute(
            "SELECT user_id,mobile_e164,created_at,updated_at "
            "FROM live_tv_mobile_users WHERE capture_method='telegram_contact'"
        ).fetchall()

    for row in rows:
        user_id = int(row["user_id"])
        mobile = str(row["mobile_e164"])
        campaign = campaign_for_user(user_id)
        created = str(row["created_at"] or _now_iso())
        updated = str(row["updated_at"] or created)

        with core.db() as conn:
            conn.execute(
                """
                INSERT INTO lead_user_map(user_id,mobile_e164,linked_at)
                VALUES(?,?,?)
                ON CONFLICT(user_id) DO UPDATE SET
                    mobile_e164=excluded.mobile_e164
                """,
                (user_id, mobile, updated),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO sales_leads(
                    mobile_e164,primary_user_id,campaign,status,
                    assigned_agent,notes,contact_permission_at,
                    created_at,updated_at,last_contact_at,converted_at
                ) VALUES(?,?,?,'NEW','','',NULL,?,?,NULL,NULL)
                """,
                (mobile, user_id, campaign, created, updated),
            )


async def adlink_command(update, context) -> None:
    if not _admin_only(update) or not update.effective_message:
        return

    raw = "_".join(context.args).strip() if context.args else "main_01"
    slug = re.sub(r"[^a-zA-Z0-9_-]", "_", raw).strip("_").lower()[:50] or "main_01"
    if not slug.startswith("ad_"):
        slug = f"ad_{slug}"

    await update.effective_message.reply_text(
        "📣 <b>TELEGRAM ADS TRACKING LINK</b>\n\n"
        f"<code>https://t.me/fantzoofficialbot?start={escape(slug)}</code>\n\n"
        "Use a different code for each ad or campaign so verified leads can be attributed correctly.",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


def install() -> None:
    global _installed
    if _installed:
        return
    _installed = True
    ensure_tables()
    _backfill_existing_verified_users()
    logger.info("Fantzo paid-ads lead attribution and CRM installed")


def register_handlers(application) -> None:
    application.add_handler(CommandHandler("lead", lead_command))
    application.add_handler(CommandHandler("leadstatus", leadstatus_command))
    application.add_handler(CommandHandler("leadassign", leadassign_command))
    application.add_handler(CommandHandler("leadnote", leadnote_command))
    application.add_handler(CommandHandler("adlink", adlink_command))
    logger.info("Fantzo lead CRM admin commands registered")
