"""One-time full fresh-state reset for the Fantzo test Telegram account.

Strictly targets username mohit_97saxena and its resolved Telegram user_id.
No other users are modified.
"""

import logging
import bot as core

logger = logging.getLogger(__name__)
TARGET_USERNAME = "mohit_97saxena"

def _table_exists(conn, name: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone())

def _delete(conn, table: str, column: str, value) -> int:
    if not _table_exists(conn, table):
        return 0
    cur = conn.execute(f"DELETE FROM {table} WHERE {column}=?", (value,))
    return int(cur.rowcount or 0)

def run_once() -> None:
    try:
        with core.db() as conn:
            rows = conn.execute(
                "SELECT user_id,username FROM users WHERE lower(username)=lower(?)",
                (TARGET_USERNAME,),
            ).fetchall()

            if len(rows) != 1:
                logger.warning(
                    "FANTZO_TEST_CLEAR username=%s matches=%s action=none",
                    TARGET_USERNAME,
                    len(rows),
                )
                return

            user_id = int(rows[0]["user_id"])

            # Capture test mobile before removing user-specific mappings.
            mobiles = set()
            if _table_exists(conn, "live_tv_mobile_users"):
                r = conn.execute(
                    "SELECT mobile_e164 FROM live_tv_mobile_users WHERE user_id=?",
                    (user_id,),
                ).fetchone()
                if r and r["mobile_e164"]:
                    mobiles.add(str(r["mobile_e164"]))

            if _table_exists(conn, "lead_user_map"):
                for r in conn.execute(
                    "SELECT mobile_e164 FROM lead_user_map WHERE user_id=?",
                    (user_id,),
                ).fetchall():
                    if r["mobile_e164"]:
                        mobiles.add(str(r["mobile_e164"]))

            deleted = {}

            # Verification / onboarding state.
            deleted["live_tv_mobile_users"] = _delete(conn, "live_tv_mobile_users", "user_id", user_id)
            deleted["mobile_verification_events"] = _delete(conn, "mobile_verification_events", "user_id", user_id)
            deleted["business_verification_pending"] = _delete(conn, "business_verification_pending", "user_id", user_id)
            deleted["lead_contact_opt_outs"] = _delete(conn, "lead_contact_opt_outs", "user_id", user_id)

            # CRM / attribution state.
            deleted["lead_attribution"] = _delete(conn, "lead_attribution", "user_id", user_id)
            deleted["lead_events"] = _delete(conn, "lead_events", "user_id", user_id)
            deleted["lead_user_map"] = _delete(conn, "lead_user_map", "user_id", user_id)

            # Remove the sales lead only when it belongs exclusively to this test user.
            deleted_sales = 0
            preserved_shared_sales = 0
            if _table_exists(conn, "sales_leads"):
                for mobile in mobiles:
                    other_links = 0
                    if _table_exists(conn, "lead_user_map"):
                        other_links = int(conn.execute(
                            "SELECT COUNT(*) FROM lead_user_map "
                            "WHERE mobile_e164=? AND user_id!=?",
                            (mobile, user_id),
                        ).fetchone()[0] or 0)

                    row = conn.execute(
                        "SELECT primary_user_id FROM sales_leads WHERE mobile_e164=?",
                        (mobile,),
                    ).fetchone()

                    if row and int(row["primary_user_id"] or 0) == user_id and other_links == 0:
                        cur = conn.execute(
                            "DELETE FROM sales_leads WHERE mobile_e164=?",
                            (mobile,),
                        )
                        deleted_sales += int(cur.rowcount or 0)
                    elif row:
                        preserved_shared_sales += 1

            deleted["sales_leads"] = deleted_sales

            # Reminder / engagement state so timing and first-touch tests are fresh.
            if _table_exists(conn, "reminder_users"):
                cur = conn.execute("DELETE FROM reminder_users WHERE user_id=?", (user_id,))
                deleted["reminder_users"] = int(cur.rowcount or 0)
            else:
                deleted["reminder_users"] = 0

            if _table_exists(conn, "reminder_sends"):
                cols = {str(r["name"]) for r in conn.execute("PRAGMA table_info(reminder_sends)").fetchall()}
                if "user_id" in cols:
                    cur = conn.execute("DELETE FROM reminder_sends WHERE user_id=?", (user_id,))
                    deleted["reminder_sends"] = int(cur.rowcount or 0)
                else:
                    deleted["reminder_sends"] = 0
            else:
                deleted["reminder_sends"] = 0

            # Business / product activity for a clean first-run experience.
            deleted["business_welcomes"] = _delete(conn, "business_welcomes", "customer_id", user_id)
            deleted["business_customers"] = _delete(conn, "business_customers", "customer_id", user_id)
            deleted["user_favourites"] = _delete(conn, "user_favourites", "user_id", user_id)
            deleted["live_tv_users"] = _delete(conn, "live_tv_users", "user_id", user_id)
            deleted["clicks"] = _delete(conn, "clicks", "user_id", user_id)
            deleted["growth_events"] = _delete(conn, "growth_events", "user_id", user_id)

            # Delete the core profile last. It is recreated automatically on next /start.
            deleted["users"] = _delete(conn, "users", "user_id", user_id)

            # Confirm no verification or core user row remains.
            verified_after = 0
            if _table_exists(conn, "live_tv_mobile_users"):
                verified_after = int(bool(conn.execute(
                    "SELECT 1 FROM live_tv_mobile_users "
                    "WHERE user_id=? AND capture_method='telegram_contact' LIMIT 1",
                    (user_id,),
                ).fetchone()))

            user_exists_after = int(bool(conn.execute(
                "SELECT 1 FROM users WHERE user_id=? LIMIT 1",
                (user_id,),
            ).fetchone())) if _table_exists(conn, "users") else 0

        logger.warning(
            "FANTZO_TEST_CLEAR username=%s user_id=%s verified_after=%s "
            "user_exists_after=%s preserved_shared_sales=%s deleted=%s",
            TARGET_USERNAME,
            user_id,
            verified_after,
            user_exists_after,
            preserved_shared_sales,
            deleted,
        )

    except Exception:
        logger.exception("FANTZO_TEST_CLEAR failed")
