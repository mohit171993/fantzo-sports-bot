"""DURA_MODE switch tests.

Synthetic data only: temporary SQLite DB, fake BOT_TOKEN, a local HTTP server
on 127.0.0.1 and no Telegram / provider network calls.

The end-to-end tests copy the repo to a temp dir, apply the same on-disk
rewrites as dura_brand_bootstrap.py does in production, then run the real
start chain (ibetin_crm_queue_start.main) with the blocking bot loop stubbed,
and render the Live Line page, menus, auto-replies and redirects:

* liveline mode: no gambling strings anywhere;
* full mode: identical to the baseline branch (git ref DURA_MODE_BASELINE_REF,
  default origin/durasports-production-2026-09-22), when that ref exists.

Run:  python -m unittest test_dura_mode_switch -v
"""
import asyncio
import http.client
import importlib.util
import json
import logging
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FORBIDDEN = ("casino", "odds", "bhav", "durabet", "ibetin.com", "payments", "gamble", "18+")
BASELINE_REF = os.getenv("DURA_MODE_BASELINE_REF", "origin/durasports-production-2026-09-22")
PROD_LIKE_ENV = {
    "DURA_CHANNEL_URL": "https://t.me/durasportsofficial",
    "DURA_BOT_USERNAME": "Dura_Sportsbot",
    # The production tip no longer falls back to a default bot username, and
    # the navigation self-test runs before get_me() can set one.
    "IBETIN_BOT_USERNAME": "Dura_Sportsbot",
}
SAMPLE_TEXTS = [
    "hi", "deposit", "withdraw money", "payout pending", "bonus offer", "join", "register",
    "cricket score", "live", "news", "alerts", "support", "thanks", "random words here",
]


def forbidden_in(text):
    low = str(text or "").lower()
    return [t for t in FORBIDDEN if t in low]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prod_like_copy(src: Path, dest: Path) -> Path:
    """Copy *.py and apply dura_brand_bootstrap's on-disk rewrites, as at startup."""
    dest.mkdir(parents=True, exist_ok=True)
    for path in src.glob("*.py"):
        shutil.copy2(path, dest / path.name)
    old_env = {k: os.environ.get(k) for k in PROD_LIKE_ENV}
    os.environ.update(PROD_LIKE_ENV)
    try:
        bootstrap = _load("_dura_bootstrap_copy", dest / "dura_brand_bootstrap.py")
        excluded = set(getattr(bootstrap, "REWRITE_EXCLUDED", set()))
        for path in dest.glob("*.py"):
            if path.name == "dura_brand_bootstrap.py" or path.name in excluded:
                continue
            bootstrap.patch_file(path)
    finally:
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return dest


def baseline_source(dest: Path):
    try:
        subprocess.run(["git", "rev-parse", "--verify", BASELINE_REF], cwd=ROOT, check=True,
                       capture_output=True)
        dest.mkdir(parents=True, exist_ok=True)
        archive = subprocess.run(["git", "archive", BASELINE_REF, "--", "*.py"], cwd=ROOT,
                                 check=True, capture_output=True).stdout
        subprocess.run(["tar", "-x", "-C", str(dest)], input=archive, check=True)
        return dest
    except Exception:
        return None


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def render_in_subprocess(app_dir: Path, mode, work: Path, toggle=False):
    work.mkdir(parents=True, exist_ok=True)
    port = free_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DURA_", "IBETIN_", "ROANUZ", "HIGHLIGHTLY"))}
    env.update(PROD_LIKE_ENV)
    env.update({
        "BOT_TOKEN": "123456:TEST-ONLY-NOT-A-REAL-TOKEN",
        "DB_PATH": str(work / "bot.db"),
        "ADMIN_USER_ID": "1",
        "PORT": str(port),
        "TRACKING_BASE_URL": f"http://127.0.0.1:{port}",
        "PYTHONPATH": str(app_dir),
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    if mode is not None:
        env["DURA_MODE"] = mode
    cmd = [sys.executable, str(ROOT / "test_dura_mode_switch.py"), "--render", str(port)]
    if toggle:
        cmd.append("--toggle")
    proc = subprocess.run(cmd, cwd=app_dir, env=env, capture_output=True, text=True, timeout=240)
    if proc.returncode != 0:
        raise AssertionError(f"render failed rc={proc.returncode}\n{proc.stderr[-4000:]}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


# ---------------------------------------------------------------------------
# Subprocess renderer (runs inside the prod-like copy)
# ---------------------------------------------------------------------------

def _markup_json(markup):
    try:
        import dura_mode  # noqa: F401  (absent on the baseline branch)
        markup = dura_mode.filter_markup(markup)  # what the send guard delivers
    except ImportError:
        pass
    return json.dumps(markup.to_dict() if markup is not None else None, sort_keys=True, ensure_ascii=False)


def _get(port, path, cookie=""):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    headers = {"Cookie": cookie} if cookie else {}
    conn.request("GET", path, headers=headers)
    resp = conn.getresponse()
    body = resp.read().decode("utf-8", "replace")
    conn.close()
    return {"status": resp.status, "location": resp.getheader("Location") or "", "body": body}


def _render_main(port: int, toggle: bool):
    logging.basicConfig(level=logging.ERROR)
    # Import only from the prod-like copy (never this repo checkout).
    sys.path[:] = [os.getcwd()] + [p for p in sys.path[1:] if Path(p or ".").resolve() != ROOT]
    # Production chain step 1 (dura_brand_bootstrap.py) creates the base schema;
    # its file rewrites were already applied to this copy by prod_like_copy().
    import dura_brand_bootstrap

    dura_brand_bootstrap.ensure_base_schema()
    import ibetin_crm_queue_start as entry
    import ibetin_liveline_v30_unified_ui as v30

    start = v30.app.base.ibetin_start
    runtime = start.ibetin_entry.runtime

    async def _no_network():
        return True

    start._telegram_capability_self_test = _no_network
    runtime.app.run = lambda: None
    out = {}
    try:
        entry.main()
        out["selftest"] = "PASS"
    except Exception as exc:  # the self-test raises RuntimeError on failure
        out["selftest"] = f"FAIL: {exc}"
        start.ibetin_entry.hub.install_on_tracking_handler(start.ibetin_entry.analytics)
        start.ibetin_entry.install_start_param_router()
        start.ibetin_entry.analytics.start_tracking_server()
    time.sleep(0.3)

    import ibetin_phone_verify as phone_verify
    liveline = v30.v23.liveline
    cookie = "ibetin_ll=" + phone_verify.issue_access_token(1)
    admin_t = liveline._token()
    paths = {
        "liveline_page": ("/liveline", cookie),
        "admin_liveline_page": (f"/admin/liveline-ibetinv23?t={admin_t}", ""),
        "admin_v40_preview": (f"/admin/ibetin-v40-visual-polish?t={admin_t}", ""),
        "admin_v37_promo_preview": (f"/admin/ibetin-v37-promo-preview?t={admin_t}", ""),
        "admin_v39_preview": (f"/admin/ibetin-v39-favourites?t={admin_t}", ""),
        "api_bhav": ("/liveline/api?action=bhav&matchId=1", cookie),
        "admin_api_bhav": (f"/admin/liveline-ibetinv23/api?action=bhav&matchId=1&t={admin_t}", ""),
        "meta_ch": ("/meta-ch", ""),
        "go": ("/go?source=test", ""),
        "hub_bare": ("/hub", ""),
        "hub_alerts": ("/hub?section=alerts", ""),
    }
    for section in ("home", "live", "sports", "results", "casino", "games", "payments", "support"):
        paths[f"hub_{section}"] = (f"/hub?section={section}", "")
        paths[f"hub_start_{section}"] = (f"/hub?tgWebAppStartParam={section}", "")
    http_out = {name: _get(port, p, c) for name, (p, c) in paths.items()}

    core = runtime.app.core
    autoreply = runtime.app.fantzo_autoreply
    business = runtime.app.fantzo_business
    reminders = runtime.reminders
    hub = start.hub
    menus = {
        "main_verified": _markup_json(core.main_keyboard(1)),
        "main_unverified": _markup_json(core.main_keyboard(0)),
        "join": _markup_json(core.join_keyboard()),
        "explore": _markup_json(core.explore_keyboard(1)),
        "conversion": _markup_json(runtime.conversion_keyboard(1)),
        "hub_clean_main": _markup_json(hub.clean_main_keyboard()),
        "quick_menu": _markup_json(runtime.app.QUICK_MENU),
        "autoreply_standard": autoreply.standard_reply() + _markup_json(autoreply.standard_keyboard()),
        "business_keyboard": _markup_json(business.business_keyboard(1)),
        "reminder_business": "".join(
            str(x) if isinstance(x, str) else _markup_json(x) for x in reminders._copy_for("general", 1, "business_dm", 1)),
        "reminder_bot": "".join(
            str(x) if isinstance(x, str) else _markup_json(x) for x in reminders._copy_for("cricket", 1, "bot", 1)),
        "hub_page_home": hub._page("home"),
        "hub_page_alerts": hub._page("alerts"),
        "hub_home_cards": hub._home_cards(),
        "launcher": start._launcher_page(),
        "redirects": json.dumps([start._redirect_target(s) for s in (
            "home", "sports", "live", "liveline", "casino", "games", "results", "payments", "support")]),
    }
    for text in SAMPLE_TEXTS:
        cat, reply, markup = autoreply.classify_and_reply(text)
        menus[f"autoreply:{text}"] = f"{cat}|{reply}|{_markup_json(markup)}"
        cat, reply, markup = business.classify_business_dm(text, 1)
        menus[f"business:{text}"] = f"{cat}|{reply}|{_markup_json(markup) if markup is not None else None}"
    out["http"] = http_out
    out["menus"] = menus
    out["pages"] = {"public_fn": v30._page_v40_public()}

    if toggle:
        import dura_mode

        before = _get(port, "/liveline", cookie)["body"]
        dura_mode.set_mode("full", 1)
        time.sleep(dura_mode._CACHE_TTL + 0.2)
        after = _get(port, "/liveline", cookie)["body"]
        out["toggle"] = {"before": forbidden_in(before), "after": forbidden_in(after),
                         "after_meta_ch": _get(port, "/meta-ch")["status"]}
    print(json.dumps(out, ensure_ascii=False))


def normalize(obj):
    """Strip per-run values (HMAC access tokens with expiry) before comparing."""
    text = json.dumps(obj, sort_keys=True, ensure_ascii=False)
    text = re.sub(r"access=[0-9]+\.[0-9]+\.[0-9a-f]+", "access=<token>", text)
    text = re.sub(r"access%3D[0-9]+\.[0-9]+\.[0-9a-f]+", "access%3D<token>", text)
    text = re.sub(r"127\.0\.0\.1:[0-9]+", "127.0.0.1:<port>", text)
    return json.loads(text)


# ---------------------------------------------------------------------------
# Unit tests: mode state, /mode command, send guard, CSS helper
# ---------------------------------------------------------------------------

class ModeStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {k: os.environ.get(k) for k in ("DB_PATH", "DURA_MODE", "ADMIN_USER_ID")}
        os.environ["DB_PATH"] = str(Path(self.tmp.name) / "mode.db")
        os.environ["ADMIN_USER_ID"] = "42"
        os.environ.pop("DURA_MODE", None)
        sys.modules.pop("bot", None)
        # Other suites stub `telegram` in sys.modules; use the real library here.
        self.saved_modules = {k: v for k, v in sys.modules.items() if k == "telegram" or k.startswith("telegram.")}
        if not hasattr(sys.modules.get("telegram"), "Bot"):
            for k in self.saved_modules:
                sys.modules.pop(k, None)
        import telegram.ext  # noqa: F401
        self.dm = _load("dura_mode_under_test", ROOT / "dura_mode.py")
        self.dm._PERSIST_DIR = str(Path(self.tmp.name) / "no-volume")

    def tearDown(self):
        for k in [k for k in sys.modules if k == "telegram" or k.startswith("telegram.")]:
            sys.modules.pop(k, None)
        sys.modules.update(self.saved_modules)
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def test_env_default_and_unrecognised_values(self):
        dm = self.dm
        self.assertEqual(dm.get_mode(), "liveline")
        for value, expected in (("full", "full"), ("FULL ", "full"), ("liveline", "liveline"),
                                ("casino", "liveline"), ("", "liveline")):
            os.environ["DURA_MODE"] = value
            dm.clear_cache()
            self.assertEqual(dm.get_mode(), expected, value)

    def test_persisted_mode_overrides_env_and_survives_restart(self):
        dm = self.dm
        os.environ["DURA_MODE"] = "liveline"
        dm.set_mode("full", 42)
        restarted = _load("dura_mode_restarted", ROOT / "dura_mode.py")
        restarted._PERSIST_DIR = dm._PERSIST_DIR
        self.assertEqual(restarted.get_mode(), "full")
        self.assertTrue(restarted.is_full_mode())

    def test_change_by_another_process_applies_within_seconds(self):
        dm = self.dm
        self.assertEqual(dm.get_mode(), "liveline")
        with sqlite3.connect(os.environ["DB_PATH"]) as conn:
            conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('dura_mode','full')")
        time.sleep(dm._CACHE_TTL + 0.1)
        self.assertEqual(dm.get_mode(), "full")

    def _update(self, user_id, args):
        replies = []

        async def reply_text(text, **kwargs):
            replies.append(text)

        update = types.SimpleNamespace(
            effective_user=types.SimpleNamespace(id=user_id),
            effective_message=types.SimpleNamespace(reply_text=reply_text),
        )
        return update, types.SimpleNamespace(args=args), replies

    def _run(self, user_id, args):
        from telegram.ext import ApplicationHandlerStop

        update, context, replies = self._update(user_id, args)
        with self.assertRaises(ApplicationHandlerStop):
            asyncio.run(self.dm.mode_command(update, context))
        return replies

    def test_mode_command_admin_only_logs_dubai_time_and_admin(self):
        dm = self.dm
        replies = self._run(7, ["full"])
        self.assertIn("restricted", replies[-1])
        self.assertEqual(dm.get_mode(), "liveline")

        with self.assertLogs("dura_mode", level="WARNING") as logs:
            replies = self._run(42, ["full"])
        self.assertEqual(dm.get_mode(), "full")
        self.assertIn("FULL", replies[-1])
        line = "\n".join(logs.output)
        self.assertIn("liveline -> full", line)
        self.assertIn("admin_id=42", line)
        self.assertIn("Asia/Dubai", line)
        with sqlite3.connect(os.environ["DB_PATH"]) as conn:
            row = conn.execute("SELECT changed_at_dubai, admin_id, old_mode, new_mode FROM dura_mode_changes").fetchone()
        self.assertTrue(row[0].endswith("+04:00"), row[0])
        self.assertEqual(row[1:], (42, "liveline", "full"))

        status = self._run(42, ["status"])[-1]
        self.assertIn("DURA MODE: FULL", status)
        self.assertIn("by 42", status)
        self.assertIn("GST (Dubai)", status)
        self._run(42, ["liveline"])
        self.assertEqual(dm.get_mode(), "liveline")
        self.assertIn("Usage", self._run(42, ["bogus"])[-1])
        self.assertEqual(dm.get_mode(), "liveline")

    def test_send_guard_filters_buttons_only_in_liveline(self):
        import telegram
        from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M, WebAppInfo

        dm = self.dm
        sys.modules["dura_mode"] = dm
        original = telegram.Bot._send_message
        had_flag = getattr(telegram.Bot, "_dura_mode_send_guard", False)
        captured = []

        async def fake_send(self, endpoint, data, *args, **kwargs):
            captured.append(kwargs.get("reply_markup"))

        telegram.Bot._send_message = fake_send
        telegram.Bot._dura_mode_send_guard = False
        try:
            dm.install_send_guard()
            markup = M([
                [B("🏏 OPEN LIVE LINE", callback_data="liveline_access")],
                [B("🎰 LIVE CASINO", web_app=WebAppInfo(url="https://www.durabet.com/casino"))],
                [B("💳 PAYMENTS", url="https://example.up.railway.app/hub?section=payments")],
                [B("🚀 JOIN DURA", url="https://t.me/Dura_Sportsbot/app?startapp=home")],
                [B("📢 JOIN CHANNEL", url="https://t.me/durasportsofficial")],
            ])
            bot = telegram.Bot("123456:TEST-ONLY")
            asyncio.run(bot._send_message("sendMessage", {}, reply_markup=markup))
            texts = [b.text for row in captured[-1].inline_keyboard for b in row]
            self.assertEqual(texts, ["🏏 OPEN LIVE LINE", "📢 JOIN CHANNEL"])
            dm.set_mode("full", 42)
            asyncio.run(bot._send_message("sendMessage", {}, reply_markup=markup))
            self.assertIs(captured[-1], markup)
        finally:
            telegram.Bot._send_message = original
            telegram.Bot._dura_mode_send_guard = had_flag
            sys.modules.pop("dura_mode", None)

    def test_strip_css_rules(self):
        css = ("/* BHAV comment */.a{x:1}.oddsRow,.foot{y:2}.quickMarket .p{z:3}"
               "@media(max-width:1px){.oddBox{a:1}.b{c:2}}@keyframes s{to{opacity:1}}")
        out = self.dm.strip_css_rules(css, r"odd|bhav|quickMarket")
        self.assertEqual(out, ".a{x:1}.foot{y:2}@media(max-width:1px){.b{c:2}}@keyframes s{to{opacity:1}}")


# ---------------------------------------------------------------------------
# End-to-end: real start chain, bootstrap-rewritten copy, both modes
# ---------------------------------------------------------------------------

class ModeRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.app = prod_like_copy(ROOT, base / "app")
        cls.liveline = render_in_subprocess(cls.app, None, base / "run-unset")
        cls.full = render_in_subprocess(cls.app, "full", base / "run-full")
        src = baseline_source(base / "baseline-src")
        cls.baseline = None
        if src is not None:
            cls.baseline = render_in_subprocess(prod_like_copy(src, base / "baseline-app"), None,
                                                base / "run-baseline")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_startup_self_test_passes_in_both_modes(self):
        self.assertEqual(self.liveline["selftest"], "PASS")
        self.assertEqual(self.full["selftest"], "PASS")

    def test_liveline_default_has_no_gambling_strings(self):
        leaks = {}
        for name, resp in self.liveline["http"].items():
            found = forbidden_in(resp["body"]) + forbidden_in(resp["location"])
            if found:
                leaks[f"http:{name}"] = found
        for name, text in {**self.liveline["menus"], **self.liveline["pages"]}.items():
            found = forbidden_in(text)
            if found:
                leaks[name] = found
        self.assertEqual(leaks, {})

    def test_liveline_page_is_the_live_scores_ui(self):
        page = self.liveline["http"]["liveline_page"]
        self.assertEqual(page["status"], 200)
        body = page["body"]
        for expected in ("UPCOMING", "RESULTS", "MATCH PULSE", "MY MATCHES", "SCORECARD", "BALL-BY-BALL",
                         "/liveline/stream"):
            self.assertIn(expected, body)
        for gone in ("MATCH ODDS", "LIVE BHAV", "LIVE MARKET", "SESSION MARKET", "POWERED BY",
                     "More live markets", "openIbetinLive", "__IBETIN_V37_PROMO__"):
            self.assertNotIn(gone.lower(), body.lower())
        self.assertEqual(self.liveline["http"]["admin_liveline_page"]["status"], 200)
        self.assertEqual(forbidden_in(self.liveline["http"]["admin_liveline_page"]["body"]), [])

    def test_liveline_page_scripts_parse(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not installed")
        for name in ("liveline_page", "admin_liveline_page"):
            scripts = re.findall(r"<script>(.*?)</script>", self.liveline["http"][name]["body"], re.S)
            self.assertGreaterEqual(len(scripts), 4)
            for i, code in enumerate(scripts):
                proc = subprocess.run([node, "-e", "new (require('vm').Script)(require('fs').readFileSync(0,'utf8'))"],
                                      input=code, capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, f"{name} script {i}: {proc.stderr[-400:]}")

    def test_liveline_redirects_and_routes(self):
        http = self.liveline["http"]
        for name in ("meta_ch", "admin_v37_promo_preview", "admin_v39_preview", "api_bhav", "admin_api_bhav",
                     "hub_casino", "hub_games", "hub_payments", "hub_support",
                     "hub_start_casino", "hub_start_games", "hub_start_payments", "hub_start_support"):
            self.assertEqual(http[name]["status"], 404, name)
        for name in ("hub_home", "hub_live", "hub_sports", "hub_results", "hub_start_home", "hub_start_live", "go"):
            self.assertEqual(http[name]["status"], 302, name)
            self.assertEqual(http[name]["location"], "/liveline", name)
        self.assertEqual(http["hub_bare"]["status"], 200)
        self.assertEqual(http["hub_alerts"]["status"], 200)
        self.assertIn("liveline_only", self.liveline["menus"]["autoreply:deposit"])
        self.assertIn("liveline_only", self.liveline["menus"]["business:withdraw money"])

    def test_full_mode_meta_and_markets_still_available(self):
        http = self.full["http"]
        self.assertEqual(http["meta_ch"]["status"], 200)
        self.assertIn("MATCH ODDS", http["liveline_page"]["body"])
        self.assertIn("POWERED BY", http["liveline_page"]["body"])

    def test_full_mode_matches_baseline_branch(self):
        if self.baseline is None:
            self.skipTest(f"baseline ref {BASELINE_REF} not available")
        self.assertEqual(self.baseline["selftest"], "PASS")
        full, base = normalize(self.full), normalize(self.baseline)
        for section in ("http", "menus", "pages"):
            for key in base[section]:
                self.assertEqual(full[section][key], base[section][key], f"{section}:{key}")
        # Unset DURA_MODE on the new code must differ from the baseline (switch works).
        self.assertNotEqual(normalize(self.liveline)["http"]["liveline_page"], base["http"]["liveline_page"])

    def test_runtime_toggle_takes_effect_without_restart(self):
        result = render_in_subprocess(self.app, None, Path(self.tmp.name) / "run-toggle", toggle=True)
        self.assertEqual(result["toggle"]["before"], [])
        self.assertIn("odds", result["toggle"]["after"])
        self.assertEqual(result["toggle"]["after_meta_ch"], 200)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--render":
        _render_main(int(sys.argv[2]), "--toggle" in sys.argv)
    else:
        unittest.main()
