import asyncio
import sqlite3
import tempfile
import types
import unittest
from pathlib import Path

from dura_one_time_hi import MARKER, TARGET_USER_ID, send_once


class OneTimeHiTests(unittest.TestCase):
    def test_one_attempt_claimed_before_send(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bot.db"
            calls = []

            async def send_message(**kwargs):
                calls.append(kwargs)
                return types.SimpleNamespace(message_id=99)

            bot = types.SimpleNamespace(send_message=send_message, token="secret")
            application = types.SimpleNamespace(bot=bot)
            asyncio.run(send_once(application, lambda: sqlite3.connect(path)))
            asyncio.run(send_once(application, lambda: sqlite3.connect(path)))
            self.assertEqual(calls, [{"chat_id": TARGET_USER_ID, "text": "hi"}])
            conn = sqlite3.connect(path)
            try:
                self.assertEqual(
                    conn.execute("SELECT value FROM settings WHERE key=?", (MARKER,))
                    .fetchone()[0],
                    "attempted",
                )
            finally:
                conn.close()

    def test_failed_telegram_attempt_is_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bot.db"
            calls = []

            class Forbidden(Exception):
                message = "blocked"

            async def send_message(**kwargs):
                calls.append(kwargs)
                raise Forbidden()

            bot = types.SimpleNamespace(send_message=send_message, token="secret")
            application = types.SimpleNamespace(bot=bot)
            asyncio.run(send_once(application, lambda: sqlite3.connect(path)))
            asyncio.run(send_once(application, lambda: sqlite3.connect(path)))
            self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
