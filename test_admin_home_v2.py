"""Synthetic tests for the grouped admin home (no network, no production DB)."""
import asyncio
from contextlib import closing
import sqlite3
import sys
import tempfile
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler

ADMINS = {8992664481, 8860632140}
OLD_HOME = [
    "reports:queue:new", "reports:queue:due", "reports:queue:all", "reports:queue:mobile",
    "reports:queue:followup", "reports:queue:interested", "reports:search", "reports:exportleads",
    "reports:queue:converted", "reports:adperformance", "reports:automation", "reports:guide",
    "mode:status",
]
OLD_ADVANCED = ["reports:users", "reports:liveline", "reports:business", "reports:reminders",
                "reports:activity", "reports:web", "reports:campaigns", "reports:all"]


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class Env:
    def __init__(self, brand="dura"):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "t.db"
        with closing(sqlite3.connect(self.path)) as c:
            c.executescript("""CREATE TABLE users(user_id INTEGER PRIMARY KEY);
            CREATE TABLE liveline_verified_users(user_id INTEGER PRIMARY KEY);
            CREATE TABLE ibetin_leads(user_id INTEGER PRIMARY KEY, next_followup_at TEXT, lead_status TEXT);
            INSERT INTO users VALUES (1),(2),(3);
            INSERT INTO liveline_verified_users VALUES (1);""")
        self.broken = False
        env = self

        @contextmanager
        def db():
            if env.broken:
                raise sqlite3.OperationalError("db down")
            conn = sqlite3.connect(self.path)
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

        self.old_sent = []
        self.old_cb = []

        async def old_send_menu(update, context):
            self.old_sent.append(update)

        async def old_callback(update, context):
            self.old_cb.append(update.callback_query.data)
            return True

        def crm_menu():
            return InlineKeyboardMarkup([[InlineKeyboardButton("X", callback_data=d)] for d in OLD_HOME])

        self.reports = types.SimpleNamespace(
            core=types.SimpleNamespace(db=db), send_menu=old_send_menu, handle_callback=old_callback,
            _crm_text=lambda: "OLD", crm_menu=crm_menu, is_authorized_admin=lambda uid: uid in ADMINS,
            ensure_tables=lambda: None, _team_guide_text=lambda: "GUIDE",
        )
        self.auto = {"reminders_enabled": True, "channel_enabled": False}
        reminders = types.SimpleNamespace(
            automation_status=lambda: dict(self.auto),
            set_automation_enabled=lambda k, v: self.auto.__setitem__(f"{k}_enabled", v))

        async def configure(app):
            return None

        tracked = types.SimpleNamespace(configure_telegram_ui=configure, LIVE_TV_MODE="off",
                                        sky_admin_url=lambda: "", app=types.SimpleNamespace())
        mode_rt = types.SimpleNamespace(
            _brand=brand, _brand_label=lambda: {"dura": "DURA", "ibetin": "iBetin"}[brand],
            _mode=lambda: "liveline",
            _mode_keyboard=lambda: InlineKeyboardMarkup([[InlineKeyboardButton("📊 Live Line", callback_data="mode:liveline")]]))
        self.mode_rt, self.tracked = mode_rt, tracked
        self.patch = mock.patch.dict(sys.modules, {"bot_mode_runtime": mode_rt, "bot_tracked": tracked,
                                                   "fantzo_reminders": reminders})
        self.patch.start()
        import admin_home_v2
        self.mod = admin_home_v2

        def queue_sql(q):
            return ("SELECT user_id FROM ibetin_leads WHERE next_followup_at IS NOT NULL", ())
        self.panel = admin_home_v2.install_ibetin(self.reports, brand_key=brand, queue_sql=queue_sql)

    def close(self):
        self.patch.stop()
        self.tmp.cleanup()


def fake_update(uid, data=None, edit_exc=None):
    message = SimpleNamespace(reply_text=mock.AsyncMock(), chat_id=uid, message_id=5)
    query = None
    if data is not None:
        query = SimpleNamespace(data=data, message=message, answer=mock.AsyncMock(),
                                edit_message_text=mock.AsyncMock(side_effect=edit_exc),
                                edit_message_reply_markup=mock.AsyncMock())
    return SimpleNamespace(effective_user=SimpleNamespace(id=uid), effective_message=message,
                           callback_query=query)


def ctx(args=None):
    return SimpleNamespace(user_data={}, args=args or [])


def callbacks(markup):
    return [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data]


class AdminHomeV2Tests(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.panel = self.env.panel

    def tearDown(self):
        self.env.close()

    def test_home_has_six_categories_two_per_row(self):
        text, markup = self.panel.home()
        cats = [d for d in callbacks(markup) if d.startswith("adm2:cat:")]
        self.assertEqual(len(cats), 6)
        self.assertTrue(all(len(r) <= 2 for r in markup.inline_keyboard))
        self.assertIn("DURA ADMIN", text)
        self.assertIn("3 users", text)
        self.assertIn("1 verified", text)
        self.assertIn("Live Line", text)

    def test_every_category_has_back_home_and_max_two(self):
        for key in self.panel.order:
            _, markup = self.panel.category(key)
            self.assertTrue(all(len(r) <= 2 for r in markup.inline_keyboard), key)
            self.assertEqual(callbacks(markup)[-2:], ["adm2:home", "adm2:home"])

    def test_all_old_dashboard_actions_reachable(self):
        reach = set()
        for key in self.panel.order:
            reach.update(callbacks(self.panel.category(key)[1]))
        missing = (set(OLD_HOME) | set(OLD_ADVANCED) | {"reports:exportfunnel", "mode:full",
                   "mode:liveline"}) - reach
        self.assertEqual(missing, set())

    def test_status_dash_on_db_error(self):
        self.env.broken = True
        text, _ = self.panel.home(force=True)
        self.assertIn("👥 -", text)
        self.assertIn("✅ -", text)

    def test_status_cached(self):
        self.panel.home(force=True)
        with closing(sqlite3.connect(self.env.path)) as c:
            c.execute("INSERT INTO users VALUES (9)")
            c.commit()
        self.assertIn("3 users", self.panel.home()[0])
        self.assertIn("4 users", self.panel.home(force=True)[0])

    def test_admin_send_menu_new_home_both_admins(self):
        for uid in ADMINS:
            up = fake_update(uid)
            run(self.env.reports.send_menu(up, ctx()))
            kwargs = up.effective_message.reply_text.call_args.kwargs
            self.assertIn("adm2:cat:crm", callbacks(kwargs["reply_markup"]))

    def test_non_admin_goes_to_old_send_menu(self):
        up = fake_update(42)
        run(self.env.reports.send_menu(up, ctx()))
        self.assertEqual(len(self.env.old_sent), 1)

    def test_kill_switch(self):
        self.panel.set_enabled(False)
        run(self.env.reports.send_menu(fake_update(8992664481), ctx()))
        self.assertEqual(len(self.env.old_sent), 1)
        self.panel.set_enabled(True)
        self.assertTrue(self.panel.enabled())

    def test_navigation_edits_in_place(self):
        up = fake_update(8860632140, "adm2:cat:reports")
        self.assertTrue(run(self.env.reports.handle_callback(up, ctx())))
        up.callback_query.edit_message_text.assert_awaited()
        up.effective_message.reply_text.assert_not_awaited()

    def test_edit_failure_falls_back_to_new_message(self):
        up = fake_update(8992664481, "adm2:home", edit_exc=RuntimeError("Message can't be edited"))
        run(self.env.reports.handle_callback(up, ctx()))
        up.effective_message.reply_text.assert_awaited()

    def test_not_modified_is_quiet(self):
        up = fake_update(8992664481, "adm2:home", edit_exc=RuntimeError("Message is not modified"))
        run(self.env.reports.handle_callback(up, ctx()))
        up.effective_message.reply_text.assert_not_awaited()

    def test_non_admin_adm2_restricted(self):
        up = fake_update(77, "adm2:cat:crm")
        self.assertTrue(run(self.env.reports.handle_callback(up, ctx())))
        up.callback_query.edit_message_text.assert_not_awaited()

    def test_old_back_buttons_open_new_home_and_others_pass_through(self):
        up = fake_update(8992664481, "reports:crm")
        run(self.env.reports.handle_callback(up, ctx()))
        self.assertIn("adm2:cat:crm", callbacks(up.callback_query.edit_message_text.call_args.kwargs["reply_markup"]))
        up = fake_update(8992664481, "reports:queue:new")
        run(self.env.reports.handle_callback(up, ctx()))
        self.assertEqual(self.env.old_cb, ["reports:queue:new"])

    def test_guide_has_back_and_home(self):
        up = fake_update(8992664481, "reports:guide")
        run(self.env.reports.handle_callback(up, ctx()))
        kw = up.callback_query.edit_message_text.call_args.kwargs
        self.assertEqual(callbacks(kw["reply_markup"]), ["adm2:cat:crm", "adm2:home"])

    def test_mode_keyboard_not_dead_end(self):
        self.assertEqual(callbacks(self.env.mode_rt._mode_keyboard())[-2:], ["adm2:cat:mode", "adm2:home"])

    def test_toggle_reminders(self):
        up = fake_update(8992664481, "adm2:act:tog_reminders")
        run(self.env.reports.handle_callback(up, ctx()))
        self.assertFalse(self.env.auto["reminders_enabled"])

    def test_cmd_card(self):
        up = fake_update(8992664481, "adm2:cmd:broadcast")
        run(self.env.reports.handle_callback(up, ctx()))
        kw = up.callback_query.edit_message_text.call_args.kwargs
        self.assertIn("/broadcast", kw["text"])
        self.assertEqual(callbacks(kw["reply_markup"]), ["adm2:cat:broadcast", "adm2:home"])

    def test_broadcast_requires_confirmation(self):
        sent = []

        async def original(update, context):
            sent.append(list(context.args))

        app = SimpleNamespace(handlers={0: [CommandHandler("broadcast", original)]}, add_handler=mock.Mock())
        self.panel.wrap_commands(app, {"broadcast": (lambda a: "x", True)})
        wrapped = app.handlers[0][0].callback
        c = ctx(["hello", "all"])
        up = fake_update(8992664481)
        run(wrapped(up, c))
        self.assertEqual(sent, [])
        markup = up.effective_message.reply_text.call_args.kwargs["reply_markup"]
        ok, no = callbacks(markup)
        run(self.panel.handle(fake_update(8992664481, no), c))
        self.assertEqual(sent, [])
        run(wrapped(up, c))
        ok = callbacks(up.effective_message.reply_text.call_args.kwargs["reply_markup"])[0]
        run(self.panel.handle(fake_update(8992664481, ok), c))
        self.assertEqual(sent, [["hello", "all"]])
        # replaying the same token does nothing
        run(self.panel.handle(fake_update(8992664481, ok), c))
        self.assertEqual(len(sent), 1)

    def test_broadcast_without_args_and_non_admin_pass_through(self):
        calls = []

        async def original(update, context):
            calls.append(update.effective_user.id)

        wrapped = self.panel.confirm_wrap("broadcast", original, lambda a: "", True)
        run(wrapped(fake_update(8992664481), ctx([])))
        run(wrapped(fake_update(5), ctx(["x"])))
        self.assertEqual(calls, [8992664481, 5])


class IbetinFlavourTests(unittest.TestCase):
    def test_ibetin_has_fb_daily_dose_and_review(self):
        env = Env("ibetin")
        try:
            reach = set()
            for key in env.panel.order:
                reach.update(callbacks(env.panel.category(key)[1]))
            self.assertIn("reports:fb_dailydose", reach)
            self.assertIn("adm2:cmd:reviewcreatives", reach)
            self.assertNotIn("adm2:cmd:creativeaudit", reach)
            self.assertIn("iBetin ADMIN", env.panel.home()[0])
        finally:
            env.close()


if __name__ == "__main__":
    unittest.main()
