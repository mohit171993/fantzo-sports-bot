"""Focused checks for DURA's verified lead handoff and first card."""

import ast
import asyncio
from contextlib import closing
from datetime import datetime, timedelta
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlparse

import dura_entry
import dura_briefing


ROOT = Path(__file__).resolve().parent


def extract(path, name, namespace):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    node = next(
        item for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name
    )
    exec(compile(ast.Module(body=[node], type_ignores=[]), path, "exec"), namespace)
    return namespace[name]


class DuraEntryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_patch = patch.dict(os.environ, {"DB_PATH": str(Path(self.temp.name) / "dura.db")})
        self.db_patch.start()

    def tearDown(self):
        self.db_patch.stop()
        self.temp.cleanup()

    def test_only_configured_campaigns_can_reach_match(self):
        with patch.dict(os.environ, {"DURA_ENTRY_MAP": '{"dura_match":{"kind":"match","match_key":"roanuz_match-17"},"scoreboard":"liveline"}'}):
            self.assertEqual(dura_entry.resolve("dura_match"),
                             {"kind": "match", "match_key": "roanuz_match-17"})
            self.assertEqual(dura_entry.resolve("scoreboard")["kind"], "liveline")
            self.assertEqual(dura_entry.resolve("unknown")["kind"], "menu")
            self.assertEqual(dura_entry.resolve("https://evil.example")["kind"], "menu")
        with patch.dict(os.environ, {"DURA_ENTRY_MAP": '{"bad":{"kind":"match","match_key":"x?access=steal"}}'}):
            self.assertEqual(dura_entry.resolve("bad")["kind"], "menu")

    def test_handoff_survives_state_loss_and_is_consumed_once(self):
        with patch.dict(os.environ, {"DURA_ENTRY_MAP": '{"matchday":{"kind":"match","match_key":"id_123"}}'}):
            dura_entry.remember(7, "matchday")
        # The map and in-memory context are gone, but the verified handoff remains.
        self.assertEqual(dura_entry.consume(7), {"kind": "match", "match_key": "id_123"})
        self.assertEqual(dura_entry.consume(7)["kind"], "menu")

    def test_unknown_start_clears_old_route(self):
        dura_entry.remember(7, "verifyliveline")
        dura_entry.remember(7, "unknown")
        self.assertEqual(dura_entry.consume(7)["kind"], "menu")

    def test_expired_handoff_falls_back(self):
        dura_entry.remember(7, "liveline")
        import sqlite3
        with closing(sqlite3.connect(os.environ["DB_PATH"])) as conn, conn:
            conn.execute("UPDATE dura_pending_entry SET requested_at='2020-01-01T00:00:00+00:00'")
        self.assertEqual(dura_entry.consume(7)["kind"], "menu")

    def test_contact_after_restart_receives_saved_match_route(self):
        with patch.dict(os.environ, {"DURA_ENTRY_MAP": '{"matchday":{"kind":"match","match_key":"id_123"}}'}):
            dura_entry.remember(7, "matchday")
        replies = []

        async def reply(text, **kwargs):
            replies.append((text, kwargs))

        async def nothing(*args):
            return None

        namespace = {
            "phone_verify": types.SimpleNamespace(
                is_verified=lambda uid: False,
                verify_user=lambda *args, **kwargs: True,
                normalize_phone=lambda number: number,
            ),
            "ibetin_leads": types.SimpleNamespace(
                get_lead=lambda uid: {"source": "bot", "campaign": "matchday"}
            ),
            "_set_user_menu_button": nothing,
            "_notify_verified_lead": nothing,
            "app": types.SimpleNamespace(
                QUICK_MENU="quick-menu",
                core=types.SimpleNamespace(touch_user=lambda update: None,
                                           track=lambda uid, action: None),
            ),
            "reminders": types.SimpleNamespace(touch_user=lambda *args: None),
            "dura_entry": dura_entry,
            "_is_private_chat": lambda update: True,
            "conversion_keyboard": lambda uid, entry: ("first-card", entry),
            "_entry_intro": lambda entry: "match entry",
            "logger": types.SimpleNamespace(info=lambda *args: None,
                                             exception=lambda *args: None),
        }
        handler = extract("bot_tracked.py", "mobile_contact_handler", namespace)
        user = types.SimpleNamespace(id=7)
        contact = types.SimpleNamespace(user_id=7, phone_number="+999123456789")
        update = types.SimpleNamespace(
            effective_user=user,
            effective_message=types.SimpleNamespace(contact=contact, reply_text=reply),
        )
        asyncio.run(handler(update, types.SimpleNamespace(bot=object(), user_data={})))
        self.assertEqual(replies[-1][1]["reply_markup"],
                         ("first-card", {"kind": "match", "match_key": "id_123"}))
        self.assertEqual(dura_entry.consume(7)["kind"], "menu")


class FirstCardTests(unittest.TestCase):
    def test_live_line_is_primary_and_match_url_is_safe(self):
        class Button:
            def __init__(self, label, url="", **kwargs):
                self.label, self.url, self.kwargs = label, url, kwargs

        class Markup:
            def __init__(self, rows):
                self.rows = rows

        namespace = {
            "phone_verify": types.SimpleNamespace(
                live_line_url=lambda user_id, base: base + "?access=signed"
            ),
            "IBETIN_LIVE_LINE_URL": "https://dura.example/liveline",
            "dura_entry": dura_entry,
            "urlencode": urlencode,
            "site_button": lambda label, url: Button(label, url),
            "hub_button": lambda label, section: Button(label, section),
            "InlineKeyboardButton": Button,
            "InlineKeyboardMarkup": Markup,
        }
        live_url = extract("bot_tracked.py", "_entry_live_line_url", namespace)
        keyboard = extract("bot_tracked.py", "conversion_keyboard", namespace)
        generic = keyboard(7)
        self.assertIn("LIVE LINE", generic.rows[0][0].label)
        self.assertEqual(len(generic.rows), 3)
        self.assertNotIn("JOIN", generic.rows[0][0].label)
        match = keyboard(7, {"kind": "match", "match_key": "roanuz_match-17"})
        self.assertIn("YOUR MATCH", match.rows[0][0].label)
        self.assertEqual(parse_qs(urlparse(match.rows[0][0].url).query)["match"], ["roanuz_match-17"])
        unsafe = live_url(7, {"kind": "match", "match_key": "x&access=bad"})
        self.assertNotIn("match=", unsafe)

    def test_public_liveline_redirect_strips_token_and_retains_safe_match(self):
        class Handler:
            def __init__(self):
                self.headers = {}

            def send_response(self, status):
                self.status = status

            def send_header(self, name, value):
                self.headers[name] = value

            def end_headers(self):
                pass

        namespace = {
            "IBETIN_PUBLIC_LIVELINE_PATH": "/liveline",
            "v23": types.SimpleNamespace(urlencode=urlencode),
            "_set_liveline_cookie": lambda handler, token: handler.headers.update({"Set-Cookie": token}),
        }
        redirect = extract("ibetin_liveline_v30_unified_ui.py", "_send_liveline_redirect_with_cookie", namespace)
        handler = Handler()
        redirect(handler, "private-token", "roanuz_match-17")
        self.assertEqual(handler.status, 302)
        self.assertEqual(parse_qs(urlparse(handler.headers["Location"]).query)["match"], ["roanuz_match-17"])
        self.assertNotIn("private-token", handler.headers["Location"])

    def test_public_page_opens_only_a_feed_confirmed_match(self):
        skeleton = """<title>IBETIN Live Line · Visual Polish V40</title>
const qs=new URLSearchParams(location.search),TOKEN=qs.get('t')||'',API_PATH='/admin/api';
const IBETIN_LIVE_STREAM='/admin/ibetin-live-stream?t='+encodeURIComponent(TOKEN);
if(v40EventSource||!TOKEN||typeof EventSource==='undefined')return;
load('live',true);
</script></body>"""
        namespace = {
            "_page_v40_visual_polish": lambda: skeleton,
            "API_PATH": "/admin/api",
            "IBETIN_PUBLIC_LIVELINE_API_PATH": "/liveline/api",
        }
        html = extract("ibetin_liveline_v30_unified_ui.py", "_page_v40_public", namespace)()
        self.assertIn("loadCampaignEntry();", html)
        self.assertIn("allMatches.some(m=>matchKey(m)===key)", html)
        self.assertIn("Selected match is unavailable", html)
        self.assertIn("/liveline/api", html)


class TodayBriefingTests(unittest.TestCase):
    def test_old_today_button_rechecks_verification_before_briefing(self):
        events = []
        checks = iter((True, False))

        async def answer(*args):
            events.append(("answer", args))

        async def no_report(*args):
            return False

        async def menu(*args):
            events.append(("menu", args[-1]))

        async def prompt(*args):
            events.append(("prompt", args[-1]))

        async def briefing(*args):
            events.append(("briefing", args))

        namespace = {
            "phone_verify": types.SimpleNamespace(is_verified=lambda uid: next(checks)),
            "ibetin_reports": types.SimpleNamespace(handle_callback=no_report),
            "_is_private_chat": lambda update: True,
            "_set_user_menu_button": menu,
            "_prompt_mobile_verification": prompt,
            "_send_today_briefing": briefing,
        }
        namespace["_require_verified"] = extract("bot_tracked.py", "_require_verified", namespace)
        handler = extract("bot_tracked.py", "smart_callback_router", namespace)
        query = types.SimpleNamespace(data="dura_today", answer=answer, message=object())
        update = types.SimpleNamespace(callback_query=query, effective_user=types.SimpleNamespace(id=7))
        asyncio.run(handler(update, types.SimpleNamespace(bot=object())))
        self.assertIn(("prompt", "bot_start"), events)
        self.assertNotIn("briefing", [kind for kind, _detail in events])
        self.assertEqual([kind for kind, _detail in events].count("answer"), 1)

    def test_live_multiday_match_and_only_today_other_rows_are_shown(self):
        now = datetime.now(dura_briefing.INDIA)
        today = now.date()
        rows = dura_briefing.select_rows({
            "live": [{"id": "live1", "home": {"name": "India"}, "away": {"name": "Sri Lanka"},
                      "startTime": (now - timedelta(days=1)).isoformat(),
                      "state": "in_play", "homeScore": "145/3"}],
            "upcoming": [
                {"id": "next1", "home": {"name": "A"}, "away": {"name": "B"},
                 "startTime": now.isoformat()},
                {"id": "tomorrow", "home": {"name": "C"}, "away": {"name": "D"},
                 "startTime": (now + timedelta(days=1)).isoformat()},
            ],
            "results": [
                {"id": "yesterday", "home": {"name": "G"}, "away": {"name": "H"},
                 "startTime": (now - timedelta(days=1)).isoformat(), "state": "finished"},
                {"id": "done1", "home": {"name": "E"}, "away": {"name": "F"},
                 "startTime": now.isoformat(), "state": "finished"},
            ],
        }, today=today)
        self.assertEqual([item["match"]["id"] for item in rows], ["live1", "next1", "done1"])
        text = dura_briefing.format_briefing(rows)
        self.assertIn("TODAY ON DURA", text)
        self.assertIn("India vs Sri Lanka", text)
        self.assertIn("145/3", text)
        self.assertNotIn("C vs D", text)

    def test_briefing_escapes_provider_names_and_has_empty_state(self):
        rows = [{"mode": "live", "match": {
            "id": "x", "home": {"name": "<unsafe>"}, "away": {"name": "Team B"},
            "state": "in_play", "homeScore": "<score>",
        }}]
        text = dura_briefing.format_briefing(rows)
        self.assertIn("&lt;unsafe&gt;", text)
        self.assertIn("&lt;score&gt;", text)
        self.assertNotIn("<unsafe>", text)
        self.assertIn("no current briefing details", dura_briefing.format_briefing([]))


if __name__ == "__main__":
    unittest.main()
