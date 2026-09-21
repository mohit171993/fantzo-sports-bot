"""One-time test reset for a single Fantzo Telegram account.

Temporary maintenance helper for controlled verification testing.
Does not delete mobile numbers, lead history, attribution, or reports.
"""

import logging

import bot as core

logger = logging.getLogger(__name__)

TARGET_USERNAME = "mohit_97saxena"


def run_once() -> None:
    try:
        with core.db() as conn:
            rows = conn.execute(
                "SELECT user_id,username FROM users WHERE lower(username)=lower(?)",
                (TARGET_USERNAME,),
            ).fetchall()

            if len(rows) != 1:
                logger.warning(
                    "FANTZO_TEST_UNVERIFY username=%s matches=%s action=none",
                    TARGET_USERNAME,
                    len(rows),
                )
                return

            user_id = int(rows[0]["user_id"])
            mobile_row = conn.execute(
                "SELECT capture_method FROM live_tv_mobile_users WHERE user_id=?",
                (user_id,),
            ).fetchone()

            before = str(mobile_row["capture_method"]) if mobile_row else "missing"
            changed = 0
            if mobile_row:
                cur = conn.execute(
                    "UPDATE live_tv_mobile_users "
                    "SET capture_method='test_reset', updated_at=datetime('now') "
                    "WHERE user_id=?",
                    (user_id,),
                )
                changed = int(cur.rowcount or 0)

            pending_cur = conn.execute(
                "DELETE FROM business_verification_pending WHERE user_id=?",
                (user_id,),
            )
            pending_deleted = int(pending_cur.rowcount or 0)

            after_row = conn.execute(
                "SELECT capture_method FROM live_tv_mobile_users WHERE user_id=?",
                (user_id,),
            ).fetchone()
            after = str(after_row["capture_method"]) if after_row else "missing"

            verified_after = int(
                bool(
                    conn.execute(
                        "SELECT 1 FROM live_tv_mobile_users "
                        "WHERE user_id=? AND capture_method='telegram_contact' LIMIT 1",
                        (user_id,),
                    ).fetchone()
                )
            )

        logger.warning(
            "FANTZO_TEST_UNVERIFY username=%s user_id=%s matches=1 "
            "mobile_row=%s rows_changed=%s before=%s after=%s "
            "pending_deleted=%s verified_after=%s",
            TARGET_USERNAME,
            user_id,
            1 if mobile_row else 0,
            changed,
            before,
            after,
            pending_deleted,
            verified_after,
        )
    except Exception:
        logger.exception("FANTZO_TEST_UNVERIFY failed")
