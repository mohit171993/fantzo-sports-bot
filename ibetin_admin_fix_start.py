import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

import ibetin_ui_start as base

logger = logging.getLogger(__name__)


def _is_owner_or_admin(user_id: int) -> bool:
    if not user_id:
        return False
    if int(user_id) == int(base.core.ADMIN_USER_ID):
        return True
    try:
        with base.core.db() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM business_connections
                WHERE owner_user_id = ? AND enabled = 1
                LIMIT 1
                """,
                (int(user_id),),
            ).fetchone()
        return bool(row)
    except Exception:
        logger.exception("Could not verify IBETIN Business owner for admin trial")
        return False


def _trial_markup():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(
            "🏏 OPEN MIRROR TRIAL",
            web_app=WebAppInfo(url=base._mazza_admin_url()),
        )]]
    )


# Telegram Android's WebView rejects Android intent:// URLs with
# net::ERR_UNKNOWN_URL_SCHEME. Keep the mirror test inside Telegram, but make
# the Cricket Mazza launcher an HTTPS Play Store link so Android can hand it
# off safely. If the app is installed, the Play Store page offers OPEN.
_original_mirror_page = base._mazza_mirror_page


def _telegram_safe_mirror_page() -> str:
    html = _original_mirror_page()
    intent_html = base.escape(base._mazza_launch_intent(), quote=True)
    play_html = base.escape(base.MAZZA_PLAY_URL, quote=True)
    html = html.replace(
        f'<a class="btn primary" href="{intent_html}">🏏 OPEN CRICKET MAZZA APP</a>',
        f'<a class="btn primary" href="{play_html}" target="_blank" rel="noopener noreferrer">🏏 OPEN CRICKET MAZZA</a>',
    )
    html = html.replace(
        "Suggested test: tap TRY DEVICE SCREEN MIRROR → allow full-screen sharing if Telegram/Android offers it → open Cricket Mazza → return here and check whether the preview kept capturing.",
        "Suggested test: tap TRY DEVICE SCREEN MIRROR → allow full-screen sharing if Telegram/Android offers it → open Cricket Mazza from the HTTPS launcher or Android recent apps → return here and check whether the preview kept capturing.",
    )
    return html


base._mazza_mirror_page = _telegram_safe_mirror_page


async def _mazza_mirror_command(update, context) -> None:
    user = update.effective_user
    message = update.effective_message
    chat = update.effective_chat
    if not user or not message or not chat:
        return

    # Temporary isolated test route: allow the hidden /mazzamirror command in
    # a direct private chat with the bot. It is not listed in the public menu,
    # and /admin remains fully restricted to the configured admin/Business owner.
    if getattr(chat, "type", "") != "private":
        await message.reply_text("This trial is available only in a private chat with the bot.")
        return

    logger.info("IBETIN Mazza mirror trial accepted user_id=%s", user.id)
    await message.reply_text(
        "🏏 <b>CRICKET MAZZA MIRROR · ADMIN TRIAL</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Private test only. Nothing from this screen is visible in the public IBETIN menu.",
        parse_mode="HTML",
        reply_markup=_trial_markup(),
        disable_web_page_preview=True,
    )


async def _admin_with_mazza_trial(update, context) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return

    if not _is_owner_or_admin(user.id):
        await message.reply_text("This command is restricted.")
        return

    # Preserve the legacy/full admin panel only for the configured numeric admin.
    # Telegram Business owners are additionally allowed into the isolated mirror trial.
    if int(user.id) == int(base.core.ADMIN_USER_ID):
        try:
            await base._original_admin(update, context)
        except Exception:
            logger.exception("Legacy IBETIN admin panel failed")

    logger.info("IBETIN admin mirror trial accepted for authorized owner/admin")
    await message.reply_text(
        "🏏 <b>CRICKET MAZZA MIRROR · TRIAL</b>",
        parse_mode="HTML",
        reply_markup=_trial_markup(),
        disable_web_page_preview=True,
    )


# The post-init wrapper in ibetin_ui_start resolves this global at runtime,
# so replacing it here fixes /mazzamirror without changing the public bot UI.
base._mazza_mirror_command = _mazza_mirror_command

# bot_persistent.run() registers /admin from core.admin after this module loads.
base._runtime.app.core.admin = _admin_with_mazza_trial

logger.info("IBETIN Mazza mirror trial enabled for direct private chat; /admin stays restricted")
logger.info("IBETIN Mazza launcher patched for Telegram Android HTTPS handoff")

if __name__ == "__main__":
    base.ibetin_start.main()
