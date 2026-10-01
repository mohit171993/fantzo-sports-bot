import ast
import asyncio
import os
import posixpath
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
import unittest

from mode_control import (
    FULL, LIVE_LINE, ModeStore, http_route, is_persistent_mode_path,
    is_persistent_volume_mounted,
    parse_admin_mode_request,
)
from scores_only import alert_score_match, score_match, score_page


EXPECTED_BRAND = "ibetin"


def _load_runtime_function(name, bindings):
    """Exercise control code without importing Railway's PTB stack."""
    source = Path(__file__).with_name("bot_mode_runtime.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(node for node in tree.body if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
                and node.name == name)
    scope = dict(bindings)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(name), "exec"), scope)
    return scope[name]


class StopUpdate(Exception):
    pass


def _private_update(user_id, text, replies):
    async def reply_text(*args, **kwargs):
        replies.append((args, kwargs))
    message = SimpleNamespace(text=text, contact=None, reply_text=reply_text)
    return SimpleNamespace(effective_user=SimpleNamespace(id=user_id),
                           effective_chat=SimpleNamespace(type="private"),
                           effective_message=message, message=message,
                           business_message=None,
                           callback_query=None)


class ModeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = os.path.join(self.temp.name, "persistent.sqlite")
        self.bot = ModeStore(self.path, "dura")

    def test_default_preserves_existing_full_mode(self):
        self.assertEqual(self.bot.state().mode, FULL)

    def test_mode_switch_persists_through_restart(self):
        self.bot.switch(LIVE_LINE)
        self.assertEqual(ModeStore(self.path, "dura").state().mode, LIVE_LINE)
        self.bot.switch(FULL)
        self.assertEqual(ModeStore(self.path, "dura").state().mode, FULL)

    def test_invalid_mode_never_changes_state(self):
        with self.assertRaises(ValueError):
            self.bot.switch("betting")
        self.assertEqual(self.bot.state().mode, FULL)

    def test_clean_switch_requires_volume_database_path(self):
        self.assertTrue(is_persistent_mode_path(
            "/app/ibetin_bot_persistent/ibetin_bot.db"))
        for path in (
            "", "ibetin_bot.db", "/app/ibetin_bot.db",
            "/app/ibetin_bot_persistent_backup/ibetin_bot.db",
            "/app/ibetin_bot_persistent/../ibetin_bot.db",
        ):
            self.assertFalse(is_persistent_mode_path(path), path)

        ready = _load_runtime_function("_persistent_mode_storage_ready", {
            "_store": SimpleNamespace(db_path="/app/ibetin_bot_persistent/ibetin_bot.db"),
            "is_persistent_mode_path": is_persistent_mode_path,
            "is_persistent_volume_mounted": lambda: True,
            "PERSISTENT_DB_ROOT": "/app/ibetin_bot_persistent",
            "os": SimpleNamespace(path=SimpleNamespace(
                isdir=lambda _path: True, realpath=lambda path: path,
                commonpath=posixpath.commonpath,
            )),
        })
        self.assertTrue(ready())

        not_mounted = _load_runtime_function("_persistent_mode_storage_ready", {
            "_store": SimpleNamespace(db_path="/app/ibetin_bot_persistent/ibetin_bot.db"),
            "is_persistent_mode_path": is_persistent_mode_path,
            "is_persistent_volume_mounted": lambda: False,
            "PERSISTENT_DB_ROOT": "/app/ibetin_bot_persistent",
            "os": SimpleNamespace(path=SimpleNamespace(
                isdir=lambda _path: True, realpath=lambda path: path,
                commonpath=posixpath.commonpath,
            )),
        })
        self.assertFalse(not_mounted())

    def test_mountinfo_distinguishes_volume_from_plain_directory(self):
        path = Path(self.temp.name) / "mountinfo"
        path.write_text(
            "36 25 0:32 / /app/ibetin_bot_persistent rw - ext4 /dev/sdb rw\n",
            encoding="utf-8",
        )
        self.assertTrue(is_persistent_volume_mounted(mountinfo_path=str(path)))
        path.write_text("36 25 0:32 / /app rw - ext4 /dev/sdb rw\n", encoding="utf-8")
        self.assertFalse(is_persistent_volume_mounted(mountinfo_path=str(path)))
        with patch("mode_control.os.path.ismount", return_value=True):
            self.assertTrue(is_persistent_volume_mounted(
                mountinfo_path=str(path) + ".missing"))

    def test_dura_clean_score_link_rejects_shared_ibetin_fallback(self):
        url_for = _load_runtime_function("_scores_url", {
            "_brand": "dura",
            "hub": SimpleNamespace(_public_base_url=lambda:
                                   "https://ibetin-app-production.up.railway.app"),
            "urlparse": urlparse,
            "phone_verify": SimpleNamespace(live_line_url=lambda _uid, url: url),
        })
        with self.assertRaises(RuntimeError):
            url_for()
        url_for = _load_runtime_function("_scores_url", {
            "_brand": "dura",
            "hub": SimpleNamespace(_public_base_url=lambda:
                                   "https://durasports-runtime.up.railway.app"),
            "urlparse": urlparse,
            "phone_verify": SimpleNamespace(live_line_url=lambda _uid, url: url),
        })
        self.assertEqual(url_for(), "https://durasports-runtime.up.railway.app/scores")
        url_with_slash = _load_runtime_function("_scores_url", {
            "_brand": "dura",
            "hub": SimpleNamespace(_public_base_url=lambda:
                                   "https://durasports-runtime.up.railway.app/"),
            "urlparse": urlparse,
            "phone_verify": SimpleNamespace(live_line_url=lambda _uid, url: url),
        })
        self.assertEqual(url_with_slash(),
                         "https://durasports-runtime.up.railway.app/scores")

    def test_ibetin_score_link_uses_its_own_public_domain(self):
        url_for = _load_runtime_function("_scores_url", {
            "_brand": "ibetin",
            "hub": SimpleNamespace(_public_base_url=lambda: "https://ibtn.me"),
            "urlparse": urlparse,
            "phone_verify": SimpleNamespace(
                live_line_url=lambda uid, url: f"{url}?access=signed-{uid}"),
        })
        self.assertEqual(url_for(), "https://ibtn.me/scores")
        self.assertEqual(url_for(7), "https://ibtn.me/scores?access=signed-7")

    def test_only_exact_admin_id_accepted(self):
        self.assertIsNone(parse_admin_mode_request(456, 123, ["full"]))
        self.assertIsNone(parse_admin_mode_request(123, 0, ["full"]))
        self.assertEqual(parse_admin_mode_request(123, 123, ["LIVEline"]), LIVE_LINE)
        self.assertEqual(parse_admin_mode_request(123, 123, ["status"]), "status")

    def test_mode_admin_matches_existing_bot_admin(self):
        func = _load_runtime_function("_admin_id", {
            "core": SimpleNamespace(ADMIN_USER_ID=987654321),
        })
        self.assertEqual(func(), 987654321)

    def test_score_projection_drops_prices_links_and_untrusted_html(self):
        row = {"id": "m1", "state": "live", "league": {"name": "Cricket"},
               "home": {"name": "<script>alert(1)</script>"}, "away": {"name": "Away"},
               "homeScore": "100/2", "awayScore": "98/3", "odds": {"x": 1.7},
               "bhav": "1.7", "market": "winner", "casino_url": "https://example.invalid",
               "session": "first innings", "payment": "UPI"}
        safe = score_match(row)
        html = score_page([safe], "Dura")
        api_json = json.dumps({"ok": True, "matches": [safe]})
        for forbidden in ("odds", "bhav", "market", "casino", "session",
                          "payment", "deposit", "1.7"):
            self.assertNotIn(forbidden, str(safe).lower())
            self.assertNotIn(forbidden, html.lower())
            self.assertNotIn(forbidden, api_json.lower())
        self.assertIn("100/2", html)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn('/scores?mode=results', html)

    def test_public_score_fields_filter_gambling_words(self):
        safe = score_match({"id": "casino", "state": "betting open",
                            "league": {"name": "Odds League"},
                            "home": {"name": "India"}, "away": {"name": "Casino Team"},
                            "homeScore": "200/2"})
        payload = json.dumps(safe).lower()
        for forbidden in ("casino", "betting", "odds"):
            self.assertNotIn(forbidden, payload)
        self.assertEqual(safe["home_score"], "200/2")

    def test_alert_projection_accepts_scores_but_not_provider_report_or_odds(self):
        match = {
            "homeTeam": {"name": "India"}, "awayTeam": {"name": "Australia"},
            "state": {"teams": {"home": {"score": "100/2"},
                                "away": {"score": "98/3"}},
                      "report": "casino odds 3.50"},
            "markets": {"winner": 3.50},
        }
        safe = alert_score_match(match, "cricket")
        self.assertEqual(safe["home"]["name"], "India")
        self.assertEqual(safe["home_score"], "100/2")
        self.assertEqual(safe["away_score"], "98/3")
        self.assertNotIn("casino", str(safe))
        self.assertNotIn("odds", str(safe))

    def test_direct_full_routes_redirect_in_liveline_only(self):
        for path in ("/liveline", "/liveline/api", "/hub", "/go", "/news",
                     "/admin/liveline-ibetinv23", "/shiko", "/fb"):
            self.assertEqual(http_route(LIVE_LINE, "GET", path), "redirect", path)
            self.assertEqual(http_route(FULL, "GET", path), "pass", path)
        self.assertEqual(http_route(LIVE_LINE, "POST", "/hub/api/preferences"), "deny")

    def test_internal_score_feed_and_health_continue_in_liveline(self):
        self.assertEqual(http_route(LIVE_LINE, "GET", "/health"), "pass")
        self.assertEqual(http_route(LIVE_LINE, "GET", "/report-metrics"), "pass")
        self.assertEqual(http_route(LIVE_LINE, "GET", "/internal/dura-roanuz-proxy"), "redirect")
        self.assertEqual(http_route(LIVE_LINE, "POST", "/roanuz/match/feed/v1/"), "pass")
        self.assertEqual(http_route(LIVE_LINE, "GET", "/scores"), "scores")
        self.assertEqual(http_route(LIVE_LINE, "GET", "/scores/api"), "scores_api")
        self.assertEqual(http_route(LIVE_LINE, "POST", "/scores/auth"), "scores_auth")
        self.assertEqual(http_route(FULL, "POST", "/scores/auth"), "pass")

    def test_admin_private_command_only_and_non_admin_silent(self):
        replies, effects = [], []
        async def set_menu(_bot):
            effects.append("menu")
        async def status(_update, _context):
            effects.append("status")
        func = _load_runtime_function("_mode_command", {
            "parse_admin_mode_request": parse_admin_mode_request,
            "_admin_id": lambda: 123,
            "_store": self.bot,
            "_set_default_menu": set_menu,
            "_persistent_mode_storage_ready": lambda: True,
            "_score_destination_ready": lambda: True,
            "_mode_status": status,
            "_mode_keyboard": lambda: None,
            "LIVE_LINE": LIVE_LINE,
            "ApplicationHandlerStop": StopUpdate,
        })
        context = SimpleNamespace(args=["liveline"], bot=object())
        for user_id, chat_type in ((456, "private"), (123, "group")):
            update = _private_update(user_id, "/mode liveline", replies)
            update.effective_chat.type = chat_type
            with self.assertRaises(StopUpdate):
                asyncio.run(func(update, context))
            self.assertEqual(self.bot.state().mode, FULL)
            self.assertEqual(replies, [])
            self.assertEqual(effects, [])
        with self.assertRaises(StopUpdate):
            asyncio.run(func(_private_update(123, "/mode liveline", replies), context))
        self.assertEqual(self.bot.state().mode, LIVE_LINE)
        self.assertEqual(effects, ["menu", "status"])

    def test_clean_switch_refuses_missing_volume_without_state_change(self):
        replies = []
        async def unused(*_args, **_kwargs):
            self.fail("A refused switch must not update Telegram menus")
        func = _load_runtime_function("_mode_command", {
            "parse_admin_mode_request": parse_admin_mode_request,
            "_admin_id": lambda: 123,
            "_store": self.bot,
            "_persistent_mode_storage_ready": lambda: False,
            "_set_default_menu": unused,
            "_mode_status": unused,
            "_mode_keyboard": lambda: None,
            "ApplicationHandlerStop": StopUpdate,
            "LIVE_LINE": LIVE_LINE,
        })
        with self.assertRaises(StopUpdate):
            asyncio.run(func(_private_update(123, "/mode liveline", replies),
                             SimpleNamespace(args=["liveline"], bot=object())))
        self.assertEqual(self.bot.state().mode, FULL)
        self.assertIn("persistent storage", replies[0][0][0].lower())

    def _guard(self, verified=lambda _uid: False, effects=None, mode=LIVE_LINE):
        effects = effects if effects is not None else []
        async def prompt(_update, _context, _source):
            effects.append("verification_prompt")
        async def scores(_message, _context, uid):
            effects.append(("scores", uid))
        return _load_runtime_function("_guard_update", {
            "_mode": lambda: mode,
            "FULL": FULL,
            "_admin_id": lambda: 123,
            "_is_verified_user": verified,
            "tracked": SimpleNamespace(_is_stop_text=lambda text: text.lower() == "stop",
                                       _prompt_mobile_verification=prompt),
            "leads": SimpleNamespace(clean_campaign=lambda value: value,
                                     record_start=lambda *_args, **_kwargs: effects.append("lead")),
            "core": SimpleNamespace(track=lambda *_args: effects.append("track")),
            "reminders": SimpleNamespace(set_opt_out=lambda *_args: effects.append("opt_out")),
            "_send_live_line_scores": scores,
            "ApplicationHandlerStop": StopUpdate,
            "log": SimpleNamespace(exception=lambda *_args: None),
        })

    def test_unverified_start_gets_only_live_line_and_no_verification_prompt(self):
        replies, effects = [], []
        func = self._guard(effects=effects)
        context = SimpleNamespace(args=[], bot=object(), user_data={})
        for text in ("/start campaign", "hello", "/support"):
            with self.subTest(text=text), self.assertRaises(StopUpdate):
                asyncio.run(func(_private_update(456, text, replies), context))
        self.assertNotIn("verification_prompt", effects)
        self.assertEqual([e for e in effects if isinstance(e, tuple)], [("scores", 456)] * 3)
        self.assertIn("lead", effects)
        self.assertEqual(replies, [])

    def test_verified_users_and_admin_pass_untouched_in_liveline(self):
        replies, effects = [], []
        func = self._guard(verified=lambda uid: uid == 789, effects=effects)
        context = SimpleNamespace(args=[], bot=object(), user_data={})
        for user_id, text in ((789, "/start"), (789, "/support"), (123, "/broadcast promo"),
                              (123, "/reports"), (123, "/admin"), (123, "/mode")):
            with self.subTest(user=user_id, text=text):
                self.assertIsNone(asyncio.run(func(_private_update(user_id, text, replies),
                                                   context)))
        # Admin callback taps from /admin or /reports panels also pass.
        callback_update = _private_update(123, "Report", replies)
        callback_update.message = None
        async def answer():
            effects.append("answered")
        callback_update.callback_query = SimpleNamespace(answer=answer)
        self.assertIsNone(asyncio.run(func(callback_update, context)))
        self.assertEqual(replies, [])
        self.assertEqual(effects, [])

    def test_full_guard_is_unchanged_pass_through(self):
        replies = []
        full_guard = _load_runtime_function("_guard_update", {
            "_mode": lambda: FULL, "FULL": FULL,
        })
        for user_id in (123, 456):
            self.assertIsNone(asyncio.run(full_guard(
                _private_update(user_id, "/broadcast promo", replies), SimpleNamespace())))
        self.assertEqual(replies, [])

    def test_unverified_contact_share_reaches_full_verification_handler(self):
        replies, effects = [], []
        func = self._guard(effects=effects)
        update = _private_update(456, "", replies)
        update.effective_message.contact = SimpleNamespace(user_id=456, phone_number="+911")
        self.assertIsNone(asyncio.run(func(update, SimpleNamespace(user_data={}))))
        self.assertEqual(effects, [])

    def test_match_alert_retry_checks_mode_again_before_sending(self):
        class Button:
            def __init__(self, text, url=None, web_app=None):
                self.text, self.url, self.web_app = text, url, web_app

        class Markup:
            def __init__(self, rows):
                self.inline_keyboard = rows

        class RetryRate(Exception):
            retry_after = 0

        mode = [FULL]
        async def sleep(_seconds):
            mode[0] = LIVE_LINE

        source = Path(__file__).with_name("bot_mode_runtime.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                    and n.name == "_ModeAwareAlertBot")
        scope = {
            "_mode": lambda: mode[0], "FULL": FULL,
            "_is_verified_user": lambda uid: uid == 789,
            "_scores_url": lambda uid: f"https://scores.example/scores?access=signed-{uid}",
            "_score_button_label": lambda: "🏏 OPEN DURASPORTS LIVE LINE",
            "InlineKeyboardButton": Button, "InlineKeyboardMarkup": Markup,
            "WebAppInfo": lambda url: SimpleNamespace(url=url),
        }
        exec(compile(ast.Module(body=[node], type_ignores=[]), "runtime", "exec"), scope)
        wrapper = scope["_ModeAwareAlertBot"]
        alert_source = Path(__file__).with_name("ibetin_match_alerts.py").read_text(encoding="utf-8")
        alert_tree = ast.parse(alert_source)
        send_node = next(n for n in alert_tree.body if isinstance(n, ast.AsyncFunctionDef)
                         and n.name == "_send")
        send_scope = {
            "RetryAfter": RetryRate, "InlineKeyboardMarkup": Markup,
            "asyncio": SimpleNamespace(sleep=sleep),
        }
        exec(compile(ast.Module(body=[send_node], type_ignores=[]), "alerts", "exec"),
             send_scope)

        class Bot:
            def __init__(self):
                self.calls = []

            async def send_message(self, **kwargs):
                self.calls.append(kwargs)
                if len(self.calls) == 1:
                    raise RetryRate()

        bot = Bot()
        unsafe = "Open casino and betting odds"
        asyncio.run(send_scope["_send"](
            wrapper(bot, 456), 456, unsafe, Markup([[Button("Casino", "https://bad.example")]]),
        ))
        self.assertEqual(bot.calls[0]["text"], unsafe)
        self.assertNotIn("casino", bot.calls[1]["text"].lower())
        self.assertNotIn("betting", bot.calls[1]["text"].lower())
        button = bot.calls[1]["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(button.text, "🏏 OPEN DURASPORTS LIVE LINE")
        self.assertEqual(button.web_app.url, "https://scores.example/scores?access=signed-456")
        # A verified recipient keeps the normal Full alert in Live Line mode.
        verified_bot = Bot()
        verified_bot.calls.append({})  # skip the simulated RetryAfter
        asyncio.run(wrapper(verified_bot, 789).send_message(text=unsafe, reply_markup="full"))
        self.assertEqual(verified_bot.calls[-1]["text"], unsafe)
        self.assertEqual(verified_bot.calls[-1]["reply_markup"], "full")

    def test_inflight_public_sends_stop_after_clean_switch(self):
        mode = [FULL]
        source = Path(__file__).with_name("bot_mode_runtime.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        nodes = [n for n in tree.body if isinstance(n, ast.ClassDef)
                 and n.name in {"_GuardedPublicBot", "_GuardedPublicApplication"}]
        scope = {"_mode": lambda: mode[0], "FULL": FULL,
                 "_is_verified_user": lambda uid: uid == 789}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "runtime", "exec"), scope)
        protected = scope["_GuardedPublicApplication"]

        class Bot:
            def __init__(self):
                self.calls = []

            async def send_message(self, **kwargs):
                self.calls.append(("message", kwargs))

            async def send_photo(self, **kwargs):
                self.calls.append(("photo", kwargs))

        bot = Bot()
        application = protected(SimpleNamespace(bot=bot, bot_data={"ready": True}))
        self.assertTrue(application.bot_data["ready"])
        asyncio.run(application.bot.send_message(chat_id=10, text="Full message"))
        self.assertEqual(len(bot.calls), 1)
        mode[0] = LIVE_LINE
        with self.assertRaisesRegex(RuntimeError, "Public send canceled"):
            asyncio.run(application.bot.send_message(chat_id=10, text="Old campaign"))
        with self.assertRaisesRegex(RuntimeError, "Public send canceled"):
            asyncio.run(application.bot.send_photo(chat_id=10, photo="old-banner"))
        self.assertEqual(len(bot.calls), 1)
        # Reminders in Live Line: verified chats are sent, unverified refused.
        reminder_app = protected(SimpleNamespace(bot=bot), allow_verified=True)
        asyncio.run(reminder_app.bot.send_message(chat_id=789, text="Verified reminder"))
        self.assertEqual(len(bot.calls), 2)
        with self.assertRaisesRegex(RuntimeError, "Public send canceled"):
            asyncio.run(reminder_app.bot.send_message(chat_id=10, text="Verify now"))
        self.assertEqual(len(bot.calls), 2)

    def test_mode_db_read_failure_closes_public_routes(self):
        class FailedStore:
            def state(self):
                raise OSError("database unavailable")
        func = _load_runtime_function("_mode", {
            "_store": FailedStore(), "LIVE_LINE": LIVE_LINE,
            "log": SimpleNamespace(exception=lambda *_args: None),
        })
        self.assertEqual(func(), LIVE_LINE)
        self.assertEqual(http_route(func(), "GET", "/hub"), "redirect")

    def test_non_admin_mode_button_is_silent(self):
        effects = []
        async def answer():
            effects.append("answer")
        async def set_menu(_bot):
            effects.append("menu")
        async def status(_update, _context):
            effects.append("status")
        func = _load_runtime_function("_mode_callback", {
            "_admin_id": lambda: 123, "_store": self.bot,
            "_set_default_menu": set_menu, "_mode_status": status,
            "ApplicationHandlerStop": StopUpdate,
            "LIVE_LINE": LIVE_LINE, "FULL": FULL,
        })
        query = SimpleNamespace(data="mode:full", answer=answer)
        update = SimpleNamespace(callback_query=query,
                                 effective_user=SimpleNamespace(id=456),
                                 effective_chat=SimpleNamespace(type="private"))
        with self.assertRaises(StopUpdate):
            asyncio.run(func(update, SimpleNamespace(bot=object())))
        self.assertEqual(effects, [])
        self.assertEqual(self.bot.state().mode, FULL)

    def test_head_and_options_have_no_repository_handlers(self):
        # All routes sit on TrackingHandler; HTTPServer returns 501 for these
        # methods because no source module defines a handler for either.
        source_dir = Path(__file__).parent
        for path in source_dir.glob("*.py"):
            if path.name.startswith("test_"):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            defined = {node.name for node in ast.walk(tree)
                       if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
            self.assertNotIn("do_HEAD", defined, str(path))
            self.assertNotIn("do_OPTIONS", defined, str(path))

    def test_railway_v34_entrypoint_installs_mode_before_bot_start(self):
        source_dir = Path(__file__).parent
        v34 = source_dir / "ibetin_liveline_v34_refined_ui.py"
        if not v34.exists():
            self.skipTest("The shared prototype directory has no brand entry point")
        brand = EXPECTED_BRAND
        tree = ast.parse(v34.read_text(encoding="utf-8"))
        main_guard = next(node for node in tree.body if isinstance(node, ast.If)
                          and ast.unparse(node.test) == "__name__ == '__main__'")
        steps = [ast.unparse(node) for node in main_guard.body]
        self.assertIn("import bot_mode_runtime", steps)
        self.assertIn(f"bot_mode_runtime.install('{brand}')", steps)
        self.assertIn("app.base.ibetin_start.main()", steps)
        self.assertLess(steps.index(f"bot_mode_runtime.install('{brand}')"),
                        steps.index("app.base.ibetin_start.main()"))
        calls = []
        fake_mode = SimpleNamespace(install=lambda value: calls.append(f"install:{value}"))
        fake_app = SimpleNamespace(base=SimpleNamespace(
            ibetin_start=SimpleNamespace(main=lambda: calls.append("start"))))
        with patch.dict(sys.modules, {"bot_mode_runtime": fake_mode}):
            exec(compile(ast.Module(body=main_guard.body, type_ignores=[]),
                         str(v34), "exec"), {"app": fake_app})
        self.assertEqual(calls, [f"install:{brand}", "start"])

    def test_railway_crm_start_command_installs_mode_before_bot_start(self):
        source_dir = Path(__file__).parent
        entry = source_dir / "ibetin_crm_queue_start.py"
        if not entry.exists():
            self.skipTest("The shared prototype directory has no brand entry point")
        brand = EXPECTED_BRAND
        tree = ast.parse(entry.read_text(encoding="utf-8"))
        main_fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                       and node.name == "main")
        steps = [ast.unparse(node) for node in main_fn.body]
        install = f"bot_mode_runtime.install('{brand}')"
        start = "runtime.app.base.ibetin_start.main()"
        self.assertIn("import bot_mode_runtime", steps)
        self.assertIn(install, steps)
        self.assertIn(start, steps)
        self.assertLess(steps.index(install), steps.index(start))
        relevant = [node for node in main_fn.body if ast.unparse(node) in {
            "import ibetin_liveline_v30_unified_ui as runtime", "import bot_mode_runtime",
            install, start,
        }]
        calls = []
        fake_mode = SimpleNamespace(install=lambda value: calls.append(f"install:{value}"))
        fake_runtime = SimpleNamespace(app=SimpleNamespace(base=SimpleNamespace(
            ibetin_start=SimpleNamespace(main=lambda: calls.append("start")))))
        with patch.dict(sys.modules, {
            "bot_mode_runtime": fake_mode,
            "ibetin_liveline_v30_unified_ui": fake_runtime,
        }):
            exec(compile(ast.Module(body=relevant, type_ignores=[]), str(entry), "exec"), {})
        self.assertEqual(calls, [f"install:{brand}", "start"])

    def test_http_gate_blocks_cached_full_renderer_before_it_runs(self):
        effects = []
        class TrackingHandler:
            def do_GET(self):
                effects.append("unsafe_full_render")
            def do_POST(self):
                effects.append("unsafe_full_post")
            def __init__(self, path):
                self.path = path
            def send_response(self, status):
                effects.append(("status", status))
            def send_header(self, name, value):
                effects.append((name, value))
            def end_headers(self):
                pass
        identity = [(0, "", False)]
        func = _load_runtime_function("_install_http_gate", {
            "analytics": SimpleNamespace(TrackingHandler=TrackingHandler),
            "_mode": lambda: LIVE_LINE, "FULL": FULL,
            "http_route": http_route,
            "urlparse": urlparse,
            "parse_qs": parse_qs,
            "phone_verify": SimpleNamespace(verify_access_token=lambda _token: 0),
            "_verified_scores_identity": lambda _handler, _parsed: identity[0],
            "_AUTH_BOOTSTRAP_PAGE": "<script>/scores/auth</script>",
            "_send_bytes": lambda *_args, **_kwargs: effects.append("safe_response"),
            "_scores_auth": lambda _handler: effects.append("auth"),
        })
        func()
        # Unknown visitors get the Mini App auth bootstrap, never a Full page.
        TrackingHandler("/hub?section=casino").do_GET()
        TrackingHandler("/liveline").do_GET()
        self.assertNotIn("unsafe_full_render", effects)
        self.assertEqual(effects.count("safe_response"), 2)
        TrackingHandler("/hub/api/preferences").do_POST()
        self.assertNotIn("unsafe_full_post", effects)
        TrackingHandler("/scores/auth").do_POST()
        self.assertIn("auth", effects)
        # A signed but unverified user is redirected to the scores page.
        identity[0] = (456, "signed", False)
        TrackingHandler("/hub").do_GET()
        self.assertEqual(effects.count(("status", 302)), 1)
        self.assertNotIn("unsafe_full_render", effects)
        # A signed verified user keeps the Full pages and posts.
        identity[0] = (789, "signed", True)
        TrackingHandler("/hub?section=home").do_GET()
        TrackingHandler("/hub/api/preferences").do_POST()
        self.assertIn("unsafe_full_render", effects)
        self.assertIn("unsafe_full_post", effects)
        effects.clear()
        identity[0] = (0, "", False)
        func.__globals__["_mode"] = lambda: FULL
        TrackingHandler("/hub?section=casino").do_GET()
        self.assertIn("unsafe_full_render", effects)


if __name__ == "__main__":
    unittest.main()
