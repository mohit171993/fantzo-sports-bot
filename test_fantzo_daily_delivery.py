"""Focused Fantzo daily fallback and exact-account reverify checks."""

import asyncio
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import mock

import bot as core
import fantzo_account_reverify as reverify
import fantzo_banner_queue as banners
import fantzo_reminders as reminders
from telegram.error import BadRequest, RetryAfter


class FakeBot:
    def __init__(self):
        self.photos = []

    async def send_photo(self, **kwargs):
        photo = kwargs["photo"]
        if hasattr(photo, "read"):
            assert photo.read(3) == b"\xff\xd8\xff"
        self.photos.append(kwargs)
        return SimpleNamespace(message_id=len(self.photos))


class FantzoDailyDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.original_db = core.db
        core.db = lambda: self.conn
        core.init_db()
        banners.ensure_tables()
        # This fixture has no persistent mode table; select Full explicitly so
        # it exercises the existing banner delivery path instead of fail-closed mode.
        self.full_mode = mock.patch("fantzo_mode.is_livetv", return_value=False)
        self.mode_is_livetv = self.full_mode.start()

    def tearDown(self):
        self.full_mode.stop()
        core.db = self.original_db
        self.conn.close()

    def test_empty_queue_posts_branded_fallback_once(self):
        bot = FakeBot()
        self.assertTrue(asyncio.run(banners._post_daily(bot)))
        self.assertFalse(asyncio.run(banners._post_daily(bot)))
        self.assertEqual(len(bot.photos), 1)
        self.assertEqual(bot.photos[0]["chat_id"], banners.CHANNEL_ID)
        self.assertIn("FANTZO", bot.photos[0]["caption"])
        self.assertEqual(banners.delivery_status()["last_post_kind"], "daily_fallback")

    def test_approved_banner_takes_priority(self):
        self.conn.execute(
            "INSERT INTO live_tv_banners(file_id,status,brand,media_type,created_at) "
            "VALUES('approved-file','queued','fantzo','photo','2026-09-29')"
        )
        bot = FakeBot()
        self.assertTrue(asyncio.run(banners._post_daily(bot)))
        self.assertEqual(bot.photos[0]["photo"], "approved-file")
        self.assertEqual(banners.delivery_status()["last_post_kind"], "approved_banner")
        self.assertEqual(banners.queue_count(), 0)

    def test_send_failure_keeps_day_unposted_and_backs_off(self):
        class FailingBot:
            async def send_photo(self, **kwargs):
                raise RuntimeError("Telegram unavailable")

        with self.assertRaises(RuntimeError):
            asyncio.run(banners._post_daily(FailingBot()))
        self.assertFalse(banners.delivery_status()["last_post_date"])
        self.assertEqual(banners.delivery_status()["last_failure_kind"], "daily_fallback")
        self.assertTrue(banners._failure_backoff_active())
        banners._set_setting(
            "last_failure_at",
            (datetime.now(timezone.utc) - timedelta(minutes=16)).isoformat(),
        )
        self.assertFalse(banners._failure_backoff_active())

    def test_mode_flip_during_media_download_keeps_banner_queued(self):
        self.conn.execute(
            "INSERT INTO live_tv_banners(file_id,status,brand,media_type,created_at) "
            "VALUES('approved-document','queued','fantzo','document','2026-09-29')"
        )

        class DownloadingFile:
            async def download_as_bytearray(inner_self):
                self.mode_is_livetv.return_value = True
                return bytearray(b"image bytes")

        class DownloadingBot(FakeBot):
            async def get_file(inner_self, file_id):
                self.assertEqual(file_id, "approved-document")
                return DownloadingFile()

        bot = DownloadingBot()
        self.assertFalse(asyncio.run(banners._post_next(bot)))
        self.assertEqual(bot.photos, [])
        self.assertEqual(banners.queue_count(), 1)
        self.assertEqual(banners.delivery_status()["last_failure_kind"], "")
        self.assertEqual(banners.delivery_status()["last_post_date"], "")
        self.mode_is_livetv.return_value = False

        class ReadyFile:
            async def download_as_bytearray(inner_self):
                return bytearray(b"image bytes")

        class ReadyBot(FakeBot):
            async def get_file(inner_self, file_id):
                return ReadyFile()

        self.assertTrue(asyncio.run(banners._post_next(ReadyBot())))
        self.assertEqual(banners.queue_count(), 0)

    def test_mode_flip_during_invalid_caption_retry_does_not_post_daily(self):
        self.conn.execute(
            "INSERT INTO live_tv_banners(file_id,status,brand,media_type,created_at) "
            "VALUES('approved-photo','queued','fantzo','photo','2026-09-29')"
        )

        class InvalidCaptionBot(FakeBot):
            def __init__(inner_self):
                super().__init__()
                inner_self.calls = 0

            async def send_photo(inner_self, **kwargs):
                inner_self.calls += 1
                self.mode_is_livetv.return_value = True
                raise BadRequest("Can't parse entities")

        bot = InvalidCaptionBot()
        self.assertFalse(asyncio.run(banners._post_daily(bot)))
        self.assertEqual(bot.calls, 1)
        self.assertEqual(bot.photos, [])
        self.assertEqual(banners.queue_count(), 1)
        self.assertEqual(banners.delivery_status()["last_failure_kind"], "")
        self.assertEqual(banners.delivery_status()["last_post_date"], "")

    def test_mode_flip_during_reminder_retry_does_not_mark_campaign(self):
        reminders.ensure_tables()
        then = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        self.conn.execute(
            "INSERT INTO reminder_users(source,user_id,business_connection_id,interest,"
            "last_activity,updated_at) VALUES(?,?,?,?,?,?)",
            ("bot", 101, "", "cricket", then, then),
        )

        class RetryingBot:
            def __init__(inner_self):
                inner_self.calls = 0

            async def send_message(inner_self, **kwargs):
                inner_self.calls += 1
                raise RetryAfter(1)

        async def flip_during_retry(_delay):
            self.mode_is_livetv.return_value = True

        bot = RetryingBot()
        application = SimpleNamespace(bot=bot)
        with mock.patch.object(reminders, "_is_mobile_verified", return_value=True), \
                mock.patch.object(reminders, "_is_quiet_hours", return_value=False), \
                mock.patch.object(reminders.asyncio, "sleep", side_effect=flip_during_retry):
            asyncio.run(reminders.run_due_reminders(application))
        self.assertEqual(bot.calls, 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM reminder_sends").fetchone()[0], 0)
        self.assertEqual(
            self.conn.execute("SELECT reminder_stage FROM reminder_users WHERE user_id=101").fetchone()[0],
            0,
        )
        self.mode_is_livetv.return_value = False

        class DeliveringBot:
            def __init__(inner_self):
                inner_self.calls = 0

            async def send_message(inner_self, **kwargs):
                inner_self.calls += 1

        resumed_bot = DeliveringBot()
        with mock.patch.object(reminders, "_is_mobile_verified", return_value=True), \
                mock.patch.object(reminders, "_is_quiet_hours", return_value=False), \
                mock.patch.object(reminders.asyncio, "sleep", return_value=None):
            asyncio.run(reminders.run_due_reminders(SimpleNamespace(bot=resumed_bot)))
        self.assertEqual(resumed_bot.calls, 1)
        self.assertEqual(self.conn.execute("SELECT status FROM reminder_sends").fetchone()[0], "sent")


class FantzoAccountReverifyTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.original_db = core.db
        core.db = lambda: self.conn
        core.init_db()
        self.conn.executescript("""
            CREATE TABLE live_tv_mobile_users (
                user_id INTEGER PRIMARY KEY, capture_method TEXT, updated_at TEXT
            );
            CREATE TABLE lead_user_map (user_id INTEGER PRIMARY KEY, mobile_e164 TEXT);
            CREATE TABLE mobile_verification_events (
                id INTEGER PRIMARY KEY, user_id INTEGER, source TEXT, event TEXT, created_at TEXT
            );
        """)
        for user_id, username in ((1456774567, "Mohit_97saxena"), (42, "another_user")):
            self.conn.execute(
                "INSERT INTO users(user_id,username) VALUES(?,?)", (user_id, username)
            )
            self.conn.execute(
                "INSERT INTO live_tv_mobile_users(user_id,capture_method) VALUES(?,'telegram_contact')",
                (user_id,),
            )
            self.conn.execute(
                "INSERT INTO lead_user_map(user_id,mobile_e164) VALUES(?,'+123456789')",
                (user_id,),
            )

    def tearDown(self):
        core.db = self.original_db
        self.conn.close()

    def test_exact_account_only_and_idempotent_after_reverification(self):
        self.assertEqual(reverify.apply_once(), "applied")
        self.assertEqual(
            self.conn.execute(
                "SELECT capture_method FROM live_tv_mobile_users WHERE user_id=1456774567"
            ).fetchone()[0],
            "reverify_required",
        )
        self.assertIsNone(self.conn.execute(
            "SELECT 1 FROM lead_user_map WHERE user_id=1456774567"
        ).fetchone())
        self.assertEqual(
            self.conn.execute(
                "SELECT capture_method FROM live_tv_mobile_users WHERE user_id=42"
            ).fetchone()[0],
            "telegram_contact",
        )
        self.conn.execute(
            "UPDATE live_tv_mobile_users SET capture_method='telegram_contact' "
            "WHERE user_id=1456774567"
        )
        self.assertEqual(reverify.apply_once(), "already_applied")
        self.assertEqual(
            self.conn.execute(
                "SELECT capture_method FROM live_tv_mobile_users WHERE user_id=1456774567"
            ).fetchone()[0],
            "telegram_contact",
        )

    def test_username_reassigned_to_other_id_never_revokes(self):
        self.conn.execute("UPDATE users SET username='renamed' WHERE user_id=1456774567")
        self.conn.execute("UPDATE users SET username='Mohit_97saxena' WHERE user_id=42")
        self.assertEqual(reverify.apply_once(), "identity_mismatch")
        self.assertEqual(
            self.conn.execute(
                "SELECT capture_method FROM live_tv_mobile_users WHERE user_id=42"
            ).fetchone()[0],
            "telegram_contact",
        )


if __name__ == "__main__":
    unittest.main()
