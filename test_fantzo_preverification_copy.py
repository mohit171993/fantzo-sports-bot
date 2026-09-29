"""Keep the Fantzo verification path neutral and gated."""

import asyncio
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bot as core
import bot_restore_test as launcher
import fantzo_business as business
import fantzo_live_tv_mobile_gate as gate
import fantzo_reminders as reminders


FORBIDDEN = ("18+", "play responsibly", "betting", "gambling", "casino", "odds", "wager")


def assert_neutral(test, text):
    value = text.lower()
    for term in FORBIDDEN:
        test.assertNotIn(term, value)


class FantzoPreverificationCopyTests(unittest.TestCase):
    def test_public_description_and_business_verification_are_neutral(self):
        for text in (
            launcher.PUBLIC_SHORT_DESCRIPTION,
            launcher.PUBLIC_DESCRIPTION,
            business.VERIFY_REPLY,
            core.promo_footer(),
        ):
            assert_neutral(self, text)

    def test_unverified_business_button_only_opens_verification(self):
        buttons = [button for row in business._welcome_buttons().inline_keyboard for button in row]
        self.assertEqual(len(buttons), 1)
        self.assertEqual(buttons[0].text, "📱 VERIFY MOBILE")
        self.assertEqual(
            buttons[0].url,
            "https://t.me/fantzoofficialbot?start=verify_business_dm",
        )
        self.assertEqual(
            len([button for row in business._funnel_buttons("verified").inline_keyboard for button in row]),
            3,
        )

    def test_direct_prompt_and_unverified_reminder_only_offer_contact(self):
        messages = []

        async def reply_text(text, **kwargs):
            messages.append((text, kwargs))

        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=123),
            callback_query=None,
            effective_message=SimpleNamespace(reply_text=reply_text),
        )
        context = SimpleNamespace(user_data={})
        with (
            patch.object(gate, "track_verification_event"),
            patch.object(gate.lead_funnel, "on_verification_prompt"),
            patch.object(gate.lead_funnel, "campaign_for_user", return_value="direct"),
        ):
            asyncio.run(gate._prompt_mobile(update, context, "bot_start"))
        self.assertEqual(len(messages), 1)
        text, kwargs = messages[0]
        assert_neutral(self, text)
        keyboard = kwargs["reply_markup"].keyboard
        self.assertEqual(len(keyboard), 1)
        self.assertEqual(len(keyboard[0]), 1)
        self.assertTrue(keyboard[0][0].request_contact)

        for source in ("bot", "business_dm"):
            reminder_text, reminder_markup = reminders._verification_copy(1, source)
            assert_neutral(self, reminder_text)
            if source == "bot":
                self.assertTrue(reminder_markup.keyboard[0][0].request_contact)
            else:
                buttons = [b for row in reminder_markup.inline_keyboard for b in row]
                self.assertEqual(len(buttons), 1)
                self.assertIn("verify_business_dm", buttons[0].url)

    def test_broadcast_only_reaches_verified_subscribers(self):
        sent = []
        replies = []

        async def send_message(**kwargs):
            sent.append(kwargs)

        async def reply_text(text, **kwargs):
            replies.append(text)

        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=core.ADMIN_USER_ID),
            effective_message=SimpleNamespace(reply_text=reply_text),
        )
        context = SimpleNamespace(
            args=["Product", "update"],
            bot=SimpleNamespace(send_message=send_message),
        )
        original_db = core.db

        @contextmanager
        def closing_db():
            conn = original_db()
            try:
                with conn:
                    yield conn
            finally:
                conn.close()

        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(core, "DB_PATH", str(Path(directory) / "fantzo.db")),
                patch.object(core, "db", closing_db),
            ):
                core.init_db()
                gate.ensure_tables()
                with core.db() as conn:
                    conn.executemany(
                        "INSERT INTO users(user_id, subscribed) VALUES(?, 1)",
                        [(101,), (102,), (103,)],
                    )
                    conn.executemany(
                        """
                        INSERT INTO live_tv_mobile_users(
                            user_id, mobile_e164, mobile_national, capture_method,
                            source, created_at, updated_at
                        ) VALUES(?, '+10000000000', '10000000000', ?, 'test', 'now', 'now')
                        """,
                        [(101, "telegram_contact"), (102, "manual")],
                    )
                asyncio.run(core.broadcast(update, context))

        self.assertEqual([message["chat_id"] for message in sent], [101])
        self.assertEqual(len(replies), 1)
        self.assertIn("Sent: 1", replies[0])


if __name__ == "__main__":
    unittest.main()
