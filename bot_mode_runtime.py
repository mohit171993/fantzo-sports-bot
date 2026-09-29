"""Draft runtime wiring for the shared iBetin/Dura bot codebase.

Install only after the V40 runtime has loaded, before ibetin_start.main().
Full mode delegates to every original handler and route. Live Line mode serves
a separate scores page and intercepts bot-owned messages and web routes.
"""

from __future__ import annotations

import json
import logging
import os
from html import escape
from urllib.parse import parse_qs, urlencode, urlparse

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonCommands,
    MenuButtonWebApp,
    ReplyKeyboardRemove,
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
from scores_only import alert_score_match, score_matches, score_page


log = logging.getLogger(__name__)
_installed = False
_store: ModeStore | None = None
_brand = ""


def _brand_label() -> str:
    return {"ibetin": "iBetin", "dura": "DURA"}.get(_brand, _brand.title())


def _admin_id() -> int:
    try:
        # Match the admin identity used by the existing bot commands, whether
        # it came from Railway's environment or the bot's current default.
        return int(core.ADMIN_USER_ID)
    except (TypeError, ValueError):
        return 0


def _mode() -> str:
    assert _store is not None
    try:
        return _store.state().mode
    except Exception:
        # A temporary SQLite failure must never reopen a betting route.
        log.exception("Mode state unavailable; using clean mode")
        return LIVE_LINE


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


def _mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Live Line", callback_data="mode:liveline")],
        [InlineKeyboardButton("⚙️ Full", callback_data="mode:full")],
        [InlineKeyboardButton("↻ Status", callback_data="mode:status")],
    ])


async def _set_default_menu(bot) -> None:
    if _mode() == LIVE_LINE:
        # Telegram's default menu is visible before mobile verification.
        # The score link is issued per verified user, with a signed token.
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        await bot.set_my_commands([
            BotCommand("start", "Verify your Telegram account"),
            BotCommand("help", "Verification help"),
        ])
    else:
        # Before verification, the existing default is commands-only. Keep
        # that neutral in Full mode; verified users already have their own
        # per-chat Mini App menu from the normal onboarding flow.
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        await bot.set_my_commands([
            BotCommand("start", "Verify your Telegram account"),
            BotCommand("help", "Verification help"),
        ])


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
        int(user.id) if user else 0, _admin_id(), list(context.args or []),
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
    if not query or not user or not chat or chat.type != "private" or user.id != _admin_id():
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


async def _send_verified_scores(message, context, user_id: int) -> None:
    url = _scores_url(user_id)
    try:
        # A neutral hub menu remains useful after switching back to Full.
        # In Live Line the HTTP gate carries its signed access to /scores.
        menu_url = hub.hub_url("home") + "&" + urlencode({
            "access": phone_verify.issue_access_token(user_id),
        })
        await context.bot.set_chat_menu_button(
            chat_id=user_id,
            menu_button=MenuButtonWebApp(
                text=f"Open {_brand_label()}", web_app=WebAppInfo(url=menu_url),
            ),
        )
    except Exception:
        log.exception("Could not update verified score menu")
    await message.reply_text(
        f"📊 {_brand_label()} match scores and updates are here.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
            "Open Match Scores", url=url,
        )]]),
    )


async def _verify_clean_contact(update, context) -> None:
    """Preserve one-time self-contact verification without the Full menu."""
    user, message = update.effective_user, update.effective_message
    contact = getattr(message, "contact", None)
    if not user or not message or not contact:
        return
    was_verified = phone_verify.is_verified(user.id)
    if was_verified and not context.user_data.get("ibetin_mobile_verify_pending"):
        await _send_verified_scores(message, context, user.id)
        return
    if contact.user_id is None or int(contact.user_id) != int(user.id):
        await message.reply_text(
            "Verification failed. Use the Telegram contact button for your own number.",
            reply_markup=tracked._verification_reply_keyboard(),
        )
        return
    lead = leads.get_lead(user.id) or {}
    source = str(context.user_data.pop("ibetin_mobile_verify_source", "") or lead.get("source") or "bot_start")
    campaign = str(context.user_data.pop("ibetin_campaign", "") or lead.get("campaign") or "direct")
    if not phone_verify.verify_user(
        user.id, contact.phone_number, source=source, campaign=campaign,
        contact_consent=True,
    ):
        await message.reply_text(
            "Verification failed. Use the Telegram contact button and try again.",
            reply_markup=tracked._verification_reply_keyboard(),
        )
        return
    context.user_data.pop("ibetin_mobile_verify_pending", None)
    try:
        core.touch_user(update)
        core.track(user.id, f"mobile_verified:{source}")
    except Exception:
        log.exception("Could not track clean-mode mobile verification")
    if not was_verified:
        await tracked._notify_verified_lead(
            context, user, phone_verify.normalize_phone(contact.phone_number), source, campaign,
        )
    await message.reply_text("Verification complete.", reply_markup=ReplyKeyboardRemove())
    await _send_verified_scores(message, context, user.id)


async def _guard_update(update, context) -> None:
    if _mode() == FULL:
        return
    message = update.business_message or update.effective_message
    chat = update.effective_chat
    user = update.effective_user
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

    # Owner commands and reports remain usable in the owner's private chat.
    if user.id == _admin_id() and message_text.startswith("/"):
        return

    if start_arg == "stopreminders" or tracked._is_stop_text(message_text):
        reminders.set_opt_out("bot", user.id, True)
        reminders.set_opt_out("business_dm", user.id, True)
        if start_arg != "stopreminders":
            leads.set_status(user.id, "dnc")
            await message.reply_text("Contact preference updated. Follow-up is stopped.")
        else:
            await message.reply_text("Reminders are off.")
        raise ApplicationHandlerStop

    if getattr(message, "contact", None) is not None:
        await _verify_clean_contact(update, context)
        raise ApplicationHandlerStop

    if is_start:
        campaign = leads.clean_campaign(parts[1] if len(parts) > 1 else "direct")
        try:
            leads.record_start(user.id, campaign=campaign, source="bot")
            context.user_data["ibetin_campaign"] = campaign
            core.track(user.id, f"campaign_start:{campaign}")
        except Exception:
            log.exception("Could not record Live Line campaign start")

    if not phone_verify.is_verified(user.id):
        if update.business_message:
            leads.record_start(user.id, source="business_dm")
            bot_url = phone_verify.verification_bot_url("verify")
            markup = InlineKeyboardMarkup([[InlineKeyboardButton(
                "Open Bot", url=bot_url,
            )]]) if bot_url else None
            await message.reply_text(
                "Open this bot privately and verify your Telegram account to view match scores.",
                reply_markup=markup,
            )
        else:
            await tracked._prompt_mobile_verification(update, context, "bot_start")
        raise ApplicationHandlerStop

    if message and chat and chat.type == "private":
        await _send_verified_scores(message, context, user.id)
    raise ApplicationHandlerStop


def _safe_rows(mode: str):
    if mode not in {"live", "upcoming", "results"}:
        mode = "live"
    # V25 has already patched this accessor to use its warm, stale-while-refresh
    # cache; only our allowlisted score fields leave the server.
    rows, _source = live_runtime.v23._fast_matches(mode)
    return score_matches(rows or [])


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


def _install_http_gate() -> None:
    cls = analytics.TrackingHandler
    if getattr(cls, "_bot_mode_http_gate", False):
        return
    original_get = cls.do_GET
    original_post = getattr(cls, "do_POST", None)

    def gated_get(self):
        parsed = urlparse(self.path)
        decision = http_route(_mode(), "GET", parsed.path)
        if decision == "pass":
            return original_get(self)
        if decision == "scores":
            _user_id, token, verified = _verified_scores_identity(self, parsed)
            if not verified:
                bot_url = phone_verify.verification_bot_url("verify")
                link = (f'<p><a href="{escape(bot_url, quote=True)}">Open the bot to verify</a></p>'
                        if bot_url else "")
                body = ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
                        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
                        "<title>Verify to view match scores</title></head><body><main>"
                        "<h1>Verify to view match scores</h1>"
                        "<p>Open the bot privately and verify your Telegram account.</p>"
                        + link + "</main></body></html>").encode("utf-8")
                return _send_bytes(self, 401, body, "text/html; charset=utf-8")
            mode = (parse_qs(parsed.query).get("mode") or ["live"])[0]
            if (parse_qs(parsed.query).get("access") or [""])[0]:
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
            try:
                rows = _safe_rows(mode)
            except Exception:
                log.exception("Score feed unavailable")
                rows = []
            body = score_page(rows, _brand_label(), mode).encode("utf-8")
            return _send_bytes(self, 200, body, "text/html; charset=utf-8", token)
        if decision == "scores_api":
            _user_id, token, verified = _verified_scores_identity(self, parsed)
            if not verified:
                return _send_bytes(self, 401, b'{"ok":false}', "application/json; charset=utf-8")
            mode = (parse_qs(parsed.query).get("mode") or ["live"])[0]
            try:
                rows = _safe_rows(mode)
                body = json.dumps({"ok": True, "matches": rows}).encode("utf-8")
                return _send_bytes(self, 200, body, "application/json; charset=utf-8", token)
            except Exception:
                log.exception("Score API unavailable")
                return _send_bytes(self, 503, b'{"ok":false}', "application/json; charset=utf-8")
        if decision == "redirect":
            # Preserve first-touch open counts for existing /go ad links while
            # routing the visitor to scores instead of the external site.
            if parsed.path == "/go":
                try:
                    source = (parse_qs(parsed.query).get("source") or ["unknown"])[0]
                    analytics.record_open(analytics._clean_source(source))
                except Exception:
                    log.exception("Could not record Live Line open")
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
        if http_route(_mode(), "POST", parsed.path) == "pass" and original_post:
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
            return await original_reminders(application)
        return None
    reminders.run_due_reminders = reminders_by_mode

    original_channel_daily = reminders.send_liveline_channel_daily
    async def channel_daily_by_mode(*args, **kwargs):
        if _mode() == FULL:
            return await original_channel_daily(*args, **kwargs)
        return False
    reminders.send_liveline_channel_daily = channel_daily_by_mode

    original_channel_launch = reminders.send_liveline_channel_launch
    async def channel_launch_by_mode(*args, **kwargs):
        if _mode() == FULL:
            return await original_channel_launch(*args, **kwargs)
        return False
    reminders.send_liveline_channel_launch = channel_launch_by_mode

    original_alert_text = match_alerts._event_text
    original_alert_markup = match_alerts._markup
    original_alert_send = match_alerts._send

    def alert_text_by_mode(match, sport, event_key, extra, language):
        if _mode() == FULL:
            return original_alert_text(match, sport, event_key, extra, language)
        safe = alert_score_match(match, sport)
        home = escape(safe["home"]["name"])
        away = escape(safe["away"]["name"])
        score = ""
        if safe["home_score"] or safe["away_score"]:
            score = f'\n{escape(safe["home_score"])} – {escape(safe["away_score"])}'
        heading = "मैच अपडेट" if language == "hi" else "Match update"
        return f"📊 <b>{heading}</b>\n\n{home} vs {away}{score}"

    def alert_markup_by_mode(event_key):
        if _mode() == FULL:
            return original_alert_markup(event_key)
        return InlineKeyboardMarkup([[InlineKeyboardButton(
            "Open Match Scores", url=_scores_url(),
        )]])

    async def alert_send_by_mode(bot, user_id, text, markup):
        if _mode() == FULL:
            return await original_alert_send(bot, user_id, text, markup)
        safe_markup = InlineKeyboardMarkup([[InlineKeyboardButton(
            "Open Match Scores", url=_scores_url(user_id),
        )]])
        return await original_alert_send(bot, user_id, text, safe_markup)

    match_alerts._event_text = alert_text_by_mode
    match_alerts._markup = alert_markup_by_mode
    match_alerts._send = alert_send_by_mode
    _installed = True
    log.info("Bot mode controller installed brand=%s initial_mode=%s", brand, _mode())
