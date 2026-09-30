import asyncio
import contextlib
import importlib.util
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stub_creative_dependencies(db_path):
    telegram = types.ModuleType("telegram")
    for name in ("InlineKeyboardButton", "InlineKeyboardMarkup", "WebAppInfo"):
        setattr(telegram, name, type(name, (), {}))

    class InputFile:
        def __init__(self, file, filename=None):
            self.file = file
            self.filename = filename

    telegram.InputFile = InputFile
    ext = types.ModuleType("telegram.ext")
    for name in ("CommandHandler", "MessageHandler"):
        setattr(ext, name, type(name, (), {}))
    ext.filters = types.SimpleNamespace()
    error = types.ModuleType("telegram.error")
    error.BadRequest = type("BadRequest", (Exception,), {})
    error.Forbidden = type("Forbidden", (Exception,), {})
    core = types.ModuleType("bot")

    @contextlib.contextmanager
    def db():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    core.db = db
    core.now_iso = lambda: "2026-09-29T00:00:00+00:00"
    core.ADMIN_USER_ID = 1
    phone_verify = types.ModuleType("ibetin_phone_verify")
    sys.modules.update({
        "telegram": telegram,
        "telegram.ext": ext,
        "telegram.error": error,
        "bot": core,
        "ibetin_phone_verify": phone_verify,
    })


class DuraCreativeGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = str(Path(self.tmp.name) / "dura.db")
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE creative_assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id TEXT NOT NULL, file_unique_id TEXT NOT NULL UNIQUE,
                    media_type TEXT NOT NULL, width INTEGER, height INTEGER,
                    filename TEXT DEFAULT '', pool TEXT NOT NULL,
                    created_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1
                )
            """)
            conn.execute("""
                INSERT INTO creative_assets(file_id,file_unique_id,media_type,
                    filename,pool,created_at,active)
                VALUES ('legacy','legacy-unique','photo','unknown.png','reminder','now',1)
            """)
            conn.commit()
        finally:
            conn.close()
        stub_creative_dependencies(self.db_path)
        self.creatives = load_module("dura_creatives_under_test", ROOT / "ibetin_creatives.py")

    def test_existing_rows_preserved_but_not_selected_until_reviewed(self):
        module = self.creatives
        module.ensure_tables()
        with module.core.db() as conn:
            row = conn.execute("SELECT active,brand FROM creative_assets WHERE id=1").fetchone()
            self.assertEqual((row["active"], row["brand"]), (1, ""))
        fallback = module.pick_creative("reminder")
        self.assertEqual(fallback["media_type"], "bundled_photo")
        self.assertIn("dura-reminder-banner.jpg", fallback["file_id"])
        self.assertEqual(module.counts()["reminder"], 0)
        with module.core.db() as conn:
            conn.execute("UPDATE creative_assets SET brand='dura' WHERE id=1")
        self.assertEqual(module.pick_creative("reminder")["id"], 1)
        self.assertEqual(module.counts()["reminder"], 1)

    def test_startup_repair_preserves_unreviewed_legacy_asset(self):
        repair = load_module("dura_repair_under_test", ROOT / "dura_creative_repair.py")
        repair.DB_PATH = self.db_path
        repair.BOT_TOKEN = ""
        repair.main()
        with self.creatives.core.db() as conn:
            row = conn.execute(
                "SELECT pool,active,brand FROM creative_assets WHERE id=1"
            ).fetchone()
            self.assertEqual((row["pool"], row["active"], row["brand"]),
                             ("reminder", 1, ""))

    def test_new_upload_waits_for_review_and_blocks_other_brand_hints(self):
        module = self.creatives
        self.assertIsNotNone(module.OTHER_BRAND.search("fantzo_banner.png"))
        self.assertIsNotNone(module.OTHER_BRAND.search("IBETIN_live.jpg"))
        creative_id = module._save("file", "unique", "photo", "channel", filename="dura.png")
        with module.core.db() as conn:
            row = conn.execute("SELECT active,brand FROM creative_assets WHERE id=?", (creative_id,)).fetchone()
            self.assertEqual((row["active"], row["brand"]), (0, ""))
        self.assertEqual(module.pick_creative("channel")["media_type"], "bundled_photo")

    def test_photo_normalization_keeps_original_unique_identity(self):
        module = self.creatives
        module.ensure_tables()
        with module.core.db() as conn:
            conn.execute("""
                INSERT INTO creative_assets(file_id,file_unique_id,media_type,
                    filename,pool,created_at,active,brand)
                VALUES ('already-photo','photo-unique','photo','other.png','channel','now',1,'dura')
            """)
            conn.execute("""
                INSERT INTO creative_assets(file_id,file_unique_id,media_type,
                    filename,pool,created_at,active,brand)
                VALUES ('doc-file','doc-unique','document','document.png','channel','now',1,'dura')
            """)
            creative = conn.execute("SELECT * FROM creative_assets WHERE file_unique_id='doc-unique'").fetchone()

        class TelegramFile:
            async def download_to_memory(self, out):
                out.write(b"image")

        class Bot:
            async def get_file(self, file_id):
                return TelegramFile()

            async def send_photo(self, photo, **kwargs):
                return types.SimpleNamespace(photo=[types.SimpleNamespace(
                    file_id="normalized-photo", file_unique_id="photo-unique", width=100, height=100
                )])

        asyncio.run(module._send_creative_as_photo(Bot(), creative, {"chat_id": 1}))
        with module.core.db() as conn:
            row = conn.execute("SELECT file_id,file_unique_id,media_type FROM creative_assets WHERE id=?", (creative["id"],)).fetchone()
            self.assertEqual((row["file_id"], row["file_unique_id"], row["media_type"]),
                             ("normalized-photo", "doc-unique", "photo"))


if __name__ == "__main__":
    unittest.main()
