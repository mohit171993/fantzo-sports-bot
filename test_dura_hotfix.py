"""Regression checks for DURA's private verification and public copy."""

import ast
import asyncio
import os
import re
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent
PUBLIC_TERMS = re.compile(r"sports|bett|gambl|casino|odds|cricket|match|live line", re.I)


def load_function(path, name, namespace):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), path, "exec"), namespace)
    return namespace[name]


class HotfixTests(unittest.TestCase):
    def test_public_chat_never_gets_contact_keyboard(self):
        class Stop(Exception):
            pass

        class Button:
            def __init__(self, label, **kwargs):
                self.label, self.kwargs = label, kwargs

        for chat_type in ("group", "supergroup", "channel"):
            with self.subTest(chat_type=chat_type):
                replies = []

                async def reply_text(copy, **kwargs):
                    replies.append((copy, kwargs))

                async def answer(*args):
                    return None

                def contact_keyboard():
                    raise AssertionError("contact button attempted outside private chat")

                namespace = {
                    "re": re,
                    "InlineKeyboardButton": Button,
                    "InlineKeyboardMarkup": lambda rows: rows,
                    "phone_verify": types.SimpleNamespace(is_verified=lambda uid: False),
                    "_verification_reply_keyboard": contact_keyboard,
                    "ApplicationHandlerStop": Stop,
                }
                namespace["_is_private_chat"] = load_function(
                    "bot_tracked.py", "_is_private_chat", namespace
                )
                namespace["_open_private_chat_prompt"] = load_function(
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
                    bot=types.SimpleNamespace(username="DuraAccessBot"), user_data={}, args=[]
                )

                asyncio.run(load_function("bot_tracked.py", "_prompt_mobile_verification", namespace)(
                    update, context
                ))
                contact_handler = load_function("bot_tracked.py", "mobile_contact_handler", namespace)
                for uid in (123, 999, None):
                    message.contact = types.SimpleNamespace(user_id=uid, phone_number="")
                    asyncio.run(contact_handler(update, context))
                asyncio.run(load_function("bot_tracked.py", "smart_start", namespace)(update, context))
                message.text = "typed mobile number"
                with self.assertRaises(Stop):
                    asyncio.run(load_function(
                        "bot_tracked.py", "pending_verification_text_handler", namespace
                    )(update, context))
                update.callback_query = types.SimpleNamespace(
                    data="legacy", answer=answer, message=message
                )
                asyncio.run(load_function("bot_tracked.py", "smart_callback_router", namespace)(
                    update, context
                ))

                self.assertEqual(len(replies), 7)
                for copy, kwargs in replies:
                    self.assertEqual(copy, "Open this bot in a private chat and send /start to continue.")
                    self.assertIsNone(PUBLIC_TERMS.search(copy))
                    button = kwargs["reply_markup"][0][0]
                    self.assertEqual(button.label, "OPEN PRIVATE CHAT")
                    self.assertNotIn("request_contact", button.kwargs)

    def test_username_comes_from_live_bot_and_missing_identity_has_no_legacy_link(self):
        import logging

        namespace = {"os": os, "re": re, "logger": logging.getLogger(__name__)}
        resolve = load_function("bot_tracked.py", "_set_active_bot_username", namespace)

        class Bot:
            username = ""

            async def get_me(self):
                return types.SimpleNamespace(username="DuraAccessBot")

        class UnavailableBot:
            username = ""

            async def get_me(self):
                raise RuntimeError("Telegram temporarily unavailable")

        url_namespace = {"os": os, "re": re, "DEFAULT_BOT_USERNAME": ""}
        url = load_function("ibetin_phone_verify.py", "verification_bot_url", url_namespace)
        with patch.dict(os.environ, {"IBETIN_BOT_USERNAME": "Ibtnofficialbot"}):
            self.assertEqual(asyncio.run(resolve(Bot())), "DuraAccessBot")
            self.assertEqual(url(), "https://t.me/DuraAccessBot?start=verifyliveline")
            self.assertEqual(asyncio.run(resolve(UnavailableBot())), "")
            self.assertEqual(url(), "")
            self.assertNotIn("IBETIN_BOT_USERNAME", os.environ)

    def test_business_verification_has_neutral_no_link_fallback(self):
        source = (ROOT / "fantzo_business.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        assignments = {
            target.id: ast.literal_eval(node.value)
            for node in tree.body if isinstance(node, ast.Assign)
            for target in node.targets if isinstance(target, ast.Name)
            and target.id in {"VERIFY_REPLY", "VERIFY_LINK_UNAVAILABLE_REPLY", "WELCOME_REPLY"}
        }
        self.assertIn("DURASPORTS", assignments["WELCOME_REPLY"])
        self.assertNotIn("IBETIN", assignments["WELCOME_REPLY"])
        for key in ("VERIFY_REPLY", "VERIFY_LINK_UNAVAILABLE_REPLY"):
            self.assertIsNone(PUBLIC_TERMS.search(assignments[key]))
        self.assertIn("the DURA team may contact you", assignments["VERIFY_REPLY"])

        class Markup:
            def __init__(self, rows):
                self.rows = rows

        namespace = {
            "InlineKeyboardMarkup": Markup,
            "phone_verify": types.SimpleNamespace(verification_bot_url=lambda *_: ""),
        }
        keyboard = load_function("fantzo_business.py", "verification_keyboard", namespace)
        self.assertIsNone(keyboard())

        replies = []

        async def reply_with_retry(message, copy, markup):
            replies.append((copy, markup))

        class Stop(Exception):
            pass

        guard_namespace = {
            "Update": object,
            "ContextTypes": types.SimpleNamespace(DEFAULT_TYPE=object),
            "fantzo_autoreply": types.SimpleNamespace(is_enabled=lambda: True),
            "phone_verify": types.SimpleNamespace(is_verified=lambda uid: False),
            "ibetin_leads": types.SimpleNamespace(record_start=lambda *args, **kwargs: None),
            "_owner_user_id": lambda _: 0,
            "_save_business_customer": lambda *args: None,
            "_is_stop_text": lambda _: False,
            "verification_keyboard": keyboard,
            "VERIFY_REPLY": assignments["VERIFY_REPLY"],
            "VERIFY_LINK_UNAVAILABLE_REPLY": assignments["VERIFY_LINK_UNAVAILABLE_REPLY"],
            "_reply_with_retry": reply_with_retry,
            "_mark_business_reply": lambda *args: None,
            "core": types.SimpleNamespace(track=lambda *args: None),
            "logger": types.SimpleNamespace(info=lambda *args: None),
            "ApplicationHandlerStop": Stop,
        }
        guard = load_function("fantzo_business.py", "business_verification_guard", guard_namespace)
        message = types.SimpleNamespace(
            sender_business_bot=False, business_connection_id="business",
            from_user=types.SimpleNamespace(id=123), text="hello",
        )
        with self.assertRaises(Stop):
            asyncio.run(guard(types.SimpleNamespace(business_message=message), None))
        self.assertEqual(replies, [(assignments["VERIFY_LINK_UNAVAILABLE_REPLY"], None)])

        class Button:
            def __init__(self, label, **kwargs):
                self.label, self.kwargs = label, kwargs

        business_button = load_function("fantzo_business.py", "_button", {
            "_business_url": lambda *args: "",
            "TelegramInlineKeyboardButton": Button,
        })
        fallback = business_button("OPEN", "home", 0)
        self.assertEqual(fallback.kwargs, {"callback_data": "dura_link_unavailable"})
        self.assertNotIn("url", fallback.kwargs)

        alerts = []

        async def answer(copy, **kwargs):
            alerts.append((copy, kwargs))

        callback = load_function("bot_tracked.py", "smart_callback_router", {
            "_is_private_chat": lambda update: True,
            "phone_verify": types.SimpleNamespace(is_verified=lambda uid: True),
        })
        asyncio.run(callback(types.SimpleNamespace(
            effective_user=types.SimpleNamespace(id=123),
            callback_query=types.SimpleNamespace(data="dura_link_unavailable", answer=answer),
        ), None))
        self.assertEqual(alerts, [(
            "This option is temporarily unavailable. Please try again later.",
            {"show_alert": True},
        )])

    def test_hub_installer_preserves_dura_runtime_configuration(self):
        calls = []

        class Handler:
            def do_GET(self):
                pass

            def do_POST(self):
                pass

        install = load_function("ibetin_hub.py", "install_on_tracking_handler", {
            "_install_clean_runtime_ui": lambda: calls.append("overrode"),
            "logger": types.SimpleNamespace(info=lambda *args: None),
            "HUB_PATH": "/hub",
        })
        install(types.SimpleNamespace(TrackingHandler=Handler), install_runtime_ui=False)
        self.assertEqual(calls, [])
        self.assertIn(
            "hub.install_on_tracking_handler(analytics, install_runtime_ui=False)",
            (ROOT / "bot_tracked.py").read_text(encoding="utf-8"),
        )

    def test_liveline_gate_is_neutral_even_without_bot_identity(self):
        render = load_function("ibetin_liveline_v30_unified_ui.py", "_liveline_verification_page", {
            "phone_verify": types.SimpleNamespace(verification_bot_url=lambda: ""),
        })
        page = render()
        self.assertNotIn('href=""', page)
        self.assertNotIn("Ibtnofficialbot", page)
        self.assertIsNone(PUBLIC_TERMS.search(page))


if __name__ == "__main__":
    unittest.main()
