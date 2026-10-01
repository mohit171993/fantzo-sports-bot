"""Admin /mode runtime wiring for the shared iBetin/Dura bot codebase.

Install only after the V40 runtime has loaded, before ibetin_start.main().
Full mode delegates to every original handler and route. In Live Line mode
verified users and the admin keep the complete Full bot; only unverified users
are intercepted and receive the separate scores page (no verification prompt).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import threading
import time
from contextlib import closing
from urllib.parse import parse_qs, urlencode, urlparse

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonCommands,
    MenuButtonWebApp,
    BotCommandScopeChat,
    Update,
    WebAppInfo,
)
from telegram.ext import (
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    TypeHandler,
)

import bot as core
import bot_tracked as tracked
import fantzo_analytics as analytics
import fantzo_reminders as reminders
import ibetin_hub as hub
import ibetin_leads as leads
import ibetin_liveline_v30_unified_ui as live_runtime
import ibetin_match_alerts as match_alerts
import ibetin_phone_verify as phone_verify
from mode_control import (
    FULL, LIVE_LINE, PERSISTENT_DB_ROOT, ModeStore, http_route,
    is_persistent_mode_path, is_persistent_volume_mounted,
    parse_admin_mode_request,
)
from scores_only import (
    merge_score_match, score_detail, score_match,
    score_matches, score_page,
)


log = logging.getLogger(__name__)
_installed = False
_store: ModeStore | None = None
_brand = ""
_menu_reconciliation_task: asyncio.Task | None = None
_default_menu_lock = asyncio.Lock()
_score_view_lock = threading.RLock()
_score_view_cache: dict[tuple[str, str], tuple[float, dict]] = {}
_score_view_key_locks: dict[tuple[str, str], threading.Lock] = {}
SCORE_VIEW_DETAIL_SECONDS = 30
# Two Telegram writes per chat at five chats per second stays below the normal
# bot-wide request budget while old per-chat settings are replaced.
MENU_RECONCILE_BATCH = 50
MENU_RECONCILE_DELAY_SECONDS = 0.2
MENU_REFRESH_SECONDS = 7 * 24 * 60 * 60
MENU_RETRY_SECONDS = 15 * 60


def _brand_label() -> str:
    return {"ibetin": "iBetin", "dura": "DURA"}.get(_brand, _brand.title())


def _score_button_label() -> str:
    return ("🏏 OPEN DURASPORTS LIVE LINE" if _brand == "dura"
            else f"🏏 OPEN {_brand_label().upper()} LIVE LINE")


def _verified_menu_text() -> str:
    """Match the bot's existing per-user Full menu button label."""
    return {"dura": "Open DURASPORTS", "ibetin": "Open IBETIN"}.get(
        _brand, f"Open {_brand_label()}")


def _preverify_commands():
    """The bot's existing public (pre-verification) command list."""
    commands = getattr(tracked, "PREVERIFY_COMMANDS", None)
    if commands:
        return commands
    return [BotCommand("start", "Get started"),
            BotCommand("help", "Help and quick guide")]


def _admin_id() -> int:
    try:
        # Match the admin identity used by the existing bot commands, whether
        # it came from Railway's environment or the bot's current default.
        return int(core.ADMIN_USER_ID)
    except (TypeError, ValueError):
        return 0


def _is_mode_admin(user_id) -> bool:
    """Whoever may open the bot's /admin panel may also use /mode."""
    try:
        uid = int(user_id or 0)
    except (TypeError, ValueError):
        return False
    if not uid:
        return False
    if uid == _admin_id():
        return True
    try:
        # iBetin/Dura /admin accepts ADMIN_USER_ID, IBETIN_REPORT_ADMIN_USER_ID
        # and the persistently unlocked report/creative admin accounts.
        import ibetin_reports
        return bool(ibetin_reports.is_authorized_admin(uid))
    except Exception:
        log.exception("Admin authorization unavailable user_id=%s", uid)
        return False


def _mode() -> str:
    assert _store is not None
    try:
        return _store.state().mode
    except Exception:
        # A temporary SQLite failure must never reopen a betting route.
        log.exception("Mode state unavailable; using clean mode")
        return LIVE_LINE


def _is_verified_user(user_id) -> bool:
    """Verified users (and the admin bypass) keep Full behavior in Live Line."""
    try:
        return bool(user_id) and bool(phone_verify.is_verified(int(user_id)))
    except Exception:
        # Fail closed: an unreadable verification table means Live Line only.
        log.exception("Verification state unavailable user_id=%s", user_id)
        return False


def _persistent_mode_storage_ready() -> bool:
    """Do not activate clean mode in a database that may disappear on restart."""
    if _store is None or not is_persistent_mode_path(_store.db_path):
        return False
    if not os.path.isdir(PERSISTENT_DB_ROOT):
        return False
    if not is_persistent_volume_mounted():
        return False
    root = os.path.realpath(PERSISTENT_DB_ROOT)
    db_path = os.path.realpath(_store.db_path)
    return os.path.commonpath((root, db_path)) == root and db_path != root


def _scores_url(user_id: int | None = None) -> str:
    root = hub._public_base_url()
    parsed = urlparse(root)
    if (parsed.scheme != "https" or not parsed.netloc
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise RuntimeError("A public HTTPS score URL is required")
    if _brand == "dura" and parsed.hostname == "ibetin-app-production.up.railway.app":
        # The shared iBetin library uses this host as its fallback. Dura must
        # have its own public Railway/custom domain before Clean mode can run.
        raise RuntimeError("Dura's public score URL is not configured")
    url = root.rstrip("/") + "/scores"
    return phone_verify.live_line_url(user_id, url) if user_id else url


def _score_destination_ready() -> bool:
    try:
        _scores_url()
        return True
    except RuntimeError:
        return False


class _ModeAwareAlertBot:
    """Recheck mode at each match-alert send, including RetryAfter retries."""

    def __init__(self, bot, user_id: int):
        self.bot = bot
        self.user_id = user_id

    async def send_message(self, **kwargs):
        if _mode() != FULL and not _is_verified_user(self.user_id):
            # A Full alert may already be waiting on Telegram's RetryAfter.
            # Unverified recipients only receive the Live Line alert.
            kwargs["text"] = ("⚡ MATCH UPDATE\n\n"
                              "🏏 A fresh score just landed.\n"
                              "👇 Tap below for the full scorecard.")
            kwargs["reply_markup"] = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    _score_button_label(), web_app=WebAppInfo(url=_scores_url(self.user_id)),
                ),
            ]])
        return await self.bot.send_message(**kwargs)


class _GuardedPublicBot:
    """Stop an in-flight reminder or channel post after a clean switch."""

    _SEND_METHODS = frozenset({
        "send_message", "send_photo", "send_document", "send_video",
        "send_media_group", "copy_message", "forward_message",
    })

    def __init__(self, bot, allow_verified: bool = False):
        self._bot = bot
        self._allow_verified = allow_verified

    def __getattr__(self, name):
        method = getattr(self._bot, name)
        if name not in self._SEND_METHODS:
            return method

        async def guarded_send(*args, **kwargs):
            if _mode() != FULL:
                chat_id = kwargs.get("chat_id", args[0] if args else None)
                if not (self._allow_verified and _is_verified_user(chat_id)):
                    raise RuntimeError("Public send canceled after Live Line activation")
            return await method(*args, **kwargs)

        return guarded_send


class _GuardedPublicApplication:
    def __init__(self, application, allow_verified: bool = False):
        self._application = application
        self.bot = _GuardedPublicBot(application.bot, allow_verified)

    def __getattr__(self, name):
        return getattr(self._application, name)


def _mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Live Line", callback_data="mode:liveline")],
        [InlineKeyboardButton("⚙️ Full", callback_data="mode:full")],
        [InlineKeyboardButton("↻ Status", callback_data="mode:status")],
    ])


def _default_menu_button(mode: str):
    """Unverified chats use the default: the Live Line scores page."""
    if mode == LIVE_LINE:
        try:
            return MenuButtonWebApp(
                text=_score_button_label(), web_app=WebAppInfo(url=_scores_url()),
            )
        except Exception:
            log.exception("Live Line default menu unavailable; using commands")
    return MenuButtonCommands()


async def _set_default_menu(bot) -> None:
    try:
        async with _default_menu_lock:
            mode = _mode()
            # Telegram's default menu is visible before mobile verification.
            # Verified users have per-chat settings reconciled below.
            await bot.set_chat_menu_button(menu_button=_default_menu_button(mode))
            if _mode() == mode:
                await bot.set_my_commands(
                    [BotCommand("start", "Live scores and sports updates"),
                     BotCommand("help", "How IBETIN Live Line works")]
                    if mode == LIVE_LINE else _preverify_commands()
                )
    except Exception:
        # The switch has already been committed. Still show the owner its
        # status and let the reconciliation task repair per-chat settings.
        log.exception("Could not update default mode menu")
    finally:
        # The mode is already persisted. A Telegram default-menu failure must
        # not leave existing verified chats with stale Full links indefinitely.
        _schedule_menu_reconciliation(bot)


async def _telegram_menu_write(operation, mode: str, user_id: int, kind: str) -> bool:
    """Retry one transient Telegram failure; return False for a later sweep."""
    for attempt in range(2):
        if _mode() != mode:
            return True
        try:
            await operation()
            return True
        except Exception as exc:
            retry_after = getattr(exc, "retry_after", None)
            transient = (retry_after is not None or type(exc).__name__ in {
                "TimedOut", "NetworkError",
            })
            if transient and attempt == 0:
                try:
                    seconds = (retry_after.total_seconds()
                               if hasattr(retry_after, "total_seconds")
                               else float(retry_after) if retry_after is not None else 1.0)
                except (TypeError, ValueError):
                    seconds = 1.0
                if 0 <= seconds <= 60:
                    await asyncio.sleep(max(seconds + 0.5, 1.0))
                    continue
            log.warning("Could not update chat %s user_id=%s error=%s",
                        kind, user_id, type(exc).__name__)
            return not transient
    return False


async def _set_verified_chat_ui(bot, user_id: int, mode: str) -> bool:
    """Set one verified private chat to the current mode without sending a DM."""
    if _mode() != mode:
        return True
    try:
        if not phone_verify.is_verified(user_id):
            return True
        # Verified users keep the Full menu in both modes; unverified users
        # fall back to the Live Line default menu set by _set_default_menu.
        commands = tracked.VERIFIED_COMMANDS
        menu_url = hub.hub_url("home")
        menu_text = _verified_menu_text()
    except Exception as exc:
        log.warning("Could not prepare chat menu user_id=%s error=%s",
                    user_id, type(exc).__name__)
        return False
    commands_ok = await _telegram_menu_write(
        lambda: bot.set_my_commands(
            commands, scope=BotCommandScopeChat(chat_id=int(user_id)),
        ), mode, user_id, "commands",
    )
    menu_ok = await _telegram_menu_write(
        lambda: bot.set_chat_menu_button(
            chat_id=int(user_id),
            menu_button=MenuButtonWebApp(
                text=menu_text, web_app=WebAppInfo(url=menu_url),
            ),
        ), mode, user_id, "menu",
    )
    return commands_ok and menu_ok


async def _reconcile_verified_chats(bot, mode: str) -> bool:
    """Page a fixed DB snapshot; keep memory, Telegram traffic, and time bounded."""
    assert _store is not None
    try:
        with closing(sqlite3.connect(_store.db_path, timeout=15)) as conn:
            row = conn.execute(
                "SELECT MAX(user_id) FROM liveline_verified_users"
            ).fetchone()
            last_user_id = int(row[0] or 0)
    except sqlite3.Error as exc:
        # An empty/legacy installation can lack the verification table.
        log.warning("Verified chat reconciliation unavailable error=%s",
                    type(exc).__name__)
        return False
    cursor = 0
    updated = 0
    needs_retry = False
    while cursor < last_user_id and _mode() == mode:
        try:
            with closing(sqlite3.connect(_store.db_path, timeout=15)) as conn:
                rows = conn.execute(
                    "SELECT user_id FROM liveline_verified_users "
                    "WHERE user_id > ? AND user_id <= ? ORDER BY user_id LIMIT ?",
                    (cursor, last_user_id, MENU_RECONCILE_BATCH),
                ).fetchall()
        except sqlite3.Error:
            log.exception("Verified chat reconciliation database read failed")
            return False
        if not rows:
            break
        for row in rows:
            if _mode() != mode:
                return True
            user_id = int(row[0])
            cursor = user_id
            if await _set_verified_chat_ui(bot, user_id, mode) is False:
                needs_retry = True
            updated += 1
            await asyncio.sleep(MENU_RECONCILE_DELAY_SECONDS)
    # Admins can be verified through the existing admin bypass without a row.
    admin_id = _admin_id()
    if _mode() == mode and admin_id:
        if await _set_verified_chat_ui(bot, admin_id, mode) is False:
            needs_retry = True
    log.info("Verified chat menu reconciliation mode=%s chats=%s full_menu=%s "
             "live_line_default_users=%s", mode, updated, updated,
             _unverified_user_count())
    return not needs_retry


def _unverified_user_count():
    """Known bot users without verification; they use the default menu."""
    try:
        with closing(sqlite3.connect(_store.db_path, timeout=15)) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM users WHERE user_id NOT IN "
                "(SELECT user_id FROM liveline_verified_users)"
            ).fetchone()
        return int(row[0] or 0)
    except Exception:
        return "unknown"


async def _menu_reconciliation_loop(bot, previous) -> None:
    if previous is not None:
        try:
            await previous
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("Previous menu reconciliation failed; restarting")
    while True:
        mode = _mode()
        try:
            success = await _reconcile_verified_chats(bot, mode)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Verified chat menu reconciliation failed")
            success = False
        if _mode() != mode:
            return
        if success is False:
            # Full restoration also needs a retry after a temporary DB or
            # Telegram failure; otherwise old clean menus could linger.
            await asyncio.sleep(MENU_RETRY_SECONDS)
            continue
        if mode != LIVE_LINE:
            return
        # Signed score URLs expire in 30 days. Reissue them weekly for chats
        # that have not interacted with the bot since the last sweep.
        await asyncio.sleep(MENU_REFRESH_SECONDS)


def _schedule_menu_reconciliation(bot) -> None:
    global _menu_reconciliation_task
    previous = _menu_reconciliation_task
    if previous is not None and not previous.done():
        previous.cancel()
    _menu_reconciliation_task = asyncio.create_task(
        _menu_reconciliation_loop(bot, previous),
        name="bot-mode-menu-reconciliation",
    )


async def _mode_status(update, context) -> None:
    try:
        mode = _store.state().mode.upper()
    except Exception:
        log.exception("Could not read mode for admin status")
        mode = "LIVELINE (state unavailable; held clean)"
    await update.effective_message.reply_text(
        f"{_brand_label()} mode: {mode}\n"
        "This switch does not pause or resume ads.",
        reply_markup=_mode_keyboard(),
    )


async def _mode_command(update, context) -> None:
    user, chat = update.effective_user, update.effective_chat
    user_id = int(user.id) if user else 0
    action = parse_admin_mode_request(
        user_id, user_id if _is_mode_admin(user_id) else 0, list(context.args or []),
    )
    if not chat or chat.type != "private" or action is None:
        raise ApplicationHandlerStop
    if action == "usage":
        await update.effective_message.reply_text(
            "Use /mode liveline, /mode full, or /mode status.",
            reply_markup=_mode_keyboard(),
        )
    elif action == "status":
        await _mode_status(update, context)
    else:
        if action == LIVE_LINE and not _persistent_mode_storage_ready():
            await update.effective_message.reply_text(
                "Live Line mode is unavailable until persistent storage is ready. "
                "The current mode is unchanged."
            )
            raise ApplicationHandlerStop
        if action == LIVE_LINE and not _score_destination_ready():
            await update.effective_message.reply_text(
                "Live Line mode is unavailable until this bot's score URL is configured. "
                "The current mode is unchanged."
            )
            raise ApplicationHandlerStop
        _store.switch(action)
        await _set_default_menu(context.bot)
        await _mode_status(update, context)
    raise ApplicationHandlerStop


async def _mode_callback(update, context) -> None:
    query = update.callback_query
    user, chat = update.effective_user, update.effective_chat
    if not query or not user or not chat or chat.type != "private" or not _is_mode_admin(user.id):
        raise ApplicationHandlerStop
    action = str(query.data or "").partition(":")[2]
    if action not in {LIVE_LINE, FULL, "status"}:
        raise ApplicationHandlerStop
    if action != "status":
        if action == LIVE_LINE and not _persistent_mode_storage_ready():
            await query.answer(
                "Persistent storage is unavailable; mode unchanged.", show_alert=True,
            )
            raise ApplicationHandlerStop
        if action == LIVE_LINE and not _score_destination_ready():
            await query.answer("Score URL unavailable; mode unchanged.", show_alert=True)
            raise ApplicationHandlerStop
        _store.switch(action)
        await _set_default_menu(context.bot)
    await query.answer()
    await _mode_status(update, context)
    raise ApplicationHandlerStop


async def _send_live_line_scores(message, context, user_id: int) -> None:
    """The only reply unverified users receive in Live Line mode."""
    url = _scores_url(user_id)
    await message.reply_text(
        f"⚡ {_brand_label().upper()} LIVE LINE\n\n"
        "🏏 Live scores, full scorecards and match updates.\n"
        "👇 Tap below to open.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
            _score_button_label(), web_app=WebAppInfo(url=url),
        )]]),
    )


async def _guard_update(update, context) -> None:
    if _mode() == FULL:
        return
    user = update.effective_user
    # The admin and verified users keep the complete Full bot in Live Line
    # mode: every command, button, Mini App link and reminder flow.
    if user and (_is_mode_admin(user.id) or _is_verified_user(user.id)):
        return
    message = update.business_message or update.effective_message
    chat = update.effective_chat
    if update.callback_query:
        try:
            await update.callback_query.answer()
        except Exception:
            pass
    if not message or not chat or chat.type != "private" or not user:
        raise ApplicationHandlerStop
    message_text = str(getattr(message, "text", "") or "").strip()
    parts = message_text.split(maxsplit=1)
    is_start = bool(parts and parts[0].split("@", 1)[0].lower() == "/start")
    start_arg = parts[1].split(maxsplit=1)[0].lower() if is_start and len(parts) > 1 else ""

    if start_arg == "stopreminders" or tracked._is_stop_text(message_text):
        reminders.set_opt_out("bot", user.id, True)
        reminders.set_opt_out("business_dm", user.id, True)
        if start_arg != "stopreminders":
            leads.set_status(user.id, "dnc")
            await message.reply_text("✅ Contact preference saved. Follow-ups are stopped.")
        else:
            await message.reply_text("🔕 Reminders are off.")
        raise ApplicationHandlerStop

    if getattr(message, "contact", None) is not None and not update.business_message:
        # The user chose to share their own contact (for example from an
        # older verification keyboard). Let the normal Full verification
        # handler process it; no verification prompt is ever sent here.
        return

    if is_start:
        campaign = leads.clean_campaign(parts[1] if len(parts) > 1 else "direct")
        try:
            leads.record_start(user.id, campaign=campaign, source="bot")
            context.user_data["ibetin_campaign"] = campaign
            core.track(user.id, f"campaign_start:{campaign}")
        except Exception:
            log.exception("Could not record Live Line campaign start")

    if update.business_message:
        try:
            leads.record_start(user.id, source="business_dm")
        except Exception:
            log.exception("Could not record Live Line business start")
        # Business chats take a plain link; the signed URL opens the scores.
        await message.reply_text(
            f"⚡ {_brand_label().upper()} LIVE LINE\n\n"
        "🏏 Live scores, full scorecards and match updates.\n"
        "👇 Tap below to open.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                _score_button_label(), url=_scores_url(user.id),
            )]]),
        )
        raise ApplicationHandlerStop

    await _send_live_line_scores(message, context, user.id)
    raise ApplicationHandlerStop


def _safe_rows(mode: str):
    if mode not in {"live", "upcoming", "results"}:
        mode = "live"
    # V25 has already patched this accessor to use its warm, stale-while-refresh
    # cache; only our allowlisted score fields leave the server.
    rows, source = live_runtime.v25._fast_matches_cached(mode)
    if not rows and source == "Feed unavailable":
        raise RuntimeError("Score feed unavailable")
    return score_matches(rows or [])


def _score_key(raw: str) -> str:
    key = str(raw or "").strip()
    numeric = key.isascii() and key.isdecimal() and len(key) <= 30
    if not key or len(key) > 100 or not (numeric or live_runtime.v25._roanuz_key(key)):
        raise ValueError("Invalid match key")
    return key


def _listed_score_match(raw_key: str, mode: str) -> dict:
    key = _score_key(raw_key)
    if mode not in {"live", "upcoming", "results"}:
        raise ValueError("Invalid match view")
    for row in _safe_rows(mode):
        if row["id"] == key:
            return row
    raise ValueError("Match is not in this score view")


def _cached_score_view(key: str, kind: str, build) -> dict:
    """Share one safe detail refresh across viewers for at least 30 seconds."""
    cache_key = (kind, key)
    with _score_view_lock:
        now = time.monotonic()
        cached = _score_view_cache.get(cache_key)
        if cached and now - cached[0] < SCORE_VIEW_DETAIL_SECONDS:
            return cached[1]
        key_lock = _score_view_key_locks.setdefault(cache_key, threading.Lock())
    # The network call is serialized per match, without blocking other matches.
    with key_lock:
        with _score_view_lock:
            now = time.monotonic()
            cached = _score_view_cache.get(cache_key)
            if cached and now - cached[0] < SCORE_VIEW_DETAIL_SECONDS:
                return cached[1]
        result = build()
        if not isinstance(result, dict):
            raise RuntimeError("Score detail unavailable")
        with _score_view_lock:
            if len(_score_view_cache) >= 256:
                _score_view_cache.clear()
            _score_view_cache[cache_key] = (time.monotonic(), result)
        return result


def _safe_score_match(raw_key: str, mode: str) -> dict:
    row = _listed_score_match(raw_key, mode)
    key = row["id"]
    def build():
        summary = live_runtime.v25._score_summary_cached(key)
        if not isinstance(summary, dict):
            raise RuntimeError("Score detail unavailable")
        if not summary.get("roanuzMatchKey") and not summary.get("id"):
            summary = {**summary, "id": key}
        return score_match(summary)
    return merge_score_match(row, _cached_score_view(key, "score", build))


def _safe_score_detail(raw_key: str, mode: str) -> dict:
    row = _listed_score_match(raw_key, mode)
    key = row["id"]
    def build():
        detail, _source = live_runtime.v25._match_detail_cached(key)
        if not isinstance(detail, dict) or not isinstance(detail.get("match"), dict):
            raise RuntimeError("Score detail unavailable")
        match = detail["match"]
        if not match.get("roanuzMatchKey") and not match.get("id"):
            detail = {**detail, "match": {**match, "id": key}}
        return score_detail(detail)
    safe = _cached_score_view(key, "match", build)
    return {**safe, "match": merge_score_match(row, safe["match"])}


def _send_bytes(handler, status: int, body: bytes, content_type: str,
                token: str = "") -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Content-Length", str(len(body)))
    if token:
        name = live_runtime.IBETIN_LIVELINE_COOKIE
        handler.send_header(
            "Set-Cookie",
            f"{name}={token}; Max-Age=2592000; Path=/; Secure; HttpOnly; SameSite=Lax",
        )
    handler.end_headers()
    handler.wfile.write(body)


def _verified_scores_identity(handler, parsed):
    try:
        return live_runtime._liveline_verified(handler, parsed)
    except Exception:
        log.exception("Score authentication unavailable")
        return 0, "", False


_AUTH_BOOTSTRAP_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<noscript><meta http-equiv="refresh" content="0;url=/scores"></noscript>
</head><body><script>
(function(){
  function fallback(){ location.replace('/scores'); }
  var data = '';
  try { data = new URLSearchParams(location.hash.slice(1)).get('tgWebAppData') || ''; } catch (e) {}
  if (!data) {
    try { data = (JSON.parse(sessionStorage.getItem('__telegram__initParams') || '{}').tgWebAppData) || ''; } catch (e) {}
  }
  var key = 'bot_mode_auth:' + location.pathname + location.search;
  var tried = '';
  try { tried = sessionStorage.getItem(key) || ''; sessionStorage.setItem(key, '1'); } catch (e) { tried = '1'; }
  if (!data || tried) { fallback(); return; }
  fetch('/scores/auth', {method: 'POST', credentials: 'same-origin',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({initData: data})})
    .then(function(r){ if (r.ok) { location.reload(); } else { fallback(); } })
    .catch(fallback);
})();
</script></body></html>"""


def _scores_auth(handler) -> None:
    """Exchange signed Telegram Mini App initData for the signed access cookie."""
    try:
        length = int(handler.headers.get("Content-Length", "0") or 0)
        if length <= 0 or length > 16384:
            raise ValueError("Invalid request")
        payload = json.loads(handler.rfile.read(length).decode("utf-8"))
        user = hub._verify_init_data(str(payload.get("initData") or ""))
        user_id = int(user["id"])
        token = phone_verify.issue_access_token(user_id)
    except Exception:
        return _send_bytes(handler, 403, b'{"ok":false}', "application/json; charset=utf-8")
    verified = _is_verified_user(user_id)
    body = json.dumps({"ok": True, "verified": verified}).encode("utf-8")
    return _send_bytes(handler, 200, body, "application/json; charset=utf-8", token)


def _install_http_gate() -> None:
    cls = analytics.TrackingHandler
    if getattr(cls, "_bot_mode_http_gate", False):
        return
    original_get = cls.do_GET
    original_post = getattr(cls, "do_POST", None)

    def gated_get(self):
        parsed = urlparse(self.path)
        current_mode = _mode()
        if current_mode == FULL and parsed.path == "/scores":
            # Old clean-mode Mini App buttons should work after switching back.
            supplied = (parse_qs(parsed.query).get("access") or [""])[0]
            access = supplied if phone_verify.verify_access_token(supplied) else ""
            target = "/liveline" + ("?" + urlencode({"access": access}) if access else "")
            self.send_response(302)
            self.send_header("Location", target)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        decision = http_route(current_mode, "GET", parsed.path)
        if decision == "pass":
            return original_get(self)
        if decision == "scores":
            # Live Line scores are public: unverified users must never meet a
            # verification wall. A signed link is still exchanged for a cookie.
            user_id, token, _verified = _verified_scores_identity(self, parsed)
            mode = (parse_qs(parsed.query).get("mode") or ["live"])[0]
            if user_id and (parse_qs(parsed.query).get("access") or [""])[0]:
                # Exchange the signed URL for an HttpOnly cookie, as the
                # existing verified Live Line does, then hide it from the URL.
                safe_mode = mode if mode in {"live", "upcoming", "results"} else "live"
                self.send_response(302)
                self.send_header("Location", "/scores?" + urlencode({"mode": safe_mode}))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Set-Cookie", f"{live_runtime.IBETIN_LIVELINE_COOKIE}={token}; "
                                 "Max-Age=2592000; Path=/; Secure; HttpOnly; SameSite=Lax")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            token = token if user_id else ""
            try:
                rows = _safe_rows(mode)
            except Exception:
                log.exception("Score feed unavailable")
                body = score_page([], _brand_label(), mode, feed_error=True).encode("utf-8")
                return _send_bytes(self, 503, body, "text/html; charset=utf-8", token)
            body = score_page(rows, _brand_label(), mode).encode("utf-8")
            return _send_bytes(self, 200, body, "text/html; charset=utf-8", token)
        if decision == "scores_api":
            user_id, token, _verified = _verified_scores_identity(self, parsed)
            token = token if user_id else ""
            query = parse_qs(parsed.query)
            action = (query.get("action") or ["matches"])[0]
            try:
                if action == "matches":
                    mode = (query.get("mode") or ["live"])[0]
                    payload = {"ok": True, "matches": _safe_rows(mode)}
                elif action == "score":
                    key = (query.get("id") or [""])[0]
                    mode = (query.get("mode") or ["live"])[0]
                    payload = {"ok": True, "match": _safe_score_match(key, mode)}
                elif action == "match":
                    key = (query.get("id") or [""])[0]
                    mode = (query.get("mode") or ["live"])[0]
                    payload = {"ok": True, "detail": _safe_score_detail(key, mode)}
                else:
                    raise ValueError("Invalid score action")
                body = json.dumps(payload).encode("utf-8")
                return _send_bytes(self, 200, body, "application/json; charset=utf-8", token)
            except ValueError:
                return _send_bytes(self, 400, b'{"ok":false,"error":"invalid_request"}',
                                   "application/json; charset=utf-8")
            except Exception:
                log.exception("Score API unavailable")
                return _send_bytes(self, 503, b'{"ok":false,"error":"feed_unavailable"}',
                                   "application/json; charset=utf-8")
        if decision == "redirect":
            user_id, _token, verified = _verified_scores_identity(self, parsed)
            if user_id and verified:
                # Verified users keep every Full page and Mini App in Live Line.
                return original_get(self)
            # Preserve first-touch open counts for existing /go links while
            # routing the visitor to scores instead of the external site.
            if parsed.path == "/go":
                try:
                    source = (parse_qs(parsed.query).get("source") or ["unknown"])[0]
                    analytics.record_open(analytics._clean_source(source))
                except Exception:
                    log.exception("Could not record Live Line open")
            if not user_id:
                # Unknown visitor: a Telegram Mini App can prove its user with
                # signed initData (then reload); anyone else lands on /scores.
                return _send_bytes(self, 200, _AUTH_BOOTSTRAP_PAGE.encode("utf-8"),
                                   "text/html; charset=utf-8")
            query = parse_qs(parsed.query)
            supplied = (query.get("access") or [""])[0]
            access = supplied if phone_verify.verify_access_token(supplied) else ""
            target = "/scores" + ("?" + urlencode({"access": access}) if access else "")
            self.send_response(302)
            self.send_header("Location", target)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        return _send_bytes(self, 403, b"", "text/plain; charset=utf-8")

    def gated_post(self):
        parsed = urlparse(self.path)
        decision = http_route(_mode(), "POST", parsed.path)
        if decision == "pass" and original_post:
            return original_post(self)
        if decision == "scores_auth":
            return _scores_auth(self)
        if decision == "deny" and original_post:
            user_id, _token, verified = _verified_scores_identity(self, parsed)
            if user_id and verified:
                return original_post(self)
        return _send_bytes(self, 403, b"", "text/plain; charset=utf-8")

    cls.do_GET = gated_get
    cls.do_POST = gated_post
    cls._bot_mode_http_gate = True


def install(brand: str) -> None:
    global _installed, _store, _brand
    if _installed:
        return
    _brand = brand
    _store = ModeStore(os.getenv("DB_PATH", "/app/ibetin_bot_persistent/ibetin_bot.db"), brand)

    original_configure = tracked.configure_telegram_ui

    async def configure_with_mode(application):
        await original_configure(application)
        application.add_handler(CommandHandler("mode", _mode_command), group=-100)
        application.add_handler(
            CallbackQueryHandler(_mode_callback, pattern=r"^mode:(liveline|full|status)$"),
            group=-100,
        )
        application.add_handler(TypeHandler(Update, _guard_update), group=-90)
        if _mode() == LIVE_LINE:
            await _set_default_menu(application.bot)
        else:
            # Resume an interrupted Full restoration after a process restart.
            _schedule_menu_reconciliation(application.bot)

    tracked.configure_telegram_ui = configure_with_mode
    tracked.app.configure_telegram_ui = configure_with_mode

    original_start_server = analytics.start_tracking_server

    def start_server_with_mode():
        # ibetin_entry.main installs every route before starting the server.
        # Wrapping here makes this gate outermost, including old direct links.
        _install_http_gate()
        return original_start_server()

    analytics.start_tracking_server = start_server_with_mode

    original_reminders = reminders.run_due_reminders
    async def reminders_by_mode(application):
        if _mode() == FULL:
            return await original_reminders(_GuardedPublicApplication(application))
        # Live Line: verified users keep their normal reminders; sends to any
        # unverified chat are refused (they never get verification prompts).
        return await original_reminders(
            _GuardedPublicApplication(application, allow_verified=True),
        )
    reminders.run_due_reminders = reminders_by_mode

    original_verification_due_stage = reminders._verification_due_stage
    def verification_due_stage_by_mode(row, now_utc):
        if _mode() == FULL:
            return original_verification_due_stage(row, now_utc)
        # No verification reminder is due in Live Line, so none is attempted
        # or recorded; the Full cadence resumes unchanged after switching back.
        return None
    reminders._verification_due_stage = verification_due_stage_by_mode

    original_channel_daily = reminders.send_liveline_channel_daily
    async def channel_daily_by_mode(application, *args, **kwargs):
        if _mode() == FULL:
            return await original_channel_daily(
                _GuardedPublicApplication(application), *args, **kwargs,
            )
        return False
    reminders.send_liveline_channel_daily = channel_daily_by_mode

    original_channel_launch = reminders.send_liveline_channel_launch
    async def channel_launch_by_mode(application, *args, **kwargs):
        if _mode() == FULL:
            return await original_channel_launch(
                _GuardedPublicApplication(application), *args, **kwargs,
            )
        return False
    reminders.send_liveline_channel_launch = channel_launch_by_mode

    # Alert copy is unchanged; each send is checked per recipient, so only
    # unverified recipients receive the Live Line alert in Live Line mode.
    original_alert_send = match_alerts._send

    async def alert_send_by_mode(bot, user_id, text, markup):
        return await original_alert_send(
            _ModeAwareAlertBot(bot, user_id), user_id, text, markup,
        )

    match_alerts._send = alert_send_by_mode
    _installed = True
    log.info("Bot mode controller installed brand=%s initial_mode=%s", brand, _mode())
