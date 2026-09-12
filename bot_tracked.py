import logging

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    WebAppInfo,
)

import bot_persistent as app
import fantzo_analytics as analytics
import private_apk_upload

logger = logging.getLogger(__name__)


def tracked_url(content: str) -> str:
    return analytics.tracking_url(content)


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
            text="Join Fantzo",
            web_app=WebAppInfo(url=tracked_url("telegram_native_menu")),
        )
    )
    logger.info("Fantzo tracked Mini App menu configured")


app.configure_telegram_ui = configure_telegram_ui


if __name__ == "__main__":
    analytics.start_tracking_server()
    private_apk_upload.start_upload_server()
    logger.info("Starting Fantzo with tracked Mini App conversion links, admin analytics, and private APK upload")
    app.run()
