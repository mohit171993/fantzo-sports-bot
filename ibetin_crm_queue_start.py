"""IBETIN-only CRM queue repair; keeps the existing bot, reports and database.

Rollback: restore Railway start command to
    python ibetin_liveline_v30_unified_ui.py
No contact details or credentials are written to diagnostics.
"""
import json
import logging
import threading
import time
from datetime import datetime, timezone

VERSION = "2026-09-22-final-flow-v4-meta-landing"
TEST_USERNAME = "mohit_97saxena"
log = logging.getLogger(__name__)
NEW_SQL = "COALESCE(NULLIF(TRIM(l.lead_status),''),'new')='new'"
PHONE_SQL = "COALESCE(NULLIF(TRIM(l.mobile_number),''),NULLIF(TRIM(v.phone_number),''),'')!=''"
JOIN_SQL = "ibetin_leads l LEFT JOIN liveline_verified_users v ON v.user_id=l.user_id"


def queue_sql(queue):
    """Owner assignment never removes a lead that still has no CRM outcome."""
    now = datetime.now(timezone.utc).isoformat()
    clauses = {
        "new": (NEW_SQL, ()),
        "all": ("1=1", ()),
        "mobile": (PHONE_SQL, ()),
        "followup": ("l.lead_status IN ('contacted','no_answer')", ()),
        "due": ("l.next_followup_at IS NOT NULL AND l.next_followup_at<=? "
                "AND COALESCE(l.lead_status,'new') NOT IN ('converted','dnc')", (now,)),
        "interested": ("l.lead_status='interested'", ()),
        "converted": ("l.lead_status='converted'", ()),
    }
    if queue not in clauses:
        return None
    where, args = clauses[queue]
    order = ("l.next_followup_at ASC, l.user_id DESC" if queue == "due" else
             "COALESCE(l.next_followup_at,l.updated_at) ASC, l.user_id DESC" if queue == "followup" else
             "l.first_seen_at DESC, l.user_id DESC")
    return f"SELECT l.user_id FROM {JOIN_SQL} WHERE {where} ORDER BY {order}", args


def snapshot(reports):
    """Aggregate-only audit of actual CRM data; no phone values or identities."""
    with reports.core.db() as conn:
        row = conn.execute(f"""
            SELECT COUNT(*) total,
                   COALESCE(SUM(CASE WHEN {NEW_SQL} THEN 1 ELSE 0 END),0) new,
                   COALESCE(SUM(CASE WHEN {NEW_SQL} AND v.user_id IS NOT NULL THEN 1 ELSE 0 END),0) new_verified,
                   COALESCE(SUM(CASE WHEN {NEW_SQL} AND l.assigned_to IS NOT NULL THEN 1 ELSE 0 END),0) new_owned,
                   COALESCE(SUM(CASE WHEN {PHONE_SQL} THEN 1 ELSE 0 END),0) with_mobile,
                   COUNT(v.user_id) verified
            FROM {JOIN_SQL}
        """).fetchone()
        result = dict(row)
        result["statuses"] = {str(r[0] or "new"): r[1] for r in conn.execute(
            "SELECT lead_status,COUNT(*) FROM ibetin_leads GROUP BY lead_status"
        ).fetchall()}
        result["bot_users"] = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        result["bot_users_missing_from_crm"] = conn.execute(
            "SELECT COUNT(*) FROM users u LEFT JOIN ibetin_leads l ON l.user_id=u.user_id WHERE l.user_id IS NULL"
        ).fetchone()[0]
        return result


def reset_test_once(reports):
    """Legacy automatic verification reset/restore is permanently disabled."""
    log.info("IBETIN CRM legacy verification reset/restore disabled")
    return


def force_test_unverified_once(reports):
    """Explicit operator request: keep only mohit_97saxena unverified for testing."""
    marker = "ibetin_test_unverified:2026-09-23-manual"
    with reports.core.db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT)")
        if conn.execute("SELECT 1 FROM settings WHERE key=?", (marker,)).fetchone():
            return

        ids = {int(r[0]) for r in conn.execute(
            "SELECT user_id FROM users WHERE lower(username)=?", (TEST_USERNAME,)
        ).fetchall()}
        if reports._table_exists(conn, "business_customers"):
            ids.update(int(r[0]) for r in conn.execute(
                "SELECT DISTINCT customer_id FROM business_customers WHERE lower(username)=?",
                (TEST_USERNAME,),
            ).fetchall())
        if len(ids) != 1:
            log.warning("IBETIN test unverify skipped: username match count=%s", len(ids))
            return

        uid = next(iter(ids))
        row = conn.execute(
            "SELECT phone_number FROM liveline_verified_users WHERE user_id=?",
            (uid,),
        ).fetchone()
        if row and str(row["phone_number"] or "").strip():
            conn.execute(
                """
                UPDATE ibetin_leads
                SET mobile_number=CASE
                    WHEN COALESCE(NULLIF(TRIM(mobile_number),''),'')='' THEN ?
                    ELSE mobile_number
                END
                WHERE user_id=?
                """,
                (str(row["phone_number"]), uid),
            )

        conn.execute(
            "DELETE FROM liveline_verified_users WHERE user_id=?",
            (uid,),
        )
        conn.execute(
            "INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
            (marker, "applied"),
        )

        verified = bool(conn.execute(
            "SELECT 1 FROM liveline_verified_users WHERE user_id=?",
            (uid,),
        ).fetchone())
        saved_mobile = bool(conn.execute(
            "SELECT 1 FROM ibetin_leads WHERE user_id=? AND COALESCE(TRIM(mobile_number),'')!=''",
            (uid,),
        ).fetchone())
    log.info(
        "IBETIN test account forced unverified verified=%s saved_mobile=%s",
        verified,
        saved_mobile,
    )


def restore_test_verified_once(reports):
    """Correct the prior wrong-project test reset by restoring this IBETIN user."""
    marker = "ibetin_test_restore_verified:2026-09-23-correction"
    with reports.core.db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT)")
        if conn.execute("SELECT 1 FROM settings WHERE key=?", (marker,)).fetchone():
            return

        ids = {int(r[0]) for r in conn.execute(
            "SELECT user_id FROM users WHERE lower(username)=?", (TEST_USERNAME,)
        ).fetchall()}
        if reports._table_exists(conn, "business_customers"):
            ids.update(int(r[0]) for r in conn.execute(
                "SELECT DISTINCT customer_id FROM business_customers WHERE lower(username)=?",
                (TEST_USERNAME,),
            ).fetchall())
        if len(ids) != 1:
            log.warning("IBETIN test restore skipped: username match count=%s", len(ids))
            return

        uid = next(iter(ids))
        lead = conn.execute(
            """
            SELECT mobile_number,campaign,source,contact_consent
            FROM ibetin_leads WHERE user_id=?
            """,
            (uid,),
        ).fetchone()
        phone = str(lead["mobile_number"] or "").strip() if lead else ""
        if not phone:
            log.warning("IBETIN test restore skipped: saved mobile unavailable")
            return

    import ibetin_phone_verify as phone_verify
    restored = phone_verify.verify_user(
        uid,
        phone,
        source=str(lead["source"] or "bot"),
        campaign=str(lead["campaign"] or "direct"),
        contact_consent=bool(int(lead["contact_consent"] or 0)),
    )
    with reports.core.db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
            (marker, "applied" if restored else "failed"),
        )
        verified = bool(conn.execute(
            "SELECT 1 FROM liveline_verified_users WHERE user_id=?",
            (uid,),
        ).fetchone())
        saved_mobile = bool(conn.execute(
            "SELECT 1 FROM ibetin_leads WHERE user_id=? AND COALESCE(TRIM(mobile_number),'')!=''",
            (uid,),
        ).fetchone())
    log.info(
        "IBETIN correction restored test account verified=%s saved_mobile=%s",
        verified,
        saved_mobile,
    )


def install(reports):
    if getattr(reports, "_crm_queue_release", None) == VERSION:
        return
    Button, Markup = reports.InlineKeyboardButton, reports.InlineKeyboardMarkup
    old_callback = reports.handle_callback
    old_keyboard = reports.lead_status_keyboard
    old_card = reports._lead_card_text
    old_title = reports._queue_title

    def queue_ids(queue):
        query = queue_sql(queue)
        if query is None:
            return []
        reports.ensure_tables()
        with reports.core.db() as conn:
            return [int(r[0]) for r in conn.execute(*query).fetchall()]

    def title(queue):
        return {"new": "🆕 NEW / UNWORKED · ALL TIME",
                "all": "👥 ALL LEADS · ALL TIME",
                "mobile": "📱 LEADS WITH SAVED MOBILE · ALL TIME"}.get(queue) or old_title(queue)

    def crm_text():
        reports.ensure_tables()
        data = snapshot(reports)
        counts = data["statuses"]
        followup = counts.get("contacted", 0) + counts.get("no_answer", 0)
        due = len(queue_ids("due"))
        try:
            import fantzo_reminders as reminders
            auto = reminders.automation_status()
            reminder_state = "🟢 ON" if auto["reminders_enabled"] else "🔴 PAUSED"
            channel_state = "🟢 ON" if auto["channel_enabled"] else "🔴 PAUSED"
            channel_time = auto["channel_time"]
            sent_24h = auto["reminder_sent_24h"]
        except Exception:
            reminder_state = "⚪ UNKNOWN"
            channel_state = "⚪ UNKNOWN"
            channel_time = "10:00"
            sent_24h = 0
        return (
            "📊 <b>IBETIN ADMIN DASHBOARD</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            "<b>LEADS</b>\n"
            f"👥 Total: <b>{data['total']}</b> · 📱 Mobile: <b>{data['with_mobile']}</b> · ✅ Verified: <b>{data['verified']}</b>\n"
            f"🆕 New/Unworked: <b>{data['new']}</b> · ⏰ Due: <b>{due}</b> · 📞 Follow-up: <b>{followup}</b>\n"
            f"⭐ Interested: <b>{counts.get('interested',0)}</b> · ✅ Converted: <b>{counts.get('converted',0)}</b>\n\n"
            "<b>AUTOMATION</b>\n"
            f"🔔 Reminders: <b>{reminder_state}</b> · sent 24h: <b>{sent_24h}</b>\n"
            f"📢 Channel: <b>{channel_state}</b> · daily <b>{channel_time}</b> Dubai\n\n"
            f"⚠️ Not verified: <b>{data['total']-data['verified']}</b> · 👨‍💼 New already assigned: <b>{data['new_owned']}</b>"
        )

    def menu():
        def b(text, action):
            return Button(text, callback_data="reports:" + action)
        return Markup([
            [b("🆕 NEW / UNWORKED", "queue:new"), b("⏰ DUE NOW", "queue:due")],
            [b("👥 ALL LEADS", "queue:all"), b("📱 SAVED MOBILES", "queue:mobile")],
            [b("📞 FOLLOW-UP", "queue:followup"), b("⭐ INTERESTED", "queue:interested")],
            [b("🔎 SEARCH", "search"), b("📥 CSV EXPORT", "exportleads")],
            [b("✅ CONVERTED", "queue:converted"), b("🎯 AD PERFORMANCE", "adperformance")],
            [b("🤖 AUTOMATION", "automation"), b("📚 TEAM GUIDE", "guide")],
            [b("⚙️ ADVANCED REPORTS", "advanced")],
        ])

    def automation_text():
        import fantzo_reminders as reminders
        auto = reminders.automation_status()
        reminder_state = "🟢 RUNNING" if auto["reminders_enabled"] else "🔴 PAUSED"
        channel_state = "🟢 RUNNING" if auto["channel_enabled"] else "🔴 PAUSED"
        last = auto.get("last_channel") or {}
        last_status = str(last.get("status") or "No post yet").upper()
        last_at = reports._fmt_admin_time(str(last.get("sent_at") or ""))
        return (
            "🤖 <b>AUTOMATION CONTROL</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            f"🔔 Reminders: <b>{reminder_state}</b>\n"
            f"   Sent in last 24h: <b>{auto['reminder_sent_24h']}</b>\n\n"
            f"📢 Channel posts: <b>{channel_state}</b>\n"
            f"   Schedule: <b>{auto['channel_time']} Dubai</b> every day\n"
            f"   Last: <b>{last_status}</b> · {last_at}\n\n"
            "Changes apply immediately. No redeploy is required."
        )

    def automation_menu():
        import fantzo_reminders as reminders
        auto = reminders.automation_status()
        reminder_button = (
            "⏸ PAUSE REMINDERS" if auto["reminders_enabled"] else "▶️ RESUME REMINDERS"
        )
        channel_button = (
            "⏸ PAUSE CHANNEL" if auto["channel_enabled"] else "▶️ RESUME CHANNEL"
        )
        return Markup([
            [b(reminder_button, "auto:reminders:toggle")],
            [b(channel_button, "auto:channel:toggle")],
            [b("🔄 REFRESH STATUS", "automation")],
            [b("⬅️ DASHBOARD", "crm")],
        ])

    def card(lead):
        text = old_card(lead)
        if not lead.get("is_currently_verified") and int(lead.get("contact_consent") or 0):
            text = text.replace("ℹ️ Contact consent not available · verification incomplete",
                                "✅ Call + WhatsApp consent recorded · currently not verified")
        return text

    def keyboard(uid):
        lead = reports._lead_view(uid) or {}
        rows = list(old_keyboard(uid).inline_keyboard)
        if str(lead.get("lead_status") or "").lower() == "dnc":
            rows = [row for row in rows if not any(str(getattr(b, "url", "") or "").startswith("https://wa.me/") for b in row)]
        return Markup(rows)

    def guide():
        return (
            "📚 <b>IBETIN TEAM GUIDE</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            "<b>Unassigned / New:</b> All old and new leads without a CRM outcome. "
            "They can be verified or unverified. Assigning an owner does not hide a New lead.\n\n"
            "<b>All Leads / Saved Mobiles:</b> Browse all-time records across every status, one record at a time. "
            "Previous / Next stays available after assigning or updating a status.\n\n"
            "<b>Calling:</b> Tap the mobile number to copy it into your dialler. "
            "<b>WhatsApp:</b> Use OPEN WHATSAPP only where contact consent is recorded. "
            "A saved phone does not itself prove consent.\n\n"
            "<b>Statuses:</b> Contacted = genuine contact attempt; No Answer = no response; "
            "Interested = positive response; Converted = completed goal; DNC = do not contact. "
            "DNC remains visible for audit, but must not be called or messaged.\n\n"
            "Add notes and follow-up times so the team can see the next action. "
            "CSV Export includes all CRM leads, their stored mobiles and current verification status."
        )

    async def callback(update, context):
        query = update.callback_query
        data = str(getattr(query, "data", "") or "")
        user = update.effective_user
        if not query or not user or not reports.is_authorized_admin(user.id):
            return await old_callback(update, context)
        states = context.user_data.setdefault("ibetin_crm_queue_messages", {})
        message = query.message
        key = f"{message.chat_id}:{message.message_id}" if message else ""
        state = states.get(key)

        if data == "reports:automation":
            try:
                await query.answer()
            except Exception:
                pass
            await message.reply_text(
                automation_text(),
                parse_mode="HTML",
                reply_markup=automation_menu(),
                disable_web_page_preview=True,
            )
            return True

        if data.startswith("reports:auto:"):
            parts = data.split(":")
            if len(parts) == 4 and parts[3] == "toggle":
                kind = parts[2]
                import fantzo_reminders as reminders
                auto = reminders.automation_status()
                current = (
                    auto["reminders_enabled"]
                    if kind == "reminders"
                    else auto["channel_enabled"]
                    if kind == "channel"
                    else None
                )
                if current is not None:
                    reminders.set_automation_enabled(kind, not bool(current))
            try:
                await query.answer("Updated")
            except Exception:
                pass
            try:
                await query.edit_message_text(
                    automation_text(),
                    parse_mode="HTML",
                    reply_markup=automation_menu(),
                    disable_web_page_preview=True,
                )
            except Exception as exc:
                if "message is not modified" not in str(exc).lower():
                    raise
            return True

        if data.startswith("reports:queue:") or data.startswith("reports:qitem:"):
            parts = data.split(":")
            queue = parts[2] if len(parts) >= 3 else "new"
            try:
                index = int(parts[3]) if len(parts) == 4 else 0
            except ValueError:
                index = 0
            lead, index, total = reports._queue_item(queue, index)
            try:
                await query.answer()
            except Exception:
                pass
            if lead:
                text = f"{title(queue)}\n<b>Record {index+1} of {total}</b>\n\n" + card(lead)
                markup = reports._queue_card_keyboard(int(lead["user_id"]), queue, index, total)
            else:
                text, markup = title(queue) + "\n\n✅ No records in this queue.", reports.queue_menu(queue)
            kwargs = dict(text=text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
            if data.startswith("reports:queue:"):
                sent = await message.reply_text(**kwargs)
                key = f"{sent.chat_id}:{sent.message_id}"
            else:
                try:
                    await query.edit_message_text(**kwargs)
                except Exception as exc:
                    if "message is not modified" not in str(exc).lower():
                        raise
            if lead:
                states[key] = {"queue": queue, "index": index, "uid": int(lead["user_id"])}
            else:
                states.pop(key, None)
            while len(states) > 30:
                states.pop(next(iter(states)))
            return True
        result = await old_callback(update, context)
        if state and (data.startswith("reports:assign:") or data.startswith("reports:lead:")):
            ids = queue_ids(state["queue"])
            uid = state["uid"]
            if uid in ids:
                index = ids.index(uid)
                markup = reports._queue_card_keyboard(uid, state["queue"], index, len(ids))
                state["index"] = index
            else:
                index = min(state["index"], max(0, len(ids)-1))
                rows = list(keyboard(uid).inline_keyboard)
                if ids:
                    rows.insert(max(0,len(rows)-1), [Button("NEXT RECORD ▶️", callback_data=f"reports:qitem:{state['queue']}:{index}")])
                markup = Markup(rows)
            try:
                await query.edit_message_reply_markup(reply_markup=markup)
            except Exception as exc:
                if "message is not modified" not in str(exc).lower():
                    log.warning("IBETIN CRM navigation refresh failed: %s", type(exc).__name__)
        return result

    reports._queue_ids = queue_ids
    reports._queue_title = title
    reports._crm_text = crm_text
    reports.crm_menu = menu
    reports._team_guide_text = guide
    reports._lead_card_text = card
    reports.lead_status_keyboard = keyboard
    reports.handle_callback = callback
    reports._crm_queue_release = VERSION


def _start_acquisition_snapshot_logger(reports) -> None:
    def worker():
        # Immediate baseline, then one snapshot every two hours.
        while True:
            try:
                log.info(
                    "IBETIN_ACQUISITION_SNAPSHOT %s",
                    json.dumps(snapshot(reports), sort_keys=True, separators=(",", ":")),
                )
            except Exception as exc:
                log.warning(
                    "IBETIN_ACQUISITION_SNAPSHOT unavailable error_type=%s",
                    type(exc).__name__,
                )
            time.sleep(2 * 60 * 60)

    threading.Thread(
        target=worker,
        name="ibetin-acquisition-snapshot",
        daemon=True,
    ).start()


def main():
    # The existing entry point sets persistent DB_PATH before importing core.
    import ibetin_liveline_v30_unified_ui as runtime
    import ibetin_reports as reports
    install(reports)
    reports.ensure_tables()
    reset_test_once(reports)
    force_test_unverified_once(reports)
    restore_test_verified_once(reports)
    log.info("IBETIN CRM QUEUE AUDIT release=%s counts=%s", VERSION, json.dumps(snapshot(reports), sort_keys=True))
    log.info("IBETIN CRM queue repair installed; all-time queues, phones and navigation enabled")
    _start_acquisition_snapshot_logger(reports)
    runtime.app.base.ibetin_start.main()


if __name__ == "__main__":
    main()
