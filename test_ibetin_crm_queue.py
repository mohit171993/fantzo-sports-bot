"""Synthetic-data tests only: no production database, bot imports or messages."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from ibetin_crm_audit import snapshot
from ibetin_crm_queue_start import queue_sql


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
