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
                contact_consent INTEGER NOT NULL DEFAULT 0,
                lead_status TEXT NOT NULL DEFAULT 'new',
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
            "CREATE INDEX IF NOT EXISTS idx_ibetin_leads_campaign "
            "ON ibetin_leads(campaign)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ibetin_leads_status "
            "ON ibetin_leads(lead_status)"
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
            # Do not overwrite a real ad campaign with a later plain /start.
            old_campaign = str(existing["campaign"] or "direct")
            chosen_campaign = (
                old_campaign
                if campaign_value == "direct" and old_campaign != "direct"
                else campaign_value
            )
            old_source = str(existing["source"] or "bot")
            chosen_source = source_value or old_source
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
        conn.execute(
            """
            UPDATE ibetin_leads
            SET verified_at=COALESCE(verified_at, ?),
                contact_consent=?,
                source=CASE WHEN ? != '' THEN ? ELSE source END,
                campaign=CASE WHEN ? != '' THEN ? ELSE campaign END,
                updated_at=?
            WHERE user_id=?
            """,
            (
                now,
                1 if contact_consent else 0,
                clean_source(source) if source else "",
                clean_source(source) if source else "",
                clean_campaign(campaign) if campaign else "",
                clean_campaign(campaign) if campaign else "",
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


def set_status(user_id: int, status: str) -> bool:
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
            record_start(int(user_id))
        conn.execute(
            "UPDATE ibetin_leads SET lead_status=?, updated_at=? WHERE user_id=?",
            (status, now, int(user_id)),
        )
        if timestamp_column:
            conn.execute(
                f"UPDATE ibetin_leads "
                f"SET {timestamp_column}=COALESCE({timestamp_column}, ?), updated_at=? "
                "WHERE user_id=?",
                (now, now, int(user_id)),
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
