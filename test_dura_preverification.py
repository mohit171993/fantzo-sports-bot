"""Behavior checks for Dura's pre-verification Telegram surfaces."""

import ast
import asyncio
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


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
            self.assertNotIn("Live Line", copy)
            self.assertNotIn("18+", copy)
            self.assertNotIn("responsibly", copy.lower())

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
            self.assertNotIn("Live Line", copy)
            self.assertNotIn("sports hub", copy.lower())
            self.assertNotIn("sports news", copy.lower())
            self.assertNotIn("casino", copy.lower())


class PreverificationGateTests(unittest.TestCase):
    def test_old_callback_cannot_reach_legacy_content(self):
        calls = []

        async def mark(name, *args):
            calls.append(name)

        namespace = {
            "phone_verify": types.SimpleNamespace(is_verified=lambda uid: False),
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

    def test_creative_test_skips_unverified_recipient(self):
        namespace = {"phone_verify": types.SimpleNamespace(is_verified=lambda uid: False)}
        bot_target = function("ibetin_creatives.py", "_send_test_to_bot_target", namespace)
        business_target = function("ibetin_creatives.py", "_send_test_to_business_target", namespace)
        target = {"user_id": 123, "business_connection_id": "connection"}
        self.assertFalse(asyncio.run(bot_target(object(), target, object())))
        self.assertFalse(asyncio.run(business_target(object(), target, object())))


if __name__ == "__main__":
    unittest.main()
