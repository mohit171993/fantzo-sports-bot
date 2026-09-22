"""One-time full fresh-state reset for the Fantzo test account after admin change."""

import logging
import bot as core

logger = logging.getLogger(__name__)
TARGET_USER_ID = 1456774567
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
            user_id = TARGET_USER_ID
            mobiles = set()

            if _table_exists(conn, "live_tv_mobile_users"):
                row = conn.execute(
                    "SELECT mobile_e164 FROM live_tv_mobile_users WHERE user_id=?",
                    (user_id,),
                ).fetchone()
                if row and row["mobile_e164"]:
                    mobiles.add(str(row["mobile_e164"]))

            if _table_exists(conn, "lead_user_map"):
                for row in conn.execute(
                    "SELECT mobile_e164 FROM lead_user_map WHERE user_id=?",
                    (user_id,),
                ).fetchall():
                    if row["mobile_e164"]:
                        mobiles.add(str(row["mobile_e164"]))

            if _table_exists(conn, "sales_leads"):
                for row in conn.execute(
                    "SELECT mobile_e164 FROM sales_leads WHERE primary_user_id=?",
                    (user_id,),
                ).fetchall():
                    if row["mobile_e164"]:
                        mobiles.add(str(row["mobile_e164"]))

            deleted = {}
            for table, column in (
                ("live_tv_mobile_users", "user_id"),
                ("mobile_verification_events", "user_id"),
                ("business_verification_pending", "user_id"),
                ("lead_contact_opt_outs", "user_id"),
                ("lead_attribution", "user_id"),
                ("lead_events", "user_id"),
                ("lead_user_map", "user_id"),
                ("business_welcomes", "customer_id"),
                ("business_customers", "customer_id"),
                ("user_favourites", "user_id"),
                ("live_tv_users", "user_id"),
                ("clicks", "user_id"),
                ("growth_events", "user_id"),
                ("users", "user_id"),
            ):
                deleted[table] = _delete(conn, table, column, user_id)

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

            if _table_exists(conn, "fantzo_lead_history"):
                cur = conn.execute(
                    "DELETE FROM fantzo_lead_history WHERE user_id=?",
                    (user_id,),
                )
                deleted["fantzo_lead_history"] = int(cur.rowcount or 0)
            else:
                deleted["fantzo_lead_history"] = 0

            deleted_sales = 0
            preserved_shared = 0
            if _table_exists(conn, "sales_leads"):
                for mobile in mobiles:
                    other_links = 0
                    if _table_exists(conn, "lead_user_map"):
                        other_links = int(conn.execute(
                            "SELECT COUNT(*) FROM lead_user_map WHERE mobile_e164=? AND user_id!=?",
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
                        preserved_shared += 1
            deleted["sales_leads"] = deleted_sales

            verified_after = 0
            if _table_exists(conn, "live_tv_mobile_users"):
                verified_after = int(bool(conn.execute(
                    "SELECT 1 FROM live_tv_mobile_users WHERE user_id=? AND capture_method='telegram_contact' LIMIT 1",
                    (user_id,),
                ).fetchone()))

            user_exists_after = int(bool(conn.execute(
                "SELECT 1 FROM users WHERE user_id=? LIMIT 1",
                (user_id,),
            ).fetchone())) if _table_exists(conn, "users") else 0

        logger.warning(
            "FANTZO_TEST_CLEAR username=%s user_id=%s verified_after=%s "
            "user_exists_after=%s preserved_shared=%s deleted=%s",
            TARGET_USERNAME,
            user_id,
            verified_after,
            user_exists_after,
            preserved_shared,
            deleted,
        )
    except Exception:
        logger.exception("FANTZO_TEST_CLEAR failed")
