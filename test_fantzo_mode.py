"""Fantzo admin /mode switch: FULL default, Live Line for unverified users only."""

import ast
import asyncio
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from telegram.ext import ApplicationHandlerStop

from mode_control import FULL, LIVE_LINE, ModeStore, is_persistent_mode_path, parse_admin_mode_request

_TEMP = tempfile.TemporaryDirectory()
os.environ.setdefault("TRACKING_BASE_URL", "https://fantzo.example")

import fantzo_analytics  # noqa: E402

fantzo_analytics.TRACKING_BASE_URL = "https://fantzo.example"

import bot_mode_runtime as runtime  # noqa: E402

ADMIN = 8992664481


def _install_once():
    if not runtime._installed:
        with patch.dict(os.environ, {"DB_PATH": os.path.join(_TEMP.name, "fantzo.db")}):
            runtime.install("fantzo")


class Message:
    def __init__(self, text="", contact=None, from_user=None, business_connection_id=""):
        self.text = text
        self.contact = contact
        self.from_user = from_user
        self.business_connection_id = business_connection_id
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


def _update(user_id, text="", *, business=False, callback=False, contact=None, edited=False):
    user = SimpleNamespace(id=user_id)
    message = Message(text, contact, user, "conn-1" if business else "")
    answered = []

    async def answer(*_args, **_kwargs):
        answered.append(True)

    query = SimpleNamespace(answer=answer, data="sports") if callback else None
    return SimpleNamespace(
        effective_user=user,
        effective_chat=SimpleNamespace(type="private"),
        effective_message=message,
        message=None if (business or callback or edited) else message,
        edited_message=message if edited else None,
        business_message=message if business else None,
        callback_query=query,
        _answered=answered,
    )


def _guard(update):
    try:
        asyncio.run(runtime._guard_update(update, SimpleNamespace(user_data={})))
    except ApplicationHandlerStop:
        return "stopped"
    return "passed"


class FantzoModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _install_once()

    def setUp(self):
        runtime._store.switch(FULL)
        self.addCleanup(runtime._store.switch, FULL)
        self.verified = {123}
        self.gate_patch = patch.object(runtime.gate, "is_registered",
                                       side_effect=lambda uid: int(uid) in self.verified)
        self.gate_patch.start()
        self.addCleanup(self.gate_patch.stop)
        self.admin_patch = patch.object(runtime.core, "ADMIN_USER_ID", ADMIN)
        self.admin_patch.start()
        self.addCleanup(self.admin_patch.stop)

    def test_release_default_is_full_and_switch_persists(self):
        path = os.path.join(_TEMP.name, "fresh.db")
        self.assertEqual(ModeStore(path, "fantzo").state().mode, FULL)
        ModeStore(path, "fantzo").switch(LIVE_LINE)
        self.assertEqual(ModeStore(path, "fantzo").state().mode, LIVE_LINE)

    def test_persistent_path_is_the_fantzo_data_volume(self):
        self.assertTrue(is_persistent_mode_path("/data/fantzo_bot.db"))
        self.assertFalse(is_persistent_mode_path("/app/ibetin_bot_persistent/ibetin_bot.db"))
        self.assertFalse(is_persistent_mode_path("fantzo_bot.db"))

    def test_only_admin_can_use_mode(self):
        self.assertIsNone(parse_admin_mode_request(5, ADMIN, ["liveline"]))
        self.assertEqual(parse_admin_mode_request(ADMIN, ADMIN, []), "status")

    def test_full_mode_passes_everyone(self):
        for update in (_update(999, "/start"), _update(999, "hi"), _update(999, callback=True)):
            self.assertEqual(_guard(update), "passed")
            self.assertEqual(update.effective_message.replies, [])

    def test_liveline_verified_and_admin_keep_full_bot(self):
        runtime._store.switch(LIVE_LINE)
        for update in (_update(123, "/start"), _update(123, "/sports"), _update(123, callback=True),
                       _update(ADMIN, "/reports"), _update(ADMIN, callback=True),
                       _update(ADMIN, "/broadcast hi")):
            self.assertEqual(_guard(update), "passed")
            self.assertEqual(update.effective_message.replies, [])

    def test_liveline_unverified_gets_only_scores_reply(self):
        runtime._store.switch(LIVE_LINE)
        with patch.object(runtime.lead_funnel, "record_start") as record, \
             patch.object(runtime.core, "touch_user"):
            for update in (_update(999, "/start ads1"), _update(999, "hello"),
                           _update(999, "/sports"), _update(999, callback=True)):
                self.assertEqual(_guard(update), "stopped")
                (text, kwargs), = update.effective_message.replies
                self.assertEqual(text, "⚡ FANTZO LIVE LINE\n\n🏏 Live scores, full scorecards and match updates.\n👇 Tap below to open.")
                button = kwargs["reply_markup"].inline_keyboard[0][0]
                self.assertEqual(button.text, "🏏 OPEN FANTZO LIVE LINE")
                self.assertEqual(button.web_app.url, "https://fantzo.example/scores")
                self.assertNotIn("VERIFY", text.upper())
            record.assert_called_once_with(999, "ads1")

    def test_liveline_opt_out_and_contact_reach_existing_handlers(self):
        runtime._store.switch(LIVE_LINE)
        for update in (_update(999, "stop"), _update(999, "/stop"),
                       _update(999, "/start stopreminders"),
                       _update(999, contact=SimpleNamespace(user_id=999))):
            self.assertEqual(_guard(update), "passed")
            self.assertEqual(update.effective_message.replies, [])

    def test_liveline_business_dm_uses_url_button_and_skips_owner(self):
        runtime._store.switch(LIVE_LINE)
        with patch.object(runtime.business, "_owner_user_id", return_value=777):
            update = _update(999, "hi", business=True)
            self.assertEqual(_guard(update), "stopped")
            (text, kwargs), = update.effective_message.replies
            self.assertEqual(text, "⚡ FANTZO LIVE LINE\n\n🏏 Live scores, full scorecards and match updates.\n👇 Tap below to open.")
            self.assertEqual(kwargs["reply_markup"].inline_keyboard[0][0].url,
                             "https://fantzo.example/scores")
            owner = _update(777, "reply from owner", business=True)
            self.assertEqual(_guard(owner), "passed")
            self.assertEqual(owner.effective_message.replies, [])

    def test_liveline_service_updates_pass(self):
        runtime._store.switch(LIVE_LINE)
        update = SimpleNamespace(message=None, edited_message=None, business_message=None,
                                 callback_query=None, effective_user=SimpleNamespace(id=999))
        self.assertEqual(_guard(update), "passed")

    def test_reminders_skip_unverified_only_in_liveline(self):
        row = {"user_id": 999, "last_activity": "2020-01-01T00:00:00+00:00",
               "reminder_stage": 0, "source": "bot"}
        with patch.object(runtime.reminders, "_is_mobile_verified", return_value=False):
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            self.assertEqual(runtime.reminders._due_stage(row, now), 1)
            runtime._store.switch(LIVE_LINE)
            self.assertIsNone(runtime.reminders._due_stage(row, now))
            self.verified.add(999)
            self.assertEqual(runtime.reminders._due_stage(row, now), 1)

    def test_guarded_reminder_bot_refuses_unverified_sends_in_liveline(self):
        sent = []

        class Bot:
            async def send_message(self, **kwargs):
                sent.append(kwargs["chat_id"])

        runtime._store.switch(LIVE_LINE)
        bot = runtime._GuardedPublicBot(Bot(), allow_verified=True)
        asyncio.run(bot.send_message(chat_id=123, text="x"))
        with self.assertRaises(RuntimeError):
            asyncio.run(bot.send_message(chat_id=999, text="x"))
        self.assertEqual(sent, [123])

    def test_channel_daily_post_paused_in_liveline(self):
        runtime._store.switch(LIVE_LINE)
        self.assertFalse(asyncio.run(runtime.banner_queue._post_daily(object())))

    def test_liveline_switch_refused_without_persistent_volume(self):
        replies = []

        async def reply_text(text, **_kwargs):
            replies.append(text)

        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=ADMIN),
            effective_chat=SimpleNamespace(type="private"),
            effective_message=SimpleNamespace(reply_text=reply_text),
        )
        with self.assertRaises(ApplicationHandlerStop):
            asyncio.run(runtime._mode_command(update, SimpleNamespace(args=["liveline"])))
        self.assertIn("persistent storage", replies[0])
        self.assertEqual(runtime._store.state().mode, FULL)
        stranger = SimpleNamespace(
            effective_user=SimpleNamespace(id=5), effective_chat=SimpleNamespace(type="private"),
            effective_message=SimpleNamespace(reply_text=reply_text),
        )
        with self.assertRaises(ApplicationHandlerStop):
            asyncio.run(runtime._mode_command(stranger, SimpleNamespace(args=["liveline"])))
        self.assertEqual(len(replies), 1)

    def test_verified_menu_matches_existing_full_menu(self):
        calls = []

        class Bot:
            async def set_my_commands(self, commands, **kwargs):
                calls.append(("commands", commands, kwargs))

            async def set_chat_menu_button(self, **kwargs):
                calls.append(("menu", kwargs))

        runtime._store.switch(LIVE_LINE)
        self.assertTrue(asyncio.run(runtime._set_verified_chat_ui(Bot(), 123, LIVE_LINE)))
        self.assertIs(calls[0][1], runtime.gate.VERIFIED_COMMANDS)
        self.assertEqual(calls[1][1]["menu_button"].text, "Open Fantzo")
        calls.clear()
        self.assertTrue(asyncio.run(runtime._set_verified_chat_ui(Bot(), 999, LIVE_LINE)))
        self.assertEqual(calls, [])
        self.assertTrue(asyncio.run(runtime._set_unverified_chat_ui(Bot(), 999, LIVE_LINE)))
        self.assertEqual(type(calls[0][1]["menu_button"]).__name__, "MenuButtonDefault")
        self.assertEqual(runtime._default_menu_button(LIVE_LINE).web_app.url,
                         "https://fantzo.example/scores")
        self.assertEqual(type(runtime._default_menu_button(FULL)).__name__, "MenuButtonCommands")

    def test_score_views_project_only_allowlisted_fields(self):
        live = {"id": 1, "homeTeam": {"name": "India", "abbreviation": "IND"},
                "awayTeam": {"name": "Sri Lanka"}, "league": {"name": "Asia Cup"},
                "format": "T20", "odds": {"home": 1.5},
                "state": {"description": "In Play", "teams": {
                    "home": {"score": "151/7", "info": "(18.5/20 ov)"}, "away": {}}}}
        upcoming = {"id": 2, "homeTeam": {"name": "A"}, "awayTeam": {"name": "B"},
                    "state": {"description": "Not started"}}
        done = {"id": 3, "homeTeam": {"name": "C"}, "awayTeam": {"name": "D"},
                "state": {"description": "Finished"}}

        async def matches(_sport, _date):
            return [live, upcoming, done]

        runtime._score_cache.clear()
        with patch.object(runtime.core, "get_sport_matches_for_date", matches):
            rows = runtime._safe_rows("live")
            self.assertEqual([r["id"] for r in rows], ["1"])
            self.assertEqual(rows[0]["state"], "Live")
            self.assertEqual(rows[0]["home_score"], "151/7")
            self.assertEqual(rows[0]["home_info"], "18.5 ov")
            self.assertNotIn("odds", rows[0])
            self.assertEqual([r["id"] for r in runtime._safe_rows("upcoming")], ["2"])
            self.assertEqual([r["id"] for r in runtime._safe_rows("results")], ["3"])
            with self.assertRaises(ValueError):
                runtime._listed_score_match("1;drop", "live")
        runtime._score_cache.clear()

    def test_scores_page_is_black_and_gold(self):
        from scores_only import score_page
        page = score_page([], "Fantzo")
        self.assertIn("Fantzo Live Line", page)
        self.assertIn("#f5d27a", page)
        self.assertIn("#0a0806", page)
        self.assertIn("Cinzel", page)

    def test_entry_point_installs_mode_before_bot_starts(self):
        tree = ast.parse(Path(__file__).with_name("bot_restore_test.py").read_text(encoding="utf-8"))
        main_guard = next(node for node in tree.body if isinstance(node, ast.If)
                          and ast.unparse(node.test) == "__name__ == '__main__'")
        steps = [ast.unparse(node) for node in main_guard.body]
        install = "bot_mode_runtime.install('fantzo')"
        self.assertIn(install, steps)
        self.assertLess(steps.index(install), steps.index("tracked.analytics.start_tracking_server()"))
        self.assertLess(steps.index(install), steps.index("tracked.app.run()"))


if __name__ == "__main__":
    unittest.main()
