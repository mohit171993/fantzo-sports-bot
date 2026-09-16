import logging
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

import ibetin_ui_start as base
import ibetin_liveline_trial as liveline

logger = logging.getLogger(__name__)

TRIAL_VERSION = "20260916-0901"


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


def _versioned_trial_url() -> str:
    url = base._mazza_admin_url()
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}v={TRIAL_VERSION}"


def _trial_markup():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(
            "🏏 OPEN MIRROR TRIAL",
            web_app=WebAppInfo(url=_versioned_trial_url()),
        )]]
    )


# Telegram Android WebView rejects intent:// links. Patch the rendered page
# defensively so no Android intent URL can survive, even if the base page changes.
_original_mirror_page = base._mazza_mirror_page


def _telegram_safe_mirror_page() -> str:
    html = _original_mirror_page()
    play_html = base.escape(base.MAZZA_PLAY_URL, quote=True)

    html = re.sub(
        r'<a class="btn primary" href="intent://[^"]*">🏏 OPEN CRICKET MAZZA APP</a>',
        f'<a class="btn primary" href="{play_html}" target="_blank" rel="noopener noreferrer">🏏 OPEN CRICKET MAZZA</a>',
        html,
        flags=re.IGNORECASE,
    )
    html = html.replace("intent://", "https://play.google.com/store/apps/details?id=com.crics.cricket11#blocked-intent-")
    html = html.replace(
        '<div class="badge">ADMIN ONLY</div>',
        f'<div class="badge">ADMIN ONLY · SAFE {TRIAL_VERSION}</div>',
    )
    html = html.replace(
        "Suggested test: tap TRY DEVICE SCREEN MIRROR → allow full-screen sharing if Telegram/Android offers it → open Cricket Mazza → return here and check whether the preview kept capturing.",
        "Direct screen capture is not supported by Telegram Android WebView on this device. The HTTPS button below is only for opening the Cricket Mazza Play Store page; the actual mirror will require a remote Android relay/source.",
    )
    return html


base._mazza_mirror_page = _telegram_safe_mirror_page


async def _mazza_mirror_command(update, context) -> None:
    user = update.effective_user
    message = update.effective_message
    chat = update.effective_chat
    if not user or not message or not chat:
        return
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


base._mazza_mirror_command = _mazza_mirror_command
base._runtime.app.core.admin = _admin_with_mazza_trial

# Install the new Live Line V1 as a hidden private preview. This adds only
# /liveline and its signed admin web routes; it does not touch the public menu.
liveline.install()

logger.info("IBETIN Mazza mirror trial enabled for direct private chat; /admin stays restricted")
logger.info("IBETIN Mazza launcher hard-patched to HTTPS; trial version=%s", TRIAL_VERSION)
logger.info("IBETIN Live Line V1 preview bootstrap installed")

if __name__ == "__main__":
    base.ibetin_start.main()
