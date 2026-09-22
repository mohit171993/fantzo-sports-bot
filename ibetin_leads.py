import os
import re
import sqlite3
from datetime import datetime, timezone

ALLOWED_STATUSES = {
    "new",
    "contacted",
    "interested",
    "converted",
    "no_answer",
    "dnc",
}


def _db_path() -> str:
    return os.getenv("DB_PATH", "/app/ibetin_bot.db").strip() or "/app/ibetin_bot.db"


def _connect():
    conn = sqlite3.connect(_db_path(), timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_campaign(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "", str(value or "").strip())[:64]
    return cleaned or "direct"


def clean_source(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "", str(value or "").strip())[:32]
    return cleaned or "bot"


def ensure_tables() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ibetin_leads (
                user_id INTEGER PRIMARY KEY,
                campaign TEXT NOT NULL DEFAULT 'direct',
                source TEXT NOT NULL DEFAULT 'bot',
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                verified_at TEXT,
                mobile_number TEXT,
                contact_consent INTEGER NOT NULL DEFAULT 0,
                lead_status TEXT NOT NULL DEFAULT 'new',
                contacted_at TEXT,
                interested_at TEXT,
                converted_at TEXT,
                no_answer_at TEXT,
                dnc_at TEXT,
                assigned_to INTEGER,
                assigned_name TEXT,
                next_followup_at TEXT,
                last_note TEXT,
                updated_by INTEGER,
                updated_by_name TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ibetin_leads_campaign "
            "ON ibetin_leads(campaign)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ibetin_leads_status "
            "ON ibetin_leads(lead_status)"
        )

        columns = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(ibetin_leads)").fetchall()
        }
        migrations = (
            ("mobile_number", "TEXT"),
            ("assigned_to", "INTEGER"),
            ("assigned_name", "TEXT"),
            ("next_followup_at", "TEXT"),
            ("last_note", "TEXT"),
            ("updated_by", "INTEGER"),
            ("updated_by_name", "TEXT"),
        )
        for name, sql_type in migrations:
            if name not in columns:
                conn.execute(
                    f"ALTER TABLE ibetin_leads ADD COLUMN {name} {sql_type}"
                )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ibetin_lead_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                value TEXT,
                actor_id INTEGER,
                actor_name TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ibetin_lead_history_user "
            "ON ibetin_lead_history(user_id, created_at)"
        )

        tables = {
            str(row["name"])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

        # Historical bot users are preserved as direct leads. This is a
        # best-effort backfill only and never overwrites newer campaign/status data.
        if "users" in tables:
            rows = conn.execute(
                """
                SELECT user_id, created_at, last_seen
                FROM users
                WHERE user_id IS NOT NULL
                """
            ).fetchall()
            for row in rows:
                first_seen = str(row["created_at"] or row["last_seen"] or _now())
                last_seen = str(row["last_seen"] or first_seen)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO ibetin_leads(
                        user_id, campaign, source, first_seen_at, last_seen_at,
                        lead_status, updated_at
                    )
                    VALUES (?, 'direct', 'bot', ?, ?, 'new', ?)
                    """,
                    (int(row["user_id"]), first_seen, last_seen, last_seen),
                )

        if "business_customers" in tables:
            rows = conn.execute(
                """
                SELECT customer_id, MIN(last_seen) first_seen, MAX(last_seen) last_seen
                FROM business_customers
                WHERE customer_id IS NOT NULL
                GROUP BY customer_id
                """
            ).fetchall()
            for row in rows:
                first_seen = str(row["first_seen"] or row["last_seen"] or _now())
                last_seen = str(row["last_seen"] or first_seen)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO ibetin_leads(
                        user_id, campaign, source, first_seen_at, last_seen_at,
                        lead_status, updated_at
                    )
                    VALUES (?, 'direct', 'business_dm', ?, ?, 'new', ?)
                    """,
                    (int(row["customer_id"]), first_seen, last_seen, last_seen),
                )

        if "liveline_verified_users" in tables:
            columns = {
                str(row["name"])
                for row in conn.execute(
                    "PRAGMA table_info(liveline_verified_users)"
                ).fetchall()
            }
            verified_col = (
                "first_verified_at"
                if "first_verified_at" in columns
                else "verified_at"
            )
            source_expr = (
                "verification_source"
                if "verification_source" in columns
                else "''"
            )
            campaign_expr = (
                "campaign"
                if "campaign" in columns
                else "'direct'"
            )
            consent_expr = (
                "contact_consent"
                if "contact_consent" in columns
                else "0"
            )
            rows = conn.execute(
                f"""
                SELECT user_id, phone_number, {verified_col} verified_at,
                       {source_expr} source, {campaign_expr} campaign,
                       {consent_expr} contact_consent
                FROM liveline_verified_users
                """
            ).fetchall()
            for row in rows:
                uid = int(row["user_id"])
                verified_at = str(row["verified_at"] or _now())
                source = clean_source(str(row["source"] or "bot"))
                campaign = clean_campaign(str(row["campaign"] or "direct"))
                conn.execute(
                    """
                    INSERT OR IGNORE INTO ibetin_leads(
                        user_id, campaign, source, first_seen_at, last_seen_at,
                        verified_at, mobile_number, contact_consent,
                        lead_status, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)
                    """,
                    (
                        uid,
                        campaign,
                        source,
                        verified_at,
                        verified_at,
                        verified_at,
                        str(row["phone_number"] or ""),
                        int(row["contact_consent"] or 0),
                        verified_at,
                    ),
                )
                conn.execute(
                    """
                    UPDATE ibetin_leads
                    SET verified_at=COALESCE(verified_at, ?),
                        mobile_number=CASE
                            WHEN COALESCE(mobile_number,'')='' THEN ?
                            ELSE mobile_number
                        END,
                        contact_consent=CASE
                            WHEN contact_consent=1 THEN 1 ELSE ?
                        END,
                        updated_at=CASE
                            WHEN updated_at < ? THEN ? ELSE updated_at
                        END
                    WHERE user_id=?
                    """,
                    (
                        verified_at,
                        str(row["phone_number"] or ""),
                        int(row["contact_consent"] or 0),
                        verified_at,
                        verified_at,
                        uid,
                    ),
                )


def record_start(
    user_id: int,
    campaign: str = "",
    source: str = "bot",
) -> None:
    if not user_id:
        return
    ensure_tables()
    now = _now()
    campaign_value = clean_campaign(campaign)
    source_value = clean_source(source)
    with _connect() as conn:
        existing = conn.execute(
            "SELECT campaign, source FROM ibetin_leads WHERE user_id=?",
            (int(user_id),),
        ).fetchone()

        if existing:
            # Preserve first-touch attribution. A later plain /start or another
            # campaign must not rewrite the source that originally acquired the lead.
            old_campaign = str(existing["campaign"] or "direct")
            chosen_campaign = (
                old_campaign
                if old_campaign != "direct"
                else campaign_value
            )
            old_source = str(existing["source"] or "bot")
            chosen_source = old_source or source_value
            conn.execute(
                """
                UPDATE ibetin_leads
                SET campaign=?, source=?, last_seen_at=?, updated_at=?
                WHERE user_id=?
                """,
                (
                    chosen_campaign,
                    chosen_source,
                    now,
                    now,
                    int(user_id),
                ),
            )
            return

        conn.execute(
            """
            INSERT INTO ibetin_leads(
                user_id, campaign, source, first_seen_at, last_seen_at,
                lead_status, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 'new', ?)
            """,
            (
                int(user_id),
                campaign_value,
                source_value,
                now,
                now,
                now,
            ),
        )


def mark_verified(
    user_id: int,
    source: str = "",
    campaign: str = "",
    contact_consent: bool = True,
    mobile_number: str = "",
) -> None:
    if not user_id:
        return
    ensure_tables()
    current = get_lead(int(user_id))
    record_start(
        int(user_id),
        campaign or (current.get("campaign") if current else "") or "direct",
        source or (current.get("source") if current else "") or "bot",
    )
    now = _now()
    with _connect() as conn:
        # Verification must never rewrite first-touch attribution.
        # record_start() above creates the lead with the correct original
        # campaign/source when the record does not exist; existing records keep
        # their original acquisition values permanently.
        conn.execute(
            """
            UPDATE ibetin_leads
            SET verified_at=COALESCE(verified_at, ?),
                mobile_number=CASE
                    WHEN ? != '' THEN ?
                    ELSE mobile_number
                END,
                contact_consent=?,
                updated_at=?
            WHERE user_id=?
            """,
            (
                now,
                str(mobile_number or "").strip(),
                str(mobile_number or "").strip(),
                1 if contact_consent else 0,
                now,
                int(user_id),
            ),
        )


def get_lead(user_id: int):
    if not user_id:
        return None
    ensure_tables()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM ibetin_leads WHERE user_id=?",
            (int(user_id),),
        ).fetchone()
    return dict(row) if row else None


def set_status(
    user_id: int,
    status: str,
    actor_id: int = 0,
    actor_name: str = "",
) -> bool:
    status = str(status or "").strip().lower()
    if status not in ALLOWED_STATUSES or not user_id:
        return False
    ensure_tables()
    now = _now()
    timestamp_column = {
        "contacted": "contacted_at",
        "interested": "interested_at",
        "converted": "converted_at",
        "no_answer": "no_answer_at",
        "dnc": "dnc_at",
    }.get(status)

    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM ibetin_leads WHERE user_id=?",
            (int(user_id),),
        ).fetchone()

        if not row:
            conn.execute(
                """
                INSERT INTO ibetin_leads(
                    user_id, campaign, source, first_seen_at, last_seen_at,
                    lead_status, assigned_to, assigned_name,
                    updated_by, updated_by_name, updated_at
                )
                VALUES (?, 'direct', 'bot', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(user_id),
                    now,
                    now,
                    status,
                    int(actor_id or 0) or None,
                    str(actor_name or "")[:128] or None,
                    int(actor_id or 0) or None,
                    str(actor_name or "")[:128] or None,
                    now,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE ibetin_leads
                SET lead_status=?,
                    assigned_to=COALESCE(assigned_to, ?),
                    assigned_name=COALESCE(assigned_name, ?),
                    updated_by=?, updated_by_name=?, updated_at=?
                WHERE user_id=?
                """,
                (
                    status,
                    int(actor_id or 0) or None,
                    str(actor_name or "")[:128] or None,
                    int(actor_id or 0) or None,
                    str(actor_name or "")[:128] or None,
                    now,
                    int(user_id),
                ),
            )

        if timestamp_column:
            conn.execute(
                f"UPDATE ibetin_leads "
                f"SET {timestamp_column}=COALESCE({timestamp_column}, ?), updated_at=? "
                "WHERE user_id=?",
                (now, now, int(user_id)),
            )

    add_history(
        int(user_id),
        "status",
        status,
        int(actor_id or 0),
        str(actor_name or ""),
    )
    return True


def status_counts() -> dict:
    ensure_tables()
    counts = {status: 0 for status in ALLOWED_STATUSES}
    with _connect() as conn:
        rows = conn.execute(
            "SELECT lead_status, COUNT(*) c FROM ibetin_leads GROUP BY lead_status"
        ).fetchall()
    for row in rows:
        counts[str(row["lead_status"] or "new")] = int(row["c"] or 0)
    return counts


def add_history(
    user_id: int,
    action: str,
    value: str = "",
    actor_id: int = 0,
    actor_name: str = "",
) -> None:
    if not user_id:
        return
    ensure_tables()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO ibetin_lead_history(
                user_id, action, value, actor_id, actor_name, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                int(user_id),
                str(action or "")[:64],
                str(value or "")[:1000],
                int(actor_id or 0) or None,
                str(actor_name or "")[:128],
                _now(),
            ),
        )


def assign_lead(
    user_id: int,
    actor_id: int,
    actor_name: str,
) -> bool:
    if not user_id or not actor_id:
        return False
    ensure_tables()
    now = _now()
    with _connect() as conn:
        cur = conn.execute(
            """
            UPDATE ibetin_leads
            SET assigned_to=?, assigned_name=?,
                updated_by=?, updated_by_name=?, updated_at=?
            WHERE user_id=?
            """,
            (
                int(actor_id),
                str(actor_name or "")[:128],
                int(actor_id),
                str(actor_name or "")[:128],
                now,
                int(user_id),
            ),
        )
    if int(cur.rowcount or 0):
        add_history(user_id, "assigned", actor_name, actor_id, actor_name)
        return True
    return False


def add_note(
    user_id: int,
    note: str,
    actor_id: int = 0,
    actor_name: str = "",
) -> bool:
    note = str(note or "").strip()
    if not user_id or not note:
        return False
    ensure_tables()
    now = _now()
    with _connect() as conn:
        cur = conn.execute(
            """
            UPDATE ibetin_leads
            SET last_note=?, updated_by=?, updated_by_name=?, updated_at=?
            WHERE user_id=?
            """,
            (
                note[:1000],
                int(actor_id or 0) or None,
                str(actor_name or "")[:128],
                now,
                int(user_id),
            ),
        )
    if int(cur.rowcount or 0):
        add_history(user_id, "note", note, actor_id, actor_name)
        return True
    return False


def set_followup(
    user_id: int,
    followup_at: str,
    actor_id: int = 0,
    actor_name: str = "",
) -> bool:
    if not user_id:
        return False
    ensure_tables()
    now = _now()
    value = str(followup_at or "").strip()
    with _connect() as conn:
        cur = conn.execute(
            """
            UPDATE ibetin_leads
            SET next_followup_at=?, updated_by=?, updated_by_name=?, updated_at=?
            WHERE user_id=?
            """,
            (
                value or None,
                int(actor_id or 0) or None,
                str(actor_name or "")[:128],
                now,
                int(user_id),
            ),
        )
    if int(cur.rowcount or 0):
        add_history(user_id, "followup", value or "cleared", actor_id, actor_name)
        return True
    return False


def search_leads(term: str, limit: int = 10):
    ensure_tables()
    raw = str(term or "").strip()
    if not raw:
        return []

    username_term = raw.lstrip("@")
    digits = re.sub(r"\D", "", raw)
    like = f"%{username_term}%"

    with _connect() as conn:
        tables = {
            str(row["name"])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

        conditions = ["CAST(l.user_id AS TEXT) LIKE ?"]
        params = [f"%{raw}%"]

        if digits:
            conditions.append(
                "replace(replace(replace(replace(replace("
                "COALESCE(l.mobile_number,''),'+',''),' ',''),'-',''),'(',''),')','') LIKE ?"
            )
            params.append(f"%{digits}%")

        if "users" in tables:
            conditions.append(
                "EXISTS (SELECT 1 FROM users u "
                "WHERE u.user_id=l.user_id AND COALESCE(u.username,'') LIKE ?)"
            )
            params.append(like)

        if "business_customers" in tables:
            conditions.append(
                "EXISTS (SELECT 1 FROM business_customers b "
                "WHERE b.customer_id=l.user_id "
                "AND COALESCE(b.username,'') LIKE ?)"
            )
            params.append(like)

        if digits and "liveline_verified_users" in tables:
            conditions.append(
                "EXISTS (SELECT 1 FROM liveline_verified_users v "
                "WHERE v.user_id=l.user_id "
                "AND replace(replace(replace(replace(replace("
                "v.phone_number,'+',''),' ',''),'-',''),'(',''),')','') LIKE ?)"
            )
            params.append(f"%{digits}%")

        where = " OR ".join(conditions)
        rows = conn.execute(
            f"""
            SELECT l.user_id
            FROM ibetin_leads l
            WHERE {where}
            ORDER BY COALESCE(l.verified_at, l.first_seen_at) DESC
            LIMIT ?
            """,
            (*params, int(limit)),
        ).fetchall()

    return [int(r["user_id"]) for r in rows]


def recent_history(user_id: int, limit: int = 5):
    if not user_id:
        return []
    ensure_tables()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT action, value, actor_name, created_at
            FROM ibetin_lead_history
            WHERE user_id=?
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(user_id), int(limit)),
        ).fetchall()
    return [dict(r) for r in rows]
