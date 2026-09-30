"""The sports reminder leads with the reminder image; text and buttons stay the same."""

import asyncio
import unittest
from unittest.mock import patch

import fantzo_reminders as reminders


class FakeBot:
    def __init__(self):
        self.calls = []

    async def send_photo(self, **kwargs):
        kwargs["photo"] = getattr(kwargs["photo"], "name", kwargs["photo"])
        self.calls.append(("photo", kwargs))

    async def send_message(self, **kwargs):
        self.calls.append(("message", kwargs))


def _row(source="bot", connection=""):
    return {"source": source, "user_id": 555, "interest": "cricket", "business_connection_id": connection}


class FantzoReminderImageTests(unittest.TestCase):
    def test_image_file_exists(self):
        self.assertTrue(reminders.REMINDER_IMAGE.is_file())

    def test_verified_reminder_sends_photo_with_same_text_and_buttons(self):
        for source, connection in (("bot", ""), ("business_dm", "bc-1")):
            bot = FakeBot()
            text, markup = reminders._copy_for("cricket", 1, source)
            with patch.object(reminders, "_is_mobile_verified", return_value=True):
                self.assertTrue(asyncio.run(reminders._send_with_retry(bot, _row(source, connection), 1)))
            self.assertEqual(len(bot.calls), 1)
            kind, kwargs = bot.calls[0]
            self.assertEqual(kind, "photo")
            self.assertEqual(kwargs["caption"], text)
            self.assertEqual(kwargs["parse_mode"], "HTML")
            self.assertEqual(kwargs["reply_markup"], markup)
            self.assertTrue(str(kwargs["photo"]).endswith("fantzo_reminder.jpg"))
            if connection:
                self.assertEqual(kwargs["business_connection_id"], connection)

    def test_long_text_sends_photo_then_unchanged_message(self):
        bot = FakeBot()
        long_text = "x" * (reminders.CAPTION_LIMIT + 1)
        text, markup = reminders._copy_for("cricket", 1, "bot")
        with (
            patch.object(reminders, "_is_mobile_verified", return_value=True),
            patch.object(reminders, "_copy_for", return_value=(long_text, markup)),
        ):
            asyncio.run(reminders._send_with_retry(bot, _row(), 1))
        self.assertEqual([c[0] for c in bot.calls], ["photo", "message"])
        self.assertNotIn("caption", bot.calls[0][1])
        self.assertEqual(bot.calls[1][1]["text"], long_text)
        self.assertEqual(bot.calls[1][1]["reply_markup"], markup)

    def test_unverified_reminder_stays_text_only(self):
        bot = FakeBot()
        with patch.object(reminders, "_is_mobile_verified", return_value=False):
            asyncio.run(reminders._send_with_retry(bot, _row(), 1))
        self.assertEqual([c[0] for c in bot.calls], ["message"])


if __name__ == "__main__":
    unittest.main()
