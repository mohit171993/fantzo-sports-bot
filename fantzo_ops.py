import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

import bot as core

logger = logging.getLogger(__name__)

BACKUP_DIR = Path(os.getenv("FANTZO_BACKUP_DIR", "/data/backups"))
BACKUP_INTERVAL_SECONDS = max(
    3600, int(os.getenv("FANTZO_BACKUP_INTERVAL_SECONDS", str(6 * 60 * 60)))
)
BACKUP_RETENTION_DAYS = max(
    1, int(os.getenv("FANTZO_BACKUP_RETENTION_DAYS", "14"))
)
BACKUP_START_DELAY_SECONDS = max(
    30, int(os.getenv("FANTZO_BACKUP_START_DELAY_SECONDS", "120"))
)

_backup_task = None
_last_backup_path = None
_last_backup_at = None
_last_backup_error = None


def _is_admin(update: Update) -> bool:
    return bool(
        update.effective_user
        and int(update.effective_user.id) == int(core.ADMIN_USER_ID)
    )


def _fmt_header(headers, *names):
    for name in names:
        value = headers.get(name)
        if value not in (None, ""):
            return str(value)
    return "n/a"


async def api_status_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not _is_admin(update):
        return

    message = update.effective_message
    if not message:
        return

    if not core.HIGHLIGHTLY_API_KEY:
        await message.reply_text(
            "⚠️ Highlightly API key is not configured.",
        )
        return

    today = datetime.now(core.APP_TIMEZONE).date().isoformat()
    url = f"{core.HIGHLIGHTLY_API_BASE}/cricket/matches"
    headers = {"x-rapidapi-key": core.HIGHLIGHTLY_API_KEY}
    params = {
        "date": today,
        "timezone": "Asia/Dubai",
        "limit": 1,
    }

    status = None
    response_headers = {}
    error_text = ""

    try:
        timeout = httpx.Timeout(12.0, connect=6.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                url,
                headers=headers,
                params=params,
            )
        status = response.status_code
        response_headers = response.headers
        if status >= 400 and status != 429:
            error_text = (response.text or "").strip()[:180]
    except Exception as exc:
        logger.exception("Fantzo /apistatus check failed")
        error_text = f"{type(exc).__name__}: {exc}"[:180]

    limit = _fmt_header(
        response_headers,
        "x-ratelimit-requests-limit",
        "x-ratelimit-limit",
    )
    remaining = _fmt_header(
        response_headers,
        "x-ratelimit-requests-remaining",
        "x-ratelimit-remaining",
    )
    reset = _fmt_header(
        response_headers,
        "x-ratelimit-requests-reset",
        "x-ratelimit-reset",
    )
    retry_after = _fmt_header(response_headers, "retry-after")

    if status is None:
        health = "❌ Request failed"
    elif status == 429:
        health = "⏳ Rate limited"
    elif 200 <= status < 300:
        health = "✅ Healthy"
    elif status in (401, 403):
        health = "🔐 Authentication problem"
    else:
        health = f"⚠️ HTTP {status}"

    text = (
        "🩺 <b>FANTZO API STATUS</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"Highlightly: <b>{health}</b>\n"
        f"HTTP status: <b>{status if status is not None else 'n/a'}</b>\n"
        f"Request limit: <b>{limit}</b>\n"
        f"Requests remaining: <b>{remaining}</b>\n"
        f"Reset: <b>{reset}</b>\n"
        f"Retry-After: <b>{retry_after}</b>\n\n"
        "ℹ️ This command makes one small Highlightly request only when you run it."
    )

    if error_text:
        safe_error = (
            error_text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        text += f"\n\nLast error: <code>{safe_error}</code>"

    await message.reply_text(text, parse_mode="HTML")


def _backup_files():
    if not BACKUP_DIR.exists():
        return []
    return sorted(
        BACKUP_DIR.glob("fantzo_bot_*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def _prune_backups(now_utc=None) -> int:
    now_utc = now_utc or datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(days=BACKUP_RETENTION_DAYS)
    removed = 0

    for path in _backup_files():
        try:
            modified = datetime.fromtimestamp(
                path.stat().st_mtime, timezone.utc
            )
            if modified < cutoff:
                path.unlink(missing_ok=True)
                removed += 1
        except Exception:
            logger.exception("Could not prune Fantzo backup %s", path)

    return removed


def create_backup() -> Path:
    global _last_backup_path, _last_backup_at, _last_backup_error

    source_path = Path(core.DB_PATH)
    if not source_path.exists():
        raise FileNotFoundError(f"Fantzo DB not found at {source_path}")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = BACKUP_DIR / f"fantzo_bot_{stamp}.db"
    partial = destination.with_suffix(".db.partial")

    if partial.exists():
        partial.unlink()

    try:
        with sqlite3.connect(str(source_path), timeout=30) as source:
            with sqlite3.connect(str(partial), timeout=30) as target:
                source.backup(target)

        with sqlite3.connect(str(partial), timeout=30) as check:
            result = check.execute("PRAGMA quick_check").fetchone()
            if not result or str(result[0]).lower() != "ok":
                raise RuntimeError(
                    f"SQLite quick_check failed: {result[0] if result else 'no result'}"
                )

        partial.replace(destination)
        _prune_backups()

        _last_backup_path = destination
        _last_backup_at = datetime.now(timezone.utc)
        _last_backup_error = None
        logger.info("Fantzo DB backup created: %s", destination)
        return destination

    except Exception as exc:
        _last_backup_error = f"{type(exc).__name__}: {exc}"
        if partial.exists():
            try:
                partial.unlink()
            except Exception:
                logger.exception("Could not remove partial Fantzo backup")
        raise


async def backup_now_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not _is_admin(update):
        return

    message = update.effective_message
    if not message:
        return

    try:
        path = await asyncio.to_thread(create_backup)
        size_mb = path.stat().st_size / (1024 * 1024)
        await message.reply_text(
            "✅ <b>Fantzo database backup created.</b>\n\n"
            f"File: <code>{path.name}</code>\n"
            f"Size: <b>{size_mb:.2f} MB</b>\n"
            f"Retention: <b>{BACKUP_RETENTION_DAYS} days</b>",
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.exception("Manual Fantzo database backup failed")
        await message.reply_text(
            f"⚠️ Backup failed: <code>{type(exc).__name__}</code>",
            parse_mode="HTML",
        )


async def backup_status_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not _is_admin(update):
        return

    message = update.effective_message
    if not message:
        return

    files = _backup_files()
    newest = files[0] if files else None
    newest_text = "none yet"
    if newest:
        newest_time = datetime.fromtimestamp(
            newest.stat().st_mtime, timezone.utc
        ).strftime("%Y-%m-%d %H:%M UTC")
        newest_text = f"{newest.name} · {newest_time}"

    last_error = _last_backup_error or "none"
    safe_error = (
        last_error.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    await message.reply_text(
        "💾 <b>FANTZO BACKUP STATUS</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"Schedule: every <b>{BACKUP_INTERVAL_SECONDS // 3600} hours</b>\n"
        f"Retention: <b>{BACKUP_RETENTION_DAYS} days</b>\n"
        f"Stored backups: <b>{len(files)}</b>\n"
        f"Newest: <code>{newest_text}</code>\n"
        f"Last error: <code>{safe_error}</code>",
        parse_mode="HTML",
    )


async def _backup_loop() -> None:
    await asyncio.sleep(BACKUP_START_DELAY_SECONDS)

    while True:
        try:
            await asyncio.to_thread(create_backup)
        except Exception:
            logger.exception("Scheduled Fantzo database backup failed")

        await asyncio.sleep(BACKUP_INTERVAL_SECONDS)


def install(application) -> None:
    global _backup_task

    application.add_handler(CommandHandler("apistatus", api_status_command))
    application.add_handler(CommandHandler("backupnow", backup_now_command))
    application.add_handler(CommandHandler("backupstatus", backup_status_command))

    if _backup_task is None or _backup_task.done():
        _backup_task = asyncio.create_task(
            _backup_loop(),
            name="fantzo-db-backup-loop",
        )

    logger.info(
        "Fantzo ops safety installed: /apistatus, DB backups every %ss, retention=%sd",
        BACKUP_INTERVAL_SECONDS,
        BACKUP_RETENTION_DAYS,
    )
