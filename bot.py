import os
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "8992664481"))

FANTZO_HOME = "https://fantzo.com"
FANTZO_LIVE = "https://fantzo.com/en/live"
FANTZO_SLOTS = "https://fantzo.com/en/slots"
FANTZO_REGISTER = "https://fantzo.com/en/registration"

WELCOME_TEXT = (
    "⚡ <b>Welcome to Fantzo Sports Updates</b>\n\n"
    "Get live scores, match updates, fixtures, results, highlights and breaking sports news — all in one place.\n\n"
    "Choose a section below to get started."
)


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🏏 Cricket", callback_data="cricket"),
                InlineKeyboardButton("⚽ Football", callback_data="football"),
            ],
            [
                InlineKeyboardButton("🔴 Live Now", callback_data="live_now"),
                InlineKeyboardButton("🗓 Upcoming", callback_data="upcoming"),
            ],
            [
                InlineKeyboardButton("✅ Results", callback_data="results"),
                InlineKeyboardButton("📰 Sports News", callback_data="news"),
            ],
            [
                InlineKeyboardButton("🔔 Subscribe", callback_data="subscribe"),
                InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
            ],
            [InlineKeyboardButton("🌐 Fantzo Home", url=FANTZO_HOME)],
            [
                InlineKeyboardButton("🔴 Live", url=FANTZO_LIVE),
                InlineKeyboardButton("📝 Register", url=FANTZO_REGISTER),
            ],
            [InlineKeyboardButton("🎰 Slots", url=FANTZO_SLOTS)],
        ]
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        WELCOME_TEXT,
        parse_mode="HTML",
        reply_markup=main_keyboard(),
        disable_web_page_preview=True,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "Use /start to open Fantzo Sports Updates and choose a section.",
        reply_markup=main_keyboard(),
    )


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_USER_ID:
        await update.effective_message.reply_text("This command is restricted.")
        return
    await update.effective_message.reply_text(
        "✅ Fantzo admin access confirmed.\n\n"
        "Admin tools will be added here next: broadcasts, link controls, user stats and content publishing."
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    responses = {
        "cricket": "🏏 <b>Cricket Updates</b>\nLive scores, fixtures and results will appear here.",
        "football": "⚽ <b>Football Updates</b>\nLive scores, fixtures and results will appear here.",
        "live_now": "🔴 <b>Live Now</b>\nLive sports data integration is the next build step.",
        "upcoming": "🗓 <b>Upcoming Matches</b>\nUpcoming fixtures will appear here.",
        "results": "✅ <b>Latest Results</b>\nCompleted match results will appear here.",
        "news": "📰 <b>Sports News</b>\nBreaking sports updates will appear here.",
        "subscribe": "🔔 <b>Subscriptions</b>\nPersonal match and news alerts will be added in the next step.",
        "settings": "⚙️ <b>Settings</b>\nLanguage and notification preferences will be available here.",
    }

    text = responses.get(query.data, "Fantzo Sports Updates")
    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Back", callback_data="back")]]
        ),
    )


async def back_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        WELCOME_TEXT,
        parse_mode="HTML",
        reply_markup=main_keyboard(),
        disable_web_page_preview=True,
    )


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query and update.callback_query.data == "back":
        await back_handler(update, context)
    else:
        await button_handler(update, context)


def run() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is required")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(callback_router))

    logger.info("Starting Fantzo Sports Updates bot")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    run()
