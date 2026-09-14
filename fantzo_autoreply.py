import logging
import os
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import bot as core

logger = logging.getLogger(__name__)
SETTING_KEY = "auto_reply_enabled"

IBETIN_HOME_URL = os.getenv("IBETIN_HOME_URL", "https://ibetin.com").strip().rstrip("/")
IBETIN_SPORTS_URL = os.getenv("IBETIN_SPORTS_URL", f"{IBETIN_HOME_URL}/line").strip()
IBETIN_LIVE_URL = os.getenv("IBETIN_LIVE_URL", f"{IBETIN_HOME_URL}/live").strip()
IBETIN_CASINO_URL = os.getenv("IBETIN_CASINO_URL", f"{IBETIN_HOME_URL}/casino").strip()
IBETIN_GAMES_URL = os.getenv("IBETIN_GAMES_URL", f"{IBETIN_HOME_URL}/games").strip()
IBETIN_RESULTS_URL = os.getenv("IBETIN_RESULTS_URL", f"{IBETIN_HOME_URL}/results").strip()
IBETIN_PAYMENT_URL = os.getenv("IBETIN_PAYMENT_URL", f"{IBETIN_HOME_URL}/information/payment").strip()
IBETIN_SUPPORT_URL = os.getenv("IBETIN_SUPPORT_URL", f"{IBETIN_HOME_URL}/information/contacts").strip()


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
        [
            [
                InlineKeyboardButton("🏏 Cricket Scores", callback_data="cricket"),
                InlineKeyboardButton("⚽ Football Scores", callback_data="football"),
            ],
            [
                InlineKeyboardButton("🏆 IBETIN Sports", url=IBETIN_SPORTS_URL),
                InlineKeyboardButton("🔴 IBETIN Live", url=IBETIN_LIVE_URL),
            ],
            [InlineKeyboardButton("⚡ Back to IBETIN Hub", callback_data="back")],
        ]
    )


def _website_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🏆 Sports", url=IBETIN_SPORTS_URL),
                InlineKeyboardButton("🔴 Live", url=IBETIN_LIVE_URL),
            ],
            [
                InlineKeyboardButton("🎰 Live Casino", url=IBETIN_CASINO_URL),
                InlineKeyboardButton("🎮 Games", url=IBETIN_GAMES_URL),
            ],
            [
                InlineKeyboardButton("📊 Results", url=IBETIN_RESULTS_URL),
                InlineKeyboardButton("💳 Payments", url=IBETIN_PAYMENT_URL),
            ],
            [InlineKeyboardButton("🛟 Support", url=IBETIN_SUPPORT_URL)],
            [InlineKeyboardButton("⚡ Back to IBETIN Hub", callback_data="back")],
        ]
    )


def _account_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🌐 OPEN IBETIN", url=IBETIN_HOME_URL)],
            [InlineKeyboardButton("🛟 SUPPORT", url=IBETIN_SUPPORT_URL)],
            [InlineKeyboardButton("⚡ Back to IBETIN Hub", callback_data="back")],
        ]
    )


def _support_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🛟 OFFICIAL SUPPORT", url=IBETIN_SUPPORT_URL)],
            [InlineKeyboardButton("⚡ IBETIN Hub", callback_data="back")],
        ]
    )


def classify_and_reply(text: str):
    t = " ".join((text or "").lower().strip().split())

    if _contains(t, ["hi", "hello", "hey", "hii", "hola", "namaste"]):
        return (
            "greeting",
            "👋 <b>Welcome to IBETIN!</b>\n\n"
            "I can help you navigate Sports, Live, Live Casino, Games, Results, Payments, Support and sports scores.\n\n"
            "What would you like to open?",
            _website_keyboard(),
        )

    if _contains(t, ["casino", "live casino", "dealer", "roulette", "blackjack", "baccarat"]):
        return (
            "casino",
            "🎰 <b>IBETIN Live Casino</b>\n\nOpen the official Live Casino section below.",
            InlineKeyboardMarkup(
                [[InlineKeyboardButton("🎰 OPEN LIVE CASINO", url=IBETIN_CASINO_URL)],
                 [InlineKeyboardButton("⚡ Back to IBETIN Hub", callback_data="back")]]
            ),
        )

    if _contains(t, ["games", "game", "slots", "slot"]):
        return (
            "games",
            "🎮 <b>IBETIN Games</b>\n\nOpen the official Games section below.",
            InlineKeyboardMarkup(
                [[InlineKeyboardButton("🎮 OPEN GAMES", url=IBETIN_GAMES_URL)],
                 [InlineKeyboardButton("⚡ Back to IBETIN Hub", callback_data="back")]]
            ),
        )

    if _contains(t, ["result", "results", "score result", "live result"]):
        return (
            "results",
            "📊 <b>IBETIN Results</b>\n\nOpen the official Results section below.",
            InlineKeyboardMarkup(
                [[InlineKeyboardButton("📊 OPEN RESULTS", url=IBETIN_RESULTS_URL)],
                 [InlineKeyboardButton("⚡ Back to IBETIN Hub", callback_data="back")]]
            ),
        )

    if _contains(t, ["cricket", "ipl", "t20", "odi", "test", "wicket", "score"]):
        return (
            "cricket",
            "🏏 <b>Cricket</b>\n\nUse the bot for scores, or open IBETIN Sports/Live from the buttons below.",
            _sports_keyboard(),
        )

    if _contains(t, ["football", "soccer", "goal", "premier", "champions"]):
        return (
            "football",
            "⚽ <b>Football</b>\n\nUse the bot for scores, or open IBETIN Sports/Live from the buttons below.",
            _sports_keyboard(),
        )

    if _contains(t, ["live", "live sports", "live match", "watch live"]):
        return (
            "live",
            "🔴 <b>IBETIN Live</b>\n\nOpen the official live section below, or use the score buttons for match updates.",
            _sports_keyboard(),
        )

    if _contains(t, ["deposit", "add money", "payment", "payments", "upi", "recharge", "withdraw", "withdrawal", "cashout", "payout"]):
        return (
            "payments",
            "💳 <b>IBETIN Payments</b>\n\nUse the official payment information page and your IBETIN account for available deposit/withdrawal methods.\n\n🔐 Never send card details, OTPs or passwords in Telegram chat.",
            InlineKeyboardMarkup(
                [[InlineKeyboardButton("💳 PAYMENT METHODS", url=IBETIN_PAYMENT_URL)],
                 [InlineKeyboardButton("🌐 OPEN IBETIN", url=IBETIN_HOME_URL)],
                 [InlineKeyboardButton("🛟 SUPPORT", url=IBETIN_SUPPORT_URL)]]
            ),
        )

    if _contains(t, ["login", "password", "otp", "account", "register", "registration", "signup", "sign up"]):
        return (
            "account",
            "👤 <b>Account Help</b>\n\nOpen the official IBETIN website for login or registration. If you have an account problem, use the official support page.\n\n🔐 Never share your password or OTP in this chat.",
            _account_keyboard(),
        )

    if _contains(t, ["bonus", "offer", "promo", "promotion", "cashback"]):
        return (
            "offers",
            "🎁 <b>Offers & Promotions</b>\n\nPlease check IBETIN directly for currently available offers, eligibility and terms.",
            _account_keyboard(),
        )

    if _contains(t, ["support", "help", "problem", "issue", "complaint", "failed", "pending"]):
        return (
            "support",
            "🛟 <b>IBETIN Support</b>\n\nFor account or transaction-specific assistance, use the official IBETIN support page. Do not send passwords, OTPs or full card/bank credentials here.",
            _support_keyboard(),
        )

    if _contains(t, ["thanks", "thank", "thx"]):
        return (
            "thanks",
            "🙏 You're welcome. Tap <b>⚡ IBETIN Hub</b> anytime to open the main sections.",
            _support_keyboard(),
        )

    return (
        "fallback",
        "🤖 <b>IBETIN Assistant</b>\n\nYou can ask me about:\n"
        "• 🏆 Sports / 🔴 Live\n"
        "• 🎰 Live Casino / 🎮 Games\n"
        "• 📊 Results\n"
        "• 💳 Payments\n"
        "• 👤 Login / Registration\n"
        "• 🛟 Support\n"
        "• 🏏 Cricket / ⚽ Football scores\n\n"
        "Or use the IBETIN Hub below.",
        _website_keyboard(),
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

    arg = context.args[0].lower() if context.args else "status"
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
