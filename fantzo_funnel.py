import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

import bot_tracked as tracked

logger = logging.getLogger(__name__)
_installed = False


def _styled_button(*args, style: str | None = None, **kwargs) -> InlineKeyboardButton:
    """Use Bot API button styles while staying compatible with PTB 21.6."""
    if style:
        kwargs["api_kwargs"] = {"style": style}
    return InlineKeyboardButton(*args, **kwargs)


def _fantzo_button(label: str, source: str, destination: str = "home") -> InlineKeyboardButton:
    return _styled_button(
        label,
        style="success",
        web_app=WebAppInfo(url=tracked.analytics.tracking_url(source, destination)),
    )


def _destination_for_action(action: str) -> str:
    if action in {"live_now", "cricket", "football", "trending"}:
        return "live"
    return "home"


def funnel_main_keyboard() -> InlineKeyboardMarkup:
    """Compact Fantzo home inspired by iBetin's clean first screen."""
    rows = [
        [_fantzo_button("⚡ OPEN FANTZO", "home_open_fantzo", "home")],
    ]

    if tracked.LIVE_TV_MODE == "public" and tracked.sky_admin_url():
        rows.append([
            _styled_button(
                "📺 WATCH LIVE TV",
                style="danger",
                callback_data="live_tv_status",
            )
        ])

    rows.extend([
        [
            _styled_button("🔴 LIVE SCORES", style="danger", callback_data="live_now"),
            _styled_button("📅 FIXTURES", style="primary", callback_data="upcoming"),
        ],
        [
            _styled_button("🏏 CRICKET", style="primary", callback_data="cricket"),
            _styled_button("⚽ FOOTBALL", style="primary", callback_data="football"),
        ],
        [
            InlineKeyboardButton("🏆 RESULTS", callback_data="results"),
            InlineKeyboardButton("🔔 MATCH ALERTS", callback_data="subscribe"),
        ],
        [
            InlineKeyboardButton("🔎 FIND TEAM", callback_data="find_team"),
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
        [_styled_button("🔄 REFRESH", style="primary", callback_data=action)],
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
            _styled_button("🔄 CHECK AGAIN", style="primary", callback_data=action),
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
        "Quick access without a crowded menu.\n\n"
        "⚡ Open Fantzo\n"
        "📺 Live TV\n"
        "🔴 Live scores\n"
        "🏏 Cricket   •   ⚽ Football\n"
        "📅 Fixtures   •   🏆 Results\n"
        "🔔 Match alerts\n\n"
        "Choose what you want to open 👇"
    )
    core.TEXT["hi"]["welcome"] = (
        "🏟 <b>FANTZO SPORTS</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "कम विकल्प, तेज़ access.\n\n"
        "⚡ Fantzo खोलें\n"
        "📺 Live TV\n"
        "🔴 लाइव स्कोर\n"
        "🏏 क्रिकेट   •   ⚽ फुटबॉल\n"
        "📅 फिक्स्चर   •   🏆 रिज़ल्ट\n"
        "🔔 मैच अलर्ट\n\n"
        "अपना विकल्प चुनें 👇"
    )

    # Keep the sports bot useful, but make Fantzo.com the dominant destination.
    core.main_keyboard = funnel_main_keyboard
    core.back_keyboard = funnel_back_keyboard
    core.score_keyboard = funnel_score_keyboard
    core.empty_keyboard = funnel_empty_keyboard

    # bot_tracked also holds the active premium main-keyboard reference.
    tracked.premium_main_keyboard = funnel_main_keyboard

    logger.info("Fantzo compact UI installed: Open Fantzo > Live TV > Live Scores > sports shortcuts")
