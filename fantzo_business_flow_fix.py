import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

import bot_tracked as tracked
import fantzo_business as business

logger = logging.getLogger(__name__)
_installed = False

FANTZO_MINI_APP_DEEP_LINK = "https://t.me/fantzoofficialbot?startapp=business_dm"
LIVE_TV_STATUS_DEEP_LINK = "https://t.me/fantzoofficialbot?start=livetv_business"
BUSINESS_VERIFY_DEEP_LINK = "https://t.me/fantzoofficialbot?start=verify_business_dm"
LIVE_TV_START_ARGS = {"livetv_business", "livetv_banner"}


def _styled_button(*args, style: str | None = None, **kwargs) -> InlineKeyboardButton:
    if style:
        kwargs["api_kwargs"] = {"style": style}
    return InlineKeyboardButton(*args, **kwargs)


def business_verify_buttons() -> InlineKeyboardMarkup:
    """Business messages cannot request a contact directly; hand off to the bot."""
    return InlineKeyboardMarkup([
        [
            _styled_button(
                "📱 VERIFY MOBILE",
                url=BUSINESS_VERIFY_DEEP_LINK,
                style="success",
            )
        ],
    ])


def business_funnel_buttons(source: str = "business", destination: str = "home") -> InlineKeyboardMarkup:
    """Three simple Business CTAs: Mini App, Live TV status, channel."""
    return InlineKeyboardMarkup([
        [
            _styled_button(
                "🎮 PLAY FANTZO",
                url=FANTZO_MINI_APP_DEEP_LINK,
                style="success",
            )
        ],
        [
            _styled_button(
                "📺 WATCH LIVE TV",
                url=LIVE_TV_STATUS_DEEP_LINK,
                style="primary",
            )
        ],
        [
            _styled_button(
                "📢 SUBSCRIBE CHANNEL",
                url=business.FANTZO_CHANNEL_URL,
                style="primary",
            )
        ],
    ])


def styled_live_tv_keyboard() -> InlineKeyboardMarkup:
    rows = []
    url = tracked.sky_admin_url()

    if url:
        rows.append([
            _styled_button(
                "▶ OPEN LIVE TV",
                web_app=WebAppInfo(url=url),
                style="success",
            )
        ])

    rows.extend([
        [
            _styled_button(
                "🔄 CHECK STATUS",
                callback_data="live_tv_status",
                style="primary",
            ),
            _styled_button(
                "🔴 LIVE SCORES",
                callback_data="live_now",
                style="primary",
            ),
        ],
        [InlineKeyboardButton("⬅️ BACK TO HOME", callback_data="back")],
    ])
    return InlineKeyboardMarkup(rows)


def styled_live_tv_wait_keyboard() -> InlineKeyboardMarkup:
    rows = []
    url = tracked.sky_admin_url()

    if url:
        rows.append([
            _styled_button(
                "▶ OPEN LIVE TV",
                web_app=WebAppInfo(url=url),
                style="success",
            )
        ])

    rows.extend([
        [
            _styled_button(
                "🔄 CHECK AGAIN",
                callback_data="live_tv_status",
                style="primary",
            ),
            InlineKeyboardButton("📅 FIXTURES", callback_data="upcoming"),
        ],
        [InlineKeyboardButton("⬅️ BACK TO HOME", callback_data="back")],
    ])
    return InlineKeyboardMarkup(rows)


async def send_live_tv_status_from_start(update, context) -> None:
    message = update.effective_message
    user = update.effective_user
    if not message:
        return

    try:
        tracked.app.core.touch_user(update)
        if user:
            tracked.app.core.track(user.id, "live_tv_status")
    except Exception:
        logger.exception("Could not track Fantzo Live TV deep-link open")

    if tracked.LIVE_TV_MODE != "public":
        await message.reply_text(
            "📺 <b>FANTZO LIVE TV</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Live TV is not currently available for public viewing.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ BACK TO HOME", callback_data="back")
            ]]),
        )
        return

    try:
        all_today, live_now, future_today = await tracked._today_tv_matches()
    except Exception:
        logger.exception("Could not open Fantzo Live TV status from deep link")
        await message.reply_text(
            "📺 <b>FANTZO LIVE TV</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "⚠️ <b>Live match status is temporarily unavailable.</b>\n\n"
            "You can still open Live TV below or check again in a moment.",
            parse_mode="HTML",
            reply_markup=styled_live_tv_wait_keyboard(),
        )
        return

    if live_now:
        lines = [
            "📺 <b>FANTZO LIVE TV</b>",
            "━━━━━━━━━━━━━━━━━━",
            "",
            "🔴 <b>LIVE NOW</b>",
            "",
        ]
        for sport, match in live_now[:3]:
            lines.append(tracked._match_name(match, sport))
        lines.extend(["", "Tap below to open Live TV."])
        await message.reply_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=styled_live_tv_keyboard(),
        )
        return

    if future_today:
        _, sport, match = future_today[0]
        await message.reply_text(
            "📺 <b>FANTZO LIVE TV</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "😴 <b>No live match right now.</b>\n\n"
            "<b>Next match today</b>\n"
            f"{tracked._match_name(match, sport)}\n"
            f"🕒 {tracked._match_time(match)} Dubai time\n\n"
            "Check again when the match starts.",
            parse_mode="HTML",
            reply_markup=styled_live_tv_wait_keyboard(),
        )
        return

    if all_today:
        text = (
            "📺 <b>FANTZO LIVE TV</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "😴 <b>No live match right now.</b>\n\n"
            "Today's scheduled matches have finished or are not currently live."
        )
    else:
        text = (
            "📺 <b>FANTZO LIVE TV</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "🏟 <b>NO MATCHES TODAY</b>\n\n"
            "There are no cricket or football matches scheduled today.\n\n"
            "Check upcoming fixtures or come back later."
        )

    await message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=styled_live_tv_wait_keyboard(),
    )


def install() -> None:
    global _installed
    if _installed:
        return
    _installed = True

    # Business messages cannot use WebAppInfo buttons when sent on behalf of a
    # business account, so PLAY FANTZO uses Telegram's Mini App deep link.
    business._funnel_buttons = business_funnel_buttons
    business._welcome_buttons = business_verify_buttons

    # Keep the existing Live TV status engine and cache, changing only its
    # presentation to native Telegram button colors.
    tracked._tv_live_keyboard = styled_live_tv_keyboard
    tracked._tv_wait_keyboard = styled_live_tv_wait_keyboard

    original_start = tracked.app.start

    async def start_with_live_tv_deeplink(update, context):
        arg = context.args[0].lower() if context.args else ""
        if arg in LIVE_TV_START_ARGS:
            await send_live_tv_status_from_start(update, context)
            return
        await original_start(update, context)

    tracked.app.start = start_with_live_tv_deeplink
    logger.info(
        "Fantzo Business flow fix installed: verification handoff + Mini App + Live TV status deep link + colored buttons"
    )
