import logging
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

LIVE_TV_URL = os.getenv("FANTZO_LIVE_TV_URL", "https://skylivepro.com/").strip()
LIVE_TV_ENABLED = os.getenv("FANTZO_LIVE_TV_ENABLED", "1").strip().lower() not in {"0", "false", "off", "no"}


def live_tv_button(label: str = "📺 Live TV") -> InlineKeyboardButton:
    return InlineKeyboardButton(label, url=LIVE_TV_URL)


def live_tv_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [live_tv_button("📺 OPEN LIVE TV")],
            [InlineKeyboardButton("⬅️ Back to Fantzo", callback_data="back")],
        ]
    )


def is_enabled() -> bool:
    return LIVE_TV_ENABLED and bool(LIVE_TV_URL)
