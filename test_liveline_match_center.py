"""Unit tests for the Live Line Match Centre (pure builders + install wiring)."""
import io
import json
import types
import unittest

import liveline_match_center as mc
from liveline_match_center_ui import page_assets

WINPROB = {"data": {"match": {"result_prediction": {"automatic": {"percentage": [
    {"team_key": "ta", "value": 40}, {"team_key": "tb", "value": 60}]}}}}}

POINTS = {"data": {
    "tournament": {"key": "t1", "name": "Cup"},
    "teams": {"aa": {"key": "aa", "code": "AA", "name": "Alpha"}, "bb": {"key": "bb", "code": "BB", "name": "Beta"}},
    "rounds": [{"key": "r1", "name": "Group Stage", "groups": [{"key": "g1", "name": "Group A", "points": [
        {"team_key": "aa", "played": 2, "won": 2, "lost": 0, "points": 4, "net_run_rate": 1.5},
        {"team_key": "bb", "played": 2, "won": 0, "lost": 2, "points": 0, "net_run_rate": -1.5}]}]}],
}}

FOOTBALL = [
    {"id": 1, "homeTeam": {"name": "Arsenal"}, "awayTeam": {"name": "Chelsea"}, "league": {"name": "Premier League"},
     "country": {"name": "England"}, "state": {"description": "Second Half", "clock": 67, "score": {"current": "2 - 1"}},
     "startDate": "2026-10-01T14:00:00Z"},
    {"id": 2, "homeTeam": {"name": "Inter"}, "awayTeam": {"name": "Milan"}, "league": {"name": "Serie A"},
     "country": {"name": "Italy"}, "state": {"description": "Not started", "score": {}},
     "startDate": "2026-10-01T19:00:00Z"},
]


class BuilderTests(unittest.TestCase):
    def test_center_scorecard_and_live(self):
        c = mc.build_center(mc._SELF_TEST_NODE, WINPROB)
        inn = c["innings"][0]
        self.assertTrue(inn["batting"])
        self.assertEqual(inn["fow"][0]["score"], "12-1")
        self.assertTrue(c["isLive"])
        self.assertTrue(c["live"]["winProbability"])
        self.assertEqual(c["live"]["recentOvers"][0]["runs"], 14)
        json.dumps(c)  # must be JSON-serialisable

    def test_center_without_odds_or_players(self):
        node = json.loads(json.dumps(mc._SELF_TEST_NODE))
        node.pop("players", None)
        c = mc.build_center(node)
        self.assertIsNone(c["live"]["winProbability"])
        self.assertTrue(c["innings"])

    def test_center_tolerates_empty_node(self):
        c = mc.build_center({})
        self.assertEqual(c["innings"], [])
        self.assertIsNone(c["live"])

    def test_ball_tokens(self):
        self.assertEqual(mc._ball_token("b4")[1], 4)
        self.assertEqual(mc._ball_token("b6")[1], 6)
        label, runs, kind = mc._ball_token("w")
        self.assertEqual(kind, "wicket")
        label, runs, kind = mc._ball_token("e1,wd")
        self.assertEqual(runs, 1)
        self.assertIn("wd", label)

    def test_points(self):
        p = mc.build_points(POINTS)
        rows = p["groups"][0]["rows"]
        self.assertEqual(rows[0]["team"], "Alpha")
        self.assertEqual(rows[0]["pts"], 4)
        self.assertEqual(mc.build_points({})["groups"], [])

    def test_football(self):
        rows = mc.build_football(FOOTBALL)
        by_id = {str(r["id"]): r for r in rows}
        self.assertEqual(by_id["1"]["phase"], "live")
        self.assertEqual((by_id["1"]["hg"], by_id["1"]["ag"]), (2, 1))
        self.assertEqual(by_id["2"]["phase"], "upcoming")
        self.assertEqual(mc.build_football(None), [])


class PageTests(unittest.TestCase):
    PAGE = "<html><style>.x{}</style><body>LIVE BHAV odds<script>function tabsHtml(){}</script></body></html>"

    def test_inject_once_and_keeps_bhav(self):
        for brand in ("ibetin", "dura"):
            page = mc.inject_page(self.PAGE, brand)
            self.assertIn("__LIVELINE_MATCH_CENTRE__", page)
            self.assertIn("LIVE BHAV", page)
            self.assertEqual(mc.inject_page(page, brand), page)

    def test_assets_render_for_both_brands(self):
        for brand in ("ibetin", "dura"):
            css, js = page_assets(brand)
            self.assertIn("BHAV", js)
            self.assertNotIn("%%", css + js)


class InstallTests(unittest.TestCase):
    def _runtime(self):
        calls = []
        liveline = types.SimpleNamespace(_api=lambda h: calls.append(h.path), _page=None)
        admin = types.SimpleNamespace(_roanuz_get=lambda *a, **k: {})
        v23 = types.SimpleNamespace(liveline=liveline, v20=types.SimpleNamespace(admin=admin), _page=None,
                                    _match_payload=lambda key: ({}, mc._SELF_TEST_NODE))
        rt = types.SimpleNamespace(v23=v23, _page_v40_public=lambda: PageTests.PAGE,
                                   _page_v40_visual_polish=lambda: PageTests.PAGE)
        return rt, calls

    def test_install_passthrough_and_center(self):
        rt, calls = self._runtime()
        self.assertTrue(mc.install(rt, brand="dura"))
        self.assertIn("__LIVELINE_MATCH_CENTRE__", rt._page_v40_public())
        self.assertIn("__LIVELINE_MATCH_CENTRE__", rt.v23._page())
        handler = types.SimpleNamespace(path="/liveline/api?action=matches&mode=live")
        rt.v23.liveline._api(handler)
        self.assertEqual(calls, ["/liveline/api?action=matches&mode=live"])
        self.assertTrue(mc.install(rt, brand="dura"))  # idempotent

    def test_install_never_raises(self):
        self.assertFalse(mc.install(types.SimpleNamespace(), brand="ibetin"))


if __name__ == "__main__":
    unittest.main()
