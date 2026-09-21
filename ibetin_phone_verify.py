import hashlib
import hmac
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import ibetin_leads

DEFAULT_LIVE_LINE_URL = "https://ibetin-app-production.up.railway.app/liveline"
DEFAULT_BOT_USERNAME = "Ibtnofficialbot"
TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60


def _db_path() -> str:
    return os.getenv("DB_PATH", "/app/ibetin_bot.db").strip() or "/app/ibetin_bot.db"


def _connect():
    conn = sqlite3.connect(_db_path(), timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_tables() -> None:
    ibetin_leads.ensure_tables()
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS liveline_verified_users (
                user_id INTEGER PRIMARY KEY,
                phone_number TEXT NOT NULL,
                verified_at TEXT NOT NULL,
                first_verified_at TEXT,
                verification_source TEXT NOT NULL DEFAULT '',
                campaign TEXT NOT NULL DEFAULT 'direct',
                contact_consent INTEGER NOT NULL DEFAULT 0,
                consent_at TEXT
            )
            """
        )
        columns = {
            str(row["name"])
            for row in conn.execute(
                "PRAGMA table_info(liveline_verified_users)"
            ).fetchall()
        }
        migrations = (
            ("first_verified_at", "TEXT"),
            ("verification_source", "TEXT NOT NULL DEFAULT ''"),
            ("campaign", "TEXT NOT NULL DEFAULT 'direct'"),
            ("contact_consent", "INTEGER NOT NULL DEFAULT 0"),
            ("consent_at", "TEXT"),
        )
        for name, sql_type in migrations:
            if name not in columns:
                conn.execute(
                    f"ALTER TABLE liveline_verified_users "
                    f"ADD COLUMN {name} {sql_type}"
                )
        conn.execute(
            """
            UPDATE liveline_verified_users
            SET first_verified_at=COALESCE(first_verified_at, verified_at)
            WHERE first_verified_at IS NULL OR first_verified_at=''
            """
        )


def normalize_phone(value: str) -> str:
    raw = str(value or "").strip()
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 7 or len(digits) > 15:
        return ""
    return ("+" if raw.startswith("+") else "") + digits


def verify_user(
    user_id: int,
    phone_number: str,
    source: str = "",
    campaign: str = "",
    contact_consent: bool = False,
) -> bool:
    phone = normalize_phone(phone_number)
    if not user_id or not phone:
        return False
    ensure_tables()
    now = datetime.now(timezone.utc).isoformat()
    lead = ibetin_leads.get_lead(int(user_id)) or {}
    source_value = (
        ibetin_leads.clean_source(source)
        if source
        else str(lead.get("source") or "bot")
    )
    campaign_value = (
        ibetin_leads.clean_campaign(campaign)
        if campaign
        else str(lead.get("campaign") or "direct")
    )
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO liveline_verified_users(
                user_id, phone_number, verified_at, first_verified_at,
                verification_source, campaign, contact_consent, consent_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                phone_number = excluded.phone_number,
                verified_at = excluded.verified_at,
                first_verified_at = COALESCE(
                    liveline_verified_users.first_verified_at,
                    liveline_verified_users.verified_at,
                    excluded.first_verified_at
                ),
                verification_source = CASE
                    WHEN excluded.verification_source != ''
                    THEN excluded.verification_source
                    ELSE liveline_verified_users.verification_source
                END,
                campaign = CASE
                    WHEN excluded.campaign != ''
                    THEN excluded.campaign
                    ELSE liveline_verified_users.campaign
                END,
                contact_consent = CASE
                    WHEN excluded.contact_consent = 1 THEN 1
                    ELSE liveline_verified_users.contact_consent
                END,
                consent_at = CASE
                    WHEN excluded.contact_consent = 1
                    THEN COALESCE(liveline_verified_users.consent_at, excluded.consent_at)
                    ELSE liveline_verified_users.consent_at
                END
            """,
            (
                int(user_id),
                phone,
                now,
                now,
                source_value,
                campaign_value,
                1 if contact_consent else 0,
                now if contact_consent else None,
            ),
        )

    ibetin_leads.mark_verified(
        int(user_id),
        source=source_value,
        campaign=campaign_value,
        contact_consent=bool(contact_consent),
    )
    return True


def is_verified(user_id: int) -> bool:
    if not user_id:
        return False
    ensure_tables()
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM liveline_verified_users WHERE user_id = ? LIMIT 1",
            (int(user_id),),
        ).fetchone()
    return bool(row)


def _secret() -> bytes:
    value = (
        os.getenv("IBETIN_LIVELINE_ACCESS_SECRET", "").strip()
        or os.getenv("BOT_TOKEN", "").strip()
    )
    if not value:
        raise RuntimeError("Live Line access secret is not configured")
    return ("ibetin-liveline-access:v1:" + value).encode("utf-8")


def issue_access_token(user_id: int, ttl_seconds: int = TOKEN_TTL_SECONDS) -> str:
    uid = int(user_id)
    exp = int(time.time()) + max(300, int(ttl_seconds))
    payload = f"{uid}.{exp}"
    sig = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:40]
    return f"{payload}.{sig}"


def verify_access_token(token: str) -> int:
    try:
        uid_s, exp_s, supplied = str(token or "").strip().split(".", 2)
        uid = int(uid_s)
        exp = int(exp_s)
        if uid <= 0 or exp < int(time.time()):
            return 0
        payload = f"{uid}.{exp}"
        expected = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:40]
        if not hmac.compare_digest(expected, supplied):
            return 0
        return uid
    except Exception:
        return 0


def live_line_url(user_id: int, base_url: str = "") -> str:
    root = (
        str(base_url or "").strip()
        or os.getenv("IBETIN_LIVE_LINE_URL", "").strip()
        or DEFAULT_LIVE_LINE_URL
    )
    token = issue_access_token(int(user_id))
    joiner = "&" if "?" in root else "?"
    return f"{root}{joiner}{urlencode({'access': token})}"


def verification_bot_url(start_arg: str = "verifyliveline") -> str:
    username = (
        os.getenv("IBETIN_BOT_USERNAME", DEFAULT_BOT_USERNAME).strip().lstrip("@")
        or DEFAULT_BOT_USERNAME
    )
    arg = re.sub(r"[^A-Za-z0-9_-]", "", str(start_arg or "verifyliveline"))[:64]
    if not arg:
        arg = "verifyliveline"
    return f"https://t.me/{username}?start={arg}"


def apply_requested_reset() -> int:
    """One-time operator reset for Live Line mobile verification.

    Controlled only through the IBETIN_RESET_VERIFICATION_PHONE environment
    variable. The caller should clear that variable immediately after use.
    """
    requested = normalize_phone(
        os.getenv("IBETIN_RESET_VERIFICATION_PHONE", "").strip()
    )
    if not requested:
        return 0

    ensure_tables()
    requested_digits = re.sub(r"\D", "", requested)
    deleted = 0
    with _connect() as conn:
        rows = conn.execute(
            "SELECT user_id, phone_number FROM liveline_verified_users"
        ).fetchall()
        for row in rows:
            stored_digits = re.sub(r"\D", "", str(row["phone_number"] or ""))
            if stored_digits == requested_digits:
                cur = conn.execute(
                    "DELETE FROM liveline_verified_users WHERE user_id = ?",
                    (int(row["user_id"]),),
                )
                deleted += int(cur.rowcount or 0)
    return deleted


def apply_requested_username_reset() -> int:
    """One-time operator reset for a user's IBETIN mobile verification.

    Controlled by IBETIN_RESET_VERIFICATION_USERNAME. It resolves the Telegram
    user ID from users/business_customers and deletes only that user's row from
    liveline_verified_users. The environment variable should be cleared
    immediately after the reset is observed.
    """
    requested = (
        os.getenv("IBETIN_RESET_VERIFICATION_USERNAME", "")
        .strip()
        .lstrip("@")
        .casefold()
    )
    if not requested:
        return 0

    ensure_tables()
    user_ids = set()
    with _connect() as conn:
        tables = {
            str(row["name"])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

        if "users" in tables:
            rows = conn.execute(
                "SELECT user_id FROM users WHERE lower(username)=?",
                (requested,),
            ).fetchall()
            user_ids.update(int(row["user_id"]) for row in rows if row["user_id"])

        if "business_customers" in tables:
            rows = conn.execute(
                "SELECT DISTINCT customer_id FROM business_customers WHERE lower(username)=?",
                (requested,),
            ).fetchall()
            user_ids.update(
                int(row["customer_id"]) for row in rows if row["customer_id"]
            )

        deleted = 0
        for user_id in user_ids:
            cur = conn.execute(
                "DELETE FROM liveline_verified_users WHERE user_id=?",
                (int(user_id),),
            )
            deleted += int(cur.rowcount or 0)

    return deleted


def apply_requested_user_id_reset() -> int:
    """One-time operator reset by exact Telegram user ID."""
    raw = os.getenv("IBETIN_RESET_VERIFICATION_USER_ID", "").strip()
    if not raw:
        return 0
    try:
        user_id = int(raw)
    except Exception:
        return 0
    if user_id <= 0:
        return 0

    ensure_tables()
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM liveline_verified_users WHERE user_id = ?",
            (user_id,),
        )
        return int(cur.rowcount or 0)
