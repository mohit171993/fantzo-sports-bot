"""Synthetic-data tests only: no production database, bot imports or messages."""
import gc
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ibetin_crm_audit import snapshot
from ibetin_crm_queue_start import TEST_USER_ID, force_test_unverified_once, queue_sql


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'test.db'
        with sqlite3.connect(self.path) as c:
            c.executescript('''CREATE TABLE users(user_id INTEGER PRIMARY KEY, username TEXT);
CREATE TABLE business_customers(customer_id INTEGER, username TEXT);
CREATE TABLE liveline_verified_users(user_id INTEGER PRIMARY KEY, phone_number TEXT);
CREATE TABLE ibetin_leads(user_id INTEGER PRIMARY KEY, mobile_number TEXT, lead_status TEXT, assigned_to INTEGER);''')

    def tearDown(self):
        gc.collect()
        self.tmp.cleanup()

    def seed(self, n=112, phones=9):
        with sqlite3.connect(self.path) as c:
            for uid in range(1, n + 1):
                c.execute('INSERT INTO users VALUES (?,?)', (uid, 'Mohit_97saxena' if uid == 1 else f'test_{uid}'))
                c.execute('INSERT INTO ibetin_leads VALUES (?,?,?,NULL)', (uid, f'+999{uid:09}' if uid <= phones else None, 'new'))
                if uid <= phones:
                    c.execute('INSERT INTO liveline_verified_users VALUES (?,?)', (uid, f'+999{uid:09}'))

    def test_all_historical_users_counted(self):
        self.seed()
        s = snapshot(self.path)
        self.assertEqual(s['unassigned_new'], 112)
        self.assertEqual(s['source_users_missing_from_crm'], 0)

    def test_user_count_not_phone_count(self):
        self.seed()
        s = snapshot(self.path)
        self.assertEqual(s['bot_users'], 112)
        self.assertEqual(s['leads_with_available_mobile'], 9)

    def test_verification_separate_from_queue(self):
        self.seed()
        s = snapshot(self.path)
        self.assertEqual((s['unassigned_verified'], s['unassigned_not_verified']), (9, 103))
        self.assertTrue(s['queue_split_consistent'])

    def test_saved_phone_survives_verification_reset(self):
        self.seed()
        with sqlite3.connect(self.path) as c:
            c.execute('DELETE FROM liveline_verified_users WHERE user_id=1')
        s = snapshot(self.path)
        self.assertEqual(s['unassigned_with_mobile'], 9)
        self.assertFalse(s['test_user']['currently_verified'])
        self.assertTrue(s['test_user']['has_saved_mobile'])

    def test_strict_unassigned_audit_excludes_owned(self):
        self.seed()
        with sqlite3.connect(self.path) as c:
            c.execute('UPDATE ibetin_leads SET assigned_to=42 WHERE user_id=1')
        self.assertEqual(snapshot(self.path)['unassigned_new'], 111)

    def test_statused_excluded_without_rewriting(self):
        self.seed()
        with sqlite3.connect(self.path) as c:
            c.execute("UPDATE ibetin_leads SET lead_status='dnc' WHERE user_id=1")
        self.assertEqual(snapshot(self.path)['unassigned_new'], 111)
        with sqlite3.connect(self.path) as c:
            self.assertEqual(c.execute('SELECT lead_status FROM ibetin_leads WHERE user_id=1').fetchone()[0], 'dnc')

    def test_missing_source_detected_and_not_backfilled(self):
        self.seed()
        with sqlite3.connect(self.path) as c:
            c.execute('INSERT INTO business_customers VALUES (999,?)', ('dm_test',))
        s = snapshot(self.path)
        self.assertEqual(s['source_users_missing_from_crm'], 1)
        self.assertEqual(s['crm_leads'], 112)

    def test_audit_does_not_modify_database(self):
        self.seed()
        before = self.path.read_bytes()
        snapshot(self.path)
        self.assertEqual(before, self.path.read_bytes())

    def test_missing_database_not_created(self):
        p = self.path.parent / 'missing.db'
        self.assertFalse(snapshot(p)['available'])
        self.assertFalse(p.exists())

    def test_no_personal_data_in_output(self):
        self.seed()
        text = json.dumps(snapshot(self.path))
        self.assertNotIn('+999', text)
        self.assertNotIn('Mohit_97saxena', text)
        self.assertNotIn('test_2', text)

    def test_missing_phone_persistence_detected(self):
        self.seed()
        with sqlite3.connect(self.path) as c:
            c.execute('UPDATE ibetin_leads SET mobile_number=NULL WHERE user_id=1')
        s = snapshot(self.path)
        self.assertEqual(s['verified_phones_missing_from_saved_leads'], 1)
        self.assertEqual(s['leads_with_available_mobile'], 9)

    def test_duplicate_sources_not_double_counted(self):
        self.seed()
        with sqlite3.connect(self.path) as c:
            c.execute('INSERT INTO business_customers VALUES (1,?)', ('Mohit_97saxena',))
        s = snapshot(self.path)
        self.assertEqual(s['all_source_users'], 112)
        self.assertEqual(s['test_user']['matches'], 1)

    def _reports_for_account_reset(self):
        @contextmanager
        def db():
            conn = sqlite3.connect(self.path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

        return SimpleNamespace(
            core=SimpleNamespace(db=db),
            _table_exists=lambda conn, name: bool(conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
            ).fetchone()),
        )

    def test_exact_account_reset_preserves_history_and_allows_reverification(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("INSERT INTO users VALUES (?,?)", (TEST_USER_ID, "@Mohit_97saxena"))
            conn.execute("INSERT INTO business_customers VALUES (?,?)", (TEST_USER_ID, "Mohit_97saxena"))
            conn.execute("INSERT INTO ibetin_leads VALUES (?,?,?,?)", (TEST_USER_ID, None, "new", None))
            conn.execute("INSERT INTO users VALUES (?,?)", (2, "other"))
            conn.execute("INSERT INTO liveline_verified_users VALUES (?,?)", (TEST_USER_ID, "+999123456789"))
            conn.execute("INSERT INTO liveline_verified_users VALUES (?,?)", (2, "+999000000002"))

        reports = self._reports_for_account_reset()
        force_test_unverified_once(reports)
        with sqlite3.connect(self.path) as conn:
            self.assertIsNone(conn.execute(
                "SELECT 1 FROM liveline_verified_users WHERE user_id=?", (TEST_USER_ID,)
            ).fetchone())
            self.assertIsNotNone(conn.execute(
                "SELECT 1 FROM liveline_verified_users WHERE user_id=2"
            ).fetchone())
            self.assertEqual(conn.execute(
                "SELECT mobile_number FROM ibetin_leads WHERE user_id=?", (TEST_USER_ID,)
            ).fetchone()[0], "+999123456789")
            self.assertIsNotNone(conn.execute(
                "SELECT 1 FROM verification_bypass_exclusions WHERE user_id=?", (TEST_USER_ID,)
            ).fetchone())
            conn.execute("INSERT INTO liveline_verified_users VALUES (?,?)", (TEST_USER_ID, "+999123456789"))

        force_test_unverified_once(reports)
        with sqlite3.connect(self.path) as conn:
            self.assertIsNotNone(conn.execute(
                "SELECT 1 FROM liveline_verified_users WHERE user_id=?", (TEST_USER_ID,)
            ).fetchone())

    def test_account_reset_skips_username_bound_to_another_id(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("INSERT INTO users VALUES (?,?)", (3, "Mohit_97saxena"))
            conn.execute("INSERT INTO liveline_verified_users VALUES (?,?)", (3, "+999000000003"))
        force_test_unverified_once(self._reports_for_account_reset())
        with sqlite3.connect(self.path) as conn:
            self.assertIsNotNone(conn.execute(
                "SELECT 1 FROM liveline_verified_users WHERE user_id=3"
            ).fetchone())
            self.assertIsNone(conn.execute(
                "SELECT 1 FROM settings WHERE key='dura_reverify_mohit_97saxena:2026-09-29'"
            ).fetchone())


class PhoneVerifyBypassTests(unittest.TestCase):
    def test_excluded_admin_must_verify_again_and_can_reverify(self):
        import ibetin_phone_verify as phone_verify

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "verify.db"
            with mock.patch.dict(os.environ, {
                "DB_PATH": str(path),
                "ADMIN_USER_ID": str(TEST_USER_ID),
                "IBETIN_REPORT_ADMIN_USER_ID": "42",
            }):
                phone_verify.ensure_tables()
                self.assertTrue(phone_verify.is_verified(TEST_USER_ID))
                with sqlite3.connect(path) as conn:
                    conn.execute(
                        "INSERT INTO verification_bypass_exclusions(user_id,reason,created_at) "
                        "VALUES(?,?,?)", (TEST_USER_ID, "account reverify", "now")
                    )
                conn.close()
                self.assertFalse(phone_verify.is_verified(TEST_USER_ID))
                self.assertTrue(phone_verify.is_verified(42))
                with sqlite3.connect(path) as conn:
                    conn.execute(
                        "INSERT INTO liveline_verified_users(user_id,phone_number,verified_at) "
                        "VALUES(?,?,?)", (TEST_USER_ID, "+999123456789", "now")
                    )
                conn.close()
                self.assertTrue(phone_verify.is_verified(TEST_USER_ID))
                gc.collect()


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(':memory:')
        self.c.executescript('''CREATE TABLE ibetin_leads(user_id INTEGER PRIMARY KEY, lead_status TEXT, mobile_number TEXT, assigned_to INTEGER, first_seen_at TEXT, updated_at TEXT, next_followup_at TEXT);
CREATE TABLE liveline_verified_users(user_id INTEGER PRIMARY KEY, phone_number TEXT);''')
        for uid, status in enumerate(('new', None, '', ' ', 'contacted', 'dnc', 'converted', 'interested', 'no_answer'), 1):
            self.c.execute('INSERT INTO ibetin_leads VALUES (?,?,?,?,?,?,?)', (uid, status, '+999000000001' if uid == 1 else None, 42 if uid == 1 else None, '2025-01-01', '2025-01-01', '2025-01-02'))

    def tearDown(self):
        self.c.close()

    def ids(self, queue):
        return [r[0] for r in self.c.execute(*queue_sql(queue))]

    def test_all_time_and_all_statuses(self):
        self.assertEqual(len(self.ids('all')), 9)

    def test_blank_and_null_status_included(self):
        self.assertEqual(set(self.ids('new')), {1, 2, 3, 4})

    def test_assignment_does_not_hide_new(self):
        self.assertIn(1, self.ids('new'))

    def test_saved_mobile_without_verification(self):
        self.assertEqual(self.ids('mobile'), [1])

    def test_current_phone_fallback(self):
        self.c.execute('INSERT INTO liveline_verified_users VALUES (2,?)', ('+999000000002',))
        self.assertEqual(set(self.ids('mobile')), {1, 2})

    def test_followup_statuses(self):
        self.assertEqual(set(self.ids('followup')), {5, 9})

    def test_dnc_and_converted_not_due(self):
        self.assertNotIn(6, self.ids('due'))
        self.assertNotIn(7, self.ids('due'))

    def test_unknown_queue_rejected(self):
        self.assertIsNone(queue_sql("new' OR 1=1"))


if __name__ == '__main__':
    unittest.main(verbosity=2)
