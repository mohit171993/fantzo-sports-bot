import asyncio
import logging
import os
import re
from html import unescape
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.error import BadRequest
from telegram.ext import (
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import bot as core
from fantzo_brand import has_foreign_brand

logger = logging.getLogger(__name__)
APP_TZ = ZoneInfo("Asia/Kolkata")
CHANNEL_ID = os.getenv("FANTZO_CHANNEL_ID", "@fantzoupdates").strip()
POST_HOUR_IST = int(os.getenv("FANTZO_BANNER_HOUR_IST", "19"))
POST_MINUTE_IST = int(os.getenv("FANTZO_BANNER_MINUTE_IST", "0"))
CHECK_INTERVAL_SECONDS = 60
FAILURE_RETRY_SECONDS = 15 * 60
DAILY_FALLBACK_IMAGE = Path(__file__).resolve().parent / "assets" / "fantzo_live_tv_daily.jpg"
DAILY_FALLBACK_CAPTION = (
    "📺 <b>FANTZO LIVE TV</b>\n\n"
    "Explore live sports streams on Fantzo. "
    "Tap below to see what is available now."
)
_post_lock = asyncio.Lock()
DEFAULT_CAPTION = (
    "📺 <b>FANTZO LIVE TV</b>\n\n"
    "🔥 Catch the live sports action on Fantzo.\n"
    "Tap below to watch Live TV."
)


def ensure_tables():
    with core.db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS live_tv_banners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT NOT NULL,
                caption TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'queued',
                brand TEXT NOT NULL DEFAULT 'legacy',
                created_at TEXT NOT NULL,
                posted_at TEXT
            )
        """)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(live_tv_banners)").fetchall()}
        if "media_type" not in cols:
            conn.execute("ALTER TABLE live_tv_banners ADD COLUMN media_type TEXT NOT NULL DEFAULT 'document'")
        if "brand" not in cols:
            conn.execute("ALTER TABLE live_tv_banners ADD COLUMN brand TEXT NOT NULL DEFAULT 'legacy'")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS live_tv_banner_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.execute("INSERT OR IGNORE INTO live_tv_banner_settings(key,value) VALUES('paused','0')")
        conn.execute("INSERT OR IGNORE INTO live_tv_banner_settings(key,value) VALUES('last_post_date','')")
        conn.execute("INSERT OR IGNORE INTO live_tv_banner_settings(key,value) VALUES('last_post_at','')")
        conn.execute("INSERT OR IGNORE INTO live_tv_banner_settings(key,value) VALUES('last_post_kind','')")


def _now_iso(): return datetime.now(timezone.utc).isoformat()

def _setting(key, default=""):
    ensure_tables()
    with core.db() as conn:
        row = conn.execute("SELECT value FROM live_tv_banner_settings WHERE key=?", (key,)).fetchone()
    return str(row["value"]) if row else default

def _set_setting(key, value):
    ensure_tables()
    with core.db() as conn:
        conn.execute("INSERT INTO live_tv_banner_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))

def is_paused() -> bool:
    return _setting("paused", "0") == "1"


def set_paused(paused: bool) -> None:
    _set_setting("paused", "1" if paused else "0")


def schedule_text() -> str:
    return f"{POST_HOUR_IST:02d}:{POST_MINUTE_IST:02d} IST"


def delivery_status() -> dict[str, str]:
    return {key: _setting(key) for key in (
        "last_post_date", "last_post_at", "last_post_kind",
        "last_failure_at", "last_failure_kind", "scheduler_heartbeat_at",
    )}


def _record_success(kind: str) -> None:
    now = _now_iso()
    today = datetime.now(APP_TZ).date().isoformat()
    ensure_tables()
    with core.db() as conn:
        conn.executemany(
            "INSERT INTO live_tv_banner_settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (("last_post_date", today), ("last_post_at", now), ("last_post_kind", kind)),
        )


def _record_failure(kind: str) -> None:
    _set_setting("last_failure_at", _now_iso())
    _set_setting("last_failure_kind", kind)


def _failure_backoff_active() -> bool:
    value = _setting("last_failure_at")
    if not value:
        return False
    try:
        failed_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) - failed_at < timedelta(seconds=FAILURE_RETRY_SECONDS)
    except ValueError:
        return False


def queue_count():
    ensure_tables()
    with core.db() as conn:
        return int(conn.execute(
            "SELECT COUNT(*) AS c FROM live_tv_banners "
            "WHERE status='queued' AND brand IN ('legacy','fantzo')"
        ).fetchone()["c"])

def pending_count():
    ensure_tables()
    with core.db() as conn:
        return int(conn.execute("SELECT COUNT(*) AS c FROM live_tv_banners WHERE status='pending_review'").fetchone()["c"])

def add_banner(file_id, caption="", media_type="photo"):
    ensure_tables()
    with core.db() as conn:
        cursor = conn.execute(
            "INSERT INTO live_tv_banners(file_id,caption,media_type,status,brand,created_at) "
            "VALUES(?,?,?,'pending_review','unverified',?)",
            (file_id, caption or "", media_type, _now_iso()),
        )
        return int(cursor.lastrowid)

def review_banner(banner_id: int, approved: bool) -> bool:
    ensure_tables()
    with core.db() as conn:
        row = conn.execute(
            "SELECT caption FROM live_tv_banners WHERE id=? AND status='pending_review'",
            (banner_id,),
        ).fetchone()
        if not row or (approved and has_foreign_brand(row["caption"])):
            return False
        result = conn.execute(
            "UPDATE live_tv_banners SET status=?, brand=? WHERE id=? AND status='pending_review'",
            ("queued" if approved else "rejected", "fantzo" if approved else "unverified", banner_id),
        )
        return result.rowcount == 1

def next_banner():
    ensure_tables()
    with core.db() as conn:
        return conn.execute(
            "SELECT id,file_id,caption,media_type FROM live_tv_banners "
            "WHERE status='queued' AND brand IN ('legacy','fantzo') ORDER BY id ASC LIMIT 1"
        ).fetchone()

def mark_posted(banner_id):
    with core.db() as conn:
        conn.execute("UPDATE live_tv_banners SET status='posted', posted_at=? WHERE id=?", (_now_iso(), banner_id))

def clear_queue():
    ensure_tables()
    with core.db() as conn: conn.execute("DELETE FROM live_tv_banners WHERE status='queued'")

def _admin_text() -> str:
    paused = is_paused()
    queued = queue_count()
    pending = pending_count()
    schedule = schedule_text()
    next_state = (
        f"Next auto post: <b>{schedule}</b>"
        if queued and not paused
        else "Next auto post: <b>PAUSED</b>"
        if paused
        else f"Next auto post: <b>{schedule} (Fantzo daily creative)</b>"
    )
    return (
        "📺 <b>LIVE TV BANNER QUEUE</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"Queued: <b>{queued}</b>\n"
        f"Awaiting visual approval: <b>{pending}</b>\n"
        f"Status: <b>{'PAUSED' if paused else 'ACTIVE'}</b>\n"
        f"{next_state}\n\n"
        "New uploads require a Fantzo visual approval before posting. "
        "Previously queued banners remain in the queue. When the approved queue is empty, "
        "the Fantzo daily creative posts instead."
    )


def admin_keyboard():
    paused = is_paused()
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "▶ RESUME" if paused else "⏸ PAUSE",
                callback_data="banner_toggle",
            ),
            InlineKeyboardButton("📤 POST NOW", callback_data="banner_postnow"),
        ],
        [
            InlineKeyboardButton("🖼 UPLOAD BANNERS", callback_data="banner_upload_help"),
            InlineKeyboardButton("✅ DONE UPLOADING", callback_data="banner_done"),
        ],
        [InlineKeyboardButton("🔄 REFRESH", callback_data="banner_refresh")],
    ])


async def banner_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not core.is_admin_user(update.effective_user.id):
        return
    await update.effective_message.reply_text(
        _admin_text(),
        parse_mode="HTML",
        reply_markup=admin_keyboard(),
    )


async def begin_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not core.is_admin_user(update.effective_user.id):
        return
    context.user_data["fantzo_banner_queue_upload"] = True
    await update.effective_message.reply_text(
        "🖼 <b>CHANNEL BANNER UPLOAD MODE ON</b>\n\n"
        "Send photos or PNG/JPG/WebP files now. Each image will be shown "
        "for Fantzo approval before entering the channel queue. Use /bannerdone when finished.",
        parse_mode="HTML",
    )


async def done_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not core.is_admin_user(update.effective_user.id):
        return
    context.user_data["fantzo_banner_queue_upload"] = False
    await update.effective_message.reply_text(
        f"✅ Channel upload mode OFF. Queue: {queue_count()}"
    )


async def banner_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    if not query or not user or not core.is_admin_user(user.id):
        if query:
            await query.answer("Restricted", show_alert=True)
        raise ApplicationHandlerStop

    data = str(query.data or "")
    review = re.fullmatch(r"banner_review_(approve|reject)_(\d+)", data)
    if review:
        approved = review.group(1) == "approve"
        changed = review_banner(int(review.group(2)), approved)
        await query.answer(
            "Fantzo banner queued" if changed and approved else
            "Banner rejected" if changed else "Review expired or blocked",
            show_alert=not changed,
        )
        if changed:
            try:
                await query.edit_message_caption(
                    caption="✅ Approved for the Fantzo channel queue." if approved else
                    "🗑 Rejected. This banner will not be posted."
                )
            except BadRequest:
                logger.warning("Could not update Fantzo banner review preview")
        raise ApplicationHandlerStop
    await query.answer()

    if data == "banner_toggle":
        set_paused(not is_paused())
    elif data == "banner_upload_help":
        context.user_data["fantzo_banner_queue_upload"] = True
        await query.message.reply_text(
            "🖼 <b>CHANNEL BANNER UPLOAD MODE ON</b>\n\n"
            "Send photos or PNG/JPG/WebP files now. Each image needs visual approval. "
            "Tap DONE UPLOADING when finished.",
            parse_mode="HTML",
        )
    elif data == "banner_done":
        context.user_data["fantzo_banner_queue_upload"] = False
    elif data == "banner_postnow":
        posted = await _post_next(context.bot)
        if posted:
            await query.message.reply_text("✅ Next channel banner posted.")
        else:
            await query.message.reply_text("ℹ️ Banner queue is empty.")

    try:
        await query.edit_message_text(
            _admin_text(),
            parse_mode="HTML",
            reply_markup=admin_keyboard(),
        )
    except BadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise
    raise ApplicationHandlerStop

async def receive_banner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not core.is_admin_user(update.effective_user.id):
        return
    if not context.user_data.get("fantzo_banner_queue_upload"):
        return
    message = update.effective_message
    if not message:
        return
    file_id = None
    media_type = None
    if message.photo:
        file_id = message.photo[-1].file_id
        media_type = "photo"
    elif message.document:
        mime = (message.document.mime_type or "").lower()
        name = (message.document.file_name or "").lower()
        if mime.startswith("image/") or name.endswith((".png", ".jpg", ".jpeg", ".webp")):
            file_id = message.document.file_id
            media_type = "document"
    if not file_id:
        return
    caption = (message.caption or "").strip()
    filename = message.document.file_name if message.document else ""
    if has_foreign_brand(caption) or has_foreign_brand(filename):
        await message.reply_text(
            "⛔ This upload mentions another brand. Send a Fantzo creative."
        )
        raise ApplicationHandlerStop

    banner_id = add_banner(file_id, caption, media_type)
    review_markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ APPROVE FANTZO", callback_data=f"banner_review_approve_{banner_id}"),
        InlineKeyboardButton("🗑 REJECT", callback_data=f"banner_review_reject_{banner_id}"),
    ]])
    preview_caption = (
        f"Fantzo channel creative #{banner_id}. Check the image and caption carefully.\n"
        "Approve only if the visual belongs to Fantzo.\n\n"
        f"{caption[:700]}"
    )
    if media_type == "photo":
        await message.reply_photo(photo=file_id, caption=preview_caption, reply_markup=review_markup)
    else:
        await message.reply_document(document=file_id, caption=preview_caption, reply_markup=review_markup)
    raise ApplicationHandlerStop

async def send_banner(bot, chat_id, row, caption_prefix=""):
    caption = caption_prefix + (str(row["caption"] or "").strip() or DEFAULT_CAPTION)
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "📺 WATCH LIVE TV",
            url="https://t.me/fantzoofficialbot?start=livetv_banner",
        )
    ]])
    file_id = str(row["file_id"])

    async def _send(caption_value: str, parse_mode):
        if str(row["media_type"] or "document") == "photo":
            return await bot.send_photo(
                chat_id=chat_id,
                photo=file_id,
                caption=caption_value,
                parse_mode=parse_mode,
                reply_markup=markup,
            )
        tg_file = await bot.get_file(file_id)
        data = await tg_file.download_as_bytearray()
        photo = InputFile(BytesIO(bytes(data)), filename="fantzo-live-tv.png")
        return await bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=caption_value,
            parse_mode=parse_mode,
            reply_markup=markup,
        )

    try:
        return await _send(caption, "HTML")
    except BadRequest as exc:
        message = str(exc).lower()
        if "parse" not in message and "entity" not in message:
            raise
        plain = unescape(re.sub(r"<[^>]*>", "", caption)).strip()
        logger.warning("Fantzo channel caption HTML invalid; retrying as plain text")
        return await _send(plain[:1000], None)


async def send_daily_fallback(bot):
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "📺 WATCH LIVE TV",
            url="https://t.me/fantzoofficialbot?start=livetv_banner",
        )
    ]])
    with DAILY_FALLBACK_IMAGE.open("rb") as image:
        return await bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=image,
            caption=DAILY_FALLBACK_CAPTION,
            parse_mode="HTML",
            reply_markup=markup,
        )

async def _post_next(bot):
    async with _post_lock:
        row = next_banner()
        if not row:
            return False
        try:
            message = await send_banner(bot, CHANNEL_ID, row)
        except Exception:
            _record_failure("approved_banner")
            raise
        mark_posted(int(row["id"]))
        _record_success("approved_banner")
        logger.info("Fantzo approved banner %s posted to %s message=%s", row["id"], CHANNEL_ID, getattr(message, "message_id", None))
        return True


async def _post_daily(bot):
    async with _post_lock:
        today = datetime.now(APP_TZ).date().isoformat()
        if _setting("last_post_date") == today:
            return False
        row = next_banner()
        kind = "approved_banner" if row else "daily_fallback"
        try:
            if row:
                message = await send_banner(bot, CHANNEL_ID, row)
            else:
                message = await send_daily_fallback(bot)
        except Exception:
            _record_failure(kind)
            raise
        if row:
            mark_posted(int(row["id"]))
        _record_success(kind)
        logger.info("Fantzo channel %s posted to %s message=%s", kind, CHANNEL_ID, getattr(message, "message_id", None))
        return True

async def post_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not core.is_admin_user(update.effective_user.id):
        return
    try:
        posted = await _post_next(context.bot)
        await update.effective_message.reply_text(
            "✅ Next channel banner posted."
            if posted else
            "ℹ️ Banner queue is empty."
        )
    except Exception:
        logger.exception("Manual banner post failed")
        await update.effective_message.reply_text(
            "⚠️ Banner post failed. Check the channel/admin logs."
        )

async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user and core.is_admin_user(update.effective_user.id):
        _set_setting("paused", "1"); await update.effective_message.reply_text("⏸ Live TV automatic banner posting paused.")
async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user and core.is_admin_user(update.effective_user.id):
        _set_setting("paused", "0"); await update.effective_message.reply_text("▶ Live TV automatic banner posting resumed.")
async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user and core.is_admin_user(update.effective_user.id):
        clear_queue(); await update.effective_message.reply_text("🗑 Unposted Live TV banner queue cleared.")

async def scheduler_loop(application):
    ensure_tables(); await asyncio.sleep(15)
    while True:
        try:
            _set_setting("scheduler_heartbeat_at", _now_iso())
            now = datetime.now(APP_TZ); today = now.date().isoformat()
            due = (now.hour > POST_HOUR_IST) or (now.hour == POST_HOUR_IST and now.minute >= POST_MINUTE_IST)
            if due and _setting("paused", "0") != "1" and _setting("last_post_date", "") != today:
                if not _failure_backoff_active():
                    await _post_daily(application.bot)
        except Exception: logger.exception("Fantzo Live TV banner scheduler error")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)

async def _start_scheduler_when_running(application):
    while not application.running:
        await asyncio.sleep(0.2)
    application.create_task(scheduler_loop(application))


def install(application):
    ensure_tables()
    application.add_handler(CommandHandler("banners", banner_admin))
    application.add_handler(CommandHandler("bannerupload", begin_upload))
    application.add_handler(CommandHandler("bannerdone", done_upload))
    application.add_handler(CommandHandler("bannerpostnow", post_now))
    application.add_handler(CommandHandler("bannerpause", pause))
    application.add_handler(CommandHandler("bannerresume", resume))
    application.add_handler(CommandHandler("bannerclear", clear))
    application.add_handler(
        CallbackQueryHandler(banner_callback, pattern=r"^banner_"),
        group=-7,
    )
    image_uploads = (
        filters.PHOTO
        | filters.Document.IMAGE
        | filters.Document.FileExtension("png")
        | filters.Document.FileExtension("jpg")
        | filters.Document.FileExtension("jpeg")
        | filters.Document.FileExtension("webp")
    )
    application.add_handler(
        MessageHandler(
            image_uploads & filters.User(user_id=sorted(core.admin_user_ids())),
            receive_banner,
        ),
        group=-6,
    )
    asyncio.create_task(
        _start_scheduler_when_running(application),
        name="fantzo-banner-scheduler-starter",
    )
