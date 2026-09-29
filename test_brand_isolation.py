"""Brand boundaries for Fantzo reports and creative approval."""

import sqlite3
import unittest

import bot as core
import fantzo_analytics as analytics
import fantzo_banner_queue as banners
from fantzo_brand import has_foreign_brand


class FantzoBrandIsolationTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.original_db = core.db
        core.db = lambda: self.conn

    def tearDown(self):
        core.db = self.original_db
        self.conn.close()

    def test_report_ignores_other_brand_tables_and_actions(self):
        self.conn.executescript(
            """
            CREATE TABLE ibetin_leads (campaign TEXT, first_seen_at TEXT);
            INSERT INTO ibetin_leads VALUES ('other-brand', '2026-09-29T00:00:00+00:00');
            CREATE TABLE liveline_verified_users (user_id INTEGER, verified_at TEXT);
            INSERT INTO liveline_verified_users VALUES (7, '2026-09-29T00:00:00+00:00');
            CREATE TABLE clicks (action TEXT, created_at TEXT);
            INSERT INTO clicks VALUES ('join_ibetin', '2026-09-29T00:00:00+00:00');
            INSERT INTO clicks VALUES ('join_dura', '2026-09-29T00:00:00+00:00');
            INSERT INTO clicks VALUES ('join_fantzo', '2026-09-29T00:00:00+00:00');
            """
        )
        report = analytics._report_metrics_payload()
        self.assertEqual(report["leads"], 0)
        self.assertEqual(report["verified"], 0)
        self.assertEqual(report["by_campaign"], {})
        self.assertEqual(report["registration_clicks"], 1)

    def test_new_banner_requires_approval_without_stopping_legacy_queue(self):
        banners.ensure_tables()
        self.conn.execute(
            "INSERT INTO live_tv_banners(file_id,status,created_at) VALUES('legacy-file','queued','2026-09-29')"
        )
        pending_id = banners.add_banner("new-file")
        self.assertEqual(banners.queue_count(), 1)
        self.assertEqual(banners.pending_count(), 1)
        self.assertEqual(banners.next_banner()["file_id"], "legacy-file")
        self.assertTrue(banners.review_banner(pending_id, True))
        self.assertEqual(banners.queue_count(), 2)
        self.assertEqual(banners.pending_count(), 0)
        self.assertEqual(
            self.conn.execute("SELECT brand FROM live_tv_banners WHERE id=?", (pending_id,)).fetchone()[0],
            "fantzo",
        )

    def test_foreign_brand_caption_cannot_be_approved(self):
        self.assertTrue(has_foreign_brand("IBETIN banner"))
        self.assertTrue(has_foreign_brand("betroxy_logo.png"))
        self.assertTrue(has_foreign_brand("Durabet"))
        self.assertFalse(has_foreign_brand("Fantzo Live TV"))
        banner_id = banners.add_banner("wrong-file", "IBETIN banner")
        self.assertFalse(banners.review_banner(banner_id, True))
        self.assertEqual(banners.queue_count(), 0)


if __name__ == "__main__":
    unittest.main()
