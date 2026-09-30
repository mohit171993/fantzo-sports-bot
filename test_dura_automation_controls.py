import ast
import asyncio
import sqlite3
import tempfile
import types
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent


def load_function(path, name, namespace):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name)
    module = ast.Module(body=[function], type_ignores=[])
    exec(compile(module, str(ROOT / path), "exec"), namespace)
    return namespace[name]


class AutomationStatusTests(unittest.TestCase):
    def test_delivery_breakdown_counts_only_last_24_hours(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reminders.db"
            recent = datetime.now(timezone.utc).isoformat()
            old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
            with sqlite3.connect(path) as conn:
                conn.executescript("""
                    CREATE TABLE reminder_sends(source TEXT, status TEXT, sent_at TEXT);
                    CREATE TABLE channel_campaigns(campaign_key TEXT, sent_at TEXT,
                        message_id INTEGER, status TEXT);
                """)
                conn.executemany(
                    "INSERT INTO reminder_sends VALUES(?,?,?)",
                    [
                        ("bot", "sent", recent),
                        ("bot", "failed", recent),
                        ("business_dm", "bad_request", recent),
                        ("business_dm", "blocked", recent),
                        ("business_dm", "sent", old),
                    ],
                )
                conn.execute(
                    "INSERT INTO channel_campaigns VALUES(?,?,?,?)",
                    ("yesterday", recent, 101, "sent"),
                )
            conn.close()

            @contextmanager
            def db():
                connection = sqlite3.connect(path)
                connection.row_factory = sqlite3.Row
                try:
                    yield connection
                finally:
                    connection.close()

            namespace = {
                "core": types.SimpleNamespace(db=db),
                "ensure_tables": lambda: None,
                "datetime": datetime,
                "timedelta": timedelta,
                "timezone": timezone,
                "APP_TZ": ZoneInfo("Asia/Kolkata"),
                "CHANNEL_AUTOPOST_HOUR": 10,
                "CHANNEL_AUTOPOST_MINUTE": 0,
                "CHANNEL_CATCHUP_HOURS": 6,
                "CHANNEL_RETRY_MINUTES": 15,
                "_daily_channel_campaign_key": lambda _: "today",
                "_parse_dt": datetime.fromisoformat,
                "reminders_enabled": lambda: True,
                "channel_autopost_enabled": lambda: True,
            }
            status = load_function("fantzo_reminders.py", "automation_status", namespace)()
            self.assertEqual(status["reminder_sent_24h"], 1)
            self.assertEqual(status["reminder_delivery_24h"]["bot"]["sent"], 1)
            self.assertEqual(status["reminder_delivery_24h"]["bot"]["failed"], 1)
            self.assertEqual(status["reminder_delivery_24h"]["business_dm"]["bad_request"], 1)
            self.assertEqual(status["reminder_delivery_24h"]["business_dm"]["blocked"], 1)
            self.assertEqual(status["reminder_delivery_24h"]["business_dm"]["sent"], 0)
            self.assertEqual(status["last_channel"]["message_id"], 101)


class ChannelLaunchIsolationTests(unittest.TestCase):
    def test_staging_opt_out_prevents_the_hard_coded_channel_send(self):
        tree = ast.parse((ROOT / "fantzo_reminders.py").read_text(encoding="utf-8"))
        assignment = next(
            node for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "CHANNEL_LAUNCH_ENABLED"
                    for target in node.targets)
        )

        def configured(value):
            namespace = {"os": types.SimpleNamespace(
                getenv=lambda name, default: value if name == "IBETIN_CHANNEL_LAUNCH_ENABLED" and value is not None else default,
            )}
            exec(compile(ast.Module(body=[assignment], type_ignores=[]), "fantzo_reminders.py", "exec"), namespace)
            return namespace["CHANNEL_LAUNCH_ENABLED"]

        self.assertTrue(configured(None))  # unchanged production default
        self.assertFalse(configured("false"))

        def unexpected(*_args, **_kwargs):
            raise AssertionError("Staging opt-out touched the database or Telegram")

        launcher = load_function("fantzo_reminders.py", "send_liveline_channel_launch", {
            "CHANNEL_LAUNCH_ENABLED": configured("false"),
            "ensure_tables": unexpected,
        })
        self.assertFalse(asyncio.run(launcher(types.SimpleNamespace(bot=types.SimpleNamespace(
            send_message=unexpected,
        )))))


class DirectReplyToggleTests(unittest.TestCase):
    def test_verified_direct_reply_respects_admin_toggle(self):
        replies = []

        async def reply_text(*args, **kwargs):
            replies.append((args, kwargs))

        message = types.SimpleNamespace(text="live score", reply_text=reply_text)
        update = types.SimpleNamespace(
            effective_user=types.SimpleNamespace(id=123), effective_message=message,
        )
        enabled = {"value": False}
        namespace = {
            "phone_verify": types.SimpleNamespace(is_verified=lambda _: True),
            "_is_private_chat": lambda update: True,
            "app": types.SimpleNamespace(
                fantzo_autoreply=types.SimpleNamespace(is_enabled=lambda: enabled["value"]),
                core=types.SimpleNamespace(touch_user=lambda _: None, track=lambda *_: None),
            ),
            "fantzo_business": types.SimpleNamespace(
                classify_business_dm=lambda *_: ("sports", "DURA reply", None),
            ),
            "logger": types.SimpleNamespace(exception=lambda *_: None),
            "reminders": types.SimpleNamespace(set_opt_out=lambda *_: None),
            "ibetin_leads": types.SimpleNamespace(set_status=lambda *_: None),
        }
        handler = load_function("bot_tracked.py", "verified_fixed_reply_handler", namespace)
        asyncio.run(handler(update, None))
        self.assertEqual(replies, [])

        enabled["value"] = True
        asyncio.run(handler(update, None))
        self.assertEqual(len(replies), 1)
        self.assertEqual(replies[0][0][0], "DURA reply")

    def test_opt_out_still_works_while_auto_reply_paused(self):
        replies = []
        status_updates = []
        opt_outs = []

        async def reply_text(*args, **kwargs):
            replies.append((args, kwargs))

        namespace = {
            "phone_verify": types.SimpleNamespace(is_verified=lambda _: True),
            "_is_private_chat": lambda update: True,
            "app": types.SimpleNamespace(
                fantzo_autoreply=types.SimpleNamespace(is_enabled=lambda: False),
            ),
            "reminders": types.SimpleNamespace(
                set_opt_out=lambda source, uid, value: opt_outs.append((source, uid, value)),
            ),
            "ibetin_leads": types.SimpleNamespace(
                set_status=lambda uid, status: status_updates.append((uid, status)),
            ),
        }
        update = types.SimpleNamespace(
            effective_user=types.SimpleNamespace(id=123),
            effective_message=types.SimpleNamespace(text="stop", reply_text=reply_text),
        )
        handler = load_function("bot_tracked.py", "verified_fixed_reply_handler", namespace)
        asyncio.run(handler(update, None))
        self.assertEqual(status_updates, [(123, "dnc")])
        self.assertEqual(opt_outs, [("bot", 123, True), ("business_dm", 123, True)])
        self.assertEqual(len(replies), 1)


if __name__ == "__main__":
    unittest.main()
