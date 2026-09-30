"""Follow-a-team score alerts: follows, detection, dedupe, and clean copy."""

import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import bot as core
import dura_match_alerts as alerts

ROOT = Path(__file__).resolve().parent
BANNED = alerts._BANNED


def _match(**overrides):
    start = datetime.now(timezone.utc) + timedelta(minutes=12)
    payload = {
        "key": "ind-aus-1",
        "status": "pre_match",
        "start_at": start.timestamp(),
        "teams": {
            "a": {"name": "India", "code": "IND"},
            "b": {"name": "Australia", "code": "AUS"},
        },
        "toss": {
            "winner": "a",
            "elected": "bat and see bhav odds at https://ibetin.com/casino",
        },
        "report": "durabet betting casino payments gambling",
        "play": {"innings": {}, "innings_order": []},
    }
    payload.update(overrides)
    return payload


def _live(wickets, batters, target=None, status="in_play"):
    payload = _match(status=status, toss=None, report="bhav odds betting")
    payload["play"] = {
        "target": target,
        "innings_order": ["a_1", "b_1"] if target else ["a_1"],
        "innings": {
            "a_1": {
                "score": {"runs": 160, "wickets": 4},
                "overs": [20, 0],
                "is_completed": bool(target),
                "batsmen": [
                    {"name": "Rohit Sharma", "runs": 102, "is_out": True},
                    {"name": "Virat Kohli", "runs": 48, "is_out": False},
                ],
            }
        },
    }
    if target:
        payload["play"]["innings"]["b_1"] = {
            "score": {"runs": 40, "wickets": wickets},
            "overs": [6, 2],
            "batsmen": batters,
        }
    else:
        payload["play"]["innings"]["a_1"]["score"] = {"runs": 40, "wickets": wickets}
        payload["play"]["innings"]["a_1"]["is_completed"] = False
        payload["play"]["innings"]["a_1"]["batsmen"] = batters
        payload["play"]["innings_order"] = ["a_1"]
    return payload


class AlertTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        core.DB_PATH = str(Path(self.tmp.name) / "alerts.db")
        core.init_db()
        alerts.ensure_tables()
        alerts.SEND_GAP_SECONDS = 0

    def tearDown(self):
        self.tmp.cleanup()

    def test_follow_unfollow_and_player(self):
        followed = alerts.follow(7, "India")
        self.assertTrue(followed["ok"])
        self.assertEqual(followed["name_key"], "india")
        self.assertTrue(alerts.follow(7, "Virat Kohli", "player")["ok"])
        self.assertFalse(alerts.follow(7, "   ")["ok"])
        names = {(row["kind"], row["display_name"]) for row in alerts.list_follows(7)}
        self.assertEqual(names, {("team", "India"), ("player", "Virat Kohli")})
        self.assertEqual(alerts.unfollow(7, "India"), 1)
        self.assertEqual(alerts.unfollow(7, "Virat Kohli", "player"), 1)
        self.assertEqual(alerts.list_follows(7), [])
        self.assertEqual(alerts.parse_follow_args(["player", "Virat", "Kohli"]), ("player", "Virat Kohli"))
        self.assertEqual(alerts.parse_follow_args(["India"]), ("team", "India"))

    def test_event_detection_and_clean_copy(self):
        now = datetime.now(timezone.utc)
        toss = alerts.snapshot_from(_match())
        toss_events = alerts.events_from_snapshot(toss, now)
        self.assertIn("toss", [event.event_key for event in toss_events])

        soon = alerts.snapshot_from(_match(status="scheduled", toss=None))
        soon_events = alerts.events_from_snapshot(soon, now)
        self.assertEqual([event.event_key for event in soon_events], ["prestart"])

        later = alerts.snapshot_from(
            _match(status="scheduled", toss=None, start_at=(now + timedelta(hours=5)).timestamp())
        )
        self.assertEqual(alerts.events_from_snapshot(later, now), [])

        live = alerts.snapshot_from(
            _live(
                1,
                [{"name": "Virat Kohli", "runs": 54, "is_out": False}, {"name": "Shubman Gill", "runs": 12, "is_out": True}],
            )
        )
        live_keys = {event.event_key for event in alerts.events_from_snapshot(live, now)}
        self.assertIn("wicket:a_1:1", live_keys)
        self.assertIn("fifty:a_1:virat kohli", live_keys)
        self.assertNotIn("hundred:a_1:virat kohli", live_keys)

        hundred = alerts.snapshot_from(
            _live(1, [{"name": "Virat Kohli", "runs": 100, "is_out": False}])
        )
        hundred_keys = {event.event_key for event in alerts.events_from_snapshot(hundred, now)}
        self.assertIn("hundred:a_1:virat kohli", hundred_keys)
        self.assertNotIn("fifty:a_1:virat kohli", hundred_keys)

        break_payload = _live(
            0,
            [],
            target=161,
            status="innings_break",
        )
        break_events = alerts.events_from_snapshot(alerts.snapshot_from(break_payload), now)
        self.assertTrue(any(event.alert_type == "innings_break" and "Target 161" in event.body for event in break_events))

        close_payload = _live(
            8,
            [{"name": "Alex Carey", "runs": 20, "is_out": False}],
            target=181,
            status="in_play",
        )
        close_payload["play"]["innings"]["b_1"]["score"] = {"runs": 170, "wickets": 8}
        close_events = alerts.events_from_snapshot(alerts.snapshot_from(close_payload), now)
        self.assertTrue(any(event.alert_type == "close_finish" for event in close_events))

        final_payload = _match(status="completed", winner="a")
        final_events = alerts.events_from_snapshot(alerts.snapshot_from(final_payload), now)
        self.assertEqual(final_events[-1].event_key, "final")
        self.assertIn("India won", final_events[-1].body)

        bodies = []
        for event in toss_events + soon_events + alerts.events_from_snapshot(live, now) + break_events + close_events + final_events:
            bodies.append(event.body)
            self.assertIsNone(BANNED.search(event.body), event.body)
            self.assertNotIn("http", event.body.casefold())
            self.assertNotIn("t.me/", event.body.casefold())

    def test_dedupe_baseline_mute_and_queue(self):
        alerts.follow(7, "India")
        alerts.follow(8, "Virat Kohli", "player")
        alerts.follow(9, "England")

        first = _live(1, [{"name": "Virat Kohli", "runs": 40, "is_out": False}, {"name": "Shubman Gill", "runs": 4, "is_out": True}])
        self.assertEqual(alerts.observe_nodes([first]), 0)

        second = _live(
            2,
            [
                {"name": "Virat Kohli", "runs": 52, "is_out": False},
                {"name": "Shubman Gill", "runs": 4, "is_out": True},
                {"name": "Suryakumar Yadav", "runs": 1, "is_out": True},
            ],
        )
        queued = alerts.observe_nodes([second])
        self.assertGreaterEqual(queued, 1)
        with core.db() as conn:
            rows = conn.execute(
                "SELECT user_id, event_key, status FROM dura_alert_outbox ORDER BY id"
            ).fetchall()
        keys = {(row["user_id"], row["event_key"]) for row in rows}
        self.assertIn((7, "fifty:a_1:virat kohli"), keys)
        self.assertIn((8, "fifty:a_1:virat kohli"), keys)
        self.assertIn((7, "wicket:a_1:2"), keys)
        self.assertNotIn((8, "wicket:a_1:2"), keys)
        self.assertNotIn((9, "wicket:a_1:2"), keys)
        self.assertTrue(all(row["status"] == "queued" for row in rows))

        again = alerts.observe_nodes([second])
        self.assertEqual(again, 0)
        with core.db() as conn:
            count = conn.execute("SELECT COUNT(*) AS c FROM dura_alert_outbox").fetchone()["c"]
        self.assertEqual(count, len(rows))

        alerts.set_pref(7, "type:wicket", False)
        third = _live(
            3,
            [
                {"name": "Virat Kohli", "runs": 52, "is_out": False},
                {"name": "Shubman Gill", "runs": 4, "is_out": True},
                {"name": "Suryakumar Yadav", "runs": 1, "is_out": True},
                {"name": "Hardik Pandya", "runs": 0, "is_out": True},
            ],
        )
        alerts.observe_nodes([third])
        with core.db() as conn:
            muted = conn.execute(
                "SELECT user_id FROM dura_alert_outbox WHERE event_key='wicket:a_1:3'"
            ).fetchall()
        self.assertEqual(muted, [])

        alerts.follow(11, "India")
        self.assertGreaterEqual(alerts.observe_nodes([_match()]), 1)
        with core.db() as conn:
            body = conn.execute(
                "SELECT body FROM dura_alert_outbox WHERE user_id=11 AND event_key='toss'"
            ).fetchone()["body"]
        self.assertIsNone(BANNED.search(body), body)
        self.assertIn("TOSS", body)
        self.assertIn("India", body)

        match_id = alerts.catalog_page("team", 0)[0]
        self.assertTrue(any(item["display_name"] == "India" for item in match_id))

    def test_close_finish_is_off_until_enabled_and_match_mute_holds(self):
        alerts.follow(4, "Australia")
        close_payload = _live(
            8,
            [{"name": "Alex Carey", "runs": 22, "is_out": False}],
            target=181,
            status="in_play",
        )
        close_payload["play"]["innings"]["b_1"]["score"] = {"runs": 170, "wickets": 8}
        self.assertEqual(alerts.observe_nodes([close_payload]), 0)
        with core.db() as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS c FROM dura_alert_outbox").fetchone()["c"],
                0,
            )
        alerts.set_pref(4, "type:close_finish", True)
        enabled = _live(
            9,
            [{"name": "Alex Carey", "runs": 30, "is_out": False}],
            target=201,
            status="in_play",
        )
        enabled["key"] = "close-enabled"
        enabled["play"]["innings"]["b_1"]["score"] = {"runs": 190, "wickets": 9}
        self.assertGreaterEqual(alerts.observe_nodes([enabled]), 1)
        with core.db() as conn:
            close_row = conn.execute(
                "SELECT body FROM dura_alert_outbox WHERE user_id=4 AND event_key='close_finish'"
            ).fetchone()
        self.assertIsNotNone(close_row)
        self.assertIsNone(BANNED.search(close_row["body"]), close_row["body"])
        self.assertIn("needed", close_row["body"])

        alerts.unfollow(4, "Australia")
        alerts.follow(5, "India")
        final_payload = _match(status="completed", winner="a", key="final-match")
        self.assertGreaterEqual(alerts.observe_nodes([final_payload]), 1)
        with core.db() as conn:
            match_key = conn.execute(
                "SELECT match_key FROM dura_alert_outbox WHERE user_id=5"
            ).fetchone()["match_key"]
            before = conn.execute(
                "SELECT COUNT(*) AS c FROM dura_alert_outbox WHERE user_id=5"
            ).fetchone()["c"]
        alerts.mute_match(5, match_key)
        chased = _live(
            1,
            [{"name": "Virat Kohli", "runs": 60, "is_out": False}],
            target=161,
            status="in_play",
        )
        chased["key"] = match_key
        alerts.observe_nodes([chased])
        with core.db() as conn:
            after = conn.execute(
                "SELECT COUNT(*) AS c FROM dura_alert_outbox WHERE user_id=5"
            ).fetchone()["c"]
        self.assertEqual(after, before)

    def test_drain_sends_each_event_once_and_survives_another_pass(self):
        alerts.follow(7, "India")
        alerts.observe_nodes([_match()])
        sent = []

        class Bot:
            async def send_message(self, chat_id, text, **kwargs):
                sent.append((chat_id, text, kwargs))

        delivered = asyncio.run(alerts.drain_outbox(Bot()))
        self.assertEqual(delivered, 1)
        self.assertEqual(len(sent), 1)
        chat_id, text, kwargs = sent[0]
        self.assertEqual(chat_id, 7)
        self.assertIsNone(BANNED.search(text), text)
        markup = kwargs["reply_markup"]
        button = markup.inline_keyboard[0][0]
        self.assertEqual(button.text, "🔕 Mute this match")
        self.assertIsNone(button.url)
        self.assertIsNone(button.web_app)
        self.assertIsNone(BANNED.search(button.text))

        self.assertEqual(asyncio.run(alerts.drain_outbox(Bot())), 0)
        self.assertEqual(alerts.observe_nodes([_match()]), 0)
        with core.db() as conn:
            status = conn.execute(
                "SELECT status FROM dura_alert_outbox WHERE user_id=7"
            ).fetchone()["status"]
        self.assertEqual(status, "sent")

    def test_blocked_user_is_not_retried(self):
        from telegram.error import Forbidden

        alerts.follow(7, "India")
        alerts.observe_nodes([_match()])

        class Bot:
            async def send_message(self, *args, **kwargs):
                raise Forbidden("blocked")

        self.assertEqual(asyncio.run(alerts.drain_outbox(Bot())), 0)
        with core.db() as conn:
            status = conn.execute("SELECT status FROM dura_alert_outbox").fetchone()["status"]
        self.assertEqual(status, "blocked")
        self.assertEqual(asyncio.run(alerts.drain_outbox(Bot())), 0)

    def test_inline_picker_follows_and_unfollows(self):
        alerts.observe_nodes([_match()])
        catalog = {item["display_name"]: item["id"] for item in alerts.catalog_page("team", 0)[0]}
        shown = {}

        class Query:
            def __init__(self, data):
                self.data = data
                self.message = SimpleNamespace()

            async def answer(self):
                return None

            async def edit_message_text(self, text, **kwargs):
                shown["text"] = text
                shown["markup"] = kwargs.get("reply_markup")

        asyncio.run(alerts.handle_callback(SimpleNamespace(
            callback_query=Query(f"durafollow:on:{catalog['India']}"),
            effective_user=SimpleNamespace(id=3),
        ), None))
        self.assertEqual([row["display_name"] for row in alerts.list_follows(3)], ["India"])
        self.assertIsNone(BANNED.search(shown["text"]))

        asyncio.run(alerts.handle_callback(SimpleNamespace(
            callback_query=Query(f"durafollow:off:{catalog['India']}"),
            effective_user=SimpleNamespace(id=3),
        ), None))
        self.assertEqual(alerts.list_follows(3), [])

    def test_feed_hook_reuses_existing_fetch_path(self):
        source = (ROOT / "ibetin_liveline_v23_stable_feed.py").read_text(encoding="utf-8")
        self.assertIn("dura_match_alerts.note_observed", source)
        self.assertIn("_note_team_alerts", source)
        self.assertEqual(source.count("def _fast_matches"), 2)
        tracked = (ROOT / "bot_tracked.py").read_text(encoding="utf-8")
        module = (ROOT / "dura_match_alerts.py").read_text(encoding="utf-8")
        self.assertIn("dura_match_alerts.install(application)", tracked)
        self.assertIn('callback_data="durafollow:menu"', tracked)
        self.assertIn('CommandHandler("follow", follow_command)', module)
        self.assertIn('CommandHandler("myteams", myteams_command)', module)


if __name__ == "__main__":
    unittest.main()
