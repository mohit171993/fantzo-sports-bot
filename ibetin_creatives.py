import logging
import os
from io import BytesIO

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, InputFile
from telegram.ext import CommandHandler, MessageHandler, filters
from telegram.error import BadRequest, Forbidden

import bot as core
import ibetin_phone_verify as phone_verify

logger = logging.getLogger(__name__)

PUBLIC_BASE_URL = (
    os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/")
    or "https://ibetin-app-production.up.railway.app"
)
LIVE_LINE_URL = os.getenv("IBETIN_LIVE_LINE_URL", f"{PUBLIC_BASE_URL}/liveline").strip()
LIVE_LINE_MINI_APP_URL = os.getenv(
    "IBETIN_LIVELINE_MINI_APP_DEEP_LINK",
    "https://t.me/Ibtnofficialbot/liveline?startapp=liveline",
).strip()
TEST_CAMPAIGN_KEY = "liveline-direct-v40-test-mohit-97saxena-20260918-v3"
CREATIVE_UNLOCK_CODE = os.getenv("IBETIN_CREATIVE_UNLOCK_CODE", "").strip()


def ensure_tables() -> None:
    with core.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS creative_test_sends (
                campaign_key TEXT PRIMARY KEY,
                target_username TEXT NOT NULL,
                target_user_id INTEGER,
                creative_id INTEGER,
                sent_at TEXT,
                status TEXT NOT NULL
            )
            """
        )
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


def _creative_admin_id():
    try:
        with core.db() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"
            )
            row = conn.execute(
                "SELECT value FROM settings WHERE key = 'creative_admin_user_id'"
            ).fetchone()
        return int(row["value"]) if row and row["value"] else None
    except Exception:
        return None


def _is_admin(update) -> bool:
    user = update.effective_user
    if not user:
        return False
    if user.id == core.ADMIN_USER_ID:
        return True
    return user.id == _creative_admin_id()


async def creativeunlock_command(update, context) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return
    code = (context.args[0] if context.args else "").strip()
    if not CREATIVE_UNLOCK_CODE or not code or code != CREATIVE_UNLOCK_CODE:
        await message.reply_text("Invalid creative-manager unlock code.")
        return
    with core.db() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"
        )
        conn.execute(
            """
            INSERT INTO settings(key, value)
            VALUES('creative_admin_user_id', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (str(user.id),),
        )
    await message.reply_text(
        "✅ <b>Creative manager unlocked for this Telegram account.</b>\n\n"
        "Now send /bulkcreatives and upload all banners.",
        parse_mode="HTML",
    )


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


def pick_creative(pool: str, key: int = 0):
    """Pick an active creative deterministically from one pool."""
    pool = str(pool or "").strip().lower()
    if pool not in {"channel", "dm", "reminder"}:
        return None
    ensure_tables()
    with core.db() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM creative_assets
            WHERE active = 1 AND pool = ?
            ORDER BY id ASC
            """,
            (pool,),
        ).fetchall()
    if not rows:
        return None
    try:
        index = abs(int(key or 0)) % len(rows)
    except Exception:
        index = 0
    return rows[index]


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


def _recent_business_targets(limit: int = 5):
    ensure_tables()
    with core.db() as conn:
        try:
            return conn.execute(
                """
                SELECT bc.customer_id AS user_id,
                       bc.username AS username,
                       bc.connection_id AS business_connection_id,
                       bc.last_seen AS last_seen
                FROM business_customers bc
                WHERE bc.connection_id != ''
                ORDER BY bc.last_seen DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        except Exception:
            return []


def _most_recent_business_target():
    rows = _recent_business_targets(1)
    return rows[0] if rows else None


def _find_business_target_username(username: str):
    clean = (username or "").strip().lstrip("@")
    if not clean:
        return None
    ensure_tables()
    with core.db() as conn:
        try:
            return conn.execute(
                """
                SELECT bc.customer_id AS user_id,
                       bc.username AS username,
                       bc.connection_id AS business_connection_id,
                       bc.last_seen AS last_seen
                FROM business_customers bc
                WHERE lower(bc.username) = lower(?)
                  AND bc.connection_id != ''
                ORDER BY bc.last_seen DESC
                LIMIT 1
                """,
                (clean,),
            ).fetchone()
        except Exception:
            return None


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


def _latest_channel_creative():
    ensure_tables()
    with core.db() as conn:
        return conn.execute(
            """
            SELECT *
            FROM creative_assets
            WHERE active = 1 AND pool = 'channel'
            ORDER BY id DESC
            LIMIT 1
            """
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


async def _send_creative_as_photo(bot, creative, kwargs):
    """Always render an uploaded image as a native Telegram photo.

    If the creative was originally uploaded as a document, download it once,
    re-send it as a photo, then cache Telegram's new photo file_id for reuse.
    """
    creative_id = int(creative["id"])
    media_type = str(creative["media_type"] or "")
    file_id = str(creative["file_id"])

    if media_type == "photo":
        return await bot.send_photo(photo=file_id, **kwargs)

    tg_file = await bot.get_file(file_id)
    buffer = BytesIO()
    await tg_file.download_to_memory(out=buffer)
    buffer.seek(0)

    filename = str(creative["filename"] or "").strip() or "ibetin-live-line.jpg"
    message = await bot.send_photo(
        photo=InputFile(buffer, filename=filename),
        **kwargs,
    )

    try:
        if message.photo:
            normalized = message.photo[-1]
            with core.db() as conn:
                conn.execute(
                    """
                    UPDATE creative_assets
                    SET file_id = ?,
                        file_unique_id = ?,
                        media_type = 'photo',
                        width = ?,
                        height = ?
                    WHERE id = ?
                    """,
                    (
                        normalized.file_id,
                        normalized.file_unique_id,
                        int(normalized.width or 0),
                        int(normalized.height or 0),
                        creative_id,
                    ),
                )
            logger.info(
                "IBETIN creative normalized to Telegram photo creative_id=%s",
                creative_id,
            )
    except Exception as exc:
        logger.warning(
            "IBETIN creative photo normalization cache failed id=%s error=%s",
            creative_id,
            str(exc)[:140],
        )

    return message


async def _send_test_to_business_target(bot, target, creative) -> bool:
    if not target or not target["business_connection_id"]:
        return False
    markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton(
            "🏏 OPEN IBETIN LIVE LINE",
            url=(
                phone_verify.live_line_url(int(target["user_id"]), LIVE_LINE_URL)
                if phone_verify.is_verified(int(target["user_id"]))
                else phone_verify.verification_bot_url()
            ),
        )]]
    )
    caption = (
        "🏏 <b>IBETIN LIVE LINE</b>\n\n"
        "Live cricket scores, Match Pulse, scorecards, fixtures and results — inside Telegram."
    )
    kwargs = {
        "chat_id": int(target["user_id"]),
        "business_connection_id": str(target["business_connection_id"]),
        "caption": caption,
        "parse_mode": "HTML",
        "reply_markup": markup,
    }
    await _send_creative_as_photo(bot, creative, kwargs)
    return True


async def _send_test_to_bot_target(bot, target, creative) -> bool:
    if not target:
        return False
    target_user_id = int(target["user_id"])
    if phone_verify.is_verified(target_user_id):
        live_line_button = InlineKeyboardButton(
            "🏏 OPEN IBETIN LIVE LINE",
            web_app=WebAppInfo(
                url=phone_verify.live_line_url(target_user_id, LIVE_LINE_URL)
            ),
        )
    else:
        live_line_button = InlineKeyboardButton(
            "🏏 OPEN IBETIN LIVE LINE",
            callback_data="liveline_access",
        )
    markup = InlineKeyboardMarkup([[live_line_button]])
    caption = (
        "🏏 <b>IBETIN LIVE LINE</b>\n\n"
        "Live cricket scores, Match Pulse, scorecards, fixtures and results — inside Telegram."
    )
    kwargs = {
        "chat_id": int(target["user_id"]),
        "caption": caption,
        "parse_mode": "HTML",
        "reply_markup": markup,
    }
    await _send_creative_as_photo(bot, creative, kwargs)
    return True


async def senddmtest_command(update, context) -> None:
    message = update.effective_message
    if not message or not _is_admin(update):
        return

    username = context.args[0] if context.args else ""
    if not username:
        await message.reply_text("Usage: /senddmtest @username")
        return

    creative = _latest_test_creative()
    if not creative:
        await message.reply_text(
            "⚠️ No creative is uploaded yet. Use /bulkcreatives first."
        )
        return

    business_target = _find_business_target_username(username)
    bot_target = _find_target_username(username)

    if not business_target and not bot_target:
        await message.reply_text(
            f"⚠️ I can't find {username} in either the Business-DM contacts "
            "or the bot-user database yet. Ask the user to send one new DM to "
            "the connected Business account or press Start on @Ibtnofficialbot."
        )
        return

    sent = []
    failed = []

    if business_target:
        try:
            if await _send_test_to_business_target(context.bot, business_target, creative):
                sent.append("Business DM")
        except Exception as exc:
            failed.append(f"Business DM: {str(exc)[:110]}")

    if bot_target:
        try:
            if await _send_test_to_bot_target(context.bot, bot_target, creative):
                sent.append("Bot DM")
        except Exception as exc:
            failed.append(f"Bot DM: {str(exc)[:110]}")

    lines = []
    if sent:
        lines.append("✅ Sent via: " + " + ".join(sent))
    if failed:
        lines.append("⚠️ " + " | ".join(failed))
    await message.reply_text("\n".join(lines) or "No test route was available.")


async def _startup_creative_status_and_test(application) -> None:
    import asyncio
    await asyncio.sleep(6)
    try:
        c = counts()
        logger.info(
            "IBETIN creative pools ready channel=%s dm=%s reminder=%s",
            c["channel"], c["dm"], c["reminder"],
        )

        creative = _latest_test_creative()
        if not creative:
            logger.info("IBETIN startup creative test skipped: no uploaded creative")
            return

        business_target = _find_business_target_username("mohit_97saxena")
        bot_target = _find_target_username("mohit_97saxena")

        if not business_target:
            business_target = _most_recent_business_target()
            if business_target:
                logger.info(
                    "IBETIN startup creative test using most recent Business DM contact user_id=%s username=%s",
                    int(business_target["user_id"]),
                    str(business_target["username"] or ""),
                )

        if not business_target and not bot_target:
            logger.info(
                "IBETIN startup creative test target not found in Business DM or bot contacts"
            )
            return

        with core.db() as conn:
            existing = conn.execute(
                "SELECT status FROM creative_test_sends WHERE campaign_key = ?",
                (TEST_CAMPAIGN_KEY,),
            ).fetchone()
        if existing and str(existing["status"]) == "sent":
            logger.info(
                "IBETIN startup creative test already sent campaign=%s",
                TEST_CAMPAIGN_KEY,
            )
            return

        sent_routes = []
        failures = []

        if business_target:
            try:
                ok = await _send_test_to_business_target(
                    application.bot, business_target, creative
                )
                if ok:
                    sent_routes.append("business_dm")
                    logger.info(
                        "IBETIN creative test BUSINESS DM sent username=%s user_id=%s",
                        str(business_target["username"] or "mohit_97saxena"),
                        int(business_target["user_id"]),
                    )
            except Exception as exc:
                failures.append("business_dm:" + str(exc)[:140])
                logger.warning(
                    "IBETIN creative test BUSINESS DM failed username=mohit_97saxena error=%s",
                    str(exc)[:180],
                )

        if bot_target:
            try:
                ok = await _send_test_to_bot_target(
                    application.bot, bot_target, creative
                )
                if ok:
                    sent_routes.append("bot_dm")
                    logger.info(
                        "IBETIN creative test BOT DM sent username=%s user_id=%s",
                        str(bot_target["username"] or "mohit_97saxena"),
                        int(bot_target["user_id"]),
                    )
            except Exception as exc:
                failures.append("bot_dm:" + str(exc)[:140])
                logger.warning(
                    "IBETIN creative test BOT DM failed username=mohit_97saxena error=%s",
                    str(exc)[:180],
                )

        status = "sent" if sent_routes else "failed"
        target_id = (
            int(business_target["user_id"])
            if business_target
            else int(bot_target["user_id"]) if bot_target else None
        )
        with core.db() as conn:
            conn.execute(
                """
                INSERT INTO creative_test_sends(
                    campaign_key, target_username, target_user_id,
                    creative_id, sent_at, status
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(campaign_key) DO UPDATE SET
                    target_user_id = excluded.target_user_id,
                    creative_id = excluded.creative_id,
                    sent_at = excluded.sent_at,
                    status = excluded.status
                """,
                (
                    TEST_CAMPAIGN_KEY,
                    "mohit_97saxena",
                    target_id,
                    int(creative["id"]),
                    core.now_iso(),
                    status,
                ),
            )

        logger.info(
            "IBETIN startup creative test complete routes=%s failures=%s creative_id=%s",
            ",".join(sent_routes) or "none",
            " | ".join(failures) or "none",
            int(creative["id"]),
        )
    except Exception as exc:
        logger.warning(
            "IBETIN creative startup verification/test failed: %s",
            str(exc)[:180],
        )


async def _startup_channel_preview_test(application) -> None:
    import asyncio
    await asyncio.sleep(8)

    username = (
        os.getenv("IBETIN_CHANNEL_PREVIEW_USERNAME", "")
        .strip()
        .lstrip("@")
    )
    if not username:
        return

    campaign_key = (
        "channel-preview:"
        + username.casefold()
        + ":"
        + os.getenv("IBETIN_CHANNEL_PREVIEW_KEY", "v1").strip()
    )

    try:
        creative = _latest_channel_creative()
        target = _find_target_username(username)

        if not creative:
            logger.warning("IBETIN channel preview skipped: no channel creative")
            return
        if not target:
            logger.warning(
                "IBETIN channel preview skipped: bot target not found username=%s",
                username,
            )
            return

        with core.db() as conn:
            existing = conn.execute(
                "SELECT status FROM creative_test_sends WHERE campaign_key=?",
                (campaign_key,),
            ).fetchone()
        if existing and str(existing["status"]) == "sent":
            logger.info(
                "IBETIN channel preview already sent campaign=%s",
                campaign_key,
            )
            return

        target_user_id = int(target["user_id"])
        if phone_verify.is_verified(target_user_id):
            live_button = InlineKeyboardButton(
                "🏏 OPEN IBETIN LIVE LINE",
                web_app=WebAppInfo(
                    url=phone_verify.live_line_url(target_user_id, LIVE_LINE_URL)
                ),
            )
        else:
            live_button = InlineKeyboardButton(
                "🏏 OPEN IBETIN LIVE LINE",
                callback_data="liveline_access",
            )

        caption = (
            "🏏 <b>IBETIN LIVE LINE</b>\n\n"
            "Live cricket scores, Match Pulse, scorecards, fixtures and results — "
            "inside Telegram.\n\n"
            "⚡ Fast live updates\n"
            "📊 Match Pulse & scorecards\n"
            "🗓 Fixtures & results\n\n"
            "Tap below to open Live Line."
        )

        msg = await _send_creative_as_photo(
            application.bot,
            creative,
            {
                "chat_id": target_user_id,
                "caption": caption,
                "parse_mode": "HTML",
                "reply_markup": InlineKeyboardMarkup([[live_button]]),
            },
        )

        with core.db() as conn:
            conn.execute(
                """
                INSERT INTO creative_test_sends(
                    campaign_key, target_username, target_user_id,
                    creative_id, sent_at, status
                )
                VALUES (?, ?, ?, ?, ?, 'sent')
                ON CONFLICT(campaign_key) DO UPDATE SET
                    target_user_id=excluded.target_user_id,
                    creative_id=excluded.creative_id,
                    sent_at=excluded.sent_at,
                    status='sent'
                """,
                (
                    campaign_key,
                    username,
                    target_user_id,
                    int(creative["id"]),
                    core.now_iso(),
                ),
            )

        logger.info(
            "IBETIN CHANNEL PREVIEW SENT username=%s creative_id=%s message_id=%s",
            username,
            int(creative["id"]),
            int(msg.message_id),
        )
    except Exception as exc:
        logger.warning(
            "IBETIN channel preview failed username=%s error=%s",
            username,
            str(exc)[:180],
        )


def install(application) -> None:
    if application.bot_data.get("ibetin_creative_manager_installed"):
        return
    application.bot_data["ibetin_creative_manager_installed"] = True
    ensure_tables()

    # Negative group ensures uploads are captured before the legacy single-banner handler.
    application.add_handler(CommandHandler("creativeunlock", creativeunlock_command), group=-5)
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
    # Production startup must never send test/preview messages automatically.
    # Tests remain available only through the explicit admin commands.
    try:
        c = counts()
        logger.info(
            "IBETIN creative pools ready channel=%s dm=%s reminder=%s",
            c["channel"], c["dm"], c["reminder"],
        )
    except Exception:
        logger.exception("Could not read IBETIN creative pool status")
    logger.info(
        "IBETIN creative manager installed: bulk upload + pools + manual DM test; "
        "startup test sends disabled"
    )
