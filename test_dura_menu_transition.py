"""Focused mode-menu checks without loading the Railway Telegram stack."""

import ast
import asyncio
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

from mode_control import FULL, LIVE_LINE


SOURCE = Path(__file__).with_name("bot_mode_runtime.py")


def load_functions(names, bindings):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    nodes = [node for node in tree.body
             if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
             and node.name in names]
    scope = dict(bindings)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), scope)
    return scope


class Command:
    def __init__(self, command, description):
        self.command = command
        self.description = description


class Scope:
    def __init__(self, chat_id):
        self.chat_id = chat_id


class WebApp:
    def __init__(self, url):
        self.url = url


class Menu:
    def __init__(self, text, web_app):
        self.text = text
        self.web_app = web_app


class FakeBot:
    def __init__(self):
        self.calls = []

    async def set_chat_menu_button(self, **kwargs):
        self.calls.append(("menu", kwargs))

    async def set_my_commands(self, commands, **kwargs):
        self.calls.append(("commands", commands, kwargs))


class MenuTransitionTests(unittest.TestCase):
    def test_verified_live_menu_is_signed_scores_and_commands_are_clean(self):
        mode = [LIVE_LINE]
        full_commands = (Command("start", "Full Hub"), Command("support", "Support"))
        scope = load_functions({"_set_verified_chat_ui", "_telegram_menu_write"}, {
            "_mode": lambda: mode[0], "LIVE_LINE": LIVE_LINE,
            "_brand": "dura", "asyncio": asyncio,
            "phone_verify": SimpleNamespace(is_verified=lambda uid: uid == 456),
            "_scores_url": lambda uid: f"https://dura.example/scores?access=signed-{uid}",
            "_score_button_label": lambda: "🏏 OPEN DURASPORTS LIVE LINE",
            "_brand_label": lambda: "DURA",
            "tracked": SimpleNamespace(VERIFIED_COMMANDS=full_commands),
            "hub": SimpleNamespace(hub_url=lambda _section:
                                   "https://dura.example/hub?section=home"),
            "BotCommand": Command, "BotCommandScopeChat": Scope,
            "MenuButtonWebApp": Menu, "WebAppInfo": WebApp,
            "log": SimpleNamespace(warning=lambda *_args: None),
        })
        bot = FakeBot()
        asyncio.run(scope["_set_verified_chat_ui"](bot, 456, LIVE_LINE))
        self.assertEqual([call[0] for call in bot.calls], ["commands", "menu"])
        self.assertEqual(bot.calls[0][2]["scope"].chat_id, 456)
        self.assertEqual([item.command for item in bot.calls[0][1]], ["start", "help"])
        self.assertEqual(bot.calls[1][1]["menu_button"].web_app.url,
                         "https://dura.example/scores?access=signed-456")
        self.assertEqual(bot.calls[1][1]["menu_button"].text,
                         "🏏 OPEN DURASPORTS LIVE LINE")
        self.assertNotIn("hub", bot.calls[1][1]["menu_button"].web_app.url)
        bot.calls.clear()
        asyncio.run(scope["_set_verified_chat_ui"](bot, 999, LIVE_LINE))
        self.assertEqual(bot.calls, [])

        mode[0] = FULL
        asyncio.run(scope["_set_verified_chat_ui"](bot, 456, FULL))
        self.assertIs(bot.calls[0][1], full_commands)
        self.assertEqual(bot.calls[1][1]["menu_button"].web_app.url,
                         "https://dura.example/hub?section=home")

    def test_default_full_commands_restore_support(self):
        mode = [LIVE_LINE]
        scheduled = []
        full = (Command("start", "Verify"), Command("help", "Help"),
                Command("support", "Contact support"))
        scope = load_functions({"_set_default_menu"}, {
            "_mode": lambda: mode[0], "LIVE_LINE": LIVE_LINE,
            "_default_menu_lock": asyncio.Lock(),
            "BotCommand": Command, "MenuButtonCommands": object,
            "tracked": SimpleNamespace(PREVERIFY_COMMANDS=full),
            "_schedule_menu_reconciliation": lambda bot: scheduled.append(bot),
            "log": SimpleNamespace(exception=lambda *_args: None),
        })
        bot = FakeBot()
        asyncio.run(scope["_set_default_menu"](bot))
        self.assertEqual([command.command for command in bot.calls[1][1]],
                         ["start", "help"])
        mode[0] = FULL
        bot.calls.clear()
        asyncio.run(scope["_set_default_menu"](bot))
        self.assertIs(bot.calls[1][1], full)
        self.assertEqual([command.command for command in bot.calls[1][1]],
                         ["start", "help", "support"])
        self.assertEqual(scheduled, [bot, bot])

    def test_reconciliation_pages_past_200_and_uses_fixed_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "bot.db")
            with closing(sqlite3.connect(db_path)) as conn, conn:
                conn.execute("CREATE TABLE liveline_verified_users (user_id INTEGER PRIMARY KEY)")
                conn.executemany("INSERT INTO liveline_verified_users VALUES (?)",
                                 ((uid,) for uid in range(1, 268)))
            seen = []
            async def set_chat(_bot, uid, _mode):
                seen.append(uid)
                if uid == 1:
                    with closing(sqlite3.connect(db_path)) as conn, conn:
                        conn.execute("INSERT INTO liveline_verified_users VALUES (999)")
            async def fast_sleep(_seconds):
                return None
            scope = load_functions({"_reconcile_verified_chats"}, {
                "_store": SimpleNamespace(db_path=db_path),
                "_mode": lambda: LIVE_LINE, "LIVE_LINE": LIVE_LINE,
                "sqlite3": sqlite3, "closing": closing,
                "MENU_RECONCILE_BATCH": 50,
                "MENU_RECONCILE_DELAY_SECONDS": 0.2,
                "asyncio": SimpleNamespace(sleep=fast_sleep),
                "_set_verified_chat_ui": set_chat,
                "_admin_id": lambda: 0,
                "log": SimpleNamespace(info=lambda *_args: None,
                                       warning=lambda *_args: None,
                                       exception=lambda *_args: None),
            })
            asyncio.run(scope["_reconcile_verified_chats"](object(), LIVE_LINE))
            self.assertEqual(seen, list(range(1, 268)))

    def test_reconciliation_stops_when_mode_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "bot.db")
            with closing(sqlite3.connect(db_path)) as conn, conn:
                conn.execute("CREATE TABLE liveline_verified_users (user_id INTEGER PRIMARY KEY)")
                conn.executemany("INSERT INTO liveline_verified_users VALUES (?)",
                                 ((uid,) for uid in range(1, 101)))
            mode, seen = [LIVE_LINE], []
            async def set_chat(_bot, uid, _mode):
                seen.append(uid)
                if uid == 52:
                    mode[0] = FULL
            async def fast_sleep(_seconds):
                return None
            scope = load_functions({"_reconcile_verified_chats"}, {
                "_store": SimpleNamespace(db_path=db_path),
                "_mode": lambda: mode[0], "LIVE_LINE": LIVE_LINE,
                "sqlite3": sqlite3, "closing": closing,
                "MENU_RECONCILE_BATCH": 50,
                "MENU_RECONCILE_DELAY_SECONDS": 0.2,
                "asyncio": SimpleNamespace(sleep=fast_sleep),
                "_set_verified_chat_ui": set_chat,
                "_admin_id": lambda: 0,
                "log": SimpleNamespace(info=lambda *_args: None,
                                       warning=lambda *_args: None,
                                       exception=lambda *_args: None),
            })
            asyncio.run(scope["_reconcile_verified_chats"](object(), LIVE_LINE))
            self.assertEqual(seen, list(range(1, 53)))

    def test_live_refresh_reissues_menu_before_token_expiry(self):
        calls, sleeps = [], []
        async def sweep(_bot, mode):
            calls.append(mode)
        async def fake_sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) == 2:
                raise asyncio.CancelledError
        scope = load_functions({"_menu_reconciliation_loop"}, {
            "_mode": lambda: LIVE_LINE,
            "_reconcile_verified_chats": sweep,
            "LIVE_LINE": LIVE_LINE,
            "MENU_REFRESH_SECONDS": 7 * 24 * 60 * 60,
            "MENU_RETRY_SECONDS": 15 * 60,
            "asyncio": SimpleNamespace(sleep=fake_sleep,
                                       CancelledError=asyncio.CancelledError),
        })
        with self.assertRaises(asyncio.CancelledError):
            asyncio.run(scope["_menu_reconciliation_loop"](object(), None))
        self.assertEqual(calls, [LIVE_LINE, LIVE_LINE])
        self.assertEqual(sleeps, [7 * 24 * 60 * 60] * 2)
        self.assertLess(sleeps[0], 30 * 24 * 60 * 60)

    def test_full_restoration_retries_after_temporary_failure(self):
        calls, sleeps = [], []
        async def sweep(_bot, mode):
            calls.append(mode)
            return len(calls) > 1
        async def fast_sleep(seconds):
            sleeps.append(seconds)
        scope = load_functions({"_menu_reconciliation_loop"}, {
            "_mode": lambda: FULL,
            "_reconcile_verified_chats": sweep,
            "LIVE_LINE": LIVE_LINE,
            "MENU_RETRY_SECONDS": 15 * 60,
            "asyncio": SimpleNamespace(sleep=fast_sleep,
                                       CancelledError=asyncio.CancelledError),
            "log": SimpleNamespace(exception=lambda *_args: None),
        })
        asyncio.run(scope["_menu_reconciliation_loop"](object(), None))
        self.assertEqual(calls, [FULL, FULL])
        self.assertEqual(sleeps, [15 * 60])


if __name__ == "__main__":
    unittest.main()
