import logging
import os
import re
from urllib.parse import quote

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import bot as core

logger = logging.getLogger(__name__)
SETTING_KEY = "auto_reply_enabled"

IBETIN_HOME_URL = os.getenv("IBETIN_HOME_URL", "https://ibetin.com").strip().rstrip("/")


def _public_base_url() -> str:
    value = (
        os.getenv("TRACKING_BASE_URL", "").strip()
        or os.getenv("RAILWAY_STATIC_URL", "").strip()
        or os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
        or "https://ibetin-app-production.up.railway.app"
    )
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    return value.rstrip("/")


def _hub_url(section: str = "home") -> str:
    section = (section or "home").strip().lower()
    return f"{_public_base_url()}/hub?section={quote(section, safe='')}"


def _news_url() -> str:
    return f"{_public_base_url()}/news?category=latest"


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


def _single_button(label: str, section: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, url=_hub_url(section))]]
    )


def _news_button(label: str = "📰 OPEN SPORTS NEWS") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, url=_news_url())]])


def _sports_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🏆 SPORTS", url=_hub_url("sports")),
                InlineKeyboardButton("🔴 LIVE NOW", url=_hub_url("live")),
            ],
            [
                InlineKeyboardButton("📊 RESULTS", url=_hub_url("results")),
                InlineKeyboardButton("📰 NEWS", url=_news_url()),
            ],
        ]
    )


def _account_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("⚡ OPEN IBETIN", url=_hub_url("home"))],
            [
                InlineKeyboardButton("💳 PAYMENTS", url=_hub_url("payments")),
                InlineKeyboardButton("🛟 SUPPORT", url=_hub_url("support")),
            ],
        ]
    )


def _alerts_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔔 MANAGE MATCH ALERTS", url=_hub_url("alerts"))]]
    )


def _support_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🛟 OPEN SUPPORT", url=_hub_url("support"))],
            [InlineKeyboardButton("⚡ IBETIN HOME", url=_hub_url("home"))],
        ]
    )


def standard_reply() -> str:
    return (
        "👋 <b>Welcome to IBETIN</b>\n\n"
        "I can help with live sports, cricket, football, news, match alerts, payments and support.\n\n"
        "Choose an option below or simply type what you need."
    )


def standard_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("⚡ OPEN IBETIN", url=_hub_url("home"))],
            [
                InlineKeyboardButton("🔴 LIVE NOW", url=_hub_url("live")),
                InlineKeyboardButton("📰 NEWS", url=_news_url()),
            ],
            [
                InlineKeyboardButton("🔔 MATCH ALERTS", url=_hub_url("alerts")),
                InlineKeyboardButton("🛟 SUPPORT", url=_hub_url("support")),
            ],
        ]
    )


def classify_and_reply(text: str):
    t = " ".join((text or "").lower().strip().split())

    if _contains(t, ["hi", "hello", "hey", "hii", "hola", "namaste"]):
        return "greeting", standard_reply(), standard_keyboard()

    if _contains(t, ["cricket", "ipl", "t20", "odi", "test", "wicket", "football", "soccer", "goal", "match", "score", "sports"]):
        return (
            "sports",
            "🏆 <b>Sports</b>\n\nOpen live action, fixtures, results or sports news below.",
            _sports_keyboard(),
        )

    if "live tv" in t or "watch live" in t or "live stream" in t or _contains(t, ["live"]):
        return (
            "live",
            "🔴 <b>Live now</b>\n\nOpen the IBETIN live section inside Telegram.",
            _single_button("🔴 OPEN LIVE", "live"),
        )

    if _contains(t, ["news", "update", "updates", "headline", "headlines"]):
        return (
            "news",
            "📰 <b>Sports News</b>\n\nOpen the latest IBETIN sports updates below.",
            _news_button(),
        )

    if _contains(t, ["alert", "alerts", "notification", "notifications", "notify", "reminder", "reminders"]):
        return (
            "alerts",
            "🔔 <b>Match Alerts</b>\n\nManage your Telegram sports notifications inside the IBETIN Mini App.",
            _alerts_keyboard(),
        )

    if _contains(t, ["deposit", "add money", "payment", "pay", "upi", "recharge", "withdraw", "withdrawal", "payout", "cashout", "cash out"]):
        return (
            "payments",
            "💳 <b>Payments</b>\n\nOpen IBETIN payment information or support below. Never share passwords or OTPs in chat.",
            _account_keyboard(),
        )

    if _contains(t, ["login", "password", "otp", "account", "register", "registration", "signup", "sign up", "bonus", "offer", "promo", "promotion"]):
        return (
            "account",
            "👤 <b>Account Help</b>\n\nOpen IBETIN to continue. For account problems, use official support and never send your password or OTP here.",
            _account_keyboard(),
        )

    if _contains(t, ["support", "help", "problem", "issue", "complaint", "failed", "pending", "stuck"]):
        return (
            "support",
            "🛟 <b>IBETIN Support</b>\n\nOpen official support below. If the issue involves a transaction, keep the reference ID ready but do not send passwords, OTPs or full banking credentials.",
            _support_keyboard(),
        )

    if _contains(t, ["thanks", "thank", "thx", "ok", "okay"]):
        return (
            "thanks",
            "🙏 You're welcome. Open IBETIN anytime below.",
            _single_button("⚡ OPEN IBETIN", "home"),
        )

    return (
        "fallback",
        "🤖 <b>IBETIN Assistant</b>\n\nYou can ask me about live sports, cricket, football, news, match alerts, payments or support.",
        standard_keyboard(),
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
        await message.reply_text("✅ IBETIN smart auto reply is ON.")
    elif arg in {"off", "disable", "0"}:
        set_enabled(False)
        await message.reply_text("⏸ IBETIN smart auto reply is OFF.")
    else:
        await message.reply_text(
            f"🤖 IBETIN smart auto reply is currently <b>{'ON' if is_enabled() else 'OFF'}</b>.\n\n"
            "Use <code>/autoreply on</code> or <code>/autoreply off</code>.",
            parse_mode="HTML",
        )
