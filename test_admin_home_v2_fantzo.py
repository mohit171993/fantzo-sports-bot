"""Synthetic tests for the Fantzo flavour of the grouped admin home."""
import asyncio
import sqlite3
import sys
import tempfile
import types
import unittest
from contextlib import closing, contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler

from test_admin_home_v2 import callbacks, ctx, fake_update, run

ADMINS = {8992664481, 8860632140}
OLD_OPS = ["ops:queue:new", "ops:queue:due", "ops:queue:all", "ops:queue:mobile", "ops:queue:followup",
           "ops:queue:interested", "ops:search", "ops:export", "ops:queue:converted", "ops:adperformance",
           "ops:automation", "ops:guide", "adm:advanced_reports"]
OLD_REPORTS = ["rpt:overview", "rpt:users", "rpt:mobile", "crm:home", "rpt:business", "rpt:reminders",
               "rpt:daily", "rpt:web", "adm:campaigns", "rptdl:all", "rpt:home", "rpt:downloads",
               "ops:delivery_health", "ops:toggle_reminders", "ops:toggle_channel"]


class FantzoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name) / "f.db"
        with closing(sqlite3.connect(path)) as c:
            c.executescript("CREATE TABLE users(user_id INTEGER PRIMARY KEY); INSERT INTO users VALUES (1),(2);")
            c.commit()

        @contextmanager
        def db():
            conn = sqlite3.connect(path)
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

        self.calls = []

        async def old_admin(update, context):
            self.calls.append(("admin", update.effective_user.id))

        async def old_router(update, context):
            self.calls.append(("router", update.callback_query.data))

        async def configure(app):
            return None

        self.core = SimpleNamespace(admin=old_admin, callback_router=old_router, db=db)
        tracked = SimpleNamespace(app=SimpleNamespace(core=self.core, configure_telegram_ui=configure),
                                  LIVE_TV_MODE="admin", sky_admin_url=lambda: "https://example.invalid/tv")
        self.tracked = tracked
        far = SimpleNamespace(_team_admin_ids=lambda: set(ADMINS), _ops_dashboard_text=lambda: "OPS",
                              _ops_dashboard_menu=lambda: InlineKeyboardMarkup(
                                  [[InlineKeyboardButton(d, callback_data=d)] for d in OLD_OPS]))
        crm_ops = SimpleNamespace(dashboard_counts=lambda: {"verified": 7}, due_count=lambda: 3)
        mode_rt = SimpleNamespace(_brand_label=lambda: "Fantzo", _mode=lambda: "full",
                                  _mode_keyboard=lambda: InlineKeyboardMarkup(
                                      [[InlineKeyboardButton("↻ Status", callback_data="mode:status")]]))
        self.mode_rt = mode_rt
        self.patch = mock.patch.dict(sys.modules, {"bot_mode_runtime": mode_rt, "bot_tracked": tracked,
                                                   "fantzo_admin_reports": far, "fantzo_crm_ops": crm_ops})
        self.patch.start()
        import admin_home_v2
        self.panel = admin_home_v2.install_fantzo()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_home_and_header(self):
        text, markup = self.panel.home(force=True)
        self.assertIn("FANTZO ADMIN", text)
        self.assertIn("2 users", text)
        self.assertIn("7 verified", text)
        self.assertIn("3 due", text)
        self.assertEqual(len([d for d in callbacks(markup) if d.startswith("adm2:cat:")]), 6)

    def test_reachability_and_layout(self):
        reach = set()
        for key in self.panel.order:
            _, markup = self.panel.category(key)
            self.assertTrue(all(len(r) <= 2 for r in markup.inline_keyboard))
            self.assertEqual(callbacks(markup)[-2:], ["adm2:home", "adm2:home"])
            reach.update(callbacks(markup))
        self.assertEqual((set(OLD_OPS) | set(OLD_REPORTS) | {"mode:liveline", "mode:full", "mode:status"}) - reach, set())
        self.assertIn("adm2:cmd:backupnow", reach)

    def test_live_tv_webapp_in_settings(self):
        _, markup = self.panel.category("mode")
        urls = [b.web_app.url for r in markup.inline_keyboard for b in r if b.web_app]
        self.assertEqual(urls, ["https://example.invalid/tv"])

    def test_admin_command_routes(self):
        up = fake_update(8860632140)
        run(self.core.admin(up, ctx()))
        self.assertIn("adm2:cat:reports", callbacks(up.effective_message.reply_text.call_args.kwargs["reply_markup"]))
        run(self.core.admin(fake_update(5), ctx()))
        self.assertEqual(self.calls, [("admin", 5)])

    def test_router(self):
        up = fake_update(8992664481, "ops:home")
        run(self.core.callback_router(up, ctx()))
        self.assertIn("adm2:cat:crm", callbacks(up.callback_query.edit_message_text.call_args.kwargs["reply_markup"]))
        run(self.core.callback_router(fake_update(8992664481, "ops:queue:new"), ctx()))
        self.assertEqual(self.calls, [("router", "ops:queue:new")])
        up = fake_update(5, "adm2:home")
        run(self.core.callback_router(up, ctx()))
        up.callback_query.edit_message_text.assert_not_awaited()

    def test_mode_keyboard_has_nav(self):
        self.assertEqual(callbacks(self.mode_rt._mode_keyboard())[-2:], ["adm2:cat:mode", "adm2:home"])

    def test_confirm_wrapping_on_configure(self):
        ran = []

        async def original(update, context):
            ran.append(1)

        handlers = {0: [CommandHandler("backupnow", original), CommandHandler("bannerclear", original),
                        CommandHandler("broadcast", original), CommandHandler("banners", original)]}
        app = SimpleNamespace(handlers=handlers, add_handler=mock.Mock())
        run(self.tracked.app.configure_telegram_ui(app))
        self.assertEqual(self.panel.confirm_wrapped, ["backupnow", "bannerclear", "broadcast"])
        self.assertFalse(getattr(handlers[0][3].callback, "_adm2_wrapped", False))
        up = fake_update(8992664481)
        c = ctx()
        run(handlers[0][0].callback(up, c))
        self.assertEqual(ran, [])
        ok = callbacks(up.effective_message.reply_text.call_args.kwargs["reply_markup"])[0]
        run(self.core.callback_router(fake_update(8992664481, ok), c))
        self.assertEqual(ran, [1])


if __name__ == "__main__":
    unittest.main()
