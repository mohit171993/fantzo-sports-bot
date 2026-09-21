import asyncio
import logging
import os
from datetime import datetime, timezone
from io import BytesIO
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, filters

import bot as core

logger = logging.getLogger(__name__)
APP_TZ = ZoneInfo("Asia/Dubai")
CHANNEL_ID = os.getenv("FANTZO_CHANNEL_ID", "@fantzoupdates").strip()
POST_HOUR_DUBAI = int(os.getenv("FANTZO_BANNER_HOUR_DUBAI", "17"))
POST_MINUTE_DUBAI = int(os.getenv("FANTZO_BANNER_MINUTE_DUBAI", "30"))
CHECK_INTERVAL_SECONDS = 60
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
                created_at TEXT NOT NULL,
                posted_at TEXT
            )
        """)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(live_tv_banners)").fetchall()}
        if "media_type" not in cols:
            conn.execute("ALTER TABLE live_tv_banners ADD COLUMN media_type TEXT NOT NULL DEFAULT 'document'")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS live_tv_banner_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.execute("INSERT OR IGNORE INTO live_tv_banner_settings(key,value) VALUES('paused','0')")
        conn.execute("INSERT OR IGNORE INTO live_tv_banner_settings(key,value) VALUES('last_post_date','')")


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

def queue_count():
    ensure_tables()
    with core.db() as conn:
        return int(conn.execute("SELECT COUNT(*) AS c FROM live_tv_banners WHERE status='queued'").fetchone()["c"])

def add_banner(file_id, caption="", media_type="photo"):
    ensure_tables()
    with core.db() as conn:
        conn.execute("INSERT INTO live_tv_banners(file_id,caption,media_type,status,created_at) VALUES(?,?,?,'queued',?)", (file_id, caption or "", media_type, _now_iso()))

def next_banner():
    ensure_tables()
    with core.db() as conn:
        return conn.execute("SELECT id,file_id,caption,media_type FROM live_tv_banners WHERE status='queued' ORDER BY id ASC LIMIT 1").fetchone()

def mark_posted(banner_id):
    with core.db() as conn:
        conn.execute("UPDATE live_tv_banners SET status='posted', posted_at=? WHERE id=?", (_now_iso(), banner_id))

def clear_queue():
    ensure_tables()
    with core.db() as conn: conn.execute("DELETE FROM live_tv_banners WHERE status='queued'")

def admin_keyboard():
    paused = _setting("paused", "0") == "1"
    return InlineKeyboardMarkup([[InlineKeyboardButton("▶ Resume" if paused else "⏸ Pause", callback_data="banner_toggle")],[InlineKeyboardButton("📤 Upload banners", callback_data="banner_upload_help")]])

async def banner_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != core.ADMIN_USER_ID: return
    paused = _setting("paused", "0") == "1"
    await update.effective_message.reply_text("📺 <b>LIVE TV BANNER QUEUE</b>\n━━━━━━━━━━━━━━━━━━\n\n" f"Queued: <b>{queue_count()}</b>\nStatus: <b>{'PAUSED' if paused else 'ACTIVE'}</b>\n" f"Auto post: <b>{POST_HOUR_DUBAI:02d}:{POST_MINUTE_DUBAI:02d} Dubai / 19:00 IST</b>\n\n" "Bulk upload: send multiple banner images as photos OR PNG/JPG/WebP files. Each image is added automatically.\n\n" "Commands:\n/bannerpostnow - post next banner now\n/bannerpause - pause automatic posting\n/bannerresume - resume automatic posting\n/bannerclear - clear unposted queue", parse_mode="HTML", reply_markup=admin_keyboard())

async def receive_banner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != core.ADMIN_USER_ID: return
    message = update.effective_message
    if not message: return
    file_id = None; media_type = None
    if message.photo:
        file_id = message.photo[-1].file_id; media_type = "photo"
    elif message.document:
        mime = (message.document.mime_type or "").lower(); name = (message.document.file_name or "").lower()
        if mime.startswith("image/") or name.endswith((".png", ".jpg", ".jpeg", ".webp")):
            file_id = message.document.file_id; media_type = "document"
    if not file_id: return
    add_banner(file_id, (message.caption or "").strip(), media_type)
    await message.reply_text(f"✅ Banner added to Live TV queue. Queue: {queue_count()}")

async def send_banner(bot, chat_id, row, caption_prefix=""):
    caption = caption_prefix + (str(row["caption"] or "").strip() or DEFAULT_CAPTION)
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("📺 WATCH LIVE TV", url="https://t.me/fantzoofficialbot?start=livetv_banner")]])
    file_id = str(row["file_id"])
    if str(row["media_type"] or "document") == "photo":
        await bot.send_photo(chat_id=chat_id, photo=file_id, caption=caption, parse_mode="HTML", reply_markup=markup)
        return
    tg_file = await bot.get_file(file_id)
    data = await tg_file.download_as_bytearray()
    photo = InputFile(BytesIO(bytes(data)), filename="fantzo-live-tv.png")
    await bot.send_photo(chat_id=chat_id, photo=photo, caption=caption, parse_mode="HTML", reply_markup=markup)

async def _post_next(bot):
    row = next_banner()
    if not row: return False
    await send_banner(bot, CHANNEL_ID, row)
    mark_posted(int(row["id"]))
    logger.info("Fantzo Live TV banner %s posted to %s", row["id"], CHANNEL_ID)
    return True

async def post_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != core.ADMIN_USER_ID: return
    try:
        posted = await _post_next(context.bot)
        await update.effective_message.reply_text("✅ Next Live TV banner posted." if posted else "ℹ️ Banner queue is empty.")
    except Exception as exc:
        logger.exception("Manual banner post failed"); await update.effective_message.reply_text(f"⚠️ Banner post failed: {exc}")

async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user and update.effective_user.id == core.ADMIN_USER_ID:
        _set_setting("paused", "1"); await update.effective_message.reply_text("⏸ Live TV automatic banner posting paused.")
async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user and update.effective_user.id == core.ADMIN_USER_ID:
        _set_setting("paused", "0"); await update.effective_message.reply_text("▶ Live TV automatic banner posting resumed.")
async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user and update.effective_user.id == core.ADMIN_USER_ID:
        clear_queue(); await update.effective_message.reply_text("🗑 Unposted Live TV banner queue cleared.")

async def scheduler_loop(application):
    ensure_tables(); await asyncio.sleep(15)
    while True:
        try:
            now = datetime.now(APP_TZ); today = now.date().isoformat()
            due = (now.hour > POST_HOUR_DUBAI) or (now.hour == POST_HOUR_DUBAI and now.minute >= POST_MINUTE_DUBAI)
            if due and _setting("paused", "0") != "1" and _setting("last_post_date", "") != today:
                if await _post_next(application.bot): _set_setting("last_post_date", today)
        except Exception: logger.exception("Fantzo Live TV banner scheduler error")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)

async def _start_scheduler_when_running(application):
    while not application.running:
        await asyncio.sleep(0.2)
    application.create_task(scheduler_loop(application))


def install(application):
    ensure_tables()
    application.add_handler(CommandHandler("banners", banner_admin)); application.add_handler(CommandHandler("bannerpostnow", post_now)); application.add_handler(CommandHandler("bannerpause", pause)); application.add_handler(CommandHandler("bannerresume", resume)); application.add_handler(CommandHandler("bannerclear", clear))
    image_uploads = filters.PHOTO | filters.Document.IMAGE | filters.Document.FileExtension("png") | filters.Document.FileExtension("jpg") | filters.Document.FileExtension("jpeg") | filters.Document.FileExtension("webp")
    application.add_handler(MessageHandler(image_uploads & filters.User(user_id=core.ADMIN_USER_ID), receive_banner))
    asyncio.create_task(
        _start_scheduler_when_running(application),
        name="fantzo-banner-scheduler-starter",
    )
