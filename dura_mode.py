"""Central DURA_MODE switch for the Dura Telegram bot.

Two modes:

* ``liveline`` (default when unset/unrecognised): a pure live-scores and
  match-updates bot.  Odds/market panels, casino/games/payments entry points,
  betting-site links/redirects, deposit auto-replies, the /meta-ch affiliate
  page and promo JS/CSS are all switched off.
* ``full``: the historical behaviour, unchanged.

The mode is persisted in the bot's SQLite DB (``settings`` table, key
``dura_mode``) so it survives restarts.  Until an admin sets it with
``/mode``, the ``DURA_MODE`` environment variable is the default.  Every
feature site calls :func:`is_full_mode` at request/render time (never at
import time); the value is cached for ``_CACHE_TTL`` seconds only, so a
``/mode`` change takes effect within seconds without a redeploy.

NOTE: dura_brand_bootstrap.py deliberately skips this file, so the literal
domain/term lists below are never rewritten on disk at startup.
"""
from __future__ import annotations

import logging
import os
import re
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

logger = logging.getLogger("dura_mode")

MODE_LIVELINE = "liveline"
MODE_FULL = "full"
MODES = (MODE_LIVELINE, MODE_FULL)
DEFAULT_MODE = MODE_LIVELINE
SETTING_KEY = "dura_mode"
DUBAI = ZoneInfo("Asia/Dubai")
_CACHE_TTL = 2.0
_PERSIST_DIR = "/app/ibetin_bot_persistent"

_lock = threading.Lock()
_cache = {"mode": None, "at": 0.0}


# ---------------------------------------------------------------------------
# Mode state
# ---------------------------------------------------------------------------

def normalize_mode(value) -> str:
    value = str(value or "").strip().lower()
    return value if value in MODES else DEFAULT_MODE


def env_default_mode() -> str:
    return normalize_mode(os.getenv("DURA_MODE", ""))


def _db_path() -> str:
    # bot.DB_PATH is resolved after the persistent-volume bootstrap in the
    # runtime entry point; fall back to the same env var / default as bot.py.
    core = sys.modules.get("bot")
    path = str(getattr(core, "DB_PATH", "") or "").strip()
    if path:
        return path
    # Same rule as the runtime entry point: the Railway volume wins when mounted.
    if os.path.isdir(_PERSIST_DIR):
        return os.path.join(_PERSIST_DIR, "ibetin_bot.db")
    return os.getenv("DB_PATH", "").strip() or "fantzo_bot.db"


def _connect():
    path = _db_path()
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dura_mode_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            changed_at_utc TEXT NOT NULL,
            changed_at_dubai TEXT NOT NULL,
            admin_id INTEGER NOT NULL,
            old_mode TEXT NOT NULL,
            new_mode TEXT NOT NULL
        )
        """
    )
    return conn


def _stored_mode():
    """Return the persisted mode, or None when no admin has set one."""
    with _connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (SETTING_KEY,)).fetchone()
    if not row:
        return None
    value = str(row["value"] or "").strip().lower()
    return value if value in MODES else None


def get_mode() -> str:
    now = time.monotonic()
    with _lock:
        if _cache["mode"] and now - _cache["at"] < _CACHE_TTL:
            return _cache["mode"]
    try:
        mode = _stored_mode() or env_default_mode()
    except Exception as exc:
        # Never fail open into gambling features because the DB is busy.
        logger.warning("DURA_MODE read failed (%s); using env default", type(exc).__name__)
        mode = env_default_mode()
    with _lock:
        _cache["mode"], _cache["at"] = mode, now
    return mode


def clear_cache() -> None:
    with _lock:
        _cache["mode"], _cache["at"] = None, 0.0


def is_full_mode() -> bool:
    return get_mode() == MODE_FULL


def is_liveline_mode() -> bool:
    return not is_full_mode()


def dubai_now() -> datetime:
    return datetime.now(DUBAI)


def set_mode(mode: str, admin_id: int) -> dict:
    new_mode = str(mode or "").strip().lower()
    if new_mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    old_mode = get_mode()
    utc_now = datetime.now(timezone.utc)
    dubai = utc_now.astimezone(DUBAI)
    with _connect() as conn:
        conn.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (SETTING_KEY, new_mode),
        )
        conn.execute(
            "INSERT INTO dura_mode_changes(changed_at_utc,changed_at_dubai,admin_id,old_mode,new_mode) "
            "VALUES(?,?,?,?,?)",
            (utc_now.isoformat(), dubai.isoformat(), int(admin_id), old_mode, new_mode),
        )
    clear_cache()
    stamp = dubai.strftime("%Y-%m-%d %H:%M:%S")
    logger.warning(
        "DURA_MODE changed %s -> %s by admin_id=%s at %s Asia/Dubai (GST)",
        old_mode, new_mode, int(admin_id), stamp,
    )
    return {"old": old_mode, "new": new_mode, "admin_id": int(admin_id), "dubai": stamp}


def status() -> dict:
    try:
        stored = _stored_mode()
        with _connect() as conn:
            last = conn.execute(
                "SELECT changed_at_dubai, admin_id, old_mode, new_mode FROM dura_mode_changes "
                "ORDER BY id DESC LIMIT 1"
            ).fetchone()
        last = dict(last) if last else None
    except Exception:
        stored, last = None, None
    return {
        "mode": get_mode(),
        "source": "db" if stored else "env DURA_MODE default",
        "env_default": env_default_mode(),
        "last_change": last,
    }


# ---------------------------------------------------------------------------
# Gambling classification (used by the Telegram send guard and HTTP gate)
# ---------------------------------------------------------------------------

# Case-insensitive terms that must never appear in liveline-mode output.
FORBIDDEN_TERMS = ("casino", "odds", "bhav", "durabet", "ibetin.com", "payments", "gamble", "18+")

_GAMBLING_HOSTS = ("ibetin.com", "durabet.com", "ibetaffiliate.com")
# Mini App sections that lead to the betting site.  home/live/sports/results
# are routed to the bot's own Live Line page in liveline mode instead.
BLOCKED_SECTIONS = frozenset({"casino", "games", "payments", "support", "slots", "registration"})
LIVELINE_SECTIONS = frozenset({"home", "live", "sports", "results", "liveline"})
_GAMBLING_LABEL = re.compile(
    r"casino|\bgames?\b|payment|deposit|withdraw|payout|cash ?out|\bslots?\b|\bbet\b|betting|bonus|"
    r"\bjoin\b(?!\s+(?:our\s+)?channel)|register|registration|sign ?up|🎰|🎮|💳",
    re.I,
)


def find_forbidden(text) -> list:
    low = str(text or "").lower()
    return [term for term in FORBIDDEN_TERMS if term in low]


def _env_betting_hosts() -> set:
    hosts = set()
    for name in ("IBETIN_HOME_URL", "IBETIN_MINI_APP_URL", "FANTZO_MINI_APP_URL"):
        host = (urlparse(os.getenv(name, "").strip()).hostname or "").lower()
        if host and not host.endswith(("railway.app", "t.me", "telegram.me")):
            hosts.add(host)
    return hosts


def is_betting_host(host: str) -> bool:
    host = str(host or "").lower().strip(".")
    if not host:
        return False
    if any(host == h or host.endswith("." + h) for h in _GAMBLING_HOSTS):
        return True
    return host in _env_betting_hosts()


def url_section(url: str) -> str:
    """Hub section or Telegram startapp parameter carried by an URL, if any."""
    try:
        parsed = urlparse(str(url or ""))
        query = parse_qs(parsed.query, keep_blank_values=True)
    except Exception:
        return ""
    for key in ("section", "startapp", "tgWebAppStartParam"):
        value = (query.get(key) or [""])[0].strip().lower()
        if value:
            return value
    return ""


def is_gambling_url(url: str) -> bool:
    if not url:
        return False
    try:
        parsed = urlparse(str(url))
    except Exception:
        return False
    if is_betting_host(parsed.hostname or ""):
        return True
    if parsed.path.rstrip("/") in {"/meta-ch", "/meta-ch-v2"}:
        return True
    return url_section(url) in BLOCKED_SECTIONS


def is_gambling_button(button) -> bool:
    text = str(getattr(button, "text", "") or "")
    urls = [getattr(button, "url", None)]
    web_app = getattr(button, "web_app", None)
    if web_app is not None:
        urls.append(getattr(web_app, "url", None))
    login_url = getattr(button, "login_url", None)
    if login_url is not None:
        urls.append(getattr(login_url, "url", None))
    if any(is_gambling_url(u) for u in urls if u):
        return True
    return bool(_GAMBLING_LABEL.search(text))


def filter_markup(markup):
    """Drop betting buttons from an inline/reply keyboard (liveline mode only)."""
    if markup is None or is_full_mode():
        return markup
    try:
        from telegram import InlineKeyboardMarkup, ReplyKeyboardMarkup
    except Exception:  # pragma: no cover - telegram always present at runtime
        return markup
    if isinstance(markup, InlineKeyboardMarkup):
        rows = [[b for b in row if not is_gambling_button(b)] for row in markup.inline_keyboard]
        rows = [row for row in rows if row]
        if sum(len(r) for r in rows) == sum(len(r) for r in markup.inline_keyboard):
            return markup
        return InlineKeyboardMarkup(rows) if rows else None
    if isinstance(markup, ReplyKeyboardMarkup):
        rows = [[b for b in row if not is_gambling_button(b)] for row in markup.keyboard]
        rows = [row for row in rows if row]
        if sum(len(r) for r in rows) == sum(len(r) for r in markup.keyboard):
            return markup
        if not rows:
            return None
        return ReplyKeyboardMarkup(
            rows,
            resize_keyboard=markup.resize_keyboard,
            one_time_keyboard=markup.one_time_keyboard,
            selective=markup.selective,
            input_field_placeholder=markup.input_field_placeholder,
            is_persistent=markup.is_persistent,
        )
    return markup


def install_send_guard() -> bool:
    """Last line of defence: filter reply_markup on every outgoing Telegram call.

    Explicit mode checks at each feature site produce the clean liveline
    menus; this guard only removes anything a legacy layer still attaches.
    It is a no-op in full mode.
    """
    try:
        import telegram
    except Exception:
        return False
    bot_cls = telegram.Bot
    if getattr(bot_cls, "_dura_mode_send_guard", False):
        return True
    original = bot_cls._send_message

    async def guarded_send_message(self, endpoint, data, *args, **kwargs):
        if not is_full_mode():
            try:
                if "reply_markup" in kwargs:
                    before = kwargs["reply_markup"]
                    kwargs["reply_markup"] = filter_markup(before)
                    changed = kwargs["reply_markup"] is not before
                elif len(args) >= 2:
                    args = list(args)
                    before = args[1]
                    args[1] = filter_markup(before)
                    changed = args[1] is not before
                    args = tuple(args)
                else:
                    changed = False
                if changed:
                    logger.info("DURA_MODE liveline guard removed betting buttons endpoint=%s", endpoint)
            except Exception as exc:
                logger.warning("DURA_MODE send guard skipped: %s", type(exc).__name__)
        return await original(self, endpoint, data, *args, **kwargs)

    bot_cls._send_message = guarded_send_message
    bot_cls._dura_mode_send_guard = True
    return True


# ---------------------------------------------------------------------------
# CSS helper for the Live Line page
# ---------------------------------------------------------------------------

def _match_brace(css: str, open_idx: int) -> int:
    depth = 0
    for i in range(open_idx, len(css)):
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return len(css) - 1


def strip_css_rules(css: str, selector_pattern) -> str:
    """Remove CSS comments and every selector matching ``selector_pattern``.

    Handles flat rules, comma selector lists and nested @media/@supports.
    A rule is dropped entirely when all of its selectors match.
    """
    pattern = re.compile(selector_pattern, re.I) if isinstance(selector_pattern, str) else selector_pattern
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out = []
    i = 0
    while i < len(css):
        brace = css.find("{", i)
        if brace < 0:
            out.append(css[i:])
            break
        prelude = css[i:brace]
        end = _match_brace(css, brace)
        body = css[brace + 1:end]
        head = prelude.strip()
        if head.startswith("@media") or head.startswith("@supports"):
            inner = strip_css_rules(body, pattern)
            if inner.strip():
                out.append(f"{prelude}{{{inner}}}")
        elif head.startswith("@"):
            out.append(css[i:end + 1])
        else:
            lead = prelude[: len(prelude) - len(prelude.lstrip())]
            selectors = [s for s in head.split(",") if s.strip() and not pattern.search(s)]
            if selectors:
                out.append(f"{lead}{','.join(selectors)}{{{body}}}")
        i = end + 1
    return "".join(out)


# ---------------------------------------------------------------------------
# HTTP gate (outermost do_GET layer of the tracking/Mini App server)
# ---------------------------------------------------------------------------
META_LANDING_PATHS = frozenset({"/meta-ch", "/meta-ch-v2"})


def _send_plain(handler, status_code: int, body: bytes = b"not found", content_type="text/plain; charset=utf-8"):
    handler.send_response(status_code)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _send_redirect(handler, target: str) -> None:
    handler.send_response(302)
    handler.send_header("Location", target)
    handler.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
    handler.send_header("Content-Length", "0")
    handler.end_headers()


def liveline_launcher_page(liveline_path: str = "/liveline") -> str:
    """Bare /hub in liveline mode: resolve a client-side start_param safely."""
    import json as _json

    targets = {"liveline": liveline_path, "news": "/news?category=latest",
               "alerts": "/hub?section=alerts", "settings": "/hub?section=settings"}
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>Live Line</title><script src=\"https://telegram.org/js/telegram-web-app.js\"></script>"
        "</head><body><p style=\"font-family:Arial,sans-serif;text-align:center;margin-top:30vh;color:#64748b\">"
        "Opening Live Line…</p><script>(function(){const tg=window.Telegram&&window.Telegram.WebApp;"
        "if(tg){try{tg.ready();tg.expand()}catch(e){}}const q=new URLSearchParams(location.search);"
        "let s=String(q.get('tgWebAppStartParam')||q.get('startapp')||'').trim().toLowerCase();"
        "if(!s&&tg&&tg.initDataUnsafe)s=String(tg.initDataUnsafe.start_param||'').trim().toLowerCase();"
        f"const t={_json.dumps(targets)};location.replace(t[s]||t.liveline)}})();</script></body></html>"
    )


def gate_request(handler, liveline_path: str = "/liveline", blocked_paths=frozenset()) -> bool:
    """Handle a GET in liveline mode. Returns True when the request was answered."""
    if is_full_mode():
        return False
    parsed = urlparse(handler.path)
    path = parsed.path.rstrip("/") or "/"
    query = parse_qs(parsed.query, keep_blank_values=True)

    if path in META_LANDING_PATHS or path in {p.rstrip("/") for p in blocked_paths}:
        _send_plain(handler, 404)
        return True

    if path.endswith("/api"):
        action = (query.get("action") or [""])[0].strip().lower()
        if action.startswith("bhav") or action.startswith("odds"):
            _send_plain(handler, 404, b'{"ok":false,"error":"not_found"}', "application/json; charset=utf-8")
            return True

    if path == "/go":
        _send_redirect(handler, liveline_path)
        return True

    if path == "/hub":
        requested = url_section(handler.path)
        if requested in {"alerts", "settings"}:
            return False
        if requested == "news":
            _send_redirect(handler, "/news?category=latest")
            return True
        if requested in LIVELINE_SECTIONS:
            _send_redirect(handler, liveline_path)
            return True
        if requested:
            # casino / games / payments / support / anything unknown
            _send_plain(handler, 404)
            return True
        raw = liveline_launcher_page(liveline_path).encode("utf-8")
        _send_plain(handler, 200, raw, "text/html; charset=utf-8")
        return True
    return False


def install_http_gate(analytics_module, liveline_path: str = "/liveline", blocked_paths=frozenset()) -> None:
    """Install the gate as the outermost do_GET layer.

    Legacy route layers are installed inside the entry point's main(), right
    before start_tracking_server(); wrapping that call guarantees the gate
    wraps every layer. It is also applied immediately if the server runs.
    """
    handler_cls = analytics_module.TrackingHandler
    blocked = frozenset(blocked_paths)

    def apply_gate():
        if getattr(handler_cls.do_GET, "_dura_mode_gate", False):
            return
        inner = handler_cls.do_GET

        def gated_get(self):
            try:
                if gate_request(self, liveline_path, blocked):
                    return
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception as exc:
                logger.warning("DURA_MODE HTTP gate error: %s", type(exc).__name__)
            return inner(self)

        gated_get._dura_mode_gate = True
        handler_cls.do_GET = gated_get
        logger.info("DURA_MODE HTTP gate installed (liveline=%s)", liveline_path)

    if getattr(analytics_module, "_dura_mode_gate_wrapped", False):
        return
    original_start = analytics_module.start_tracking_server

    def start_with_gate(*args, **kwargs):
        apply_gate()
        return original_start(*args, **kwargs)

    analytics_module.start_tracking_server = start_with_gate
    analytics_module._dura_mode_gate_wrapped = True
    if getattr(analytics_module, "_server_started", False):
        apply_gate()


# ---------------------------------------------------------------------------
# /mode admin command
# ---------------------------------------------------------------------------

def admin_user_id() -> int:
    core = sys.modules.get("bot")
    value = getattr(core, "ADMIN_USER_ID", None)
    if value:
        return int(value)
    try:
        return int(os.getenv("ADMIN_USER_ID", "8992664481").strip() or "0")
    except ValueError:
        return 0


def _status_text() -> str:
    info = status()
    lines = [
        f"⚙️ <b>DURA MODE: {info['mode'].upper()}</b>",
        "",
        f"Source: {info['source']}",
        f"Env default (DURA_MODE): {info['env_default']}",
    ]
    last = info.get("last_change")
    if last:
        stamp = str(last["changed_at_dubai"])[:19].replace("T", " ")
        lines.append(
            f"Last change: {last['old_mode']} → {last['new_mode']} by {last['admin_id']} at {stamp} GST (Dubai)"
        )
    lines += ["", "Use <code>/mode liveline</code>, <code>/mode full</code> or <code>/mode status</code>."]
    return "\n".join(lines)


async def mode_command(update, context) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return
    try:
        from telegram.ext import ApplicationHandlerStop
    except Exception:  # pragma: no cover
        ApplicationHandlerStop = None
    try:
        if int(user.id) != admin_user_id():
            logger.warning("DURA_MODE /mode refused for non-admin user_id=%s", user.id)
            await message.reply_text("This command is restricted.")
            return
        arg = (context.args[0].strip().lower() if getattr(context, "args", None) else "status")
        if arg in MODES:
            result = set_mode(arg, user.id)
            await message.reply_text(
                f"✅ DURA mode set to <b>{result['new'].upper()}</b> (was {result['old']}).\n"
                f"Logged at {result['dubai']} GST (Dubai) by admin {result['admin_id']}.\n"
                "Takes effect within a few seconds; no redeploy needed.",
                parse_mode="HTML",
            )
        elif arg == "status":
            await message.reply_text(_status_text(), parse_mode="HTML")
        else:
            await message.reply_text(
                "Usage: <code>/mode liveline</code> | <code>/mode full</code> | <code>/mode status</code>",
                parse_mode="HTML",
            )
    finally:
        if ApplicationHandlerStop is not None:
            raise ApplicationHandlerStop


def register_command(application) -> None:
    from telegram.ext import CommandHandler

    # Group -20 runs before the pending-verification gate (-15), so the admin
    # can always switch modes; the handler stops further processing itself.
    application.add_handler(CommandHandler("mode", mode_command), group=-20)
    logger.info("DURA_MODE /mode admin command registered (current=%s)", get_mode())
