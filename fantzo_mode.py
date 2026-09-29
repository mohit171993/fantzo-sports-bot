"""Persistent Fantzo mode switch for the production Telegram launcher.

Full mode leaves the existing handlers alone. Live Line handles every incoming
update before the normal handlers so old inline buttons and direct commands
cannot reopen the website or other full-mode bot flows.
"""

from __future__ import annotations

import asyncio
import logging
import re
from contextlib import closing
from datetime import datetime, timezone
from html import escape
from types import SimpleNamespace
from urllib.parse import urlsplit

from telegram import (
    BotCommand,
    BotCommandScopeChat,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonCommands,
    MenuButtonWebApp,
    ReplyKeyboardRemove,
    Update,
    WebAppInfo,
)
from telegram.ext import ApplicationHandlerStop, CallbackQueryHandler, CommandHandler, TypeHandler

import bot as core

logger = logging.getLogger(__name__)
_MODE_KEY = "fantzo_public_mode"
_installed = False
_menu_sync_task: asyncio.Task | None = None
_menu_sync_lock = asyncio.Lock()
_TEAM_ACTION = re.compile(r"^team:(cricket|football):([A-Za-z0-9_-]{1,32})$")
_TEAM_LIST_ACTION = re.compile(r"^team_(up|recent):(cricket|football):([A-Za-z0-9_-]{1,32})$")


def ensure_table() -> None:
    with closing(core.db()) as conn, conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS fantzo_mode_settings "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS fantzo_mode_audit "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, mode TEXT NOT NULL, "
            "actor_user_id INTEGER NOT NULL, changed_at TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS fantzo_mode_menu_sync "
            "(user_id INTEGER PRIMARY KEY, target_mode TEXT NOT NULL, "
            "status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, "
            "last_error TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL)"
        )


def get_mode() -> str:
    try:
        with closing(core.db()) as conn:
            row = conn.execute(
                "SELECT value FROM fantzo_mode_settings WHERE key=?", (_MODE_KEY,)
            ).fetchone()
        mode = str(row["value"]) if row else "full"
        if mode == "liveline":
            mode = "livetv"
        if mode not in {"full", "livetv"}:
            raise ValueError("Invalid Fantzo mode in database")
        return mode
    except Exception:
        # An unreadable state must never accidentally expose full-mode flows.
        logger.exception("Fantzo mode state unavailable; serving Live Line")
        return "livetv"


def is_liveline() -> bool:
    return get_mode() == "livetv"


def is_livetv() -> bool:
    return is_liveline()


def public_livetv_problem() -> str | None:
    """Return a non-secret reason Live TV cannot be activated, or None."""
    import fantzo_live_tv
    if not fantzo_live_tv.is_public_enabled():
        return "public Live TV is disabled"
    base = str(fantzo_live_tv.TRACKING_BASE_URL or "").strip()
    public_url = str(fantzo_live_tv.minitv_url() or "").strip()
    public = urlsplit(public_url)
    if not base or public.scheme != "https" or not public.hostname or public.path != "/minitv" or public.query or public.fragment:
        return "the public HTTPS MiniTV URL is not configured"
    provider = urlsplit(str(fantzo_live_tv.LIVE_TV_URL or ""))
    if provider.scheme != "https" or not provider.hostname or provider.username or provider.password:
        return "the public Live TV provider URL is not configured"
    if provider.path == "/open" and "key=" in provider.query.casefold():
        return "the Live TV provider URL appears to be a private test link"
    return None


def set_mode(mode: str, actor_user_id: int) -> None:
    if mode not in {"full", "livetv"}:
        raise ValueError("Unsupported Fantzo mode")
    if int(actor_user_id) != int(core.ADMIN_USER_ID):
        raise PermissionError("Only the Fantzo admin can change mode")
    now = datetime.now(timezone.utc).isoformat()
    with closing(core.db()) as conn, conn:
        conn.execute(
            "INSERT INTO fantzo_mode_settings(key,value,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
            (_MODE_KEY, mode, now),
        )
        conn.execute(
            "INSERT INTO fantzo_mode_audit(mode,actor_user_id,changed_at) VALUES(?,?,?)",
            (mode, int(actor_user_id), now),
        )
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='live_tv_mobile_users'"
        ).fetchone()
        if table:
            conn.execute(
                "INSERT INTO fantzo_mode_menu_sync(user_id,target_mode,status,attempts,last_error,updated_at) "
                "SELECT user_id, ?, 'pending', 0, '', ? FROM live_tv_mobile_users "
                "WHERE capture_method='telegram_contact' "
                "ON CONFLICT(user_id) DO UPDATE SET "
                "target_mode=excluded.target_mode,status='pending',attempts=0,last_error='',updated_at=excluded.updated_at",
                (mode, now),
            )
    logger.info("Fantzo mode changed to %s by admin %s", mode, actor_user_id)


def menu_sync_counts(mode: str | None = None) -> dict[str, int]:
    target = mode or get_mode()
    with closing(core.db()) as conn:
        rows = conn.execute(
            "SELECT status,COUNT(*) AS c FROM fantzo_mode_menu_sync "
            "WHERE target_mode=? GROUP BY status", (target,)
        ).fetchall()
    return {str(row["status"]): int(row["c"]) for row in rows}


async def _sync_one_chat_menu(bot, user_id: int, mode: str) -> None:
    import fantzo_live_tv_mobile_gate
    # A user can lose verification after being queued (for example during a
    # re-verification reset). Never install a verified menu for that chat.
    if not fantzo_live_tv_mobile_gate.is_registered(user_id):
        await bot.set_my_commands(
            fantzo_live_tv_mobile_gate.PREVERIFY_COMMANDS,
            scope=BotCommandScopeChat(chat_id=user_id),
        )
        await bot.set_chat_menu_button(chat_id=user_id, menu_button=MenuButtonCommands())
        return
    if mode == "livetv":
        await bot.set_my_commands([
            BotCommand("start", "Open Fantzo Live TV"),
            BotCommand("team", "Find a cricket or football team"),
            BotCommand("sports", "View live sports coverage"),
            BotCommand("help", "Fantzo Live TV help"),
        ], scope=BotCommandScopeChat(chat_id=user_id))
        await bot.set_chat_menu_button(chat_id=user_id, menu_button=MenuButtonCommands())
    else:
        import bot_tracked
        await bot.set_my_commands(
            fantzo_live_tv_mobile_gate.VERIFIED_COMMANDS,
            scope=BotCommandScopeChat(chat_id=user_id),
        )
        await bot.set_chat_menu_button(
            chat_id=user_id,
            menu_button=MenuButtonWebApp(
                text="Open Fantzo",
                web_app=WebAppInfo(url=bot_tracked.tracked_url("telegram_native_menu")),
            ),
        )


async def _drain_menu_sync(bot) -> None:
    async with _menu_sync_lock:
        while True:
            mode = get_mode()
            with closing(core.db()) as conn:
                row = conn.execute(
                    "SELECT user_id,attempts FROM fantzo_mode_menu_sync "
                    "WHERE target_mode=? AND status='pending' ORDER BY user_id LIMIT 1",
                    (mode,),
                ).fetchone()
            if row is None:
                return
            user_id = int(row["user_id"])
            attempts = int(row["attempts"])
            error = ""
            try:
                await _sync_one_chat_menu(bot, user_id, mode)
                status = "done"
            except Exception as exc:
                error = f"{type(exc).__name__}: {str(exc)[:160]}"
                status = "failed" if attempts + 1 >= 3 else "pending"
                logger.warning("Fantzo %s menu sync failed for user %s: %s", mode, user_id, error)
            with closing(core.db()) as conn, conn:
                conn.execute(
                    "UPDATE fantzo_mode_menu_sync SET status=?,attempts=?,last_error=?,updated_at=? "
                    "WHERE user_id=? AND target_mode=?",
                    (status, attempts + 1, error, datetime.now(timezone.utc).isoformat(), user_id, mode),
                )
            # Bounded rate, including retries. A later mode switch updates the
            # target rows and is picked up by this same worker.
            await asyncio.sleep(0.25 if status == "done" else min(3, attempts + 1))


def schedule_menu_sync(bot) -> None:
    global _menu_sync_task
    if _menu_sync_task is None or _menu_sync_task.done():
        _menu_sync_task = asyncio.create_task(_drain_menu_sync(bot), name="fantzo-mode-menu-sync")


def mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📺 Live TV", callback_data="fantzo_mode:livetv")],
        [InlineKeyboardButton("🔓 Full", callback_data="fantzo_mode:full")],
    ])


def liveline_keyboard() -> InlineKeyboardMarkup:
    import fantzo_live_tv
    rows = []
    # Only the existing public MiniTV route is eligible. The private SKY_ADMIN
    # URL embeds a test credential and must never appear in public mode.
    public_url = fantzo_live_tv.minitv_url()
    if public_livetv_problem() is None:
        rows.append([InlineKeyboardButton("▶ Watch Live TV", web_app=WebAppInfo(url=public_url))])
    rows.extend([
        [InlineKeyboardButton("📺 Check Live TV", callback_data="live_tv_status")],
        [InlineKeyboardButton("🔴 Live scores", callback_data="live_now")],
        [
            InlineKeyboardButton("🏏 Cricket", callback_data="cricket"),
            InlineKeyboardButton("⚽ Football", callback_data="football"),
        ],
        [
            InlineKeyboardButton("🗓 Fixtures", callback_data="upcoming"),
            InlineKeyboardButton("✅ Results", callback_data="results"),
        ],
        [InlineKeyboardButton("🔎 Find a team", callback_data="find_team")],
    ])
    return InlineKeyboardMarkup(rows)


def liveline_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔴 Live scores", callback_data="live_now")],
        [InlineKeyboardButton("⬅️ Sports menu", callback_data="back")],
    ])


async def _sync_public_menu(bot) -> None:
    """Apply the mode's global menu, restoring the launcher's exact Full UI."""
    if is_livetv():
        await bot.set_my_commands([
            BotCommand("start", "Open Fantzo Live TV"),
            BotCommand("sports", "Cricket and football scores"),
            BotCommand("team", "Find a cricket or football team"),
            BotCommand("help", "Fantzo Live TV help"),
        ])
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    else:
        import fantzo_live_tv_mobile_gate
        await fantzo_live_tv_mobile_gate.configure_public_ui(
            SimpleNamespace(bot=bot)
        )


async def _mode_reply(update: Update, context, requested: str) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message or not update.effective_chat:
        return
    if update.effective_chat.type != "private" or int(user.id) != int(core.ADMIN_USER_ID):
        return
    if requested == "livetv":
        problem = public_livetv_problem()
        if problem:
            await message.reply_text(
                f"Live TV mode was not activated: {problem}. Current mode remains "
                f"{'Live TV' if is_livetv() else 'Full'}.",
                reply_markup=mode_keyboard(),
            )
            return
    if requested in {"livetv", "full"}:
        set_mode(requested, int(user.id))
        schedule_menu_sync(context.bot)
        try:
            await _sync_public_menu(context.bot)
        except Exception:
            logger.exception("Fantzo mode saved but Telegram global menu update failed")
    current = get_mode()
    counts = menu_sync_counts(current)
    degraded = public_livetv_problem() if current == "livetv" else None
    warning = f"⚠️ Public Live TV unavailable: {degraded}.\n" if degraded else ""
    await message.reply_text(
        f"Fantzo mode: <b>{'Live TV' if current == 'livetv' else 'Full'}</b>\n"
        "Live TV shows the clean TV and sports screens. Full restores the existing bot flows.\n"
        "Ad campaigns are managed separately.\n"
        f"{warning}"
        f"Chat menus updated: {counts.get('done', 0)}; pending: {counts.get('pending', 0)}; failed: {counts.get('failed', 0)}.",
        parse_mode="HTML",
        reply_markup=mode_keyboard(),
    )


async def mode_command(update: Update, context) -> None:
    requested = str(context.args[0]).lower() if context.args else "status"
    if requested in {"clean", "liveline"}:
        requested = "livetv"
    if requested not in {"status", "livetv", "full"}:
        requested = "status"
    await _mode_reply(update, context, requested)
    # Non-admins receive no response, including from later generic handlers.
    raise ApplicationHandlerStop


async def mode_callback(update: Update, context) -> None:
    query = update.callback_query
    user = update.effective_user
    chat = update.effective_chat
    if not query or not user or not chat or chat.type != "private" or int(user.id) != int(core.ADMIN_USER_ID):
        raise ApplicationHandlerStop
    mode = str(query.data or "").partition(":")[2]
    if mode == "livetv":
        problem = public_livetv_problem()
        if problem:
            await query.answer(f"Live TV not activated: {problem}. Mode unchanged.", show_alert=True)
            raise ApplicationHandlerStop
    if mode in {"full", "livetv"}:
        set_mode(mode, int(user.id))
        schedule_menu_sync(context.bot)
        try:
            await _sync_public_menu(context.bot)
        except Exception:
            logger.exception("Fantzo mode saved but Telegram global menu update failed")
    await query.answer()
    counts = menu_sync_counts()
    await query.edit_message_text(
        f"Fantzo mode: <b>{'Live TV' if get_mode() == 'livetv' else 'Full'}</b>\n"
        "Ad campaigns are managed separately.\n"
        f"Chat menus updated: {counts.get('done', 0)}; pending: {counts.get('pending', 0)}; failed: {counts.get('failed', 0)}.",
        parse_mode="HTML",
        reply_markup=mode_keyboard(),
    )
    raise ApplicationHandlerStop


def _clean_match_list(matches, sport: str, heading: str, empty: str) -> str:
    if not matches:
        return f"<b>{heading}</b>\n\n{empty}"
    lines = [f"<b>{heading}</b>", ""]
    for idx, match in enumerate(matches[:8], start=1):
        home = escape(core._team_name(match, "home")[:80])
        away = escape(core._team_name(match, "away")[:80])
        if sport == "cricket":
            home_score = core._cricket_team_score(match, "home")
            away_score = core._cricket_team_score(match, "away")
            if home_score or away_score:
                score_line = f"{home} {escape(str(home_score or '-'))} · {away} {escape(str(away_score or '-'))}"
            else:
                score_line = f"{home} vs {away}"
        else:
            score = core._generic_score(match)
            score_line = f"{home} {escape(str(score))} {away}" if score else f"{home} vs {away}"
        status = escape(core._state_description(match)[:70])
        lines.append(f"{idx}. {score_line}\n⏱ {status}")
        lines.append("")
    return "\n".join(lines).strip()


async def _live_scores() -> str:
    results = await asyncio.gather(
        core.get_live_matches("cricket"), core.get_live_matches("football"),
        return_exceptions=True,
    )
    if all(isinstance(result, Exception) for result in results):
        return "Live scores are temporarily unavailable. Please try again shortly."
    sections = ["🔴 <b>LIVE SCORES</b>"]
    for sport, result in zip(("cricket", "football"), results):
        sections.append(_clean_match_list(
            [] if isinstance(result, Exception) else result,
            sport,
            "🏏 Cricket" if sport == "cricket" else "⚽ Football",
            "No live matches right now." if not isinstance(result, Exception) else "Updates temporarily unavailable.",
        ))
    return "\n\n".join(sections)


async def _sport_scores(sport: str) -> str:
    try:
        matches = await core.get_live_matches(sport)
    except Exception:
        logger.exception("Fantzo Live Line %s scores unavailable", sport)
        return "Live scores are temporarily unavailable. Please try again shortly."
    return _clean_match_list(matches, sport, "🏏 CRICKET" if sport == "cricket" else "⚽ FOOTBALL", "No live matches right now.")


async def _today_matches(recent: bool) -> str:
    date_text = datetime.now(core.APP_TIMEZONE).date().isoformat()
    results = await asyncio.gather(
        core.get_sport_matches_for_date("cricket", date_text),
        core.get_sport_matches_for_date("football", date_text),
        return_exceptions=True,
    )
    if all(isinstance(result, Exception) for result in results):
        return "Match updates are temporarily unavailable. Please try again shortly."
    sections = ["✅ <b>TODAY'S RESULTS</b>" if recent else "🗓 <b>TODAY'S FIXTURES</b>"]
    for sport, result in zip(("cricket", "football"), results):
        if isinstance(result, Exception):
            matches = []
            empty = "Updates temporarily unavailable."
        else:
            matches = [
                match for match in result
                if isinstance(match, dict)
                and core._state_description(match).casefold() in (
                    core.FINISHED_STATES if recent else core.UPCOMING_STATES
                )
            ]
            empty = "No matches found."
        sections.append(_clean_match_list(
            matches, sport,
            "🏏 Cricket" if sport == "cricket" else "⚽ Football",
            empty,
        ))
    return "\n\n".join(sections)


async def _tv_status() -> str:
    import bot_tracked_livefix
    if public_livetv_problem():
        return "📺 <b>Fantzo Live TV</b>\n\nPublic Live TV is currently unavailable. You can still check match scores."
    try:
        _all_today, live_now, future_today = await bot_tracked_livefix.cached_today_tv_matches()
    except Exception:
        logger.exception("Fantzo Live TV status unavailable")
        return "📺 <b>Fantzo Live TV</b>\n\nMatch status is temporarily unavailable. Check again shortly."
    if live_now:
        lines = ["📺 <b>Fantzo Live TV</b>", "", "🔴 Live now:"]
        for sport, match in live_now[:3]:
            home = escape(core._team_name(match, "home")[:80])
            away = escape(core._team_name(match, "away")[:80])
            lines.append(f"{'🏏' if sport == 'cricket' else '⚽'} {home} vs {away}")
        lines.append("\nUse Watch Live TV below to open the stream.")
        return "\n".join(lines)
    if future_today:
        _, sport, match = future_today[0]
        home = escape(core._team_name(match, "home")[:80])
        away = escape(core._team_name(match, "away")[:80])
        return f"📺 <b>Fantzo Live TV</b>\n\nNo live match now. Next today: {'🏏' if sport == 'cricket' else '⚽'} {home} vs {away}."
    return "📺 <b>Fantzo Live TV</b>\n\nNo live matches right now. Check again later."


async def send_livetv_home(update: Update) -> None:
    text = (
        "📺 <b>Fantzo Live TV</b>\n\nLive TV is temporarily unavailable. Match updates remain available."
        if public_livetv_problem() else
        "📺 <b>Fantzo Live TV</b>\n\nWatch live sports and follow match updates."
    )
    await _edit_or_send(update, text, liveline_keyboard())


async def _team_search(query: str) -> tuple[str, InlineKeyboardMarkup]:
    if not query:
        return "🔎 <b>Find a team</b>\n\nUse <code>/team India</code> or <code>/team Arsenal</code>.", liveline_back_keyboard()
    cricket, football = await asyncio.gather(
        core.search_teams("cricket", query), core.search_teams("football", query),
        return_exceptions=True,
    )
    rows = []
    for sport, result in (("cricket", cricket), ("football", football)):
        if isinstance(result, Exception):
            continue
        for team in result[:3]:
            team_id = str(team.get("id") or "")
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", team_id):
                continue
            name = str(team.get("name") or "Team")[:38]
            rows.append([InlineKeyboardButton(
                ("🏏 " if sport == "cricket" else "⚽ ") + name,
                callback_data=f"team:{sport}:{team_id}",
            )])
    rows.append([InlineKeyboardButton("⬅️ Sports menu", callback_data="back")])
    text = f"🔎 <b>Teams matching {escape(query[:80])}</b>" if len(rows) > 1 else "No teams found. Try another spelling."
    return text, InlineKeyboardMarkup(rows)


async def _team_action(action: str) -> tuple[str, InlineKeyboardMarkup]:
    found = _TEAM_ACTION.fullmatch(action)
    if found:
        sport, team_id = found.groups()
        try:
            team = await core.get_team(sport, team_id)
            name = escape(str(team.get("name") or "Team")[:80])
        except Exception:
            name = "Team"
        return f"<b>{name}</b>\n\nChoose an update:", InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🗓 Fixtures", callback_data=f"team_up:{sport}:{team_id}"),
                InlineKeyboardButton("✅ Results", callback_data=f"team_recent:{sport}:{team_id}"),
            ],
            [InlineKeyboardButton("⬅️ Sports menu", callback_data="back")],
        ])
    found = _TEAM_LIST_ACTION.fullmatch(action)
    if found:
        period, sport, team_id = found.groups()
        try:
            matches = await core.get_team_matches(sport, team_id, period == "recent")
        except Exception:
            logger.exception("Fantzo Live Line team match lookup failed")
            return "Match updates are temporarily unavailable.", liveline_back_keyboard()
        heading = "LATEST RESULTS" if period == "recent" else "UPCOMING FIXTURES"
        return _clean_match_list(matches, sport, heading, "No matches found."), liveline_back_keyboard()
    return "Sports menu", liveline_keyboard()


async def _edit_or_send(update: Update, text: str, keyboard: InlineKeyboardMarkup) -> None:
    query = update.callback_query
    if query:
        await query.answer()
        try:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard, disable_web_page_preview=True)
        except Exception:
            # Old full-mode cards may be a photo with caption rather than text.
            await query.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard, disable_web_page_preview=True)
    elif update.effective_message:
        await update.effective_message.reply_text(text, parse_mode="HTML", reply_markup=keyboard, disable_web_page_preview=True)


async def _handle_liveline(update: Update, context) -> None:
    message = update.effective_message
    query = update.callback_query
    if query:
        action = str(query.data or "")
        if action == "live_tv_status":
            text, keyboard = await _tv_status(), liveline_keyboard()
        elif action == "live_now":
            text, keyboard = await _live_scores(), liveline_back_keyboard()
        elif action in {"cricket", "football"}:
            text, keyboard = await _sport_scores(action), liveline_back_keyboard()
        elif _TEAM_ACTION.fullmatch(action) or _TEAM_LIST_ACTION.fullmatch(action):
            text, keyboard = await _team_action(action)
        elif action == "find_team":
            text, keyboard = await _team_search("")
        elif action in {"upcoming", "results"}:
            text, keyboard = await _today_matches(action == "results"), liveline_back_keyboard()
        else:
            # Old full-mode buttons, including joins, funnels and admin previews,
            # must not reach the previous callback handlers.
            text, keyboard = "📺 <b>Fantzo Live TV</b>\n\nLive sports and match updates are available below.", liveline_keyboard()
        await _edit_or_send(update, text, keyboard)
        return
    if not message:
        return
    raw = str(message.text or "").strip()
    command = raw.split(None, 1)[0].split("@", 1)[0].lower() if raw.startswith("/") else ""
    if command in {"/stop", "/stopreminders"} or raw.casefold() in {"stop", "unsubscribe", "do not contact"}:
        # A user's opt-out must still work in either mode.
        import fantzo_lead_funnel
        if update.effective_user:
            fantzo_lead_funnel.stop_user_contact(update.effective_user.id)
        await message.reply_text("Contact and reminder messages are off.", reply_markup=ReplyKeyboardRemove())
        return
    if command == "/team":
        text, keyboard = await _team_search(" ".join(raw.split()[1:]))
    elif command == "/sports":
        text, keyboard = "📺 Live TV, 🏏 cricket and ⚽ football match updates.", liveline_keyboard()
    elif command == "/help":
        text, keyboard = "Use /start for Fantzo Live TV, or /team TEAMNAME for fixtures and results.", liveline_keyboard()
    else:
        text, keyboard = "📺 <b>Fantzo Live TV</b>\n\nLive sports and match updates.", liveline_keyboard()
    # Remove any persistent full-mode reply keyboard before showing new inline actions.
    if command == "/start":
        await message.reply_text("Fantzo Live TV is ready.", reply_markup=ReplyKeyboardRemove())
    await _edit_or_send(update, text, keyboard)


async def liveline_guard(update: Update, context) -> None:
    message = update.effective_message
    query = update.callback_query
    # Mode commands from non-admins must stay silent even in Full mode.
    words = str(message.text or "").split(None, 1) if message else []
    if words and words[0].split("@", 1)[0].lower() == "/mode":
        raise ApplicationHandlerStop
    if query and str(query.data or "").startswith("fantzo_mode:"):
        raise ApplicationHandlerStop
    if not is_livetv():
        return
    user = update.effective_user
    chat = update.effective_chat
    if user and chat and chat.type == "private" and int(user.id) == int(core.ADMIN_USER_ID):
        # Administrative reporting, CRM, banner drafting and ops still work.
        # Suppress only public sends; the channel queue has a second guard.
        if words and words[0].split("@", 1)[0].lower() == "/broadcast":
            await message.reply_text("Switch to Full mode before broadcasting.")
            raise ApplicationHandlerStop
        if not words or words[0].split("@", 1)[0].lower() not in {"/start", "/help", "/sports", "/team"}:
            return
    # Keep Telegram Business connection bookkeeping, which produces no public content.
    if update.business_connection and not message and not query:
        return
    if update.business_message:
        if message:
            import fantzo_live_tv_mobile_gate
            verified = bool(user and fantzo_live_tv_mobile_gate.is_registered(user.id))
            kwargs = {
                "chat_id": message.chat_id,
                "text": (
                    "Fantzo Live TV is ready. Open @fantzoofficialbot to watch live sports."
                    if verified else
                    "Open @fantzoofficialbot and verify your Telegram account to watch Live TV."
                ),
            }
            business_id = getattr(message, "business_connection_id", None)
            if business_id:
                kwargs["business_connection_id"] = business_id
            try:
                await context.bot.send_message(**kwargs)
            except Exception:
                logger.exception("Fantzo clean Business DM handoff failed")
        raise ApplicationHandlerStop
    if chat and chat.type != "private":
        # A group or channel update must never fall through to old Full
        # handlers or cause unsolicited Live TV replies to every group post.
        raise ApplicationHandlerStop
    if user and chat and chat.type == "private":
        import fantzo_live_tv_mobile_gate
        if not fantzo_live_tv_mobile_gate.is_registered(user.id):
            # Keep the existing neutral Telegram self-contact verification.
            # Its verified handoff is patched below to land on Live TV.
            return
    if message and not update.effective_user:
        raise ApplicationHandlerStop
    try:
        await _handle_liveline(update, context)
    except Exception:
        logger.exception("Fantzo Live Line update failed")
        if query:
            try:
                await query.answer("Scores are temporarily unavailable.", show_alert=True)
            except Exception:
                pass
    raise ApplicationHandlerStop


def install(application) -> None:
    global _installed
    if _installed:
        return
    ensure_table()
    _installed = True
    application.add_handler(CommandHandler("mode", mode_command), group=-101)
    application.add_handler(CallbackQueryHandler(mode_callback, pattern=r"^fantzo_mode:(?:livetv|full)$"), group=-101)
    application.add_handler(TypeHandler(Update, liveline_guard), group=-100)
    logger.info("Fantzo persistent Full/Live Line mode guard installed")
