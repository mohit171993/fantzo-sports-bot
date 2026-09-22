"""Fantzo-only native Telegram UI helpers.

Inspired by the proven iBetin interaction pattern, but intentionally isolated:
- no iBetin imports;
- Fantzo-specific labels and tracking;
- START always routes through Fantzo's own verification gate;
- OPEN FANTZO quick access is only sent after verification.
"""

from __future__ import annotations

import logging

from telegram import (
    InlineKeyboardButton,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)
from telegram.ext import ApplicationHandlerStop, MessageHandler, filters

import bot_tracked as tracked

logger = logging.getLogger(__name__)

_installed = False
_handlers_registered = False


def _fantzo_button_style(text: str) -> str:
    value = str(text or "").casefold()

    if any(token in value for token in ("live", "stop", "delete", "remove", "off")):
        return "danger"

    if any(
        token in value
        for token in (
            "open fantzo",
            "join fantzo",
            "verify",
            "converted",
        )
    ):
        return "success"

    return "primary"


def install_native_button_styles() -> None:
    """Apply consistent Telegram-native button colors in Fantzo only."""
    if getattr(InlineKeyboardButton, "_fantzo_styles_installed", False):
        return

    original_inline_to_dict = InlineKeyboardButton.to_dict
    original_keyboard_to_dict = KeyboardButton.to_dict

    def inline_to_dict(self, *args, **kwargs):
        data = original_inline_to_dict(self, *args, **kwargs)
        data.setdefault("style", _fantzo_button_style(getattr(self, "text", "")))
        return data

    def keyboard_to_dict(self, *args, **kwargs):
        data = original_keyboard_to_dict(self, *args, **kwargs)
        data.setdefault("style", _fantzo_button_style(getattr(self, "text", "")))
        return data

    InlineKeyboardButton.to_dict = inline_to_dict
    KeyboardButton.to_dict = keyboard_to_dict
    InlineKeyboardButton._fantzo_styles_installed = True
    KeyboardButton._fantzo_styles_installed = True

    logger.info("Fantzo native Telegram button colors installed")


def start_only_quick_menu() -> ReplyKeyboardMarkup:
    """Safe persistent keyboard for an account that is not yet verified."""
    return ReplyKeyboardMarkup(
        [[KeyboardButton("▶️ START")]],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Tap START",
    )


def verified_quick_menu() -> ReplyKeyboardMarkup:
    """Compact iBetin-style bottom keyboard for verified Fantzo users."""
    return ReplyKeyboardMarkup(
        [[
            KeyboardButton("▶️ START"),
            KeyboardButton(
                "⚡ OPEN FANTZO",
                web_app=WebAppInfo(
                    url=tracked.analytics.tracking_url(
                        "telegram_quick_open_fantzo",
                        "home",
                    )
                ),
            ),
        ]],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Tap START or open FANTZO",
    )


async def start_button_handler(update, context) -> None:
    """Route native START through Fantzo's wrapped /start verification flow."""
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return

    # tracked.app.start is wrapped by fantzo_live_tv_mobile_gate.install().
    await tracked.app.start(update, context)
    raise ApplicationHandlerStop


def install() -> None:
    global _installed
    if _installed:
        return
    _installed = True

    install_native_button_styles()

    # Keep the shared base launcher safe by default. Verified users receive the
    # two-button version after Fantzo verification succeeds.
    tracked.app.QUICK_MENU_LABEL = "▶️ START"
    tracked.app.QUICK_MENU = start_only_quick_menu()

    logger.info("Fantzo native UI installed: compact START keyboard + native colors")


def register_handlers(application) -> None:
    global _handlers_registered
    if _handlers_registered:
        return
    _handlers_registered = True

    # Handle both the new START button and the legacy Fantzo Menu button so an
    # old persistent keyboard can never bypass the verification gate.
    application.add_handler(
        MessageHandler(
            filters.UpdateType.MESSAGE
            & filters.TEXT
            & filters.Regex(r"^(?:▶️ START|⚡ Fantzo Menu)$"),
            start_button_handler,
        ),
        group=-8,
    )

    logger.info("Fantzo native START handler registered")
