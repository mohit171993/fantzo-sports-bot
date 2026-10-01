"""Startup navigation checks after a persisted Dura mode switch."""

import ast
import os
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from mode_control import FULL, LIVE_LINE, ModeStore


ROOT = Path(__file__).parent
SCORES_URL = "https://durasports-runtime.up.railway.app/scores"


class Button:
    def __init__(self, text, *, url=None, web_app=None, callback_data=None):
        self.text = text
        self.url = url
        self.web_app = web_app
        self.callback_data = callback_data


class Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


def _load_functions(filename, names, scope):
    source = ROOT.joinpath(filename).read_text(encoding="utf-8")
    tree = ast.parse(source)
    nodes = [node for node in tree.body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
             and node.name in names]
    assert {node.name for node in nodes} == set(names)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), filename, "exec"), scope)


class NavigationRestartTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = os.path.join(temporary.name, "bot.sqlite")
        ModeStore(path, "dura").switch(LIVE_LINE)

        alert_scope = {
            "InlineKeyboardButton": Button,
            "InlineKeyboardMarkup": Markup,
            "WebAppInfo": lambda url: SimpleNamespace(url=url),
            "_hub_url": lambda section: f"https://durasports-runtime.up.railway.app/hub?section={section}",
        }
        _load_functions("ibetin_match_alerts.py", {"_markup"}, alert_scope)
        self.alerts = SimpleNamespace(
            _markup=alert_scope["_markup"],
            _event_text=lambda *_args: "full alert",
            _send=lambda *_args: None,
        )

        channel = "https://t.me/ibetinoffcial"
        web_app = SimpleNamespace(url="https://durasports-runtime.up.railway.app/hub")
        main = Markup([[
            Button("🏏 OPEN IBETIN LIVE LINE", callback_data="liveline_access"),
            Button("📢 JOIN CHANNEL", url=channel),
            Button("🚀 OPEN IBETIN", web_app=web_app),
        ]])
        phone_verify = SimpleNamespace(
            is_verified=lambda _user_id: False,
            live_line_url=lambda _user_id, _base_url: "https://example.invalid/liveline?access=signed",
        )

        def premium_main_keyboard(user_id=0):
            if user_id and phone_verify.is_verified(user_id):
                return Markup([[
                    Button("🏏 OPEN IBETIN LIVE LINE", web_app=SimpleNamespace(
                        url=phone_verify.live_line_url(user_id, "https://example.invalid/liveline"),
                    )),
                ]])
            return main
        autoreply = Markup([[
            Button("📢 JOIN CHANNEL", url=channel),
            Button("🚀 OPEN IBETIN", web_app=web_app),
            Button("🔴 OPEN LIVE", web_app=web_app),
        ]])
        business = SimpleNamespace(
            verification_keyboard=lambda: Markup([[
                Button("VERIFY & CONTINUE", url="https://t.me/example?start=verify_business_dm"),
            ]]),
            business_keyboard=lambda _user: Markup([[
                Button("🚀 OPEN IBETIN", url="https://t.me/example?startapp=home"),
                Button("🏏 OPEN IBETIN LIVE LINE", url="https://t.me/example?startapp=liveline"),
                Button("📢 JOIN CHANNEL", url=channel),
            ]]),
        )

        def reminder_copy(_kind, _index, destination):
            if destination == "business_dm":
                return "copy", Markup([[
                    Button("OPEN LIVE LINE", url="https://t.me/example?startapp=liveline"),
                    Button("JOIN IBETIN", url="https://t.me/example?startapp=home"),
                    Button("JOIN CHANNEL", url=channel),
                ]])
            return "copy", Markup([[
                Button("OPEN LIVE LINE", callback_data="liveline_access"),
                Button("JOIN CHANNEL", url=channel),
                Button("OPEN IBETIN", web_app=web_app),
            ]])

        reminders = SimpleNamespace(
            _copy_for=reminder_copy,
            run_due_reminders=lambda *_args: None,
            _verification_due_stage=lambda *_args: 1,
            send_liveline_channel_daily=lambda *_args: None,
            send_liveline_channel_launch=lambda *_args: None,
        )
        tracked = SimpleNamespace(
            configure_telegram_ui=lambda *_args: None,
            app=SimpleNamespace(configure_telegram_ui=lambda *_args: None),
        )
        analytics = SimpleNamespace(start_tracking_server=lambda: None)
        runtime = ModuleType("bot_mode_runtime")
        runtime.__dict__.update({
            "_installed": False, "_store": None, "_brand": "",
            "ModeStore": ModeStore,
            "os": SimpleNamespace(getenv=lambda name, default=None: path if name == "DB_PATH" else default),
            "tracked": tracked, "analytics": analytics, "reminders": reminders,
            "match_alerts": self.alerts,
            "log": SimpleNamespace(info=lambda *_args: None, exception=lambda *_args: None),
            "FULL": FULL, "LIVE_LINE": LIVE_LINE,
            "InlineKeyboardButton": Button, "InlineKeyboardMarkup": Markup,
            "WebAppInfo": lambda url: SimpleNamespace(url=url),
            "_scores_url": lambda: SCORES_URL,
            "_score_button_label": lambda: "🏏 OPEN DURASPORTS LIVE LINE",
        })
        _load_functions("bot_mode_runtime.py", {"_mode", "install"}, runtime.__dict__)
        runtime.install("dura")  # Reopens the switched SQLite mode as startup does.
        self.runtime = runtime

        hub = SimpleNamespace(IBETIN_HOME_URL="https://example.test/home",
                              IBETIN_LIVE_URL="https://example.test/live",
                              IBETIN_SUPPORT_URL="https://example.test/support")
        start_scope = {
            "sys": SimpleNamespace(modules={"bot_mode_runtime": runtime}),
            "ibetin_entry": SimpleNamespace(runtime=SimpleNamespace(
                premium_main_keyboard=premium_main_keyboard,
                phone_verify=phone_verify,
                fantzo_live_tv=SimpleNamespace(minitv_url=lambda _user_id: ""),
                app=SimpleNamespace(fantzo_autoreply=SimpleNamespace(
                    standard_keyboard=lambda: autoreply)))),
            "business": business, "reminders": reminders, "match_alerts": self.alerts,
            "news": SimpleNamespace(launcher_keyboard=lambda: Markup([[Button("NEWS", web_app=web_app)]])),
            "hub": hub,
            "_redirect_target": lambda section: {
                "home": hub.IBETIN_HOME_URL, "live": hub.IBETIN_LIVE_URL,
                "support": hub.IBETIN_SUPPORT_URL,
            }[section],
            "logger": SimpleNamespace(info=lambda *_args: None),
            "patch": patch,
        }
        _load_functions("ibetin_start.py", {
            "_buttons", "_expect_webapps", "_expect_score_link",
            "run_navigation_self_test",
        }, start_scope)
        self.self_test = start_scope["run_navigation_self_test"]

    def test_persisted_liveline_restart_keeps_full_alert_buttons(self):
        # Verified users keep Full alerts in Live Line; unverified recipients
        # get the score link at send time, so startup validates Full markup.
        self.assertEqual(self.runtime._mode(), LIVE_LINE)
        self.self_test()
        for event in ("started", "final"):
            button = self.alerts._markup(event).inline_keyboard[0][0]
            self.assertIsNotNone(button.web_app)
        # No verification reminder is due in Live Line; Full cadence otherwise.
        self.assertIsNone(self.runtime.reminders._verification_due_stage({}, None))
        self.runtime._store.switch(FULL)
        self.assertEqual(self.runtime.reminders._verification_due_stage({}, None), 1)

        self.alerts._markup = lambda _event: Markup([[
            Button("🏏 OPEN DURASPORTS LIVE LINE", url=SCORES_URL),
        ]])
        with self.assertRaisesRegex(RuntimeError, "not a web_app button"):
            self.self_test()

    def test_full_mode_still_requires_webapp_match_alerts(self):
        self.runtime._store.switch(FULL)
        self.assertEqual(self.runtime._mode(), FULL)
        self.self_test()

        self.alerts._markup = lambda _event: Markup([[
            Button("Open Match Scores", url=SCORES_URL),
        ]])
        with self.assertRaisesRegex(RuntimeError, "not a web_app button"):
            self.self_test()


if __name__ == "__main__":
    unittest.main()
