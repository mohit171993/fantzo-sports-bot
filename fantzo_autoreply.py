import logging
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import bot as core

logger = logging.getLogger(__name__)
SETTING_KEY = "auto_reply_enabled"


def ensure_setting() -> None:
    with core.db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute(
            "INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)",
            (SETTING_KEY, "1"),
        )


def is_enabled() -> bool:
    ensure_setting()
    with core.db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (SETTING_KEY,)).fetchone()
    return not row or str(row["value"]) != "0"


def set_enabled(enabled: bool) -> None:
    ensure_setting()
    with core.db() as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (SETTING_KEY, "1" if enabled else "0"),
        )


def _contains(text: str, words) -> bool:
    return any(re.search(rf"\b{re.escape(word)}\b", text) for word in words)


def _sports_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("🏏 Cricket", callback_data="cricket"),
            InlineKeyboardButton("⚽ Football", callback_data="football"),
        ], [
            InlineKeyboardButton("🔴 Live Now", callback_data="live_now"),
            InlineKeyboardButton("🗓 Upcoming", callback_data="upcoming"),
        ]]
    )


def _account_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔥 JOIN IBETIN NOW 🔥", callback_data="join_fantzo")],
         [InlineKeyboardButton("⚡ Back to IBETIN Menu", callback_data="back")]]
    )


def _support_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⚡ IBETIN Menu", callback_data="back")]]
    )


def classify_and_reply(text: str):
    t = " ".join((text or "").lower().strip().split())

    if _contains(t, ["hi", "hello", "hey", "hii", "hola", "namaste"]):
        return (
            "greeting",
            "👋 <b>Welcome to IBETIN!</b>\n\n"
            "I can help with live scores, cricket, football, account access, deposits/withdrawals and general IBETIN questions.\n\n"
            "What would you like help with?",
            _sports_keyboard(),
        )

    if _contains(t, ["cricket", "ipl", "t20", "odi", "test", "wicket", "score"]):
        return (
            "cricket",
            "🏏 <b>Cricket</b>\n\nUse the buttons below for live matches and upcoming fixtures.",
            _sports_keyboard(),
        )

    if _contains(t, ["football", "soccer", "goal", "premier", "champions"]):
        return (
            "football",
            "⚽ <b>Football</b>\n\nUse the buttons below for live matches and upcoming fixtures.",
            _sports_keyboard(),
        )

    if ("live tv" in t or "live stream" in t or "watch live" in t or "ground commentary" in t):
        return (
            "live_tv",
            "📺 <b>Live TV</b>\n\nLive TV is currently being tested and is not yet available to public users. Live scores and match updates are available from the IBETIN sports menu.",
            _sports_keyboard(),
        )

    if _contains(t, ["deposit", "add money", "payment", "upi", "recharge"]):
        return (
            "deposit",
            "💳 <b>Deposit / Add Money</b>\n\nOpen IBETIN and use the payment options shown inside your account. For security, never send card details, OTPs or passwords in Telegram chat.",
            _account_keyboard(),
        )

    if _contains(t, ["withdraw", "withdrawal", "cashout", "payout"]):
        return (
            "withdrawal",
            "💸 <b>Withdrawal</b>\n\nPlease check the withdrawal section inside your IBETIN account for the current status and available methods. If a transaction is pending, keep the transaction/reference ID ready for support.",
            _account_keyboard(),
        )

    if _contains(t, ["login", "password", "otp", "account", "register", "registration", "signup", "sign up"]):
        return (
            "account",
            "👤 <b>Account Help</b>\n\nTap <b>JOIN IBETIN NOW</b> below to open IBETIN. If you have a login or OTP problem, use the recovery/help option shown on the IBETIN account screen.\n\n🔐 Never share your password or OTP in this chat.",
            _account_keyboard(),
        )

    if _contains(t, ["bonus", "offer", "promo", "promotion", "cashback"]):
        return (
            "offers",
            "🎁 <b>Offers & Promotions</b>\n\nAny currently available offer should be checked directly inside IBETIN, together with its eligibility and terms. I won't invent or promise an offer that isn't shown there.",
            _account_keyboard(),
        )

    if _contains(t, ["support", "help", "problem", "issue", "complaint", "failed", "pending"]):
        return (
            "support",
            "🛟 <b>IBETIN Help</b>\n\nPlease send a short description of the issue and, if it involves a transaction, include only the transaction/reference ID. Do not send passwords, OTPs or full card/bank credentials here.\n\nYou can also open IBETIN and use its official support/help option.",
            _support_keyboard(),
        )

    if _contains(t, ["thanks", "thank", "thx"]):
        return (
            "thanks",
            "🙏 You're welcome. Tap <b>⚡ IBETIN Menu</b> anytime for sports and IBETIN options.",
            _support_keyboard(),
        )

    return (
        "fallback",
        "🤖 <b>IBETIN Assistant</b>\n\nI didn't fully understand that yet. You can ask me about:\n"
        "• 🏏 Cricket / ⚽ Football\n"
        "• 🔴 Live matches\n"
        "• 💳 Deposit / 💸 Withdrawal\n"
        "• 👤 Login / Registration\n"
        "• 🛟 Support\n\n"
        "Or tap the IBETIN Menu below.",
        _support_keyboard(),
    )


async def auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message or not message.text:
        return
    if not is_enabled():
        return

    text = message.text.strip()
    if not text or text.startswith("/"):
        return

    core.touch_user(update)
    category, reply, markup = classify_and_reply(text)
    try:
        core.track(user.id, f"autoreply:{category}")
    except Exception:
        logger.exception("Could not track IBETIN auto reply")

    await message.reply_text(
        reply,
        parse_mode="HTML",
        reply_markup=markup,
        disable_web_page_preview=True,
    )


async def autoreply_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return
    if user.id != core.ADMIN_USER_ID:
        await message.reply_text("This command is restricted.")
        return

    arg = (context.args[0].lower() if context.args else "status")
    if arg in {"on", "enable", "1"}:
        set_enabled(True)
        await message.reply_text("✅ IBETIN auto reply is ON.")
    elif arg in {"off", "disable", "0"}:
        set_enabled(False)
        await message.reply_text("⏸ IBETIN auto reply is OFF.")
    else:
        await message.reply_text(
            f"🤖 IBETIN auto reply is currently <b>{'ON' if is_enabled() else 'OFF'}</b>.\n\n"
            "Use <code>/autoreply on</code> or <code>/autoreply off</code>.",
            parse_mode="HTML",
        )
