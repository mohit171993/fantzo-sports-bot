"""Brand isolation checks for the IBETIN creative library."""

import asyncio
import os
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import bot as core
import ibetin_creatives as creatives


class _Message:
    def __init__(self, caption=""):
        self.caption = caption
        self.photo = []
        self.document = None
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)


class CreativeBrandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_path = core.DB_PATH
        self.original_db = core.db
        self.original_env = os.environ.get("DB_PATH")
        self.original_admin = core.ADMIN_USER_ID
        core.DB_PATH = str(Path(self.temp.name) / "ibetin.db")
        os.environ["DB_PATH"] = core.DB_PATH
        core.ADMIN_USER_ID = 123

        @contextmanager
        def closed_db():
            conn = sqlite3.connect(core.DB_PATH)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

        core.db = closed_db

    def tearDown(self):
        core.DB_PATH = self.original_path
        core.db = self.original_db
        core.ADMIN_USER_ID = self.original_admin
        if self.original_env is None:
            os.environ.pop("DB_PATH", None)
        else:
            os.environ["DB_PATH"] = self.original_env
        self.temp.cleanup()

    def _legacy_row(self):
        with core.db() as conn:
            conn.execute(
                """
                CREATE TABLE creative_assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id TEXT NOT NULL,
                    file_unique_id TEXT NOT NULL UNIQUE,
                    media_type TEXT NOT NULL,
                    width INTEGER,
                    height INTEGER,
                    filename TEXT DEFAULT '',
                    pool TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            conn.execute(
                """
                INSERT INTO creative_assets
                (file_id, file_unique_id, media_type, filename, pool, created_at, active)
                VALUES ('old-photo', 'old-unique', 'photo', '', 'reminder', '2026-09-18', 1)
                """
            )

    def test_legacy_assets_are_quarantined_until_approved(self):
        self._legacy_row()
        creatives.ensure_tables()
        with core.db() as conn:
            row = conn.execute(
                "SELECT brand, active FROM creative_assets WHERE id = 1"
            ).fetchone()
        self.assertEqual((row["brand"], row["active"]), ("unverified", 0))
        self.assertIsNone(creatives.pick_creative("reminder", 1))

        message = _Message()
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=123), effective_message=message
        )
        context = SimpleNamespace(args=["1", "IBETIN"])
        asyncio.run(creatives.approvecreative_command(update, context))
        self.assertEqual(creatives.pick_creative("reminder", 1)["id"], 1)

    def test_other_brand_upload_is_rejected(self):
        message = _Message(caption="#reminder Fantzo sports banner")
        message.photo = [
            SimpleNamespace(file_id="photo-a", file_unique_id="unique-a", width=800, height=800)
        ]
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=123), effective_message=message
        )
        context = SimpleNamespace(user_data={"creative_bulk_mode": True})
        asyncio.run(creatives.creative_upload(update, context))
        self.assertIn("cannot enter", message.replies[0])
        self.assertEqual(creatives.counts()["reminder"], 0)

    def test_document_photo_normalization_keeps_original_unique_id(self):
        creatives.ensure_tables()
        with core.db() as conn:
            conn.execute(
                """
                INSERT INTO creative_assets
                (file_id, file_unique_id, media_type, filename, pool, created_at, active, brand)
                VALUES ('doc-file', 'doc-unique', 'document', 'ibetin.jpg', 'reminder',
                        '2026-09-18', 1, 'ibetin')
                """
            )
            conn.execute(
                """
                INSERT INTO creative_assets
                (file_id, file_unique_id, media_type, filename, pool, created_at, active, brand)
                VALUES ('other-photo', 'normalized-unique', 'photo', 'other.jpg', 'channel',
                        '2026-09-18', 1, 'ibetin')
                """
            )
            row = conn.execute("SELECT * FROM creative_assets WHERE id = 1").fetchone()

        class TelegramFile:
            async def download_to_memory(self, out):
                out.write(b"image bytes")

        class TelegramBot:
            async def get_file(self, file_id):
                return TelegramFile()

            async def send_photo(self, **kwargs):
                return SimpleNamespace(
                    photo=[
                        SimpleNamespace(
                            file_id="normalized-file",
                            file_unique_id="normalized-unique",
                            width=800,
                            height=800,
                        )
                    ]
                )

        asyncio.run(creatives._send_creative_as_photo(TelegramBot(), row, {"chat_id": 123}))
        with core.db() as conn:
            normalized = conn.execute(
                "SELECT file_id, file_unique_id, media_type FROM creative_assets WHERE id = 1"
            ).fetchone()
        self.assertEqual(
            (normalized["file_id"], normalized["file_unique_id"], normalized["media_type"]),
            ("normalized-file", "doc-unique", "photo"),
        )


if __name__ == "__main__":
    unittest.main()
