"""Focused checks for the verified IBETIN first card and match deep links."""

import os
import gc
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ibetin_activation
import ibetin_leads
import bot_tracked


class ActivationTests(unittest.TestCase):
    def test_campaign_match_map_only_accepts_provider_keys(self):
        mapping = '{"matchday":"international.match:123","bad":"https://evil.example/m"}'
        self.assertEqual(
            ibetin_activation.campaign_match_key("matchday", mapping),
            "international.match:123",
        )
        self.assertEqual(ibetin_activation.campaign_match_key("bad", mapping), "")
        self.assertEqual(ibetin_activation.campaign_match_key("other", mapping), "")
        self.assertEqual(ibetin_activation.campaign_match_key("matchday", "not JSON"), "")

    def test_match_url_encodes_key_and_rejects_urls(self):
        base = "https://ibet.in/liveline?access=signed"
        self.assertEqual(
            ibetin_activation.match_url(base, "international.match:123"),
            base + "&match=international.match%3A123",
        )
        self.assertEqual(
            ibetin_activation.match_url(base, "https://evil.example/m"), base
        )

    def test_verified_first_card_shows_live_line_before_join(self):
        with patch.object(
            bot_tracked.phone_verify,
            "live_line_url",
            return_value="https://ibetin.example/liveline?access=signed",
        ):
            buttons = [
                row[0]
                for row in bot_tracked.conversion_keyboard(123).inline_keyboard
            ]
        self.assertIn("LIVE LINE", buttons[0].text)
        self.assertIn("JOIN IBETIN", buttons[1].text)
        self.assertEqual(len(buttons), 3)

    def test_approved_match_campaign_is_first_action(self):
        mapping = '{"matchday":"international.match:123"}'
        with patch.dict(os.environ, {"IBETIN_MATCH_CAMPAIGNS": mapping}):
            with patch.object(
                bot_tracked.phone_verify,
                "live_line_url",
                return_value="https://ibetin.example/liveline?access=signed",
            ):
                buttons = [
                    row[0]
                    for row in bot_tracked.conversion_keyboard(123, "matchday").inline_keyboard
                ]
        self.assertIn("OPEN MATCH", buttons[0].text)
        self.assertIn("match=international.match%3A123", buttons[0].web_app.url)
        self.assertIn("JOIN IBETIN", buttons[1].text)

    def test_latest_destination_survives_restart_without_rewriting_attribution(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "ibetin.db")
            with patch.dict(os.environ, {"DB_PATH": db_path}):
                ibetin_leads.record_start(123, campaign="first_campaign")
                ibetin_leads.record_start(123, campaign="matchday")
                lead = ibetin_leads.get_lead(123)
                self.assertEqual(lead["campaign"], "first_campaign")
                self.assertEqual(lead["last_requested_campaign"], "matchday")

                ibetin_leads.record_start(123, campaign="direct")
                self.assertEqual(
                    ibetin_leads.get_lead(123)["last_requested_campaign"],
                    "direct",
                )
            # sqlite3's connection context commits but does not close on exit.
            # Let the short-lived test connections be collected before Windows
            # removes the temporary database file.
            gc.collect()


if __name__ == "__main__":
    unittest.main()
