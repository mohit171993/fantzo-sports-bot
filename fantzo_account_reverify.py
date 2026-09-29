"""One-time, exact-account Fantzo verification revocation requested by the owner.

The username is only a cross-check. The pinned Telegram user ID prevents a
renamed or reassigned username from revoking someone else's verification.
"""

import logging
from datetime import datetime, timezone

import bot as core

logger = logging.getLogger(__name__)

TARGET_USER_ID = 1456774567
TARGET_USERNAME = "mohit_97saxena"
ACTION_KEY = "reverify_mohit_97saxena_2026_09_29"


def apply_once() -> str:
    now = datetime.now(timezone.utc).isoformat()
    with core.db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fantzo_account_actions (
                action_key TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                verified_revoked INTEGER NOT NULL,
                mapping_removed INTEGER NOT NULL,
                applied_at TEXT NOT NULL
            )
        """)
        if conn.execute(
            "SELECT 1 FROM fantzo_account_actions WHERE action_key=?",
            (ACTION_KEY,),
        ).fetchone():
            logger.info("Fantzo targeted reverify action already applied for user=%s", TARGET_USER_ID)
            return "already_applied"

        matches = conn.execute(
            "SELECT user_id FROM users WHERE lower(trim(COALESCE(username,'')))=?",
            (TARGET_USERNAME,),
        ).fetchall()
        if len(matches) != 1 or int(matches[0]["user_id"]) != TARGET_USER_ID:
            logger.warning(
                "Fantzo targeted reverify skipped: username=%s expected_user=%s match_count=%s matched_user=%s",
                TARGET_USERNAME,
                TARGET_USER_ID,
                len(matches),
                int(matches[0]["user_id"]) if len(matches) == 1 else None,
            )
            return "identity_mismatch"

        verified_revoked = conn.execute(
            "UPDATE live_tv_mobile_users "
            "SET capture_method='reverify_required', updated_at=? "
            "WHERE user_id=? AND capture_method='telegram_contact'",
            (now, TARGET_USER_ID),
        ).rowcount
        has_mapping = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='lead_user_map'",
        ).fetchone()
        mapping_removed = (
            conn.execute("DELETE FROM lead_user_map WHERE user_id=?", (TARGET_USER_ID,)).rowcount
            if has_mapping else 0
        )
        conn.execute(
            "INSERT INTO mobile_verification_events(user_id,source,event,created_at) "
            "VALUES(?,?,?,?)",
            (TARGET_USER_ID, "owner_request", "reverify_required", now),
        )
        conn.execute(
            "INSERT INTO fantzo_account_actions "
            "(action_key,user_id,username,verified_revoked,mapping_removed,applied_at) "
            "VALUES(?,?,?,?,?,?)",
            (ACTION_KEY, TARGET_USER_ID, TARGET_USERNAME, verified_revoked, mapping_removed, now),
        )
    logger.warning(
        "Fantzo targeted reverify applied: user=%s verified_revoked=%s mapping_removed=%s",
        TARGET_USER_ID,
        verified_revoked,
        mapping_removed,
    )
    return "applied"
