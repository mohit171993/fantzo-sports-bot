import asyncio
import logging
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

import bot_tracked as base

logger = logging.getLogger(__name__)

# Keep the restored Fantzo code intact and layer only the Live TV reliability fix.
LIVE_TV_CACHE_TTL_SECONDS = 60.0
LIVE_TV_STALE_TTL_SECONDS = 600.0

_tv_cache = None
_tv_cache_at = 0.0
_tv_cache_lock = asyncio.Lock()
_original_today_tv_matches = base._today_tv_matches


async def cached_today_tv_matches():
    """Reuse match status briefly so repeated Live TV taps do not hammer Highlightly."""
    global _tv_cache, _tv_cache_at

    now = time.monotonic()
    if _tv_cache is not None and (now - _tv_cache_at) < LIVE_TV_CACHE_TTL_SECONDS:
        return _tv_cache

    async with _tv_cache_lock:
        now = time.monotonic()
        if _tv_cache is not None and (now - _tv_cache_at) < LIVE_TV_CACHE_TTL_SECONDS:
            return _tv_cache

        try:
            result = await _original_today_tv_matches()
        except Exception:
            # If Highlightly is temporarily rate-limited, keep serving recent known status.
            if _tv_cache is not None and (now - _tv_cache_at) < LIVE_TV_STALE_TTL_SECONDS:
                logger.warning(
                    "Highlightly unavailable; using cached Live TV status (age %.1fs)",
                    now - _tv_cache_at,
                )
                return _tv_cache
            raise

        _tv_cache = result
        _tv_cache_at = time.monotonic()
        return result


def live_tv_wait_keyboard() -> InlineKeyboardMarkup:
    """Never let sports-status availability block access to Live TV itself."""
    rows = []
    url = base.sky_admin_url()

    if url:
        rows.append([
            InlineKeyboardButton(
                "▶ OPEN LIVE TV",
                web_app=WebAppInfo(url=url),
            )
        ])

    rows.extend([
        [
            InlineKeyboardButton(
                "🔄 CHECK AGAIN",
                callback_data="live_tv_status",
            ),
            InlineKeyboardButton(
                "📅 FIXTURES",
                callback_data="upcoming",
            ),
        ],
        [
            InlineKeyboardButton(
                "⬅️ BACK TO HOME",
                callback_data="back",
            )
        ],
    ])

    return InlineKeyboardMarkup(rows)


# Patch only the Live TV status data path and the waiting/error keyboard.
base._today_tv_matches = cached_today_tv_matches
base._tv_wait_keyboard = live_tv_wait_keyboard


if __name__ == "__main__":
    base.private_apk_upload.install_on_tracking_handler(base.analytics)
    base.trial_live_tv.install_on_tracking_handler(base.analytics)
    base.fantzo_live_tv.install_on_tracking_handler(base.analytics)
    base.analytics.start_tracking_server()

    logger.info(
        "Starting Fantzo Live TV reliability layer with LIVE_TV_MODE=%s",
        base.LIVE_TV_MODE,
    )

    base.app.run()
