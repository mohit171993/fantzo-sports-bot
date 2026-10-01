"""Admin /mode switch for the Fantzo bot (FULL vs LIVELINE).

Install from bot_restore_test.py before the bot starts. FULL mode delegates to
every original handler, menu and loop unchanged; it is the default. In
LIVELINE mode the admin and verified users keep the complete Full bot; only
unverified users are intercepted and receive the Fantzo Live Line scores page
(no mobile verification prompt). The /scores page itself is served in both
modes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

from telegram import (
    BotCommand,
    BotCommandScopeChat,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonCommands,
    MenuButtonDefault,
    MenuButtonWebApp,
    Update,
    WebAppInfo,
)
from telegram.ext import (
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    TypeHandler,
)

import bot_tracked as tracked
import fantzo_analytics as analytics
import fantzo_banner_queue as banner_queue
import fantzo_business as business
import fantzo_lead_funnel as lead_funnel
import fantzo_live_tv_mobile_gate as gate
import fantzo_reminders as reminders
from mode_control import (
    FULL, LIVE_LINE, PERSISTENT_DB_ROOT, ModeStore,
    is_persistent_mode_path, is_persistent_volume_mounted,
    parse_admin_mode_request,
)
from scores_only import merge_score_match, score_detail, score_match, score_matches, score_page


log = logging.getLogger(__name__)
core = tracked.app.core

_installed = False
_store: ModeStore | None = None
_brand = "fantzo"
_menu_reconciliation_task: asyncio.Task | None = None
_default_menu_lock = asyncio.Lock()

MENU_RECONCILE_BATCH = 50
MENU_RECONCILE_DELAY_SECONDS = 0.2
MENU_RETRY_SECONDS = 15 * 60
SCORE_VIEWS = ("live", "upcoming", "results")
# Highlightly is shared with Live TV; keep score traffic small and shared.
SCORE_DATE_TTL_SECONDS = {"today": 45, "other": 300}
SCORE_DETAIL_TTL_SECONDS = 60
STOP_TEXTS = {"stop", "unsubscribe", "do not contact", "cancel"}
FINISHED_STATES = {
    "finished", "ended", "result", "complete", "completed", "abandoned",
    "cancelled", "canceled", "no result",
}

_score_lock = threading.RLock()
_score_cache: dict[tuple[str, str], tuple[float, object]] = {}
_score_key_locks: dict[tuple[str, str], threading.Lock] = {}


def _brand_label() -> str:
    return "Fantzo"


def _score_button_label() -> str:
    return "🏏 OPEN FANTZO LIVE LINE"


def _verified_menu_text() -> str:
    # Matches fantzo_live_tv_mobile_gate.configure_chat_ui.
    return "Open Fantzo"


def _admin_id() -> int:
    try:
        return int(core.ADMIN_USER_ID)
    except (TypeError, ValueError):
        return 0


def _admin_ids() -> frozenset:
    try:
        return frozenset(core.admin_user_ids())
    except Exception:
        admin_id = _admin_id()
        return frozenset({admin_id}) if admin_id else frozenset()


def _is_admin_user(user_id) -> bool:
    try:
        return int(user_id) in _admin_ids()
    except (TypeError, ValueError):
        return False


def _mode() -> str:
    assert _store is not None
    try:
        return _store.state().mode
    except Exception:
        # Same rule as the other bots: an unreadable state holds Live Line.
        log.exception("Mode state unavailable; using Live Line mode")
        return LIVE_LINE


def _is_verified_user(user_id) -> bool:
    try:
        return bool(user_id) and bool(gate.is_registered(int(user_id)))
    except Exception:
        log.exception("Verification state unavailable user_id=%s", user_id)
        return False


def _persistent_mode_storage_ready() -> bool:
    """Live Line must survive a restart, so require the mounted /data volume."""
    if _store is None or not is_persistent_mode_path(_store.db_path):
        return False
    if not os.path.isdir(PERSISTENT_DB_ROOT):
        return False
    if not is_persistent_volume_mounted():
        return False
    root = os.path.realpath(PERSISTENT_DB_ROOT)
    db_path = os.path.realpath(_store.db_path)
    return os.path.commonpath((root, db_path)) == root and db_path != root


def _scores_url() -> str:
    root = str(analytics.TRACKING_BASE_URL or "").strip()
    if root and not root.startswith(("http://", "https://")):
        root = "https://" + root
    parsed = urlparse(root)
    if (parsed.scheme != "https" or not parsed.netloc
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise RuntimeError("A public HTTPS score URL is required")
    return root.rstrip("/") + "/scores"


def _score_destination_ready() -> bool:
    try:
        _scores_url()
        return True
    except RuntimeError:
        return False


class _GuardedPublicBot:
    """Stop an in-flight reminder or channel post after a Live Line switch."""

    _SEND_METHODS = frozenset({
        "send_message", "send_photo", "send_document", "send_video",
        "send_animation", "send_media_group", "copy_message", "forward_message",
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
    """Unverified chats use the default menu: the Live Line scores page."""
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
            await bot.set_chat_menu_button(menu_button=_default_menu_button(mode))
            if _mode() == mode:
                # Live Line mode: a scores-first public menu. Full mode keeps
                # Fantzo's existing public command list.
                await bot.set_my_commands(
                    [BotCommand("start", "Live scores and sports updates"),
                     BotCommand("help", "How Fantzo Live Line works")]
                    if mode == LIVE_LINE else gate.PREVERIFY_COMMANDS
                )
    except Exception:
        log.exception("Could not update default mode menu")
    finally:
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
    """Verified private chats keep the Full Fantzo menu in both modes."""
    if _mode() != mode:
        return True
    try:
        if not gate.is_registered(user_id):
            return True
        commands = gate.VERIFIED_COMMANDS
        menu_url = tracked.tracked_url("telegram_native_menu")
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
                text=_verified_menu_text(), web_app=WebAppInfo(url=menu_url),
            ),
        ), mode, user_id, "menu",
    )
    return commands_ok and menu_ok


async def _set_unverified_chat_ui(bot, user_id: int, mode: str) -> bool:
    """A verification prompt pinned a per-chat Commands menu; follow the default."""
    if _mode() != mode or mode != LIVE_LINE:
        return True
    if _is_verified_user(user_id):
        return True
    return await _telegram_menu_write(
        lambda: bot.set_chat_menu_button(
            chat_id=int(user_id), menu_button=MenuButtonDefault(),
        ), mode, user_id, "menu",
    )


def _paged_user_ids(sql_max: str, sql_page: str):
    """Yield user ids from a fixed snapshot in small pages."""
    assert _store is not None
    with closing(sqlite3.connect(_store.db_path, timeout=15)) as conn:
        row = conn.execute(sql_max).fetchone()
        last_user_id = int(row[0] or 0)
    cursor = 0
    while cursor < last_user_id:
        with closing(sqlite3.connect(_store.db_path, timeout=15)) as conn:
            rows = conn.execute(sql_page, (cursor, last_user_id, MENU_RECONCILE_BATCH)).fetchall()
        if not rows:
            return
        for row in rows:
            cursor = int(row[0])
            yield cursor


async def _reconcile_chats(bot, mode: str) -> bool:
    verified = 0
    defaulted = 0
    needs_retry = False
    try:
        for user_id in _paged_user_ids(
            "SELECT MAX(user_id) FROM live_tv_mobile_users WHERE capture_method='telegram_contact'",
            "SELECT user_id FROM live_tv_mobile_users WHERE capture_method='telegram_contact' "
            "AND user_id > ? AND user_id <= ? ORDER BY user_id LIMIT ?",
        ):
            if _mode() != mode:
                return True
            if await _set_verified_chat_ui(bot, user_id, mode) is False:
                needs_retry = True
            verified += 1
            await asyncio.sleep(MENU_RECONCILE_DELAY_SECONDS)
        for admin_id in sorted(_admin_ids()):
            if _mode() == mode and admin_id:
                if await _set_verified_chat_ui(bot, admin_id, mode) is False:
                    needs_retry = True
        if mode == LIVE_LINE:
            # Only chats that were shown the verification prompt carry a
            # per-chat Commands menu that would hide the Live Line default.
            for user_id in _paged_user_ids(
                "SELECT MAX(user_id) FROM mobile_verification_events",
                "SELECT DISTINCT user_id FROM mobile_verification_events "
                "WHERE user_id > ? AND user_id <= ? ORDER BY user_id LIMIT ?",
            ):
                if _mode() != mode:
                    return True
                if _is_verified_user(user_id):
                    continue
                if await _set_unverified_chat_ui(bot, user_id, mode) is False:
                    needs_retry = True
                defaulted += 1
                await asyncio.sleep(MENU_RECONCILE_DELAY_SECONDS)
    except sqlite3.Error as exc:
        log.warning("Chat menu reconciliation unavailable error=%s", type(exc).__name__)
        return False
    log.info("Fantzo chat menu reconciliation mode=%s full_menu=%s live_line_default=%s",
             mode, verified, defaulted)
    return not needs_retry


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
            success = await _reconcile_chats(bot, mode)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Fantzo chat menu reconciliation failed")
            success = False
        if _mode() != mode or success:
            return
        await asyncio.sleep(MENU_RETRY_SECONDS)


def _schedule_menu_reconciliation(bot) -> None:
    global _menu_reconciliation_task
    previous = _menu_reconciliation_task
    if previous is not None and not previous.done():
        previous.cancel()
    _menu_reconciliation_task = asyncio.create_task(
        _menu_reconciliation_loop(bot, previous),
        name="fantzo-mode-menu-reconciliation",
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
    action = parse_admin_mode_request(
        int(user.id) if user else 0, _admin_ids(), list(context.args or []),
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
    if not query or not user or not chat or chat.type != "private" or not _is_admin_user(user.id):
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


def _live_line_text() -> str:
    return (f"⚡ {_brand_label().upper()} LIVE LINE\n\n"
            "🏏 Live scores, full scorecards and match updates.\n"
            "👇 Tap below to open.")


async def _send_live_line_scores(message) -> None:
    """The only reply unverified users receive in Live Line mode."""
    await message.reply_text(
        _live_line_text(),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
            _score_button_label(), web_app=WebAppInfo(url=_scores_url()),
        )]]),
    )


def _is_business_owner(message) -> bool:
    try:
        owner_id = business._owner_user_id(getattr(message, "business_connection_id", "") or "")
    except Exception:
        return False
    sender = getattr(message, "from_user", None)
    return bool(owner_id and sender and int(sender.id) == int(owner_id))


async def _guard_update(update, context) -> None:
    if _mode() == FULL:
        return
    # Only user messages, Business messages and button taps are intercepted;
    # connection, membership and other service updates keep their handlers.
    if not (update.message or update.edited_message or update.business_message
            or update.callback_query):
        return
    user = update.effective_user
    # The admin and verified users keep the complete Full bot.
    if user and (_is_admin_user(user.id) or _is_verified_user(user.id)):
        return
    if update.business_message and _is_business_owner(update.business_message):
        return  # The owner's own replies in a client chat.
    if update.edited_message:
        raise ApplicationHandlerStop
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
    command = parts[0].split("@", 1)[0].lower() if parts and parts[0].startswith("/") else ""
    start_arg = parts[1].split(maxsplit=1)[0].lower() if command == "/start" and len(parts) > 1 else ""

    if not update.business_message and (
        start_arg == "stopreminders" or command == "/stop"
        or " ".join(message_text.casefold().split()) in STOP_TEXTS
    ):
        # Fantzo's existing opt-out handlers reply and stop contact.
        return

    if getattr(message, "contact", None) is not None and not update.business_message:
        # A self-shared contact goes to the normal verification handler.
        return

    if update.business_message:
        await message.reply_text(
            _live_line_text(),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                _score_button_label(), url=_scores_url(),
            )]]),
        )
        raise ApplicationHandlerStop

    if command == "/start":
        try:
            core.touch_user(update)
            lead_funnel.record_start(user.id, parts[1].split(maxsplit=1)[0] if len(parts) > 1 else "")
        except Exception:
            log.exception("Could not record Live Line start")

    await _send_live_line_scores(message)
    raise ApplicationHandlerStop


# ---------------------------------------------------------------------------
# /scores page (Highlightly cricket, allowlisted score fields only)
# ---------------------------------------------------------------------------

def _run_async(coro):
    """The tracking server runs request handlers in plain threads."""
    return asyncio.run(coro)


def _cached(kind: str, key: str, ttl: float, build):
    cache_key = (kind, key)
    with _score_lock:
        cached = _score_cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < ttl:
            return cached[1]
        key_lock = _score_key_locks.setdefault(cache_key, threading.Lock())
    with key_lock:
        with _score_lock:
            cached = _score_cache.get(cache_key)
            if cached and time.monotonic() - cached[0] < ttl:
                return cached[1]
        try:
            value = build()
        except Exception:
            with _score_lock:
                stale = _score_cache.get(cache_key)
            if stale is not None:
                log.warning("Fantzo score feed refresh failed; serving cached %s/%s", kind, key)
                return stale[1]
            raise
        with _score_lock:
            if len(_score_cache) >= 256:
                _score_cache.clear()
            _score_cache[cache_key] = (time.monotonic(), value)
        return value


def _matches_for_date(date_text: str, ttl: float) -> list:
    def build():
        rows = _run_async(core.get_sport_matches_for_date("cricket", date_text))
        return [row for row in rows if isinstance(row, dict)]
    return _cached("date", date_text, ttl, build)


def _state_text(match) -> str:
    return core._state_description(match).casefold()


def _overs(info) -> str:
    found = re.search(r"(\d+(?:\.\d+)?)\s*(?:/\s*\d+\s*)?(?:ov|overs)\b", str(info or ""), re.I)
    return f"{found.group(1)} ov" if found else ""


def _team(match, side: str) -> dict:
    team = match.get(f"{side}Team") or match.get(side) or {}
    team = team if isinstance(team, dict) else {"name": str(team)}
    return {"name": team.get("name") or team.get("displayName") or "",
            "abbr": team.get("abbreviation") or team.get("shortName") or ""}


def _highlightly_row(match) -> dict:
    state = match.get("state") if isinstance(match.get("state"), dict) else {}
    teams = state.get("teams") if isinstance(state.get("teams"), dict) else {}
    home = teams.get("home") if isinstance(teams.get("home"), dict) else {}
    away = teams.get("away") if isinstance(teams.get("away"), dict) else {}
    description = _state_text(match)
    if core._is_live(match, "cricket"):
        display_state = "Live" if description == "in play" else description
    else:
        display_state = description
    return score_match({
        "id": str(match.get("id") or ""),
        "state": display_state,
        "startTime": match.get("startTime") or match.get("date") or "",
        "format": match.get("format") or "",
        "league": core._league_name(match),
        "home": _team(match, "home"),
        "away": _team(match, "away"),
        "homeScore": home.get("score") or "",
        "homeInfo": _overs(home.get("info")),
        "awayScore": away.get("score") or "",
        "awayInfo": _overs(away.get("info")),
    })


def _dates():
    today = datetime.now(core.APP_TIMEZONE).date()
    return today, today - timedelta(days=1), today + timedelta(days=1)


def _safe_rows(mode: str) -> list[dict]:
    if mode not in SCORE_VIEWS:
        mode = "live"
    today, yesterday, tomorrow = _dates()
    today_ttl, other_ttl = SCORE_DATE_TTL_SECONDS["today"], SCORE_DATE_TTL_SECONDS["other"]
    if mode == "live":
        raw = [m for m in _matches_for_date(today.isoformat(), today_ttl)
               if core._is_live(m, "cricket")]
    elif mode == "upcoming":
        raw = [m for m in (_matches_for_date(today.isoformat(), today_ttl)
                           + _matches_for_date(tomorrow.isoformat(), other_ttl))
               if not core._is_live(m, "cricket") and _state_text(m) not in FINISHED_STATES]
        raw.sort(key=lambda m: str(m.get("startTime") or m.get("date") or ""))
    else:
        raw = [m for m in (_matches_for_date(today.isoformat(), today_ttl)
                           + _matches_for_date(yesterday.isoformat(), other_ttl))
               if _state_text(m) in FINISHED_STATES]
        raw.sort(key=lambda m: str(m.get("startTime") or m.get("date") or ""), reverse=True)
    unique, seen = [], set()
    for match in raw:
        key = str(match.get("id") or "")
        if key and key in seen:
            continue
        seen.add(key)
        unique.append(match)
    return score_matches([_highlightly_row(m) for m in unique])


def _score_key(raw: str) -> str:
    key = str(raw or "").strip()
    if not (key.isascii() and key.isdecimal() and 0 < len(key) <= 30):
        raise ValueError("Invalid match key")
    return key


def _listed_score_match(raw_key: str, mode: str) -> dict:
    key = _score_key(raw_key)
    if mode not in SCORE_VIEWS:
        raise ValueError("Invalid match view")
    for row in _safe_rows(mode):
        if row["id"] == key:
            return row
    raise ValueError("Match is not in this score view")


def _safe_score_detail(raw_key: str, mode: str) -> dict:
    row = _listed_score_match(raw_key, mode)
    key = row["id"]

    def build():
        data = _run_async(core.highlightly_get(f"/cricket/matches/{key}"))
        match = data[0] if isinstance(data, list) and data else data
        if not isinstance(match, dict):
            raise RuntimeError("Score detail unavailable")
        return score_detail({
            "match": {**_highlightly_row(match), "id": key},
            "statistics": match.get("statistics") or match.get("innings") or [],
        })

    try:
        safe = _cached("detail", key, SCORE_DETAIL_TTL_SECONDS, build)
    except Exception:
        log.warning("Fantzo score detail unavailable key=%s", key)
        safe = {"match": row, "innings": []}
    return {**safe, "match": merge_score_match(row, safe.get("match") or {})}


def _send_bytes(handler, status: int, body: bytes, content_type: str) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _serve_scores(handler, parsed) -> None:
    query = parse_qs(parsed.query)
    mode = (query.get("mode") or ["live"])[0]
    if mode not in SCORE_VIEWS:
        mode = "live"
    try:
        rows = _safe_rows(mode)
    except Exception:
        log.exception("Fantzo score feed unavailable")
        body = score_page([], _brand_label(), mode, feed_error=True).encode("utf-8")
        return _send_bytes(handler, 503, body, "text/html; charset=utf-8")
    body = score_page(rows, _brand_label(), mode).encode("utf-8")
    return _send_bytes(handler, 200, body, "text/html; charset=utf-8")


def _serve_scores_api(handler, parsed) -> None:
    query = parse_qs(parsed.query)
    action = (query.get("action") or ["matches"])[0]
    mode = (query.get("mode") or ["live"])[0]
    try:
        if action == "matches":
            payload = {"ok": True, "matches": _safe_rows(mode)}
        elif action == "score":
            payload = {"ok": True, "match": _listed_score_match(
                (query.get("id") or [""])[0], mode)}
        elif action == "match":
            payload = {"ok": True, "detail": _safe_score_detail(
                (query.get("id") or [""])[0], mode)}
        else:
            raise ValueError("Invalid score action")
        body = json.dumps(payload).encode("utf-8")
        return _send_bytes(handler, 200, body, "application/json; charset=utf-8")
    except ValueError:
        return _send_bytes(handler, 400, b'{"ok":false,"error":"invalid_request"}',
                           "application/json; charset=utf-8")
    except Exception:
        log.exception("Fantzo score API unavailable")
        return _send_bytes(handler, 503, b'{"ok":false,"error":"feed_unavailable"}',
                           "application/json; charset=utf-8")


def _install_scores_route() -> None:
    cls = analytics.TrackingHandler
    if getattr(cls, "_fantzo_scores_route", False):
        return
    original_get = cls.do_GET

    def scores_get(self):
        parsed = urlparse(self.path)
        if parsed.path == "/scores":
            return _serve_scores(self, parsed)
        if parsed.path == "/scores/api":
            return _serve_scores_api(self, parsed)
        return original_get(self)

    cls.do_GET = scores_get
    cls._fantzo_scores_route = True


def install(brand: str = "fantzo") -> None:
    global _installed, _store, _brand
    if _installed:
        return
    if brand != "fantzo":
        raise ValueError("This runtime is for the Fantzo bot")
    _brand = brand
    _store = ModeStore(os.getenv("DB_PATH", core.DB_PATH), brand)

    original_configure = tracked.app.configure_telegram_ui

    async def configure_with_mode(application):
        await original_configure(application)
        application.add_handler(CommandHandler("mode", _mode_command), group=-100)
        application.add_handler(
            CallbackQueryHandler(_mode_callback, pattern=r"^mode:(liveline|full|status)$"),
            group=-100,
        )
        application.add_handler(TypeHandler(Update, _guard_update), group=-90)
        state = _store.state()
        if state.mode == LIVE_LINE:
            await _set_default_menu(application.bot)
        elif state.revision > 0:
            # Finish restoring Full menus after an earlier Live Line period.
            _schedule_menu_reconciliation(application.bot)

    tracked.app.configure_telegram_ui = configure_with_mode

    original_start_server = analytics.start_tracking_server

    def start_server_with_scores():
        _install_scores_route()
        return original_start_server()

    analytics.start_tracking_server = start_server_with_scores

    original_reminders = reminders.run_due_reminders

    async def reminders_by_mode(application):
        if _mode() == FULL:
            return await original_reminders(_GuardedPublicApplication(application))
        # Verified users keep their normal reminders; unverified chats get none.
        return await original_reminders(
            _GuardedPublicApplication(application, allow_verified=True),
        )

    reminders.run_due_reminders = reminders_by_mode

    original_due_stage = reminders._due_stage

    def due_stage_by_mode(row, now_utc):
        if _mode() != FULL and not _is_verified_user(int(row["user_id"])):
            # No verification reminder is due (nor recorded) in Live Line.
            return None
        return original_due_stage(row, now_utc)

    reminders._due_stage = due_stage_by_mode

    original_post_daily = banner_queue._post_daily

    async def post_daily_by_mode(bot):
        if _mode() != FULL:
            return False  # Channel daily posts stay paused in Live Line.
        return await original_post_daily(_GuardedPublicBot(bot))

    banner_queue._post_daily = post_daily_by_mode

    _installed = True
    log.info(
        "Bot mode controller installed brand=%s initial_mode=%s persistent_storage_ready=%s "
        "scores_url_ready=%s", brand, _mode(), _persistent_mode_storage_ready(),
        _score_destination_ready(),
    )
