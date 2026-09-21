"""IBETIN-only CRM queue repair; keeps the existing bot, reports and database.

Rollback: restore Railway start command to
    python ibetin_liveline_v30_unified_ui.py
No contact details or credentials are written to diagnostics.
"""
import json
import logging
from datetime import datetime, timezone

VERSION = "2026-09-22-crm-queue-v1"
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
    """Reset only the requested test account once per release, preserving its phone."""
    marker = "ibetin_crm_test_reset:" + VERSION
    with reports.core.db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT)")
        ids = {int(r[0]) for r in conn.execute(
            "SELECT user_id FROM users WHERE lower(username)=?", (TEST_USERNAME,)
        ).fetchall()}
        if reports._table_exists(conn, "business_customers"):
            ids.update(int(r[0]) for r in conn.execute(
                "SELECT DISTINCT customer_id FROM business_customers WHERE lower(username)=?", (TEST_USERNAME,)
            ).fetchall())
        if len(ids) != 1:
            log.warning("IBETIN CRM test reset not applied: username match count=%s", len(ids))
            return
        uid = next(iter(ids))
        if not conn.execute("SELECT 1 FROM settings WHERE key=?", (marker,)).fetchone():
            conn.execute("""
                UPDATE ibetin_leads SET mobile_number=COALESCE(NULLIF(TRIM(mobile_number),''),
                    (SELECT phone_number FROM liveline_verified_users WHERE user_id=?))
                WHERE user_id=?
            """, (uid, uid))
            conn.execute("DELETE FROM liveline_verified_users WHERE user_id=?", (uid,))
            conn.execute("INSERT INTO settings(key,value) VALUES(?,?)", (marker, "applied"))
        verified = bool(conn.execute("SELECT 1 FROM liveline_verified_users WHERE user_id=?", (uid,)).fetchone())
        phone_saved = bool(conn.execute(
            "SELECT 1 FROM ibetin_leads WHERE user_id=? AND COALESCE(TRIM(mobile_number),'')!=''", (uid,)
        ).fetchone())
    log.info("IBETIN CRM test account audit verified=%s phone_saved=%s release=%s", verified, phone_saved, VERSION)


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
        return {"new": "🆕 UNASSIGNED / NEW · ALL TIME",
                "all": "👥 ALL LEADS · ALL TIME",
                "mobile": "📱 LEADS WITH SAVED MOBILE · ALL TIME"}.get(queue) or old_title(queue)

    def crm_text():
        reports.ensure_tables()
        data = snapshot(reports)
        counts = data["statuses"]
        followup = counts.get("contacted", 0) + counts.get("no_answer", 0)
        return (
            "📞 <b>IBETIN TEAM WORK QUEUE</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            f"👥 All leads · ALL TIME: <b>{data['total']}</b>\n"
            f"📱 Saved mobile: <b>{data['with_mobile']}</b> · Not saved: <b>{data['total']-data['with_mobile']}</b>\n\n"
            f"🆕 Unassigned / New: <b>{data['new']}</b>\n"
            f"✅ Verified: <b>{data['new_verified']}</b> · ⚠️ Not verified: <b>{data['new']-data['new_verified']}</b>\n"
            f"👨‍💼 New leads already owned by team: <b>{data['new_owned']}</b>\n"
            f"📞 Follow-up: <b>{followup}</b> · ⏰ Due now: <b>{len(queue_ids('due'))}</b>\n"
            f"⭐ Interested: <b>{counts.get('interested',0)}</b> · ✅ Converted: <b>{counts.get('converted',0)}</b>\n\n"
            "New includes every historical lead without a CRM outcome, even after assignment to a teammate. "
            "Verification is separate. All Leads includes every status; saved mobiles remain visible after a verification reset."
        )

    def menu():
        def b(text, action):
            return Button(text, callback_data="reports:" + action)
        return Markup([
            [b("🆕 UNASSIGNED / NEW", "queue:new")],
            [b("👥 ALL LEADS", "queue:all"), b("📱 SAVED MOBILES", "queue:mobile")],
            [b("📞 FOLLOW-UP", "queue:followup"), b("⭐ INTERESTED", "queue:interested")],
            [b("🔎 SEARCH", "search"), b("📥 CSV EXPORT", "exportleads")],
            [b("⏰ DUE NOW", "queue:due"), b("✅ CONVERTED", "queue:converted")],
            [b("📚 TEAM GUIDE", "guide"), b("🎯 AD PERFORMANCE", "adperformance")],
            [b("⚙️ ADVANCED REPORTS", "advanced")],
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


def main():
    # The existing entry point sets persistent DB_PATH before importing core.
    import ibetin_liveline_v30_unified_ui as runtime
    import ibetin_reports as reports
    install(reports)
    reports.ensure_tables()
    reset_test_once(reports)
    log.info("IBETIN CRM QUEUE AUDIT release=%s counts=%s", VERSION, json.dumps(snapshot(reports), sort_keys=True))
    log.info("IBETIN CRM queue repair installed; all-time queues, phones and navigation enabled")
    runtime.app.base.ibetin_start.main()


if __name__ == "__main__":
    main()
