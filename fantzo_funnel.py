import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

import bot_tracked as tracked

logger = logging.getLogger(__name__)
_installed = False


def _fantzo_button(label: str, source: str, destination: str = "home") -> InlineKeyboardButton:
    return InlineKeyboardButton(
        label,
        web_app=WebAppInfo(url=tracked.analytics.tracking_url(source, destination)),
    )


def _destination_for_action(action: str) -> str:
    if action in {"live_now", "cricket", "football", "trending"}:
        return "live"
    return "home"


def funnel_main_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [_fantzo_button("✨ OPEN FANTZO", "home_open_fantzo", "home")],
    ]

    if tracked.LIVE_TV_MODE == "public" and tracked.sky_admin_url():
        rows.append([
            tracked.public_live_tv_button("📺 WATCH LIVE TV")
        ])

    rows.extend([
        [InlineKeyboardButton("🔴 LIVE SCORES", callback_data="live_now")],
        [
            InlineKeyboardButton("🏏 CRICKET", callback_data="cricket"),
            InlineKeyboardButton("⚽ FOOTBALL", callback_data="football"),
        ],
        [
            InlineKeyboardButton("📅 FIXTURES", callback_data="upcoming"),
            InlineKeyboardButton("🔎 FIND TEAM", callback_data="find_team"),
        ],
        [
            InlineKeyboardButton("🔔 ALERTS", callback_data="subscribe"),
            InlineKeyboardButton("⚙️ SETTINGS", callback_data="settings"),
        ],
    ])
    return InlineKeyboardMarkup(rows)


def funnel_back_keyboard(extra=None) -> InlineKeyboardMarkup:
    rows = list(extra or [])
    rows.append([
        _fantzo_button("✨ CONTINUE ON FANTZO", "screen_continue_fantzo", "home")
    ])
    rows.append([
        InlineKeyboardButton("⬅️ BACK TO HOME", callback_data="back")
    ])
    return InlineKeyboardMarkup(rows)


def funnel_score_keyboard(action: str) -> InlineKeyboardMarkup:
    destination = _destination_for_action(action)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 REFRESH", callback_data=action)],
        [_fantzo_button(
            "✨ CONTINUE ON FANTZO",
            f"{action}_continue_fantzo",
            destination,
        )],
        [
            InlineKeyboardButton("🔎 FIND TEAM", callback_data="find_team"),
            InlineKeyboardButton("⬅️ HOME", callback_data="back"),
        ],
    ])


def funnel_empty_keyboard(action: str) -> InlineKeyboardMarkup:
    destination = _destination_for_action(action)
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 CHECK AGAIN", callback_data=action),
            InlineKeyboardButton("📅 FIXTURES", callback_data="upcoming"),
        ],
        [_fantzo_button(
            "✨ CONTINUE ON FANTZO",
            f"{action}_empty_continue_fantzo",
            destination,
        )],
        [InlineKeyboardButton("⬅️ BACK TO HOME", callback_data="back")],
    ])


def install() -> None:
    global _installed
    if _installed:
        return
    _installed = True

    core = tracked.app.core

    core.TEXT["en"]["welcome"] = (
        "🏟 <b>FANTZO SPORTS</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "<b>Live sports updates, scores & more.</b>\n\n"
        "Open Fantzo, watch Live TV, or check live scores below."
    )
    core.TEXT["hi"]["welcome"] = (
        "🏟 <b>FANTZO SPORTS</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "<b>लाइव स्पोर्ट्स अपडेट, स्कोर और बहुत कुछ।</b>\n\n"
        "Fantzo खोलें, Live TV देखें या नीचे लाइव स्कोर चेक करें।"
    )

    # Keep the sports bot useful, but make Fantzo.com the dominant destination.
    core.main_keyboard = funnel_main_keyboard
    core.back_keyboard = funnel_back_keyboard
    core.score_keyboard = funnel_score_keyboard
    core.empty_keyboard = funnel_empty_keyboard

    # bot_tracked also holds the active premium main-keyboard reference.
    tracked.premium_main_keyboard = funnel_main_keyboard

    logger.info("Fantzo funnel UI installed: Open Fantzo > Live TV > Live Scores")
