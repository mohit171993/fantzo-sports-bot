"""Score Mini App contract tests without importing the live provider stack."""

import ast
import json
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlencode, urlparse

from mode_control import FULL, LIVE_LINE, http_route
from scores_only import merge_score_match, score_detail, score_match, score_matches, score_page


ROOT = Path(__file__).parent


def load_functions(file_name, names, bindings):
    path = ROOT / file_name
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = [node for node in tree.body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
             and node.name in names]
    scope = dict(bindings)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), scope)
    return scope


class ScoreMiniAppTests(unittest.TestCase):
    def test_missing_list_score_uses_safe_cached_detail_and_numeric_fallback(self):
        calls = []
        list_row = {"id": "12345", "state": "live", "home": {"name": "Home"},
                    "away": {"name": "Away"}, "homeScore": "", "awayScore": "",
                    "market": {"odd": 2.5}}
        detail = {"id": "12345", "homeScore": "151/4", "awayScore": "149/7",
                  "homeInfo": "19.2 ov", "report": "Home won", "bhav": "2.5"}
        v25 = SimpleNamespace(
            _fast_matches_cached=lambda mode: ([list_row], "Highlightly display fallback"),
            _score_summary_cached=lambda key: (calls.append(key) or detail),
            _roanuz_key=lambda key: False,
        )
        scope = load_functions("bot_mode_runtime.py",
                               {"_safe_rows", "_score_key", "_listed_score_match", "_safe_score_match"},
                               {"live_runtime": SimpleNamespace(v25=v25),
                                "score_matches": score_matches, "score_match": score_match,
                                "merge_score_match": merge_score_match,
                                "_cached_score_view": lambda key, kind, build: build()})
        # Loading the list must not wait on a cold per-match provider call.
        self.assertEqual(scope["_safe_rows"]("live")[0]["home_score"], "")
        self.assertEqual(calls, [])
        hydrated = scope["_safe_score_match"]("12345", "live")
        self.assertEqual(calls, ["12345"])
        merged = merge_score_match(score_match(list_row), hydrated)
        self.assertEqual((merged["home_score"], merged["away_score"]),
                         ("151/4", "149/7"))
        self.assertEqual(merged["home_info"], "19.2 ov")
        self.assertNotIn("market", json.dumps(merged).lower())
        self.assertNotIn("bhav", json.dumps(hydrated).lower())
        list_row["homeScore"] = "160/5"
        self.assertEqual(scope["_safe_score_match"]("12345", "live")["home_score"],
                         "160/5")
        with self.assertRaises(ValueError):
            scope["_safe_score_match"]("99999", "live")
        self.assertEqual(calls, ["12345", "12345"])

    def test_detail_projects_scorecard_without_provider_markets(self):
        raw = {
            "match": {"id": "cricket_1", "home": {"name": "Home"},
                      "away": {"name": "Away"}, "homeScore": "201/5",
                      "awayScore": "190/8", "odds": "2.5", "bhav": {"winner": 2.5}},
            "statistics": [{"name": "Home innings", "score": {"runs": 201, "wickets": 5},
                            "overs": "20.0", "market": "winner",
                            "inningBatsmen": [{"name": "Player", "runs": 80,
                                                "balls": 44, "odds": 99}],
                            "inningBowlers": [{"name": "Bowler", "overs": "4.0",
                                                "wickets": 2, "bhav": 22}]}],
            "markets": ["not for scores"], "session": {"run": 20},
        }
        v25 = SimpleNamespace(
            _fast_matches_cached=lambda mode: ([{"id": "cricket_1"}], "Roanuz V5 primary"),
            _match_detail_cached=lambda key: (raw, "Roanuz V5 primary"),
            _roanuz_key=lambda key: key == "cricket_1",
        )
        scope = load_functions("bot_mode_runtime.py",
                               {"_safe_rows", "_score_key", "_listed_score_match", "_safe_score_detail"},
                               {"live_runtime": SimpleNamespace(v25=v25),
                                "score_matches": score_matches, "score_detail": score_detail,
                                "merge_score_match": merge_score_match,
                                "_cached_score_view": lambda key, kind, build: build()})
        safe = scope["_safe_score_detail"]("cricket_1", "live")
        self.assertEqual(safe["match"]["home_score"], "201/5")
        self.assertEqual(safe["innings"][0]["score"], "201/5")
        self.assertEqual(safe["innings"][0]["batters"][0]["runs"], "80")
        payload = json.dumps(safe).lower()
        for blocked in ("odds", "bhav", "market", "session", "2.5", "99"):
            self.assertNotIn(blocked, payload)
        page = score_page([score_match(raw["match"])], "DURA")
        self.assertIn("telegram-web-app.js", page)
        self.assertIn("hydrateScores", page)
        self.assertNotIn("bhav", page.lower())

    def test_score_view_cache_single_flights_cold_detail(self):
        calls = []
        scope = load_functions("bot_mode_runtime.py", {"_cached_score_view"}, {
            "_score_view_lock": threading.RLock(), "_score_view_cache": {},
            "_score_view_key_locks": {}, "SCORE_VIEW_DETAIL_SECONDS": 30,
            "time": time, "threading": threading,
        })

        def build():
            calls.append("provider")
            time.sleep(0.03)
            return {"match": {"home_score": "151/4"}}

        results = []
        threads = [threading.Thread(target=lambda: results.append(
            scope["_cached_score_view"]("12345", "match", build))) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(calls, ["provider"])
        self.assertEqual(len(results), 5)

        barrier = threading.Barrier(2)
        errors = []
        def parallel(key):
            try:
                scope["_cached_score_view"](key, "match", lambda: (
                    barrier.wait(timeout=1), {"match": {"id": key}})[1])
            except Exception as exc:
                errors.append(exc)
        threads = [threading.Thread(target=parallel, args=(key,))
                   for key in ("other_1", "other_2")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])

    def test_unavailable_feed_marker_raises_instead_of_empty_page(self):
        # iBetin's existing feed keeps its own source labels; the score page
        # still treats an explicit "Feed unavailable" marker as an outage.
        scope = load_functions("bot_mode_runtime.py", {"_safe_rows"}, {
            "live_runtime": SimpleNamespace(v25=SimpleNamespace(
                _fast_matches_cached=lambda mode: ([], "Feed unavailable"))),
            "score_matches": score_matches,
        })
        with self.assertRaises(RuntimeError):
            scope["_safe_rows"]("upcoming")

    def test_score_api_is_public_in_liveline_and_keeps_signed_cookie(self):
        responses, lookups = [], []

        class Handler:
            def __init__(self, path):
                self.path = path

            def do_GET(self):
                raise AssertionError("Original Full route reached")

            def do_POST(self):
                raise AssertionError("Original Full post reached")

        verified = [False]
        scope = load_functions("bot_mode_runtime.py", {"_install_http_gate"}, {
            "analytics": SimpleNamespace(TrackingHandler=Handler),
            "_mode": lambda: LIVE_LINE, "FULL": FULL, "http_route": http_route,
            "urlparse": urlparse, "parse_qs": parse_qs, "urlencode": urlencode,
            "_verified_scores_identity": lambda handler, parsed:
                (7, "signed", True) if verified[0] else (0, "", False),
            "_safe_score_detail": lambda key, mode:
                (lookups.append((key, mode)) or {"match": {"id": key}}),
            "_send_bytes": lambda handler, status, body, content_type, token="":
                responses.append((status, body, token)),
            "phone_verify": SimpleNamespace(verify_access_token=lambda token: False),
            "json": json,
        })
        scope["_install_http_gate"]()
        # Live Line scores are public: no verification wall for new users.
        Handler("/scores/api?action=match&id=cricket_1&mode=live").do_GET()
        self.assertEqual(responses[-1][0], 200)
        self.assertEqual(responses[-1][2], "")
        self.assertEqual(lookups, [("cricket_1", "live")])
        verified[0] = True
        Handler("/scores/api?action=match&id=cricket_1&mode=live").do_GET()
        self.assertEqual(responses[-1][0], 200)
        self.assertEqual(responses[-1][2], "signed")
        self.assertEqual(lookups, [("cricket_1", "live")] * 2)
        self.assertEqual(json.loads(responses[-1][1])["detail"]["match"]["id"],
                         "cricket_1")


if __name__ == "__main__":
    unittest.main()
