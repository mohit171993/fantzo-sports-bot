import logging
import os
from urllib.parse import urlencode

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    WebAppInfo,
)
from telegram.ext import CommandHandler

import bot_persistent as app
import fantzo_analytics as analytics
import fantzo_live_tv
import fantzo_reminders as reminders
import private_apk_upload
import trial_live_tv

logger = logging.getLogger(__name__)


# =========================================================
# LIVE TV SETTINGS
# =========================================================

SKY_ADMIN_BASE_URL = os.getenv(
    "SKY_ADMIN_BASE_URL",
    ""
).strip().rstrip("/")

SKY_ADMIN_TEST_TOKEN = os.getenv(
    "SKY_ADMIN_TEST_TOKEN",
    ""
).strip()

LIVE_TV_MODE = os.getenv(
    "LIVE_TV_MODE",
    "admin"
).strip().lower()

if LIVE_TV_MODE not in {"off", "admin", "public"}:
    LIVE_TV_MODE = "admin"


# =========================================================
# NORMAL FANTZO HELPERS
# =========================================================

def tracked_url(content: str) -> str:
    return analytics.tracking_url(content)


def mini_app_button(
    label: str,
    content: str
) -> InlineKeyboardButton:

    return InlineKeyboardButton(
        label,
        web_app=WebAppInfo(
            url=tracked_url(content)
        ),
    )


# =========================================================
# PREMIUM SPORTS UI COPY
# =========================================================

def install_premium_ui_copy() -> None:
    """Keep the first screen short, sports-first, and easy to scan."""

    app.core.TEXT["en"]["welcome"] = (
        "🏟 <b>FANTZO SPORTS</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "<b>Your sports. Live.</b>\n\n"
        "🔴 Live scores & match action\n"
        "🏏 Cricket   •   ⚽ Football\n"
        "📅 Fixtures   •   🏆 Results\n"
        "🔔 Match alerts & fast updates\n\n"
        "Choose what you want to follow 👇"
    )

    app.core.TEXT["hi"]["welcome"] = (
        "🏟 <b>FANTZO SPORTS</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "<b>आपके खेल। लाइव।</b>\n\n"
        "🔴 लाइव स्कोर और मैच अपडेट\n"
        "🏏 क्रिकेट   •   ⚽ फुटबॉल\n"
        "📅 फिक्स्चर   •   🏆 रिज़ल्ट\n"
        "🔔 मैच अलर्ट और तेज़ अपडेट\n\n"
        "अपना स्पोर्ट चुनें 👇"
    )

    app.core.TEXT["en"]["explore"] = (
        "✨ <b>EXPLORE FANTZO</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Discover featured sports, find a team, or open the full Fantzo experience."
    )

    app.core.TEXT["hi"]["explore"] = (
        "✨ <b>EXPLORE FANTZO</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Featured sports देखें, अपनी team खोजें या पूरा Fantzo experience खोलें।"
    )


install_premium_ui_copy()


# =========================================================
# PRIVATE SKY ADMIN ROUTE
# =========================================================

def sky_admin_url() -> str:

    if not SKY_ADMIN_BASE_URL:
        return ""

    if not SKY_ADMIN_TEST_TOKEN:
        return ""

    query = urlencode({
        "key": SKY_ADMIN_TEST_TOKEN
    })

    return (
        f"{SKY_ADMIN_BASE_URL}"
        f"/open?"
        f"{query}"
    )


# =========================================================
# MAIN HOME KEYBOARD
# =========================================================

def premium_main_keyboard() -> InlineKeyboardMarkup:
    """Sports-first home with fewer, stronger primary actions."""

    rows = [
        [
            InlineKeyboardButton(
                "🔴 LIVE NOW",
                callback_data="live_now"
            )
        ],
        [
            InlineKeyboardButton(
                "🏏 CRICKET",
                callback_data="cricket"
            ),
            InlineKeyboardButton(
                "⚽ FOOTBALL",
                callback_data="football"
            ),
        ],
        [
            InlineKeyboardButton(
                "📅 FIXTURES",
                callback_data="upcoming"
            ),
            InlineKeyboardButton(
                "🏆 RESULTS",
                callback_data="results"
            ),
        ],
    ]

    # Keep the existing Live TV route and visibility logic unchanged.
    if LIVE_TV_MODE == "public":
        url = sky_admin_url()

        if url:
            rows.append([
                InlineKeyboardButton(
                    "📺 WATCH LIVE TV",
                    web_app=WebAppInfo(
                        url=url
                    )
                )
            ])

    rows.extend([
        [
            InlineKeyboardButton(
                "🔔 MATCH ALERTS",
                callback_data="subscribe"
            ),
            InlineKeyboardButton(
                "⚙️ SETTINGS",
                callback_data="settings"
            ),
        ],
        [
            InlineKeyboardButton(
                "✨ EXPLORE",
                callback_data="explore"
            ),
            InlineKeyboardButton(
                "🔎 FIND TEAM",
                callback_data="find_team"
            ),
        ],
        [
            mini_app_button(
                "✨ OPEN FANTZO",
                "home_open_fantzo"
            )
        ],
    ])

    return InlineKeyboardMarkup(rows)


# =========================================================
# JOIN KEYBOARD
# =========================================================

def premium_join_keyboard() -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup([
        [
            mini_app_button(
                "✨ OPEN FANTZO",
                "join_screen_open"
            )
        ],
        [
            InlineKeyboardButton(
                "🔴 LIVE NOW",
                callback_data="live_now"
            ),
            InlineKeyboardButton(
                "📅 FIXTURES",
                callback_data="upcoming"
            ),
        ],
        [
            InlineKeyboardButton(
                "⬅️ BACK TO HOME",
                callback_data="back"
            )
        ],
    ])


# =========================================================
# EXPLORE KEYBOARD
# =========================================================

def premium_explore_keyboard() -> InlineKeyboardMarkup:

    rows = [
        [
            InlineKeyboardButton(
                "🔥 FEATURED",
                callback_data="trending"
            ),
            InlineKeyboardButton(
                "🔎 FIND TEAM",
                callback_data="find_team"
            ),
        ],
        [
            mini_app_button(
                "✨ OPEN FANTZO",
                "explore_open_fantzo"
            )
        ],
    ]

    if LIVE_TV_MODE == "public":
        url = sky_admin_url()

        if url:
            rows.append([
                InlineKeyboardButton(
                    "📺 WATCH LIVE TV",
                    web_app=WebAppInfo(
                        url=url
                    )
                )
            ])

    rows.append([
        InlineKeyboardButton(
            "⬅️ BACK TO HOME",
            callback_data="back"
        )
    ])

    return InlineKeyboardMarkup(rows)


# =========================================================
# INSTALL KEYBOARDS
# =========================================================

app.core.main_keyboard = premium_main_keyboard
app.core.join_keyboard = premium_join_keyboard
app.core.explore_keyboard = premium_explore_keyboard


# =========================================================
# TRACKING / REMINDER HOOKS
# =========================================================

_original_track = app.core.track
_original_touch_user = app.core.touch_user
_original_start = app.start
_original_admin = app.core.admin


def _business_connection_id() -> str:

    try:
        with app.core.db() as conn:

            row = conn.execute(
                """
                SELECT connection_id
                FROM business_connections
                WHERE enabled = 1
                ORDER BY updated_at DESC
                LIMIT 1
                """
            ).fetchone()

        if row and row["connection_id"]:
            return str(row["connection_id"])

    except Exception:
        pass

    return ""


def _category_from_action(
    action: str
) -> str:

    if ":" in action:
        return action.split(":", 1)[1]

    if action in {
        "cricket",
        "football",
        "sports",
        "live_now",
        "trending",
    }:
        return action

    return "general"


def tracked_core_event(
    user_id: int,
    action: str
):

    result = _original_track(
        user_id,
        action
    )

    try:

        if action.startswith(
            "business_dm:"
        ):

            reminders.touch_user(
                "business_dm",
                user_id,
                _category_from_action(action),
                _business_connection_id(),
            )

        else:

            reminders.touch_user(
                "bot",
                user_id,
                _category_from_action(action)
            )

    except Exception:

        logger.exception(
            "Could not update reminder activity"
        )

    return result


def tracked_touch_user(update):

    result = _original_touch_user(
        update
    )

    try:

        user = update.effective_user

        if user:

            reminders.touch_user(
                "bot",
                user.id,
                "general"
            )

    except Exception:

        logger.exception(
            "Could not update reminder user"
        )

    return result


app.core.track = tracked_core_event
app.core.touch_user = tracked_touch_user


# =========================================================
# /START
# =========================================================

async def smart_start(
    update,
    context
) -> None:

    user = update.effective_user

    arg = (
        context.args[0].lower()
        if context.args
        else ""
    )

    if (
        user
        and arg == "stopreminders"
    ):

        reminders.set_opt_out(
            "bot",
            user.id,
            True
        )

        reminders.set_opt_out(
            "business_dm",
            user.id,
            True
        )

        await update.effective_message.reply_text(
            "🔕 <b>Fantzo reminders are OFF.</b>",
            parse_mode="HTML"
        )

        return

    # Premium start: show one clean sports dashboard instead of
    # following it with the old extra Quick Access explanation.
    await app.show_home(
        update,
        context
    )


app.start = smart_start


# =========================================================
# ADMIN PANEL
# =========================================================

async def smart_admin(
    update,
    context
) -> None:

    user = update.effective_user
    message = update.effective_message

    if not user:
        return

    if not message:
        return

    if user.id != app.core.ADMIN_USER_ID:
        return


    await _original_admin(
        update,
        context
    )


    if LIVE_TV_MODE not in {
        "admin",
        "public"
    }:
        return


    url = sky_admin_url()


    if not url:

        await message.reply_text(
            "⚠️ <b>Private Sky admin URL is not configured.</b>",
            parse_mode="HTML"
        )

        return


    await message.reply_text(

        "📺 <b>LIVE TV CONTROL</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"Current mode: <b>{LIVE_TV_MODE.upper()}</b>",

        parse_mode="HTML",

        reply_markup=InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "📺 OPEN LIVE TV",
                    web_app=WebAppInfo(
                        url=sky_admin_url()
                    )
                )
            ]

        ]),

        disable_web_page_preview=True,
    )


app.core.admin = smart_admin


# =========================================================
# /LIVETVADMIN
# =========================================================

async def live_tv_admin_command(
    update,
    context
) -> None:

    user = update.effective_user
    message = update.effective_message

    if not user:
        return

    if not message:
        return

    if user.id != app.core.ADMIN_USER_ID:
        return


    if LIVE_TV_MODE == "off":

        await message.reply_text(
            "⛔ <b>Live TV mode is OFF.</b>",
            parse_mode="HTML"
        )

        return


    url = sky_admin_url()


    if not url:

        await message.reply_text(
            "⚠️ <b>Sky admin Live TV is not configured.</b>",
            parse_mode="HTML"
        )

        return


    await message.reply_text(

        "📺 <b>FANTZO LIVE TV · ADMIN</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"Current mode: <b>{LIVE_TV_MODE.upper()}</b>",

        parse_mode="HTML",

        reply_markup=InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "▶ OPEN SKY LIVE · ADMIN",
                    web_app=WebAppInfo(
                        url=url
                    )
                )
            ]

        ]),

        disable_web_page_preview=True,
    )


# =========================================================
# TELEGRAM UI
# =========================================================

async def configure_telegram_ui(
    application
) -> None:

    await application.bot.set_my_commands([

        BotCommand(
            "start",
            "Open Fantzo Sports"
        ),

        BotCommand(
            "team",
            "Find a cricket or football team"
        ),

        BotCommand(
            "sports",
            "View Fantzo sports coverage"
        ),

        BotCommand(
            "help",
            "Fantzo quick guide"
        ),

    ])


    await application.bot.set_chat_menu_button(

        menu_button=MenuButtonWebApp(

            text="Open Fantzo",

            web_app=WebAppInfo(
                url=tracked_url(
                    "telegram_native_menu"
                )
            )

        )

    )


    application.add_handler(
        CommandHandler(
            "livetvadmin",
            live_tv_admin_command
        )
    )


    reminders.ensure_tables()

    reminders.start_background_loop(
        application
    )


app.configure_telegram_ui = configure_telegram_ui


# =========================================================
# START FANTZO
# =========================================================

if __name__ == "__main__":

    private_apk_upload.install_on_tracking_handler(
        analytics
    )

    trial_live_tv.install_on_tracking_handler(
        analytics
    )

    fantzo_live_tv.install_on_tracking_handler(
        analytics
    )

    analytics.start_tracking_server()

    logger.info(
        "Starting Fantzo with LIVE_TV_MODE=%s",
        LIVE_TV_MODE
    )

    app.run()
