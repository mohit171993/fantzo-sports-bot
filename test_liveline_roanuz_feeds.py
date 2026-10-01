"""Tests for the Roanuz ball-by-ball / over-summary / live-odds feeds."""
import os
import types
import unittest
from unittest import mock

import liveline_match_center as mc
import liveline_roanuz_feeds as feeds

TEAMS = {"a": {"key": "zimw", "code": "ZIM-W", "name": "Zimbabwe Women"}, "b": {"key": "rsaw", "code": "SA-W", "name": "South Africa Women"}}
NODE = {"key": "m1", "status": "started", "format": "t20", "teams": TEAMS, "play": {"live": {"innings": "b_1"}}}


def over_payload(n, prev, reprs=("r1", "b4", "w", "b6", "e1,wd", "r0", "r2")):
    balls, legal = [], 0
    for i, rp in enumerate(reprs):
        if not rp.endswith("wd"):
            legal += 1
        balls.append({"key": f"{n}-{i}", "innings": "b_1", "overs": [n - 1, max(legal, 1)], "repr": rp,
                      "comment": f"Bowler {n} to Batter {i}: something", "entry_time": n * 100 + i,
                      "batsman": {"player_key": "bat"}, "bowler": {"player_key": "bwl"},
                      "wicket": {"player_key": "bat", "wicket_type": "caught"} if rp == "w" else None,
                      "display_score": f"{n * 10}/{0} in {n - 1}.{legal} overs"})
    return {"data": {"over": {"index": {"innings": "b_1", "over_number": n}, "balls": balls},
                     "previous_over_key": prev, "next_over_key": None}}


class FakeAdmin:
    def __init__(self, n_overs=20):
        self.calls = []
        self.n = n_overs

    def _roanuz_get(self, path, ttl=10):
        self.calls.append(path)
        parts = path.strip("/").split("/")
        if parts[2] == "ball-by-ball":
            n = self.n if len(parts) == 3 else int(parts[3].rsplit("_", 1)[1])
            return over_payload(n, f"b_1_{n - 1}" if n > 1 else None)
        if parts[2] == "over-summary":
            return {"data": {"summaries": [{"index": {"innings": "b_1", "over_number": 2}, "runs": 8, "wickets": 1,
                                            "match_score": {"runs": 15, "wickets": 1, "run_rate": 7.5}},
                                           {"index": {"innings": "b_1", "over_number": 1}, "runs": 7, "wickets": 0,
                                            "match_score": {"runs": 7, "wickets": 0, "run_rate": 7.0}}],
                             "previous_page_key": None}}
        raise RuntimeError("unexpected path " + path)


def feeds_for(admin, brand="ibetin"):
    return feeds.Feeds(admin, brand, mc._cached, mc._cache_get, mc._lock_for, mc._ball_token, mc._clean)


class BuildTests(unittest.TestCase):
    def test_ball_feed_groups_overs_latest_first(self):
        payloads = [over_payload(3, "b_1_2"), over_payload(2, "b_1_1")]
        feed = feeds.build_ball_feed(payloads, TEAMS, mc._ball_token, mc._clean, lambda k: str(k).upper())
        inn = feed["innings"][0]
        self.assertEqual([o["over"] for o in inn["overs"]], [3, 2])
        over = inn["overs"][0]
        self.assertEqual(over["wickets"], 1)
        self.assertEqual(over["fours"], 1)
        self.assertEqual(over["sixes"], 1)
        self.assertEqual(over["runs"], 1 + 4 + 6 + 1 + 2)
        kinds = [b["k"] for b in over["balls"]]
        self.assertIn("wicket", kinds)
        self.assertEqual(over["balls"][2]["out"], "BAT")
        self.assertEqual(inn["label"], "SA-W")

    def test_ball_feed_empty(self):
        self.assertEqual(feeds.build_ball_feed([{}, None], TEAMS, mc._ball_token, mc._clean, str)["innings"], [])

    def test_over_summary_offset_and_totals(self):
        pages = [{"data": {"summaries": [
            {"index": {"innings": "b_1", "over_number": 0}, "runs": 7, "wickets": 0, "match_score": {"runs": 7, "wickets": 0, "run_rate": 7.0}},
            {"index": {"innings": "b_1", "over_number": 1}, "runs": 9, "wickets": 1, "match_score": {"runs": 16, "wickets": 1, "run_rate": 8.0}}]}}]
        out = feeds.build_over_summary(pages, TEAMS, str)
        overs = out["innings"][0]["overs"]
        self.assertEqual([o["over"] for o in overs], [1, 2])  # 0-based index detected from run rates
        self.assertEqual(out["innings"][0]["runs"], 16)
        out1 = feeds.build_over_summary(pages, TEAMS, str, offset=1)
        self.assertEqual([o["over"] for o in out1["innings"][0]["overs"]], [0, 1])

    def test_odds_match_winner(self):
        payload = {"data": {"match": {
            "bet_odds": {"automatic": {"decimal": [{"team_key": "zimw", "value": 1.88}, {"team_key": "rsaw", "value": 1.62}],
                                       "fractional": [{"team_key": "zimw", "numerator": 22, "denominator": 25}, {"team_key": "rsaw", "numerator": 31, "denominator": 50}]}},
            "result_prediction": {"automatic": {"percentage": [{"team_key": "zimw", "value": 25}, {"team_key": "rsaw", "value": 75}]}},
            "meta": {"format": "t20", "status": "started"}}}}
        odds = feeds.build_odds(payload, TEAMS)
        self.assertEqual(odds["favourite"], "SA-W")
        self.assertEqual(odds["teams"][0]["decimal"], 1.88)
        self.assertEqual(odds["teams"][0]["fractional"], "22/25")
        self.assertEqual(odds["teams"][1]["pct"], 75)
        self.assertIsNone(odds["draw"])
        self.assertIsNone(feeds.build_odds({}, TEAMS))

    def test_odds_test_match_draw(self):
        payload = {"data": {"match": {
            "bet_odds_with_draw": {"automatic": {"decimal": [{"team_key": "zimw", "value": 3.1}, {"team_key": "rsaw", "value": 2.2}]},
                                   "draw": {"decimal": {"value": 3.4}}},
            "result_prediction_with_draw": {"automatic": {"percentage": []}, "draw": {"value": 22}},
            "meta": {"format": "test"}}}}
        odds = feeds.build_odds(payload, TEAMS)
        self.assertEqual(odds["draw"]["decimal"], 3.4)

    def test_center_includes_odds(self):
        c = mc.build_center(NODE, {"data": {"match": {"bet_odds": {"automatic": {"decimal": [{"team_key": "zimw", "value": 2}, {"team_key": "rsaw", "value": 1.8}]}}}}})
        self.assertEqual(c["odds"]["favourite"], "SA-W")

    def test_paths(self):
        self.assertEqual(feeds.feed_path_ttl("match/k/ball-by-ball/"), feeds.BALL_LIVE_TTL)
        self.assertEqual(feeds.feed_path_ttl("match/k/ball-by-ball/b_1_3/"), feeds.DONE_TTL)
        self.assertEqual(feeds.feed_path_ttl("match/k/over-summary/"), feeds.SUMMARY_LIVE_TTL)
        self.assertIsNone(feeds.feed_path_ttl("match/k/"))
        self.assertTrue(feeds.relay_path_allowed("match/a-rz--cricket--x1/over-summary/b_1_11/"))
        self.assertFalse(feeds.relay_path_allowed("match/k/over-summary/../../x"))
        self.assertFalse(feeds.relay_path_allowed("tournament/k/points/"))


class BudgetTests(unittest.TestCase):
    def setUp(self):
        mc._cache.clear()

    def test_backfill_is_budgeted_and_cached(self):
        admin = FakeAdmin(20)
        f = feeds_for(admin)
        payloads, complete = f.ball_payloads("m1", True)
        self.assertFalse(complete)
        self.assertEqual(len(admin.calls), 1 + feeds.BALL_BUDGET)
        payloads, complete = f.ball_payloads("m1", True)
        self.assertTrue(complete)
        self.assertEqual(len(payloads), 20)
        first_total = len(admin.calls)
        self.assertEqual(first_total, 20)  # every over fetched exactly once
        f.ball_payloads("m1", True)
        self.assertEqual(len(admin.calls), first_total)  # latest still cached, older overs cached for hours

    def test_not_started_match_makes_no_feed_calls(self):
        admin = FakeAdmin(5)
        node = dict(NODE, status="not_started")
        v23 = types.SimpleNamespace(liveline=types.SimpleNamespace(), v20=types.SimpleNamespace(admin=admin),
                                    _match_payload=lambda key: ({}, node))
        rt = mc._Runtime(types.SimpleNamespace(v23=v23))
        data, status = rt.balls("m1")
        self.assertIsNone(data)
        data, status = rt.over_summary("m1")
        self.assertIsNone(data)
        self.assertEqual(admin.calls, [])

    def test_runtime_feeds(self):
        admin = FakeAdmin(3)
        v23 = types.SimpleNamespace(liveline=types.SimpleNamespace(), v20=types.SimpleNamespace(admin=admin),
                                    _match_payload=lambda key: ({}, NODE))
        rt = mc._Runtime(types.SimpleNamespace(v23=v23))
        balls, status = rt.balls("m1")
        self.assertEqual(status, "started")
        self.assertTrue(balls["complete"])
        self.assertEqual(balls["offset"], 1)
        self.assertEqual(balls["innings"][0]["overs"][0]["bowler"], "Bowler 3")  # learnt from commentary
        summary, _ = rt.over_summary("m1")
        self.assertEqual([o["over"] for o in summary["innings"][0]["overs"]], [1, 2])
        calls = len(admin.calls)
        rt.balls("m1")
        rt.over_summary("m1")
        self.assertEqual(len(admin.calls), calls)

    def test_provider_failure_is_negative_cached(self):
        admin = mock.Mock()
        admin._roanuz_get.side_effect = RuntimeError("HTTP 400")
        f = feeds_for(admin)
        for _ in range(3):
            with self.assertRaises(RuntimeError):
                f.ball_payloads("m2", True)
        self.assertEqual(admin._roanuz_get.call_count, 1)


class TransportTests(unittest.TestCase):
    def test_shared_ttl_policy(self):
        v14 = types.SimpleNamespace(_roanuz_effective_ttl=lambda path, requested: 99)
        self.assertTrue(feeds.install_shared_ttl(v14))
        self.assertEqual(v14._roanuz_effective_ttl("match/k/ball-by-ball/b_1_2/", 5), feeds.DONE_TTL)
        self.assertEqual(v14._roanuz_effective_ttl("match/k/ball-by-ball/", 5), feeds.BALL_LIVE_TTL)
        self.assertEqual(v14._roanuz_effective_ttl("match/k/", 5), 99)

    def test_dura_relay_first_then_direct(self):
        raw_calls, relay_calls = [], []
        v14 = types.SimpleNamespace(_raw_roanuz_get=lambda path, ttl=10: raw_calls.append(path) or {"direct": path})

        def relay(path):
            relay_calls.append(path)
            if "fail" in path:
                raise RuntimeError("relay HTTP 502")
            return {"relay": path}

        feeds._RELAY_STATE["paused_until"] = 0
        with mock.patch.dict(os.environ, {"IBETIN_ROANUZ_PROXY_URL": "https://relay.invalid/x", "DURA_FEED_RELAY_SECRET": "t"}):
            self.assertTrue(feeds.install_dura_relay(v14, relay_get=relay))
            self.assertEqual(v14._raw_roanuz_get("match/k/ball-by-ball/"), {"relay": "match/k/ball-by-ball/"})
            self.assertEqual(v14._raw_roanuz_get("match/k/live-match-odds/"), {"relay": "match/k/live-match-odds/"})
            self.assertEqual(v14._raw_roanuz_get("featured-matches-2/"), {"direct": "featured-matches-2/"})
            self.assertEqual(v14._raw_roanuz_get("match/fail/over-summary/"), {"direct": "match/fail/over-summary/"})
            # relay paused after a failure: straight to direct, no relay attempt
            n = len(relay_calls)
            self.assertEqual(v14._raw_roanuz_get("match/k/over-summary/"), {"direct": "match/k/over-summary/"})
            self.assertEqual(len(relay_calls), n)
        feeds._RELAY_STATE["paused_until"] = 0

    def test_relay_unconfigured_goes_direct(self):
        v14 = types.SimpleNamespace(_raw_roanuz_get=lambda path, ttl=10: {"direct": path})
        with mock.patch.dict(os.environ, {"IBETIN_ROANUZ_PROXY_URL": "", "DURA_FEED_RELAY_SECRET": ""}):
            feeds.install_dura_relay(v14, relay_get=lambda p: self.fail("relay used"))
            self.assertEqual(v14._raw_roanuz_get("match/k/ball-by-ball/"), {"direct": "match/k/ball-by-ball/"})

    def test_ibetin_relay_allowlist_extended(self):
        base = lambda v: v == "fixtures"  # noqa: E731
        v30 = types.SimpleNamespace(_allowed_dura_roanuz_proxy_path=base)
        self.assertTrue(feeds.install_relay_paths(v30))
        self.assertTrue(v30._allowed_dura_roanuz_proxy_path("fixtures"))
        self.assertTrue(v30._allowed_dura_roanuz_proxy_path("match/k1/ball-by-ball/b_1_4/"))
        self.assertFalse(v30._allowed_dura_roanuz_proxy_path("match/k1/../../secret"))


if __name__ == "__main__":
    unittest.main()
