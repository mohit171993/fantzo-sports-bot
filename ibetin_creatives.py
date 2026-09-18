import logging
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import CommandHandler, MessageHandler, filters
from telegram.error import BadRequest, Forbidden

import bot as core

logger = logging.getLogger(__name__)

PUBLIC_BASE_URL = (
    os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/")
    or "https://ibetin-app-production.up.railway.app"
)
LIVE_LINE_URL = os.getenv("IBETIN_LIVE_LINE_URL", f"{PUBLIC_BASE_URL}/liveline").strip()


def ensure_tables() -> None:
    with core.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS creative_assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT NOT NULL,
                file_unique_id TEXT NOT NULL UNIQUE,
                media_type TEXT NOT NULL,
                width INTEGER,
                height INTEGER,
                filename TEXT DEFAULT '',
                pool TEXT NOT NULL,
                created_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            )
            """
        )


def _is_admin(update) -> bool:
    user = update.effective_user
    return bool(user and user.id == core.ADMIN_USER_ID)


def _pool_from(message, width: int = 0, height: int = 0, filename: str = "") -> str:
    hint = " ".join([(message.caption or ""), filename or ""]).lower()
    if any(x in hint for x in ("#channel", "channel_", "channel-", "[channel]")):
        return "channel"
    if any(x in hint for x in ("#dm", "dm_", "dm-", "[dm]")):
        return "dm"
    if any(x in hint for x in ("#reminder", "reminder_", "reminder-", "[reminder]", "#bot")):
        return "reminder"

    if width and height:
        ratio = width / max(1, height)
        if ratio >= 1.35:
            return "channel"
        if ratio <= 0.88:
            return "dm"
        return "reminder"

    # Unknown document dimensions: channel is the safest default for banner-style assets.
    return "channel"


def _save(file_id: str, file_unique_id: str, media_type: str, pool: str,
          width: int = 0, height: int = 0, filename: str = "") -> bool:
    ensure_tables()
    with core.db() as conn:
        before = conn.total_changes
        conn.execute(
            """
            INSERT INTO creative_assets(
                file_id, file_unique_id, media_type, width, height,
                filename, pool, created_at, active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(file_unique_id) DO UPDATE SET
                file_id = excluded.file_id,
                media_type = excluded.media_type,
                width = excluded.width,
                height = excluded.height,
                filename = excluded.filename,
                pool = excluded.pool,
                active = 1
            """,
            (
                file_id, file_unique_id, media_type,
                width or None, height or None, filename or "",
                pool, core.now_iso(),
            ),
        )
        return conn.total_changes > before


def counts() -> dict:
    ensure_tables()
    with core.db() as conn:
        rows = conn.execute(
            """
            SELECT pool, COUNT(*) AS c
            FROM creative_assets
            WHERE active = 1
            GROUP BY pool
            """
        ).fetchall()
    out = {"channel": 0, "dm": 0, "reminder": 0}
    for row in rows:
        out[str(row["pool"])] = int(row["c"])
    return out


async def bulkcreatives_command(update, context) -> None:
    message = update.effective_message
    if not message:
        return
    if not _is_admin(update):
        await message.reply_text("This command is restricted.")
        return

    ensure_tables()
    context.user_data["creative_bulk_mode"] = True
    context.user_data["creative_bulk_added"] = {"channel": 0, "dm": 0, "reminder": 0}
    await message.reply_text(
        "🖼 <b>IBETIN BULK CREATIVE UPLOAD</b>\n\n"
        "Now send all banners here as photos or image files. You can send an album.\n\n"
        "I will auto-sort them:\n"
        "• Landscape / 16:9 → <b>Channel</b>\n"
        "• Portrait / 4:5 → <b>DM</b>\n"
        "• Square / 1:1 → <b>Bot Reminder</b>\n\n"
        "Optional caption tags override sorting: <code>#channel</code>, "
        "<code>#dm</code>, <code>#reminder</code>.\n\n"
        "When finished, send <b>/done</b>.",
        parse_mode="HTML",
    )


async def creative_upload(update, context) -> None:
    message = update.effective_message
    if not message or not _is_admin(update):
        return
    if not context.user_data.get("creative_bulk_mode"):
        return

    file_id = ""
    unique_id = ""
    media_type = ""
    width = 0
    height = 0
    filename = ""

    if message.photo:
        photo = message.photo[-1]
        file_id = photo.file_id
        unique_id = photo.file_unique_id
        width = int(photo.width or 0)
        height = int(photo.height or 0)
        media_type = "photo"
    elif message.document and str(message.document.mime_type or "").startswith("image/"):
        doc = message.document
        file_id = doc.file_id
        unique_id = doc.file_unique_id
        filename = str(doc.file_name or "")
        media_type = "document"
        thumb = getattr(doc, "thumbnail", None)
        if thumb:
            width = int(getattr(thumb, "width", 0) or 0)
            height = int(getattr(thumb, "height", 0) or 0)
    else:
        return

    pool = _pool_from(message, width, height, filename)
    _save(file_id, unique_id, media_type, pool, width, height, filename)
    added = context.user_data.setdefault(
        "creative_bulk_added", {"channel": 0, "dm": 0, "reminder": 0}
    )
    added[pool] = int(added.get(pool, 0)) + 1

    await message.reply_text(
        f"✅ Saved → <b>{pool.upper()}</b>",
        parse_mode="HTML",
    )


async def done_command(update, context) -> None:
    message = update.effective_message
    if not message or not _is_admin(update):
        return
    if not context.user_data.get("creative_bulk_mode"):
        await message.reply_text("No bulk creative upload is active.")
        return

    context.user_data["creative_bulk_mode"] = False
    batch = context.user_data.pop(
        "creative_bulk_added", {"channel": 0, "dm": 0, "reminder": 0}
    )
    total = counts()
    await message.reply_text(
        "✅ <b>BULK UPLOAD COMPLETE</b>\n\n"
        f"This batch: Channel <b>{batch.get('channel', 0)}</b> · "
        f"DM <b>{batch.get('dm', 0)}</b> · "
        f"Reminder <b>{batch.get('reminder', 0)}</b>\n\n"
        f"Creative library: Channel <b>{total['channel']}</b> · "
        f"DM <b>{total['dm']}</b> · Reminder <b>{total['reminder']}</b>\n\n"
        "Use /creativepool anytime to check the library.",
        parse_mode="HTML",
    )


async def creativepool_command(update, context) -> None:
    message = update.effective_message
    if not message or not _is_admin(update):
        return
    c = counts()
    await message.reply_text(
        "🗂 <b>IBETIN CREATIVE LIBRARY</b>\n\n"
        f"📢 Channel: <b>{c['channel']}</b>\n"
        f"💬 DM: <b>{c['dm']}</b>\n"
        f"🔔 Bot Reminder: <b>{c['reminder']}</b>",
        parse_mode="HTML",
    )


def _find_target_username(username: str):
    clean = (username or "").strip().lstrip("@")
    if not clean:
        return None
    with core.db() as conn:
        return conn.execute(
            """
            SELECT user_id, username
            FROM users
            WHERE lower(username) = lower(?)
            ORDER BY last_seen DESC
            LIMIT 1
            """,
            (clean,),
        ).fetchone()


def _latest_test_creative():
    ensure_tables()
    with core.db() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM creative_assets
            WHERE active = 1 AND pool = 'dm'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        if row:
            return row
        return conn.execute(
            """
            SELECT *
            FROM creative_assets
            WHERE active = 1
            ORDER BY CASE pool WHEN 'reminder' THEN 0 WHEN 'channel' THEN 1 ELSE 2 END, id DESC
            LIMIT 1
            """
        ).fetchone()


async def senddmtest_command(update, context) -> None:
    message = update.effective_message
    if not message or not _is_admin(update):
        return

    username = context.args[0] if context.args else ""
    if not username:
        await message.reply_text("Usage: /senddmtest @username")
        return

    target = _find_target_username(username)
    if not target:
        await message.reply_text(
            f"⚠️ I don't have {username} in the bot user database yet. "
            "Ask that account to open/start @Ibtnofficialbot once, then retry."
        )
        return

    creative = _latest_test_creative()
    if not creative:
        await message.reply_text(
            "⚠️ No creative is uploaded yet. Use /bulkcreatives first."
        )
        return

    markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton(
            "🏏 OPEN IBETIN LIVE LINE",
            web_app=WebAppInfo(url=LIVE_LINE_URL),
        )]]
    )
    caption = (
        "🏏 <b>IBETIN LIVE LINE</b>\n\n"
        "Live cricket scores, Match Pulse, scorecards, fixtures and results — inside Telegram."
    )

    try:
        if str(creative["media_type"]) == "document":
            await context.bot.send_document(
                chat_id=int(target["user_id"]),
                document=str(creative["file_id"]),
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup,
            )
        else:
            await context.bot.send_photo(
                chat_id=int(target["user_id"]),
                photo=str(creative["file_id"]),
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup,
            )
        await message.reply_text(
            f"✅ Live Line creative test sent to @{target['username']}."
        )
    except (Forbidden, BadRequest) as exc:
        await message.reply_text(f"⚠️ Telegram rejected the test: {exc}")
    except Exception as exc:
        logger.exception("IBETIN creative DM test failed")
        await message.reply_text(f"⚠️ Test send failed: {str(exc)[:160]}")


def install(application) -> None:
    if application.bot_data.get("ibetin_creative_manager_installed"):
        return
    application.bot_data["ibetin_creative_manager_installed"] = True
    ensure_tables()

    # Negative group ensures uploads are captured before the legacy single-banner handler.
    application.add_handler(CommandHandler("bulkcreatives", bulkcreatives_command), group=-5)
    application.add_handler(CommandHandler("done", done_command), group=-5)
    application.add_handler(CommandHandler("creativepool", creativepool_command), group=-5)
    application.add_handler(CommandHandler("senddmtest", senddmtest_command), group=-5)
    application.add_handler(
        MessageHandler(
            filters.UpdateType.MESSAGE
            & (filters.PHOTO | filters.Document.IMAGE),
            creative_upload,
        ),
        group=-5,
    )
    logger.info("IBETIN creative manager installed: bulk upload + pools + DM test")
