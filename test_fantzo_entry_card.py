"""The advertised feature must survive verification without changing attribution."""

import asyncio
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import bot as core
import bot_restore_test as launcher
import bot_tracked as tracked
import fantzo_growth as growth
import fantzo_lead_funnel as funnel
import fantzo_live_tv_mobile_gate as gate


class FantzoEntryCardTests(unittest.TestCase):
    def test_latest_feature_link_routes_card_but_first_campaign_is_preserved(self):
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
                funnel.ensure_tables()
                funnel.record_start(101, "ad_cricket")
                funnel.record_start(101, "ad_football")
                funnel.record_start(101, "")

                self.assertEqual(funnel.campaign_for_user(101), "ad_cricket")
                self.assertEqual(funnel.last_start_arg_for_user(101), "ad_football")
                card = funnel.post_verify_keyboard(101)
                self.assertEqual(card.inline_keyboard[0][0].callback_data, "football")
                buttons = [row[0] for row in card.inline_keyboard]
                self.assertEqual(buttons[2].text, "🚀 JOIN FANTZO")
                self.assertIn("verified_join_fantzo", buttons[2].web_app.url)
                self.assertEqual(buttons[3].text, "📺 WATCH LIVE TV")
                self.assertEqual(buttons[3].callback_data, "live_tv_status")
                self.assertEqual(buttons[4].text, "📢 JOIN CHANNEL")
                self.assertEqual(buttons[4].url, "https://t.me/fantzoupdates")
                self.assertIn("football", funnel.post_verify_text(101).lower())

    def test_tv_entry_respects_public_mode_and_unknown_links_fall_back(self):
        with patch.object(tracked, "LIVE_TV_MODE", "admin"):
            self.assertEqual(funnel._campaign_primary("ad_livetv")[1], "live_now")
        with (
            patch.object(tracked, "LIVE_TV_MODE", "public"),
            patch.object(tracked, "sky_admin_url", return_value="https://example.com/tv"),
        ):
            self.assertEqual(funnel._campaign_primary("ad_livetv")[1], "live_tv_status")
        self.assertFalse(funnel.has_feature_intent("stopreminders"))
        self.assertFalse(funnel.has_feature_intent("ad_unknown"))

    def test_verified_campaign_start_preserves_home_then_adds_focused_card(self):
        self.assertIsNotNone(launcher)  # Import installs production handler wrappers.
        message = SimpleNamespace(text="/start ad_cricket", reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=101),
            effective_message=message,
            callback_query=None,
        )
        context = SimpleNamespace(user_data={}, args=["ad_cricket"])
        with (
            patch.object(gate, "is_registered", return_value=True),
            patch.object(gate, "configure_chat_ui", new_callable=AsyncMock),
            patch.object(funnel, "record_start"),
            patch.object(growth, "track"),
            patch.object(tracked.app, "show_home", new_callable=AsyncMock) as home,
            patch.object(funnel, "send_post_verify", new_callable=AsyncMock) as focused_card,
        ):
            asyncio.run(tracked.app.start(update, context))
        home.assert_awaited_once_with(update, context)
        message.reply_text.assert_awaited_once()
        focused_card.assert_awaited_once_with(message, 101)

    def test_verified_unknown_deep_link_keeps_normal_start_without_extra_card(self):
        message = SimpleNamespace(text="/start partner42", reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=101),
            effective_message=message,
            callback_query=None,
        )
        context = SimpleNamespace(user_data={}, args=["partner42"])
        with (
            patch.object(gate, "is_registered", return_value=True),
            patch.object(gate, "configure_chat_ui", new_callable=AsyncMock),
            patch.object(funnel, "record_start"),
            patch.object(growth, "track"),
            patch.object(tracked.app, "show_home", new_callable=AsyncMock) as home,
            patch.object(funnel, "send_post_verify", new_callable=AsyncMock) as focused_card,
        ):
            asyncio.run(tracked.app.start(update, context))
        home.assert_awaited_once_with(update, context)
        message.reply_text.assert_awaited_once()
        focused_card.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
