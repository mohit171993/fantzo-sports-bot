"""Fantzo-only CRM operations.

This module mirrors the useful operational workflow of iBetin's CRM while
remaining completely separate from iBetin code, tables and settings.
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


def ensure_tables() -> None:
    """Extend Fantzo's existing deduplicated sales_leads safely."""
    with core.db() as conn:
        if not _table_exists(conn, "sales_leads"):
            return

        cols = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(sales_leads)").fetchall()
        }
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


def _mobile_for_user(conn, user_id: int) -> str:
    if _table_exists(conn, "lead_user_map"):
        row = conn.execute(
            "SELECT mobile_e164 FROM lead_user_map WHERE user_id=?",
            (int(user_id),),
        ).fetchone()
        if row and row["mobile_e164"]:
            return str(row["mobile_e164"])

    if _table_exists(conn, "sales_leads"):
        row = conn.execute(
            "SELECT mobile_e164 FROM sales_leads WHERE primary_user_id=? LIMIT 1",
            (int(user_id),),
        ).fetchone()
        if row and row["mobile_e164"]:
            return str(row["mobile_e164"])
    return ""


def get_lead(user_id: int):
    if not user_id:
        return None
    ensure_tables()
    with core.db() as conn:
        mobile = _mobile_for_user(conn, int(user_id))
        if not mobile:
            return None
        row = conn.execute(
            "SELECT * FROM sales_leads WHERE mobile_e164=?",
            (mobile,),
        ).fetchone()
        if not row:
            return None
        lead = dict(row)

        user = conn.execute(
            "SELECT username,first_name FROM users WHERE user_id=?",
            (int(user_id),),
        ).fetchone() if _table_exists(conn, "users") else None

        verify = conn.execute(
            "SELECT source,created_at FROM live_tv_mobile_users "
            "WHERE user_id=? AND capture_method='telegram_contact' LIMIT 1",
            (int(user_id),),
        ).fetchone() if _table_exists(conn, "live_tv_mobile_users") else None

    lead["user_id"] = int(user_id)
    lead["username"] = str(user["username"] or "") if user else ""
    lead["first_name"] = str(user["first_name"] or "") if user else ""
    lead["verification_source"] = str(verify["source"] or "") if verify else ""
    lead["verified_at"] = str(verify["created_at"] or "") if verify else ""
    return lead


def add_history(
    mobile: str,
    user_id: int,
    action: str,
    value: str = "",
    actor_id: int = 0,
    actor_name: str = "",
) -> None:
    if not mobile:
        return
    ensure_tables()
    with core.db() as conn:
        conn.execute(
            """
            INSERT INTO fantzo_lead_history(
                mobile_e164,user_id,action,value,actor_id,actor_name,created_at
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (
                str(mobile),
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
    now = _now()
    with core.db() as conn:
        mobile = _mobile_for_user(conn, int(user_id))
        if not mobile:
            return False

        row = conn.execute(
            "SELECT 1 FROM sales_leads WHERE mobile_e164=?",
            (mobile,),
        ).fetchone()
        if not row:
            return False

        timestamp_col = {
            "CONTACTED": "contacted_at",
            "INTERESTED": "interested_at",
            "CONVERTED": "converted_at",
            "NO_ANSWER": "no_answer_at",
            "DO_NOT_CONTACT": "dnc_at",
        }.get(status)

        conn.execute(
            """
            UPDATE sales_leads
            SET status=?,
                assigned_to=COALESCE(assigned_to, ?),
                assigned_agent=CASE
                    WHEN COALESCE(assigned_agent,'')='' THEN ?
                    ELSE assigned_agent END,
                updated_by=?, updated_by_name=?, updated_at=?,
                last_contact_at=CASE
                    WHEN ? IN ('CONTACTED','NO_ANSWER','INTERESTED','CONVERTED','NOT_INTERESTED','DO_NOT_CONTACT')
                    THEN ? ELSE last_contact_at END,
                converted_at=CASE
                    WHEN ?='CONVERTED' THEN COALESCE(converted_at, ?)
                    WHEN ?!='CONVERTED' THEN NULL
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
                status,
                mobile,
            ),
        )

        if timestamp_col and timestamp_col != "converted_at":
            conn.execute(
                f"UPDATE sales_leads "
                f"SET {timestamp_col}=COALESCE({timestamp_col}, ?), updated_at=? "
                "WHERE mobile_e164=?",
                (now, now, mobile),
            )

    if status == "DO_NOT_CONTACT":
        try:
            reminders.set_opt_out("bot", int(user_id), True)
            reminders.set_opt_out("business_dm", int(user_id), True)
        except Exception:
            logger.exception("Could not apply Fantzo DNC reminder opt-out")

    add_history(mobile, user_id, "status", status, actor_id, actor_name)
    return True


def assign_lead(user_id: int, actor_id: int, actor_name: str) -> bool:
    if not user_id or not actor_id:
        return False
    ensure_tables()
    now = _now()
    with core.db() as conn:
        mobile = _mobile_for_user(conn, int(user_id))
        if not mobile:
            return False
        cur = conn.execute(
            """
            UPDATE sales_leads
            SET assigned_to=?, assigned_agent=?,
                updated_by=?, updated_by_name=?, updated_at=?
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
    if int(cur.rowcount or 0):
        add_history(mobile, user_id, "assigned", actor_name, actor_id, actor_name)
        return True
    return False


def add_note(user_id: int, note: str, actor_id: int = 0, actor_name: str = "") -> bool:
    note = str(note or "").strip()
    if not user_id or not note:
        return False
    ensure_tables()
    now = _now()
    with core.db() as conn:
        mobile = _mobile_for_user(conn, int(user_id))
        if not mobile:
            return False
        cur = conn.execute(
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
    if int(cur.rowcount or 0):
        add_history(mobile, user_id, "note", note, actor_id, actor_name)
        return True
    return False


def set_followup(user_id: int, followup_at: str, actor_id: int = 0, actor_name: str = "") -> bool:
    if not user_id:
        return False
    ensure_tables()
    now = _now()
    value = str(followup_at or "").strip()
    with core.db() as conn:
        mobile = _mobile_for_user(conn, int(user_id))
        if not mobile:
            return False
        cur = conn.execute(
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
    if int(cur.rowcount or 0):
        add_history(mobile, user_id, "followup", value or "cleared", actor_id, actor_name)
        return True
    return False


def status_counts() -> dict:
    ensure_tables()
    counts = {s: 0 for s in ALLOWED_STATUSES}
    with core.db() as conn:
        rows = conn.execute(
            "SELECT status,COUNT(*) c FROM sales_leads GROUP BY status"
        ).fetchall()
    for row in rows:
        key = str(row["status"] or "NEW").upper()
        if key in counts:
            counts[key] = int(row["c"] or 0)
    return counts


def due_count() -> int:
    ensure_tables()
    with core.db() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) c
            FROM sales_leads
            WHERE next_followup_at IS NOT NULL
              AND next_followup_at<=?
              AND status NOT IN ('CONVERTED','DO_NOT_CONTACT')
            """,
            (_now(),),
        ).fetchone()
    return int(row["c"] or 0)


def new_assigned_count() -> int:
    ensure_tables()
    with core.db() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) c
            FROM sales_leads
            WHERE status='NEW'
              AND (assigned_to IS NOT NULL OR COALESCE(assigned_agent,'')!='')
            """
        ).fetchone()
    return int(row["c"] or 0)


def queue_user_ids(queue: str, limit: int = 12) -> list[int]:
    ensure_tables()
    queue = str(queue or "").lower()
    where = "1=1"
    params: list = []

    if queue == "new":
        where = "status='NEW'"
        order = "CASE WHEN assigned_to IS NULL THEN 0 ELSE 1 END, created_at ASC"
    elif queue == "due":
        where = (
            "next_followup_at IS NOT NULL AND next_followup_at<=? "
            "AND status NOT IN ('CONVERTED','DO_NOT_CONTACT')"
        )
        params.append(_now())
        order = "next_followup_at ASC"
    elif queue == "followup":
        where = "status IN ('CONTACTED','NO_ANSWER')"
        order = "COALESCE(next_followup_at,updated_at) ASC"
    elif queue == "interested":
        where = "status='INTERESTED'"
        order = "updated_at ASC"
    elif queue == "converted":
        where = "status='CONVERTED'"
        order = "converted_at DESC"
    elif queue == "all":
        order = "updated_at DESC"
    else:
        return []

    with core.db() as conn:
        rows = conn.execute(
            f"""
            SELECT primary_user_id
            FROM sales_leads
            WHERE {where}
            ORDER BY {order}
            LIMIT ?
            """,
            (*params, int(limit)),
        ).fetchall()

    return [int(row["primary_user_id"]) for row in rows if row["primary_user_id"]]


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
            "s.mobile_e164,'+',''),' ',''),'-',''),'(',''),')','') LIKE ? "
        )
        params.append(f"%{digits}%")

    with core.db() as conn:
        rows = conn.execute(
            f"""
            SELECT DISTINCT s.primary_user_id
            FROM sales_leads s
            LEFT JOIN users u ON u.user_id=s.primary_user_id
            WHERE CAST(s.primary_user_id AS TEXT) LIKE ?
               OR COALESCE(u.username,'') LIKE ?
               {phone_clause}
            ORDER BY s.updated_at DESC
            LIMIT ?
            """,
            (*params, int(limit)),
        ).fetchall()

    return [int(r["primary_user_id"]) for r in rows if r["primary_user_id"]]


def recent_history(user_id: int, limit: int = 6):
    ensure_tables()
    with core.db() as conn:
        mobile = _mobile_for_user(conn, int(user_id))
        if not mobile:
            return []
        rows = conn.execute(
            """
            SELECT action,value,actor_name,created_at
            FROM fantzo_lead_history
            WHERE mobile_e164=?
            ORDER BY id DESC
            LIMIT ?
            """,
            (mobile, int(limit)),
        ).fetchall()
    return [dict(r) for r in rows]
