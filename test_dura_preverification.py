"""Behavior checks for Dura's pre-verification Telegram surfaces."""

import ast
import asyncio
import re
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PUBLIC_TERMS = re.compile(r"sports|bett|gambl|casino|odds|cricket|match|live line", re.I)


def function(path, name, namespace):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    node = next(
        n for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    )
    exec(compile(ast.Module(body=[node], type_ignores=[]), path, "exec"), namespace)
    return namespace[name]


class PreverificationCopyTests(unittest.TestCase):
    def test_business_and_reminder_prompts_are_neutral(self):
        tree = ast.parse((ROOT / "fantzo_business.py").read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "VERIFY_REPLY"
                            for t in n.targets))
        business_copy = ast.literal_eval(node.value)
        namespace = {
            "ReplyKeyboardMarkup": lambda rows, **kwargs: rows,
            "KeyboardButton": lambda text, **kwargs: text,
        }
        reminder_copy = function(
            "fantzo_reminders.py", "_verification_reminder_copy", namespace
        )(1)[0]
        for copy in (business_copy, reminder_copy):
            self.assertIn("VERIFY & CONTINUE", copy)
            self.assertIsNone(PUBLIC_TERMS.search(copy))
            self.assertNotIn("IBETIN", copy)
            self.assertNotIn("ibetin.com", copy.lower())
            self.assertNotIn("18+", copy)
            self.assertNotIn("responsibly", copy.lower())

    def test_contact_button_stays_until_verified(self):
        class Button:
            def __init__(self, text, **kwargs):
                self.text, self.kwargs = text, kwargs

        class Markup:
            def __init__(self, rows, **kwargs):
                self.rows, self.kwargs = rows, kwargs

        keyboard = function("bot_tracked.py", "_verification_reply_keyboard", {
            "KeyboardButton": Button,
            "ReplyKeyboardMarkup": Markup,
        })()
        self.assertEqual(len(keyboard.rows), 1)
        self.assertEqual(len(keyboard.rows[0]), 1)
        self.assertEqual(keyboard.rows[0][0].text, "📱 VERIFY & CONTINUE")
        self.assertTrue(keyboard.rows[0][0].kwargs["request_contact"])
        self.assertTrue(keyboard.kwargs["is_persistent"])
        self.assertFalse(keyboard.kwargs["one_time_keyboard"])

    def test_global_description_and_commands_are_neutral(self):
        source = (ROOT / "bot_tracked.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        preverify = next(n for n in tree.body if isinstance(n, ast.Assign)
                         and any(isinstance(t, ast.Name) and t.id == "PREVERIFY_COMMANDS"
                                 for t in n.targets))
        commands = []
        exec(compile(ast.Module(body=[preverify], type_ignores=[]), "bot_tracked.py", "exec"),
             {"BotCommand": lambda name, desc: commands.append((name, desc))})
        self.assertEqual([name for name, _ in commands], ["start", "help", "support"])
        configure = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef)
                         and n.name == "configure_telegram_ui")
        desc_calls = [n for n in ast.walk(configure) if isinstance(n, ast.Call)
                      and isinstance(n.func, ast.Attribute)
                      and n.func.attr in {"set_my_description", "set_my_short_description"}]
        self.assertEqual(len(desc_calls), 2)
        descriptions = ["".join(ast.literal_eval(arg) for arg in call.args)
                        for call in desc_calls]
        for copy in descriptions:
            self.assertIsNone(PUBLIC_TERMS.search(copy))
        for _name, description in commands:
            self.assertIsNone(PUBLIC_TERMS.search(description))

    def test_business_welcome_and_buttons_use_dura_only_after_verification(self):
        tree = ast.parse((ROOT / "fantzo_business.py").read_text(encoding="utf-8"))
        welcome = next(n for n in tree.body if isinstance(n, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == "WELCOME_REPLY"
                               for t in n.targets))
        self.assertIn("DURASPORTS", ast.literal_eval(welcome.value))
        self.assertNotIn("IBETIN", ast.literal_eval(welcome.value))

        class Button:
            def __init__(self, label, **kwargs):
                self.label, self.kwargs = label, kwargs

        keyboard = function("fantzo_business.py", "business_keyboard", {
            "_button": lambda label, section, uid: Button(label, section=section),
            "TelegramInlineKeyboardButton": Button,
            "InlineKeyboardMarkup": lambda rows: rows,
        })(123)
        labels = [button.label for row in keyboard for button in row]
        self.assertTrue(any("DURASPORTS" in label for label in labels))
        self.assertTrue(all("IBETIN" not in label for label in labels))
        self.assertEqual(keyboard[-1][0].kwargs["url"], "https://t.me/durasportsofficial")

    def test_dura_hub_route_does_not_replace_verification_ui(self):
        calls = []

        class Handler:
            def do_GET(self):
                pass

            def do_POST(self):
                pass

        install = function("ibetin_hub.py", "install_on_tracking_handler", {
            "_install_clean_runtime_ui": lambda: calls.append("overrode DURA UI"),
            "logger": types.SimpleNamespace(info=lambda *args: None),
            "HUB_PATH": "/hub",
        })
        install(types.SimpleNamespace(TrackingHandler=Handler), install_runtime_ui=False)
        self.assertTrue(Handler._ibetin_hub_installed)
        self.assertEqual(calls, [])
        source = (ROOT / "bot_tracked.py").read_text(encoding="utf-8")
        self.assertIn("hub.install_on_tracking_handler(analytics, install_runtime_ui=False)", source)


class PreverificationGateTests(unittest.TestCase):
    def test_all_contact_prompt_paths_use_private_chat_only(self):
        class Stop(Exception):
            pass

        class Button:
            def __init__(self, label, **kwargs):
                self.label, self.kwargs = label, kwargs

        for chat_type in ("group", "supergroup", "channel"):
            with self.subTest(chat_type=chat_type):
                replies = []

                async def reply_text(text, **kwargs):
                    replies.append((text, kwargs))

                async def answer(*args):
                    return None

                def must_not_run(*args):
                    raise AssertionError("contact keyboard or verified handler reached public chat")

                namespace = {
                    "re": re,
                    "InlineKeyboardButton": Button,
                    "InlineKeyboardMarkup": lambda rows: rows,
                    "phone_verify": types.SimpleNamespace(is_verified=lambda uid: False),
                    "_verification_reply_keyboard": must_not_run,
                    "_set_user_menu_button": must_not_run,
                    "ApplicationHandlerStop": Stop,
                }
                namespace["_is_private_chat"] = function("bot_tracked.py", "_is_private_chat", namespace)
                namespace["_open_private_chat_prompt"] = function(
                    "bot_tracked.py", "_open_private_chat_prompt", namespace
                )
                message = types.SimpleNamespace(
                    text="/start", contact=types.SimpleNamespace(user_id=123),
                    reply_text=reply_text,
                )
                update = types.SimpleNamespace(
                    effective_user=types.SimpleNamespace(id=123),
                    effective_chat=types.SimpleNamespace(type=chat_type),
                    effective_message=message,
                )
                context = types.SimpleNamespace(
                    bot=types.SimpleNamespace(username="DuraAccessBot"),
                    user_data={}, args=[],
                )
                asyncio.run(function("bot_tracked.py", "_prompt_mobile_verification", namespace)(
                    update, context
                ))
                contact_handler = function("bot_tracked.py", "mobile_contact_handler", namespace)
                for contact_user_id in (123, 999, None):
                    message.contact = types.SimpleNamespace(
                        user_id=contact_user_id, phone_number=""
                    )
                    asyncio.run(contact_handler(update, context))
                asyncio.run(function("bot_tracked.py", "smart_start", namespace)(update, context))

                message.text = "typed mobile number"
                with self.assertRaises(Stop):
                    asyncio.run(function(
                        "bot_tracked.py", "pending_verification_text_handler", namespace
                    )(update, context))

                update.callback_query = types.SimpleNamespace(
                    data="dura_today", answer=answer, message=message,
                )
                asyncio.run(function("bot_tracked.py", "smart_callback_router", namespace)(
                    update, context
                ))

                self.assertEqual(len(replies), 7)
                for text, kwargs in replies:
                    self.assertEqual(text, "Open this bot in a private chat and send /start to continue.")
                    self.assertIsNone(PUBLIC_TERMS.search(text))
                    button = kwargs["reply_markup"][0][0]
                    self.assertEqual(button.label, "OPEN PRIVATE CHAT")
                    self.assertNotIn("request_contact", button.kwargs)

    def test_private_verification_prompt_is_neutral_and_requests_self_contact(self):
        replies = []

        async def reply_text(text, **kwargs):
            replies.append((text, kwargs))

        namespace = {
            "phone_verify": types.SimpleNamespace(is_verified=lambda uid: False),
            "reminders": types.SimpleNamespace(touch_user=lambda *args: None),
            "logger": types.SimpleNamespace(exception=lambda *args: None),
            "_verification_reply_keyboard": lambda: "contact button",
        }
        namespace["_is_private_chat"] = function("bot_tracked.py", "_is_private_chat", namespace)
        prompt = function("bot_tracked.py", "_prompt_mobile_verification", namespace)
        update = types.SimpleNamespace(
            effective_user=types.SimpleNamespace(id=123),
            effective_chat=types.SimpleNamespace(type="private"),
            effective_message=types.SimpleNamespace(reply_text=reply_text),
        )
        asyncio.run(prompt(update, types.SimpleNamespace(bot=object(), user_data={})))
        self.assertEqual(len(replies), 1)
        self.assertEqual(replies[0][1]["reply_markup"], "contact button")
        self.assertIsNone(PUBLIC_TERMS.search(replies[0][0]))

    def test_profile_commands_switch_to_full_menu_after_verification(self):
        calls = []

        class Bot:
            async def set_chat_menu_button(self, **kwargs):
                calls.append(("menu", kwargs))

            async def set_my_commands(self, commands, **kwargs):
                calls.append(("commands", commands, kwargs))

        class CommandsMenu:
            pass

        class WebAppMenu:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        namespace = {
            "MenuButtonCommands": CommandsMenu,
            "MenuButtonWebApp": WebAppMenu,
            "WebAppInfo": lambda **kwargs: kwargs,
            "BotCommandScopeChat": lambda **kwargs: kwargs,
            "PREVERIFY_COMMANDS": ("start", "help", "support"),
            "VERIFIED_COMMANDS": ("start", "sports", "support"),
            "hub": types.SimpleNamespace(hub_url=lambda section: "https://dura.test/hub"),
            "logger": types.SimpleNamespace(exception=lambda *args: None),
        }
        handler = function("bot_tracked.py", "_set_user_menu_button", namespace)
        asyncio.run(handler(Bot(), 123, False))
        self.assertIsInstance(calls[0][1]["menu_button"], CommandsMenu)
        self.assertEqual(calls[1][1], namespace["PREVERIFY_COMMANDS"])
        self.assertEqual(calls[1][2]["scope"], {"chat_id": 123})
        calls.clear()
        asyncio.run(handler(Bot(), 123, True))
        self.assertIsInstance(calls[0][1]["menu_button"], WebAppMenu)
        self.assertEqual(calls[1][1], namespace["VERIFIED_COMMANDS"])

    def test_old_callback_cannot_reach_legacy_content(self):
        calls = []

        async def mark(name, *args):
            calls.append(name)

        namespace = {
            "phone_verify": types.SimpleNamespace(is_verified=lambda uid: False),
            "_is_private_chat": lambda update: True,
            "_set_user_menu_button": lambda *args: mark("menu"),
            "_prompt_mobile_verification": lambda *args: mark("verify"),
            "ibetin_reports": types.SimpleNamespace(handle_callback=lambda *args: mark("reports")),
            "_original_callback_router": lambda *args: mark("legacy"),
        }
        handler = function("bot_tracked.py", "smart_callback_router", namespace)
        query = types.SimpleNamespace(data="legacy_casino", answer=lambda: mark("answer"))
        update = types.SimpleNamespace(
            callback_query=query, effective_user=types.SimpleNamespace(id=123)
        )
        asyncio.run(handler(update, types.SimpleNamespace(bot=object())))
        self.assertEqual(calls, ["answer", "menu", "verify"])

    def test_unverified_command_prompts_except_start(self):
        calls = []

        async def mark(name, *args):
            calls.append(name)

        class Stop(Exception):
            pass

        namespace = {
            "phone_verify": types.SimpleNamespace(is_verified=lambda uid: False),
            "_set_user_menu_button": lambda *args: mark("menu"),
            "_prompt_mobile_verification": lambda *args: mark("verify"),
            "ApplicationHandlerStop": Stop,
        }
        handler = function("bot_tracked.py", "pending_verification_command_handler", namespace)
        update = types.SimpleNamespace(
            effective_user=types.SimpleNamespace(id=123),
            effective_message=types.SimpleNamespace(text="/start verify_business_dm"),
        )
        asyncio.run(handler(update, types.SimpleNamespace(bot=object())))
        self.assertEqual(calls, [])
        update.effective_message.text = "/sports"
        with self.assertRaises(Stop):
            asyncio.run(handler(update, types.SimpleNamespace(bot=object())))
        self.assertEqual(calls, ["menu", "verify"])

    def test_unverified_media_cannot_reach_admin_upload(self):
        calls = []

        async def mark(name, *args):
            calls.append(name)

        class Stop(Exception):
            pass

        namespace = {
            "phone_verify": types.SimpleNamespace(is_verified=lambda uid: False),
            "_set_user_menu_button": lambda *args: mark("menu"),
            "_prompt_mobile_verification": lambda *args: mark("verify"),
            "ApplicationHandlerStop": Stop,
        }
        handler = function("bot_tracked.py", "pending_verification_media_handler", namespace)
        update = types.SimpleNamespace(
            effective_user=types.SimpleNamespace(id=123),
            effective_message=types.SimpleNamespace(photo=[object()]),
        )
        with self.assertRaises(Stop):
            asyncio.run(handler(update, types.SimpleNamespace(bot=object())))
        self.assertEqual(calls, ["menu", "verify"])

    def test_creative_test_skips_unverified_recipient(self):
        namespace = {"phone_verify": types.SimpleNamespace(is_verified=lambda uid: False)}
        bot_target = function("ibetin_creatives.py", "_send_test_to_bot_target", namespace)
        business_target = function("ibetin_creatives.py", "_send_test_to_business_target", namespace)
        target = {"user_id": 123, "business_connection_id": "connection"}
        self.assertFalse(asyncio.run(bot_target(object(), target, object())))
        self.assertFalse(asyncio.run(business_target(object(), target, object())))


if __name__ == "__main__":
    unittest.main()
