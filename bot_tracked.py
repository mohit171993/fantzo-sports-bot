import logging
from urllib.parse import urlencode

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    WebAppInfo,
)

import bot_persistent as app

logger = logging.getLogger(__name__)

BASE_URL = "https://www.fantzo.com/"


def tracked_url(content: str, campaign: str = "fantzo_sports_hub") -> str:
    query = urlencode(
        {
            "utm_source": "telegram",
            "utm_medium": "bot",
            "utm_campaign": campaign,
            "utm_content": content,
        }
    )
    return f"{BASE_URL}?{query}"


def mini_app_button(label: str, content: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        label,
        web_app=WebAppInfo(url=tracked_url(content)),
    )


def premium_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [mini_app_button("🔥 JOIN FANTZO NOW 🔥", "home_join_cta")],
            [
                InlineKeyboardButton("🔴 Live Now", callback_data="live_now"),
                InlineKeyboardButton("🔥 Featured", callback_data="trending"),
            ],
            [
                InlineKeyboardButton("🏏 Cricket", callback_data="cricket"),
                InlineKeyboardButton("⚽ Football", callback_data="football"),
            ],
            [
                InlineKeyboardButton("🗓 Upcoming", callback_data="upcoming"),
                InlineKeyboardButton("✅ Results", callback_data="results"),
            ],
            [
                InlineKeyboardButton("🔎 Find Team", callback_data="find_team"),
                InlineKeyboardButton("🔔 Match Alerts", callback_data="subscribe"),
            ],
            [
                InlineKeyboardButton("✨ Explore Fantzo", callback_data="explore"),
                InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
            ],
        ]
    )


def premium_join_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [mini_app_button("🔥 JOIN FANTZO NOW 🔥", "join_screen_cta")],
            [mini_app_button("✨ OPEN FANTZO", "join_screen_explore")],
            [InlineKeyboardButton("⬅️ Back to Home", callback_data="back")],
        ]
    )


def premium_explore_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [mini_app_button("✨ OPEN FANTZO", "explore_home")],
            [mini_app_button("🚀 JOIN FANTZO NOW", "explore_join")],
            [InlineKeyboardButton("⬅️ Back to Home", callback_data="back")],
        ]
    )


# Override conversion-facing keyboards while retaining the existing sports logic,
# banner management, subscriptions, admin tools, and Highlightly integration.
app.core.main_keyboard = premium_main_keyboard
app.core.join_keyboard = premium_join_keyboard
app.core.explore_keyboard = premium_explore_keyboard


async def configure_telegram_ui(application) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Open Fantzo Sports Hub"),
            BotCommand("team", "Find a cricket or football team"),
            BotCommand("sports", "View Fantzo sports coverage"),
            BotCommand("help", "Fantzo quick guide"),
            BotCommand("setbanner", "Change the Fantzo home banner"),
        ]
    )
    await application.bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text="Open Fantzo",
            web_app=WebAppInfo(url=tracked_url("telegram_native_menu")),
        )
    )
    logger.info("Fantzo tracked Mini App menu configured")


# bot_persistent.run() resolves this global at runtime, so overriding it here
# preserves the existing application wiring while changing the Telegram launcher.
app.configure_telegram_ui = configure_telegram_ui


if __name__ == "__main__":
    logger.info("Starting Fantzo with tracked Mini App conversion links")
    app.run()
