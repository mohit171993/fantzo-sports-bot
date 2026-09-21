"""Read-only, aggregate-only IBETIN CRM startup diagnostics.

This module does not import the bot, run migrations, contact users, or modify data.
A diagnostic failure must not prevent the bot from starting.
"""
import json
import logging
import os
import sqlite3
from contextlib import closing
from pathlib import Path

LOGGER = logging.getLogger("ibetin_crm_audit")
PERSISTENT_DB = Path("/app/ibetin_bot_persistent/ibetin_bot.db")


def snapshot(path, test_username="Mohit_97saxena"):
    """Return aggregate counts from a consistent read-only SQLite snapshot."""
    db_path = Path(path).resolve()
    if not db_path.is_file():
        return {"available": False, "reason": "database_not_present"}
    with closing(sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True, timeout=5)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {"users", "business_customers", "liveline_verified_users", "ibetin_leads"}
        missing = sorted(required - tables)
        if missing:
            return {"available": False, "reason": "schema_incomplete", "missing_tables": missing}
        columns = {r[1] for r in conn.execute("PRAGMA table_info(ibetin_leads)")}
        if not {"mobile_number", "lead_status", "assigned_to"} <= columns:
            return {"available": False, "reason": "crm_migration_pending"}

        def count(sql, params=()):
            return int(conn.execute(sql, params).fetchone()[0])

        source = ("SELECT user_id FROM users WHERE user_id IS NOT NULL UNION "
                  "SELECT customer_id FROM business_customers WHERE customer_id IS NOT NULL UNION "
                  "SELECT user_id FROM liveline_verified_users WHERE user_id IS NOT NULL")
        queue = "l.lead_status='new' AND l.assigned_to IS NULL"
        verified = "EXISTS (SELECT 1 FROM liveline_verified_users v WHERE v.user_id=l.user_id)"
        mobile = ("(TRIM(COALESCE(l.mobile_number,'')) <> '' OR EXISTS "
                  "(SELECT 1 FROM liveline_verified_users v WHERE v.user_id=l.user_id "
                  "AND TRIM(COALESCE(v.phone_number,'')) <> ''))")
        result = {
            "available": True,
            "bot_users": count("SELECT COUNT(DISTINCT user_id) FROM users"),
            "dm_users": count("SELECT COUNT(DISTINCT customer_id) FROM business_customers"),
            "current_verified_users": count("SELECT COUNT(*) FROM liveline_verified_users"),
            "crm_leads": count("SELECT COUNT(*) FROM ibetin_leads"),
            "all_source_users": count("SELECT COUNT(*) FROM (" + source + ")"),
            "source_users_missing_from_crm": count("SELECT COUNT(*) FROM (" + source + ") s WHERE NOT EXISTS (SELECT 1 FROM ibetin_leads l WHERE l.user_id=s.user_id)"),
            "unassigned_new": count("SELECT COUNT(*) FROM ibetin_leads l WHERE " + queue),
            "unassigned_verified": count("SELECT COUNT(*) FROM ibetin_leads l WHERE " + queue + " AND " + verified),
            "unassigned_not_verified": count("SELECT COUNT(*) FROM ibetin_leads l WHERE " + queue + " AND NOT " + verified),
            "leads_with_saved_mobile": count("SELECT COUNT(*) FROM ibetin_leads WHERE TRIM(COALESCE(mobile_number,'')) <> ''"),
            "leads_with_available_mobile": count("SELECT COUNT(*) FROM ibetin_leads l WHERE " + mobile),
            "unassigned_with_mobile": count("SELECT COUNT(*) FROM ibetin_leads l WHERE " + queue + " AND " + mobile),
            "verified_phones_missing_from_saved_leads": count("SELECT COUNT(*) FROM liveline_verified_users v LEFT JOIN ibetin_leads l ON l.user_id=v.user_id WHERE TRIM(COALESCE(v.phone_number,'')) <> '' AND TRIM(COALESCE(l.mobile_number,'')) = ''"),
            "status_and_assignment": [dict(r) for r in conn.execute("SELECT lead_status, CASE WHEN assigned_to IS NULL THEN 'unassigned' ELSE 'assigned' END AS assignment, COUNT(*) AS count FROM ibetin_leads GROUP BY lead_status, assigned_to IS NULL ORDER BY lead_status, assigned_to IS NULL")],
        }
        if test_username:
            identities = ("SELECT user_id FROM users WHERE lower(COALESCE(username,''))=lower(?) UNION "
                          "SELECT customer_id FROM business_customers WHERE lower(COALESCE(username,''))=lower(?)")
            params = (test_username.lstrip("@"),) * 2
            found = count("SELECT COUNT(*) FROM (" + identities + ")", params)
            result["test_user"] = {"matches": found}
            if found == 1:
                result["test_user"].update({
                    "currently_verified": bool(count("SELECT COUNT(*) FROM liveline_verified_users WHERE user_id IN (" + identities + ")", params)),
                    "has_saved_mobile": bool(count("SELECT COUNT(*) FROM ibetin_leads WHERE TRIM(COALESCE(mobile_number,''))<>'' AND user_id IN (" + identities + ")", params)),
                })
        result["queue_split_consistent"] = result["unassigned_new"] == result["unassigned_verified"] + result["unassigned_not_verified"]
        return result


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    configured = Path(os.getenv("DB_PATH", "").strip() or "/app/ibetin_bot.db")
    active = PERSISTENT_DB if PERSISTENT_DB.is_file() else configured
    try:
        LOGGER.info("IBETIN_CRM_AUDIT %s", json.dumps(snapshot(active), sort_keys=True, separators=(",", ":")))
    except Exception as exc:
        # Report only the exception class, never SQL rows, phone numbers or secrets.
        LOGGER.warning("IBETIN_CRM_AUDIT unavailable error_type=%s", type(exc).__name__)


if __name__ == "__main__":
    main()
