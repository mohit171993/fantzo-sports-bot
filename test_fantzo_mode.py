"""Focused mode tests that run without a Telegram token or network access."""

import asyncio
import importlib
import sqlite3
import sys
import tempfile
import types
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


class TelegramObject:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.text = args[0] if args else ""


class HandlerStop(Exception):
    pass


telegram = types.ModuleType("telegram")
for name in (
    "BotCommand", "BotCommandScopeChat", "InlineKeyboardButton", "InlineKeyboardMarkup",
    "MenuButtonCommands", "MenuButtonWebApp", "ReplyKeyboardRemove", "Update", "WebAppInfo",
):
    setattr(telegram, name, TelegramObject)
telegram_ext = types.ModuleType("telegram.ext")
for name in ("CallbackQueryHandler", "CommandHandler", "TypeHandler"):
    setattr(telegram_ext, name, TelegramObject)
telegram_ext.ApplicationHandlerStop = HandlerStop
sys.modules["telegram"] = telegram
sys.modules["telegram.ext"] = telegram_ext

core = types.ModuleType("bot")
core.ADMIN_USER_ID = 123
core.DB_PATH = ""


def db():
    connection = sqlite3.connect(core.DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


core.db = db
core.now_iso = lambda: datetime.now(timezone.utc).isoformat()
sys.modules["bot"] = core

television = types.ModuleType("fantzo_live_tv")
television.is_public_enabled = lambda: False
television.TRACKING_BASE_URL = "https://example.invalid"
television.LIVE_TV_URL = "https://public-provider.example.invalid/"
television.minitv_url = lambda: "https://example.invalid/minitv"
sys.modules["fantzo_live_tv"] = television
verification = types.ModuleType("fantzo_live_tv_mobile_gate")
verification.is_registered = lambda user_id: True
verification.VERIFIED_COMMANDS = [TelegramObject("start", "Open Fantzo")]
verification.PREVERIFY_COMMANDS = [TelegramObject("start", "Verify your Telegram account")]
sys.modules["fantzo_live_tv_mobile_gate"] = verification
tracked = types.ModuleType("bot_tracked")
tracked.tracked_url = lambda source: "https://fantzo.example/go?source=" + source
sys.modules["bot_tracked"] = tracked

sys.path.insert(0, str(Path(__file__).parent))
mode = importlib.import_module("fantzo_mode")
analytics = importlib.import_module("fantzo_analytics")
analytics.record_open = lambda source: None


class FakeMessage:
    def __init__(self, text=""):
        self.text = text
        self.replies = []
        self.chat_id = 456
        self.business_connection_id = "business-1"

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.edits = []
        self.answers = []
        self.message = FakeMessage()

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


class FakeUpdate:
    def __init__(self, text=None, data=None, user_id=456, chat_type="private"):
        self.effective_user = types.SimpleNamespace(id=user_id)
        self.effective_chat = types.SimpleNamespace(type=chat_type)
        self.effective_message = FakeMessage(text) if text is not None else None
        self.callback_query = FakeQuery(data) if data is not None else None
        self.business_connection = None
        self.business_message = None


class ModeTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        core.DB_PATH = str(Path(self.tempdir.name) / "mode.sqlite")
        mode.ensure_table()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_default_full_and_restart_persistence(self):
        self.assertEqual(mode.get_mode(), "full")
        mode.set_mode("livetv", core.ADMIN_USER_ID)
        importlib.reload(mode)
        self.assertEqual(mode.get_mode(), "livetv")
        mode.set_mode("full", core.ADMIN_USER_ID)
        self.assertEqual(mode.get_mode(), "full")

    def test_non_admin_mode_command_is_silent(self):
        update = FakeUpdate(text="/mode full", user_id=456)
        context = types.SimpleNamespace(args=["full"])
        with self.assertRaises(HandlerStop):
            asyncio.run(mode.mode_command(update, context))
        self.assertEqual(update.effective_message.replies, [])
        self.assertEqual(mode.get_mode(), "full")

    def test_forwarded_admin_button_cannot_change_mode(self):
        update = FakeUpdate(data="fantzo_mode:livetv", user_id=456)
        with self.assertRaises(HandlerStop):
            asyncio.run(mode.mode_callback(update, types.SimpleNamespace()))
        self.assertEqual(mode.get_mode(), "full")
        self.assertEqual(update.callback_query.answers, [])

    def test_admin_mode_button_replay_is_idempotent(self):
        original_sync = mode._sync_public_menu
        original_schedule = mode.schedule_menu_sync
        async def no_network_menu(bot):
            pass
        mode._sync_public_menu = no_network_menu
        mode.schedule_menu_sync = lambda bot: None
        old_enabled = television.is_public_enabled
        television.is_public_enabled = lambda: True
        try:
            context = types.SimpleNamespace(bot=object())
            for _ in range(2):
                update = FakeUpdate(data="fantzo_mode:livetv", user_id=core.ADMIN_USER_ID)
                with self.assertRaises(HandlerStop):
                    asyncio.run(mode.mode_callback(update, context))
                self.assertEqual(len(update.callback_query.edits), 1)
            self.assertEqual(mode.get_mode(), "livetv")
        finally:
            television.is_public_enabled = old_enabled
            mode._sync_public_menu = original_sync
            mode.schedule_menu_sync = original_schedule

    def test_livetv_switch_refuses_disabled_or_invalid_public_url(self):
        update = FakeUpdate(text="/mode livetv", user_id=core.ADMIN_USER_ID)
        context = types.SimpleNamespace(args=["livetv"], bot=object())
        with self.assertRaises(HandlerStop):
            asyncio.run(mode.mode_command(update, context))
        self.assertEqual(mode.get_mode(), "full")
        self.assertIn("not activated", update.effective_message.replies[0][0])
        self.assertIn("Full", update.effective_message.replies[0][0])

        old_enabled = television.is_public_enabled
        old_url = television.minitv_url
        television.is_public_enabled = lambda: True
        television.minitv_url = lambda: "http://example.invalid/minitv"
        try:
            button = FakeUpdate(data="fantzo_mode:livetv", user_id=core.ADMIN_USER_ID)
            with self.assertRaises(HandlerStop):
                asyncio.run(mode.mode_callback(button, types.SimpleNamespace(bot=object())))
            self.assertEqual(mode.get_mode(), "full")
            self.assertTrue(button.callback_query.answers[0][1]["show_alert"])
        finally:
            television.is_public_enabled = old_enabled
            television.minitv_url = old_url

    def test_full_mode_passes_normal_update_unchanged(self):
        update = FakeUpdate(data="join_fantzo")
        asyncio.run(mode.liveline_guard(update, types.SimpleNamespace()))
        self.assertEqual(update.callback_query.edits, [])

    def test_livetv_blocks_old_join_callback(self):
        mode.set_mode("livetv", core.ADMIN_USER_ID)
        update = FakeUpdate(data="join_fantzo")
        with self.assertRaises(HandlerStop):
            asyncio.run(mode.liveline_guard(update, types.SimpleNamespace()))
        self.assertIn("Live TV", update.callback_query.edits[0][0])
        buttons = update.callback_query.edits[0][1]["reply_markup"].args[0]
        self.assertFalse(any("web_app" in button.kwargs for row in buttons for button in row))

    def test_livetv_group_command_is_silent(self):
        mode.set_mode("livetv", core.ADMIN_USER_ID)
        update = FakeUpdate(text="/sports", chat_type="group")
        with self.assertRaises(HandlerStop):
            asyncio.run(mode.liveline_guard(update, types.SimpleNamespace()))
        self.assertEqual(update.effective_message.replies, [])

    def test_admin_read_only_command_still_reaches_existing_handler(self):
        mode.set_mode("livetv", core.ADMIN_USER_ID)
        update = FakeUpdate(text="/reports", user_id=core.ADMIN_USER_ID)
        asyncio.run(mode.liveline_guard(update, types.SimpleNamespace()))
        self.assertEqual(update.effective_message.replies, [])

    def test_unverified_start_still_reaches_existing_verification_gate(self):
        mode.set_mode("livetv", core.ADMIN_USER_ID)
        previous = verification.is_registered
        verification.is_registered = lambda user_id: False
        try:
            update = FakeUpdate(text="/start", user_id=456)
            asyncio.run(mode.liveline_guard(update, types.SimpleNamespace()))
            self.assertEqual(update.effective_message.replies, [])
        finally:
            verification.is_registered = previous

    def test_clean_business_dm_uses_business_connection(self):
        mode.set_mode("livetv", core.ADMIN_USER_ID)
        update = FakeUpdate(text="hello", user_id=456)
        update.business_message = update.effective_message
        sent = []
        async def send_message(**kwargs):
            sent.append(kwargs)
        context = types.SimpleNamespace(bot=types.SimpleNamespace(send_message=send_message))
        with self.assertRaises(HandlerStop):
            asyncio.run(mode.liveline_guard(update, context))
        self.assertEqual(sent[0]["business_connection_id"], "business-1")
        self.assertIn("Live TV", sent[0]["text"])

    def test_go_redirect_is_mode_aware(self):
        class FakeHTTP:
            path = "/go?source=old_button&dest=register"
            def __init__(self):
                self.status = None
                self.headers = {}
            def send_response(self, code):
                self.status = code
            def send_header(self, name, value):
                self.headers[name] = value
            def end_headers(self):
                pass

        mode.set_mode("livetv", core.ADMIN_USER_ID)
        clean = FakeHTTP()
        analytics.TrackingHandler.do_GET(clean)
        self.assertEqual(clean.status, 302)
        self.assertEqual(clean.headers["Location"], "https://t.me/fantzoofficialbot?start=livetv_mode")
        mode.set_mode("full", core.ADMIN_USER_ID)
        normal = FakeHTTP()
        analytics.TrackingHandler.do_GET(normal)
        self.assertEqual(normal.status, 302)
        self.assertIn("fantzo.com/en/registration", normal.headers["Location"])

    def test_verified_chat_menu_sync_survives_mode_switch(self):
        with closing(db()) as conn, conn:
            conn.execute(
                "CREATE TABLE live_tv_mobile_users "
                "(user_id INTEGER PRIMARY KEY,capture_method TEXT)"
            )
            conn.executemany(
                "INSERT INTO live_tv_mobile_users VALUES (?, 'telegram_contact')",
                [(2001,), (2002,)],
            )
        class FakeBot:
            def __init__(self):
                self.menus = []
            async def set_my_commands(self, commands, **kwargs):
                pass
            async def set_chat_menu_button(self, *, chat_id, menu_button):
                self.menus.append((chat_id, type(menu_button).__name__))

        bot = FakeBot()
        mode.set_mode("livetv", core.ADMIN_USER_ID)
        asyncio.run(mode._drain_menu_sync(bot))
        self.assertEqual(mode.menu_sync_counts()["done"], 2)
        self.assertEqual(len(bot.menus), 2)
        mode.set_mode("full", core.ADMIN_USER_ID)
        asyncio.run(mode._drain_menu_sync(bot))
        self.assertEqual(mode.menu_sync_counts()["done"], 2)
        self.assertEqual(len(bot.menus), 4)

    def test_menu_sync_does_not_expose_verified_menu_after_revocation(self):
        class FakeBot:
            def __init__(self):
                self.commands = []
                self.menus = []
            async def set_my_commands(self, commands, **kwargs):
                self.commands.append((commands, kwargs))
            async def set_chat_menu_button(self, *, chat_id, menu_button):
                self.menus.append((chat_id, menu_button))

        bot = FakeBot()
        previous = verification.is_registered
        verification.is_registered = lambda user_id: False
        try:
            asyncio.run(mode._sync_one_chat_menu(bot, 2001, "full"))
            self.assertIs(bot.commands[-1][0], verification.PREVERIFY_COMMANDS)
            self.assertEqual(type(bot.menus[-1][1]).__name__, "TelegramObject")
            self.assertFalse(any("web_app" in menu.kwargs for _, menu in bot.menus))
        finally:
            verification.is_registered = previous


if __name__ == "__main__":
    unittest.main()

