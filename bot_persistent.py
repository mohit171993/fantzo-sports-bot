import logging

from telegram import (
    BotCommand,
    MenuButtonCommands,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import bot as core

logger = logging.getLogger(__name__)

QUICK_MENU_LABEL = "⚡ Fantzo Menu"
QUICK_MENU = ReplyKeyboardMarkup(
    [[QUICK_MENU_LABEL]],
    resize_keyboard=True,
    is_persistent=True,
    input_field_placeholder="Tap Fantzo Menu anytime",
)


async def configure_telegram_ui(application: Application) -> None:
    """Configure Telegram's native menu so /start never needs manual typing."""
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Open Fantzo Sports Hub"),
            BotCommand("team", "Find a cricket or football team"),
            BotCommand("sports", "View Fantzo sports coverage"),
            BotCommand("help", "Fantzo quick guide"),
        ]
    )
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    logger.info("Fantzo Telegram menu button and commands configured")


async def show_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    core.touch_user(update)
    lang = core.get_user_lang(update.effective_user.id)
    await update.effective_message.reply_text(
        core.TEXT[lang]["welcome"],
        parse_mode="HTML",
        reply_markup=core.main_keyboard(),
        disable_web_page_preview=True,
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_home(update, context)
    await update.effective_message.reply_text(
        "⚡ <b>Quick access enabled</b>\n\n"
        "From now on, tap <b>⚡ Fantzo Menu</b> below anytime — no need to type /start again.\n"
        "You can also use Telegram's <b>Menu</b> button.",
        parse_mode="HTML",
        reply_markup=QUICK_MENU,
    )


async def quick_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    core.track(update.effective_user.id, "quick_menu")
    await show_home(update, context)


def run() -> None:
    if not core.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is required")

    core.init_db()
    app = (
        Application.builder()
        .token(core.BOT_TOKEN)
        .post_init(configure_telegram_ui)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", core.help_command))
    app.add_handler(CommandHandler("sports", core.sports_command))
    app.add_handler(CommandHandler("team", core.team_command))
    app.add_handler(CommandHandler("admin", core.admin))
    app.add_handler(CommandHandler("broadcast", core.broadcast))
    app.add_handler(
        MessageHandler(filters.TEXT & filters.Regex(r"^⚡ Fantzo Menu$"), quick_menu)
    )
    app.add_handler(CallbackQueryHandler(core.callback_router))

    logger.info("Starting Fantzo Premium Sports Hub with persistent menu")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    run()
