"""Fantzo-only CRM operations.

The admin CRM is keyed by Telegram/user ID, like the proven iBetin workflow.
The existing mobile-keyed sales_leads table is kept for deduplicated funnel
reporting and is synchronized when a CRM record has a saved mobile number.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import bot as core
import fantzo_reminders as reminders

logger = logging.getLogger(__name__)

ALLOWED_STATUSES = {
    "NEW",
    "CONTACTED",
    "NO_ANSWER",
    "INTERESTED",
    "CONVERTED",
    "NOT_INTERESTED",
    "DO_NOT_CONTACT",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _table_exists(conn, name: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone())


def _columns(conn, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {
        str(row["name"])
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }


def ensure_tables() -> None:
    """Create the user-keyed CRM and backfill every historical Fantzo identity."""
    with core.db() as conn:
        # Preserve/extend the existing deduplicated mobile lead table.
        if _table_exists(conn, "sales_leads"):
            cols = _columns(conn, "sales_leads")
            migrations = (
                ("assigned_to", "INTEGER"),
                ("next_followup_at", "TEXT"),
                ("last_note", "TEXT"),
                ("updated_by", "INTEGER"),
                ("updated_by_name", "TEXT"),
                ("contacted_at", "TEXT"),
                ("interested_at", "TEXT"),
                ("no_answer_at", "TEXT"),
                ("dnc_at", "TEXT"),
            )
            for name, sql_type in migrations:
                if name not in cols:
                    conn.execute(
                        f"ALTER TABLE sales_leads ADD COLUMN {name} {sql_type}"
                    )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fantzo_crm_users (
                user_id INTEGER PRIMARY KEY,
                mobile_e164 TEXT,
                campaign TEXT NOT NULL DEFAULT 'direct',
                source TEXT NOT NULL DEFAULT 'bot',
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                verified_at TEXT,
                contact_permission_at TEXT,
                status TEXT NOT NULL DEFAULT 'NEW',
                assigned_to INTEGER,
                assigned_agent TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                last_note TEXT,
                next_followup_at TEXT,
                updated_by INTEGER,
                updated_by_name TEXT,
                contacted_at TEXT,
                interested_at TEXT,
                converted_at TEXT,
                no_answer_at TEXT,
                dnc_at TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fantzo_crm_status "
            "ON fantzo_crm_users(status, first_seen_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fantzo_crm_mobile "
            "ON fantzo_crm_users(mobile_e164)"
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fantzo_lead_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mobile_e164 TEXT NOT NULL,
                user_id INTEGER,
                action TEXT NOT NULL,
                value TEXT,
                actor_id INTEGER,
                actor_name TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fantzo_lead_history_mobile "
            "ON fantzo_lead_history(mobile_e164, created_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fantzo_lead_history_user "
            "ON fantzo_lead_history(user_id, created_at)"
        )

        now = _now()

        # 1) Existing deduplicated sales leads: retain every CRM outcome.
        if _table_exists(conn, "sales_leads"):
            rows = conn.execute("SELECT * FROM sales_leads").fetchall()
            for row in rows:
                uid = int(row["primary_user_id"] or 0)
                if not uid:
                    continue
                created = str(row["created_at"] or row["updated_at"] or now)
                updated = str(row["updated_at"] or created)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO fantzo_crm_users(
                        user_id,mobile_e164,campaign,source,first_seen_at,last_seen_at,
                        verified_at,contact_permission_at,status,assigned_to,assigned_agent,
                        notes,last_note,next_followup_at,updated_by,updated_by_name,
                        contacted_at,interested_at,converted_at,no_answer_at,dnc_at,updated_at
                    ) VALUES(?,?,?,'bot',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        uid,
                        str(row["mobile_e164"] or ""),
                        str(row["campaign"] or "direct"),
                        created,
                        updated,
                        created if row["contact_permission_at"] else None,
                        row["contact_permission_at"],
                        str(row["status"] or "NEW").upper(),
                        row["assigned_to"] if "assigned_to" in row.keys() else None,
                        str(row["assigned_agent"] or ""),
                        str(row["notes"] or ""),
                        str(row["last_note"] or "") if "last_note" in row.keys() else "",
                        row["next_followup_at"] if "next_followup_at" in row.keys() else None,
                        row["updated_by"] if "updated_by" in row.keys() else None,
                        str(row["updated_by_name"] or "") if "updated_by_name" in row.keys() else "",
                        row["contacted_at"] if "contacted_at" in row.keys() else None,
                        row["interested_at"] if "interested_at" in row.keys() else None,
                        row["converted_at"],
                        row["no_answer_at"] if "no_answer_at" in row.keys() else None,
                        row["dnc_at"] if "dnc_at" in row.keys() else None,
                        updated,
                    ),
                )
                # If this CRM row came from an earlier generic user backfill, enrich
                # it from sales_leads without overwriting later manual CRM work.
                conn.execute(
                    """
                    UPDATE fantzo_crm_users
                    SET mobile_e164=CASE WHEN COALESCE(mobile_e164,'')='' THEN ? ELSE mobile_e164 END,
                        campaign=CASE WHEN campaign IN ('','direct','internal') THEN ? ELSE campaign END,
                        contact_permission_at=COALESCE(contact_permission_at, ?),
                        assigned_to=COALESCE(assigned_to, ?),
                        assigned_agent=CASE WHEN COALESCE(assigned_agent,'')='' THEN ? ELSE assigned_agent END,
                        notes=CASE WHEN COALESCE(notes,'')='' THEN ? ELSE notes END,
                        last_note=CASE WHEN COALESCE(last_note,'')='' THEN ? ELSE last_note END,
                        next_followup_at=COALESCE(next_followup_at, ?),
                        contacted_at=COALESCE(contacted_at, ?),
                        interested_at=COALESCE(interested_at, ?),
                        converted_at=COALESCE(converted_at, ?),
                        no_answer_at=COALESCE(no_answer_at, ?),
                        dnc_at=COALESCE(dnc_at, ?),
                        status=CASE
                            WHEN status='NEW' AND updated_by IS NULL AND ?!='NEW' THEN ?
                            ELSE status END
                    WHERE user_id=?
                    """,
                    (
                        str(row["mobile_e164"] or ""),
                        str(row["campaign"] or "direct"),
                        row["contact_permission_at"],
                        row["assigned_to"] if "assigned_to" in row.keys() else None,
                        str(row["assigned_agent"] or ""),
                        str(row["notes"] or ""),
                        str(row["last_note"] or "") if "last_note" in row.keys() else "",
                        row["next_followup_at"] if "next_followup_at" in row.keys() else None,
                        row["contacted_at"] if "contacted_at" in row.keys() else None,
                        row["interested_at"] if "interested_at" in row.keys() else None,
                        row["converted_at"],
                        row["no_answer_at"] if "no_answer_at" in row.keys() else None,
                        row["dnc_at"] if "dnc_at" in row.keys() else None,
                        str(row["status"] or "NEW").upper(),
                        str(row["status"] or "NEW").upper(),
                        uid,
                    ),
                )

        # 2) Every historical bot user becomes an all-time CRM record.
        if _table_exists(conn, "users"):
            user_cols = _columns(conn, "users")
            created_expr = "created_at" if "created_at" in user_cols else "last_seen"
            last_expr = "last_seen" if "last_seen" in user_cols else created_expr
            rows = conn.execute(
                f"SELECT user_id,{created_expr} first_seen,{last_expr} last_seen "
                "FROM users WHERE user_id IS NOT NULL"
            ).fetchall()
            for row in rows:
                first_seen = str(row["first_seen"] or row["last_seen"] or now)
                last_seen = str(row["last_seen"] or first_seen)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO fantzo_crm_users(
                        user_id,campaign,source,first_seen_at,last_seen_at,status,updated_at
                    ) VALUES(?,'direct','bot',?,?,'NEW',?)
                    """,
                    (int(row["user_id"]), first_seen, last_seen, last_seen),
                )

        # 3) Historical Business DMs are also all-time CRM identities.
        if _table_exists(conn, "business_welcomes"):
            rows = conn.execute(
                """
                SELECT customer_id, MIN(welcomed_at) first_seen, MAX(welcomed_at) last_seen
                FROM business_welcomes
                WHERE customer_id IS NOT NULL
                GROUP BY customer_id
                """
            ).fetchall()
            for row in rows:
                first_seen = str(row["first_seen"] or row["last_seen"] or now)
                last_seen = str(row["last_seen"] or first_seen)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO fantzo_crm_users(
                        user_id,campaign,source,first_seen_at,last_seen_at,status,updated_at
                    ) VALUES(?,'direct','business_dm',?,?,'NEW',?)
                    """,
                    (int(row["customer_id"]), first_seen, last_seen, last_seen),
                )

        # 4) Attribution-only historical starts are kept even if the users row is absent.
        if _table_exists(conn, "lead_attribution"):
            rows = conn.execute(
                "SELECT user_id,campaign,first_seen_at,last_seen_at FROM lead_attribution "
                "WHERE user_id IS NOT NULL"
            ).fetchall()
            for row in rows:
                first_seen = str(row["first_seen_at"] or row["last_seen_at"] or now)
                last_seen = str(row["last_seen_at"] or first_seen)
                uid = int(row["user_id"])
                campaign = str(row["campaign"] or "direct")
                conn.execute(
                    """
                    INSERT OR IGNORE INTO fantzo_crm_users(
                        user_id,campaign,source,first_seen_at,last_seen_at,status,updated_at
                    ) VALUES(?,?,'bot',?,?,'NEW',?)
                    """,
                    (uid, campaign, first_seen, last_seen, last_seen),
                )
                conn.execute(
                    """
                    UPDATE fantzo_crm_users
                    SET campaign=CASE
                        WHEN campaign IN ('','direct','internal') THEN ?
                        ELSE campaign END
                    WHERE user_id=?
                    """,
                    (campaign, uid),
                )

        # 5) Recover every saved mobile, not only currently verified contacts.
        if _table_exists(conn, "live_tv_mobile_users"):
            rows = conn.execute(
                """
                SELECT user_id,mobile_e164,capture_method,source,created_at,updated_at
                FROM live_tv_mobile_users
                WHERE user_id IS NOT NULL
                """
            ).fetchall()
            for row in rows:
                uid = int(row["user_id"])
                created = str(row["created_at"] or row["updated_at"] or now)
                updated = str(row["updated_at"] or created)
                mobile = str(row["mobile_e164"] or "")
                source = str(row["source"] or "live_tv")
                verified_at = created if str(row["capture_method"] or "") == "telegram_contact" else None
                conn.execute(
                    """
                    INSERT OR IGNORE INTO fantzo_crm_users(
                        user_id,mobile_e164,campaign,source,first_seen_at,last_seen_at,
                        verified_at,status,updated_at
                    ) VALUES(?,?,'direct',?,?,?,?,'NEW',?)
                    """,
                    (uid, mobile, source, created, updated, verified_at, updated),
                )
                conn.execute(
                    """
                    UPDATE fantzo_crm_users
                    SET mobile_e164=CASE WHEN COALESCE(mobile_e164,'')='' THEN ? ELSE mobile_e164 END,
                        source=CASE WHEN source IN ('','bot') THEN ? ELSE source END,
                        verified_at=CASE
                            WHEN ? IS NOT NULL THEN COALESCE(verified_at, ?)
                            ELSE verified_at END,
                        last_seen_at=CASE WHEN last_seen_at<? THEN ? ELSE last_seen_at END
                    WHERE user_id=?
                    """,
                    (mobile, source, verified_at, verified_at, updated, updated, uid),
                )

        # 6) Recover older lead-user mappings when the live-TV table is incomplete.
        if _table_exists(conn, "lead_user_map"):
            rows = conn.execute(
                "SELECT user_id,mobile_e164,linked_at FROM lead_user_map "
                "WHERE user_id IS NOT NULL"
            ).fetchall()
            for row in rows:
                uid = int(row["user_id"])
                linked = str(row["linked_at"] or now)
                mobile = str(row["mobile_e164"] or "")
                conn.execute(
                    """
                    INSERT OR IGNORE INTO fantzo_crm_users(
                        user_id,mobile_e164,campaign,source,first_seen_at,last_seen_at,
                        status,updated_at
                    ) VALUES(?,?,'direct','bot',?,?,'NEW',?)
                    """,
                    (uid, mobile, linked, linked, linked),
                )
                conn.execute(
                    """
                    UPDATE fantzo_crm_users
                    SET mobile_e164=CASE WHEN COALESCE(mobile_e164,'')='' THEN ? ELSE mobile_e164 END
                    WHERE user_id=?
                    """,
                    (mobile, uid),
                )


def _mobile_for_user(conn, user_id: int) -> str:
    uid = int(user_id)
    if _table_exists(conn, "fantzo_crm_users"):
        row = conn.execute(
            "SELECT mobile_e164 FROM fantzo_crm_users WHERE user_id=?",
            (uid,),
        ).fetchone()
        if row and row["mobile_e164"]:
            return str(row["mobile_e164"])

    if _table_exists(conn, "lead_user_map"):
        row = conn.execute(
            "SELECT mobile_e164 FROM lead_user_map WHERE user_id=?",
            (uid,),
        ).fetchone()
        if row and row["mobile_e164"]:
            return str(row["mobile_e164"])

    if _table_exists(conn, "live_tv_mobile_users"):
        row = conn.execute(
            "SELECT mobile_e164 FROM live_tv_mobile_users WHERE user_id=? LIMIT 1",
            (uid,),
        ).fetchone()
        if row and row["mobile_e164"]:
            return str(row["mobile_e164"])

    if _table_exists(conn, "sales_leads"):
        row = conn.execute(
            "SELECT mobile_e164 FROM sales_leads WHERE primary_user_id=? LIMIT 1",
            (uid,),
        ).fetchone()
        if row and row["mobile_e164"]:
            return str(row["mobile_e164"])
    return ""


def _ensure_sales_row(conn, user_id: int) -> str:
    """Create a deduplicated sales row only when this CRM user has a mobile."""
    if not _table_exists(conn, "sales_leads"):
        return ""
    row = conn.execute(
        "SELECT * FROM fantzo_crm_users WHERE user_id=?",
        (int(user_id),),
    ).fetchone()
    if not row:
        return ""
    mobile = str(row["mobile_e164"] or "")
    if not mobile:
        return ""

    conn.execute(
        """
        INSERT OR IGNORE INTO sales_leads(
            mobile_e164,primary_user_id,campaign,status,assigned_agent,notes,
            contact_permission_at,created_at,updated_at,last_contact_at,converted_at
        ) VALUES(?,?,?,?,?,?,?,?,?,NULL,?)
        """,
        (
            mobile,
            int(user_id),
            str(row["campaign"] or "direct"),
            str(row["status"] or "NEW"),
            str(row["assigned_agent"] or ""),
            str(row["notes"] or ""),
            row["contact_permission_at"],
            str(row["first_seen_at"] or _now()),
            str(row["updated_at"] or _now()),
            row["converted_at"],
        ),
    )
    return mobile


def get_lead(user_id: int):
    if not user_id:
        return None
    ensure_tables()
    uid = int(user_id)
    with core.db() as conn:
        row = conn.execute(
            "SELECT * FROM fantzo_crm_users WHERE user_id=?",
            (uid,),
        ).fetchone()
        if not row:
            return None
        lead = dict(row)

        user = conn.execute(
            "SELECT username,first_name FROM users WHERE user_id=?",
            (uid,),
        ).fetchone() if _table_exists(conn, "users") else None

        verify = conn.execute(
            "SELECT source,created_at,capture_method,mobile_e164 "
            "FROM live_tv_mobile_users WHERE user_id=? LIMIT 1",
            (uid,),
        ).fetchone() if _table_exists(conn, "live_tv_mobile_users") else None

    lead["primary_user_id"] = uid
    lead["user_id"] = uid
    lead["username"] = str(user["username"] or "") if user else ""
    lead["first_name"] = str(user["first_name"] or "") if user else ""
    lead["verification_source"] = str(verify["source"] or "") if verify else str(lead.get("source") or "bot")
    lead["is_currently_verified"] = bool(
        verify and str(verify["capture_method"] or "") == "telegram_contact"
    )
    if verify and verify["mobile_e164"] and not lead.get("mobile_e164"):
        lead["mobile_e164"] = str(verify["mobile_e164"])
    if lead["is_currently_verified"] and not lead.get("verified_at"):
        lead["verified_at"] = str(verify["created_at"] or "")
    return lead


def add_history(
    mobile: str,
    user_id: int,
    action: str,
    value: str = "",
    actor_id: int = 0,
    actor_name: str = "",
) -> None:
    ensure_tables()
    with core.db() as conn:
        conn.execute(
            """
            INSERT INTO fantzo_lead_history(
                mobile_e164,user_id,action,value,actor_id,actor_name,created_at
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (
                str(mobile or ""),
                int(user_id or 0) or None,
                str(action or "")[:64],
                str(value or "")[:1000],
                int(actor_id or 0) or None,
                str(actor_name or "")[:128],
                _now(),
            ),
        )


def set_status(
    user_id: int,
    status: str,
    actor_id: int = 0,
    actor_name: str = "",
) -> bool:
    status = str(status or "").strip().upper()
    if status not in ALLOWED_STATUSES or not user_id:
        return False

    ensure_tables()
    uid = int(user_id)
    now = _now()
    timestamp_col = {
        "CONTACTED": "contacted_at",
        "INTERESTED": "interested_at",
        "CONVERTED": "converted_at",
        "NO_ANSWER": "no_answer_at",
        "DO_NOT_CONTACT": "dnc_at",
    }.get(status)

    with core.db() as conn:
        row = conn.execute(
            "SELECT 1 FROM fantzo_crm_users WHERE user_id=?",
            (uid,),
        ).fetchone()
        if not row:
            return False

        conn.execute(
            """
            UPDATE fantzo_crm_users
            SET status=?,
                assigned_to=COALESCE(assigned_to, ?),
                assigned_agent=CASE WHEN COALESCE(assigned_agent,'')='' THEN ? ELSE assigned_agent END,
                updated_by=?,updated_by_name=?,updated_at=?
            WHERE user_id=?
            """,
            (
                status,
                int(actor_id or 0) or None,
                str(actor_name or "")[:128],
                int(actor_id or 0) or None,
                str(actor_name or "")[:128],
                now,
                uid,
            ),
        )
        if timestamp_col:
            conn.execute(
                f"UPDATE fantzo_crm_users SET {timestamp_col}=COALESCE({timestamp_col},?) "
                "WHERE user_id=?",
                (now, uid),
            )

        mobile = _ensure_sales_row(conn, uid)
        if mobile:
            conn.execute(
                """
                UPDATE sales_leads
                SET status=?,
                    assigned_to=COALESCE(assigned_to, ?),
                    assigned_agent=CASE WHEN COALESCE(assigned_agent,'')='' THEN ? ELSE assigned_agent END,
                    updated_by=?,updated_by_name=?,updated_at=?,
                    last_contact_at=CASE
                        WHEN ? IN ('CONTACTED','NO_ANSWER','INTERESTED','CONVERTED','NOT_INTERESTED','DO_NOT_CONTACT')
                        THEN ? ELSE last_contact_at END,
                    converted_at=CASE
                        WHEN ?='CONVERTED' THEN COALESCE(converted_at, ?)
                        ELSE converted_at END
                WHERE mobile_e164=?
                """,
                (
                    status,
                    int(actor_id or 0) or None,
                    str(actor_name or "")[:128],
                    int(actor_id or 0) or None,
                    str(actor_name or "")[:128],
                    now,
                    status,
                    now,
                    status,
                    now,
                    mobile,
                ),
            )
            if timestamp_col and timestamp_col != "converted_at":
                conn.execute(
                    f"UPDATE sales_leads SET {timestamp_col}=COALESCE({timestamp_col},?), updated_at=? "
                    "WHERE mobile_e164=?",
                    (now, now, mobile),
                )

    if status == "DO_NOT_CONTACT":
        try:
            reminders.set_opt_out("bot", uid, True)
            reminders.set_opt_out("business_dm", uid, True)
        except Exception:
            logger.exception("Could not apply Fantzo DNC reminder opt-out")

    add_history(mobile, uid, "status", status, actor_id, actor_name)
    return True


def assign_lead(user_id: int, actor_id: int, actor_name: str) -> bool:
    if not user_id or not actor_id:
        return False
    ensure_tables()
    uid = int(user_id)
    now = _now()
    with core.db() as conn:
        cur = conn.execute(
            """
            UPDATE fantzo_crm_users
            SET assigned_to=?,assigned_agent=?,updated_by=?,updated_by_name=?,updated_at=?
            WHERE user_id=?
            """,
            (
                int(actor_id),
                str(actor_name or "")[:128],
                int(actor_id),
                str(actor_name or "")[:128],
                now,
                uid,
            ),
        )
        if not int(cur.rowcount or 0):
            return False
        mobile = _ensure_sales_row(conn, uid)
        if mobile:
            conn.execute(
                """
                UPDATE sales_leads
                SET assigned_to=?,assigned_agent=?,updated_by=?,updated_by_name=?,updated_at=?
                WHERE mobile_e164=?
                """,
                (
                    int(actor_id),
                    str(actor_name or "")[:128],
                    int(actor_id),
                    str(actor_name or "")[:128],
                    now,
                    mobile,
                ),
            )
    add_history(mobile, uid, "assigned", actor_name, actor_id, actor_name)
    return True


def add_note(user_id: int, note: str, actor_id: int = 0, actor_name: str = "") -> bool:
    note = str(note or "").strip()
    if not user_id or not note:
        return False
    ensure_tables()
    uid = int(user_id)
    now = _now()
    with core.db() as conn:
        cur = conn.execute(
            """
            UPDATE fantzo_crm_users
            SET notes=?,last_note=?,updated_by=?,updated_by_name=?,updated_at=?
            WHERE user_id=?
            """,
            (
                note[:1000],
                note[:1000],
                int(actor_id or 0) or None,
                str(actor_name or "")[:128],
                now,
                uid,
            ),
        )
        if not int(cur.rowcount or 0):
            return False
        mobile = _ensure_sales_row(conn, uid)
        if mobile:
            conn.execute(
                """
                UPDATE sales_leads
                SET notes=?,last_note=?,updated_by=?,updated_by_name=?,updated_at=?
                WHERE mobile_e164=?
                """,
                (
                    note[:1000],
                    note[:1000],
                    int(actor_id or 0) or None,
                    str(actor_name or "")[:128],
                    now,
                    mobile,
                ),
            )
    add_history(mobile, uid, "note", note, actor_id, actor_name)
    return True


def set_followup(user_id: int, followup_at: str, actor_id: int = 0, actor_name: str = "") -> bool:
    if not user_id:
        return False
    ensure_tables()
    uid = int(user_id)
    now = _now()
    value = str(followup_at or "").strip()
    with core.db() as conn:
        cur = conn.execute(
            """
            UPDATE fantzo_crm_users
            SET next_followup_at=?,updated_by=?,updated_by_name=?,updated_at=?
            WHERE user_id=?
            """,
            (
                value or None,
                int(actor_id or 0) or None,
                str(actor_name or "")[:128],
                now,
                uid,
            ),
        )
        if not int(cur.rowcount or 0):
            return False
        mobile = _ensure_sales_row(conn, uid)
        if mobile:
            conn.execute(
                """
                UPDATE sales_leads
                SET next_followup_at=?,updated_by=?,updated_by_name=?,updated_at=?
                WHERE mobile_e164=?
                """,
                (
                    value or None,
                    int(actor_id or 0) or None,
                    str(actor_name or "")[:128],
                    now,
                    mobile,
                ),
            )
    add_history(mobile, uid, "followup", value or "cleared", actor_id, actor_name)
    return True


def status_counts() -> dict:
    ensure_tables()
    counts = {s: 0 for s in ALLOWED_STATUSES}
    with core.db() as conn:
        rows = conn.execute(
            "SELECT status,COUNT(*) c FROM fantzo_crm_users GROUP BY status"
        ).fetchall()
    for row in rows:
        key = str(row["status"] or "NEW").upper()
        if key in counts:
            counts[key] = int(row["c"] or 0)
    return counts


def dashboard_counts() -> dict:
    ensure_tables()
    with core.db() as conn:
        total = int(conn.execute(
            "SELECT COUNT(*) FROM fantzo_crm_users"
        ).fetchone()[0] or 0)
        with_mobile = int(conn.execute(
            "SELECT COUNT(*) FROM fantzo_crm_users WHERE COALESCE(TRIM(mobile_e164),'')!=''"
        ).fetchone()[0] or 0)
        new = int(conn.execute(
            "SELECT COUNT(*) FROM fantzo_crm_users WHERE status='NEW'"
        ).fetchone()[0] or 0)
        new_unassigned = int(conn.execute(
            """
            SELECT COUNT(*) FROM fantzo_crm_users
            WHERE status='NEW' AND assigned_to IS NULL
              AND COALESCE(assigned_agent,'')=''
            """
        ).fetchone()[0] or 0)
        new_assigned = max(new - new_unassigned, 0)
        verified = 0
        if _table_exists(conn, "live_tv_mobile_users"):
            verified = int(conn.execute(
                """
                SELECT COUNT(*)
                FROM fantzo_crm_users c
                WHERE EXISTS(
                    SELECT 1 FROM live_tv_mobile_users m
                    WHERE m.user_id=c.user_id
                      AND m.capture_method='telegram_contact'
                )
                """
            ).fetchone()[0] or 0)
    return {
        "total": total,
        "with_mobile": with_mobile,
        "verified": verified,
        "not_verified": max(total - verified, 0),
        "new": new,
        "new_unassigned": new_unassigned,
        "new_assigned": new_assigned,
    }


def due_count() -> int:
    ensure_tables()
    with core.db() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) c
            FROM fantzo_crm_users
            WHERE next_followup_at IS NOT NULL
              AND next_followup_at<=?
              AND status NOT IN ('CONVERTED','DO_NOT_CONTACT')
            """,
            (_now(),),
        ).fetchone()
    return int(row["c"] or 0)


def new_assigned_count() -> int:
    return int(dashboard_counts()["new_assigned"])


def _queue_sql(queue: str):
    queue = str(queue or "").lower()
    where = "1=1"
    params: list = []

    if queue == "new":
        # Match the final iBetin behavior: assignment must not hide a lead that
        # still has no CRM outcome.
        where = "status='NEW'"
        order = "first_seen_at DESC, user_id DESC"
    elif queue == "mobile":
        where = "COALESCE(TRIM(mobile_e164),'')!=''"
        order = "first_seen_at DESC, user_id DESC"
    elif queue == "due":
        where = (
            "next_followup_at IS NOT NULL AND next_followup_at<=? "
            "AND status NOT IN ('CONVERTED','DO_NOT_CONTACT')"
        )
        params.append(_now())
        order = "next_followup_at ASC, user_id DESC"
    elif queue == "followup":
        where = "status IN ('CONTACTED','NO_ANSWER')"
        order = "COALESCE(next_followup_at,updated_at) ASC, user_id DESC"
    elif queue == "interested":
        where = "status='INTERESTED'"
        order = "updated_at ASC, user_id DESC"
    elif queue == "converted":
        where = "status='CONVERTED'"
        order = "converted_at DESC, user_id DESC"
    elif queue == "all":
        order = "first_seen_at DESC, user_id DESC"
    else:
        return None, [], None

    return where, params, order


def queue_count(queue: str) -> int:
    ensure_tables()
    where, params, _ = _queue_sql(queue)
    if not where:
        return 0
    with core.db() as conn:
        row = conn.execute(
            f"SELECT COUNT(*) c FROM fantzo_crm_users WHERE {where}",
            tuple(params),
        ).fetchone()
    return int(row["c"] or 0)


def queue_user_id_at(queue: str, index: int) -> int:
    """Return one all-time CRM record at a zero-based queue position."""
    ensure_tables()
    where, params, order = _queue_sql(queue)
    if not where or not order:
        return 0

    total = queue_count(queue)
    if total <= 0:
        return 0

    safe_index = max(0, min(int(index), total - 1))
    with core.db() as conn:
        row = conn.execute(
            f"""
            SELECT user_id
            FROM fantzo_crm_users
            WHERE {where}
            ORDER BY {order}
            LIMIT 1 OFFSET ?
            """,
            (*params, safe_index),
        ).fetchone()

    return int(row["user_id"]) if row and row["user_id"] else 0


def queue_user_ids(queue: str, limit: int = 12) -> list[int]:
    ensure_tables()
    where, params, order = _queue_sql(queue)
    if not where or not order:
        return []

    with core.db() as conn:
        rows = conn.execute(
            f"""
            SELECT user_id
            FROM fantzo_crm_users
            WHERE {where}
            ORDER BY {order}
            LIMIT ?
            """,
            (*params, int(limit)),
        ).fetchall()

    return [int(row["user_id"]) for row in rows if row["user_id"]]


def search_user_ids(term: str, limit: int = 12) -> list[int]:
    ensure_tables()
    raw = str(term or "").strip()
    if not raw:
        return []

    username = raw.lstrip("@")
    digits = re.sub(r"\D", "", raw)
    params = [f"%{raw}%", f"%{username}%"]
    phone_clause = ""
    if digits:
        phone_clause = (
            " OR replace(replace(replace(replace(replace("
            "c.mobile_e164,'+',''),' ',''),'-',''),'(',''),')','') LIKE ? "
        )
        params.append(f"%{digits}%")

    with core.db() as conn:
        rows = conn.execute(
            f"""
            SELECT DISTINCT c.user_id
            FROM fantzo_crm_users c
            LEFT JOIN users u ON u.user_id=c.user_id
            WHERE CAST(c.user_id AS TEXT) LIKE ?
               OR COALESCE(u.username,'') LIKE ?
               {phone_clause}
            ORDER BY c.updated_at DESC
            LIMIT ?
            """,
            (*params, int(limit)),
        ).fetchall()

    return [int(r["user_id"]) for r in rows if r["user_id"]]


def recent_history(user_id: int, limit: int = 6):
    ensure_tables()
    uid = int(user_id)
    with core.db() as conn:
        mobile = _mobile_for_user(conn, uid)
        rows = conn.execute(
            """
            SELECT action,value,actor_name,created_at
            FROM fantzo_lead_history
            WHERE user_id=?
               OR (user_id IS NULL AND mobile_e164=? AND COALESCE(?, '')!='')
            ORDER BY id DESC
            LIMIT ?
            """,
            (uid, mobile, mobile, int(limit)),
        ).fetchall()
    return [dict(r) for r in rows]
