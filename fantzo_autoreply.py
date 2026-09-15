import logging
import os
from urllib.parse import quote

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import bot as core

logger = logging.getLogger(__name__)
SETTING_KEY = "auto_reply_enabled"

IBETIN_HOME_URL = os.getenv("IBETIN_HOME_URL", "https://ibetin.com").strip().rstrip("/")
IBETIN_SUPPORT_URL = os.getenv(
    "IBETIN_SUPPORT_URL", f"{IBETIN_HOME_URL}/information/contacts"
).strip()


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


def standard_reply() -> str:
    return (
        "👋 <b>Welcome to IBETIN</b>\n\n"
        "Your sports companion for live cricket, football, scores, sports news, match alerts and support.\n\n"
        "⚡ Follow live matches\n"
        "🏏 Cricket & football updates\n"
        "📰 Latest sports news\n"
        "🔔 Match alerts\n"
        "🛟 Customer support\n\n"
        "Choose an option below to continue."
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
    """Compatibility helper: every customer message receives the same IBETIN menu."""
    return "universal", standard_reply(), standard_keyboard()


async def auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return
    if not is_enabled():
        return

    text = (message.text or message.caption or "").strip()
    if text.startswith("/"):
        return

    core.touch_user(update)
    try:
        core.track(user.id, "dm:message")
    except Exception:
        logger.exception("Could not track IBETIN incoming DM")

    await message.reply_text(
        standard_reply(),
        parse_mode="HTML",
        reply_markup=standard_keyboard(),
        disable_web_page_preview=True,
    )

    try:
        core.track(user.id, "dm:autoreply_sent")
    except Exception:
        logger.exception("Could not track IBETIN auto reply send")


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
        await message.reply_text("✅ IBETIN universal auto reply is ON.")
    elif arg in {"off", "disable", "0"}:
        set_enabled(False)
        await message.reply_text("⏸ IBETIN universal auto reply is OFF.")
    else:
        await message.reply_text(
            f"🤖 IBETIN universal auto reply is currently <b>{'ON' if is_enabled() else 'OFF'}</b>.\n\n"
            "Every customer DM receives the same IBETIN menu.\n\n"
            "Use <code>/autoreply on</code> or <code>/autoreply off</code>.",
            parse_mode="HTML",
        )
