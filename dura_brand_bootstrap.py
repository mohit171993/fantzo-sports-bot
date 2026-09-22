"""DURA production branding/bootstrap layer.

Internal IBETIN module, table and environment names stay unchanged for
compatibility. Only user-visible branding/default URLs are rewritten.
"""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

ROOT = Path("/app")
DB_PATH = Path(os.getenv("DB_PATH", "/app/ibetin_bot_persistent/ibetin_bot.db"))

STATIC_REPLACEMENTS = [
    (re.compile(r"\bIBETIN\.COM\b"), "DURABET.COM"),
    (re.compile(r"\bIBETIN\b"), "DURA"),
    (re.compile(r"\bIbetin\b"), "Dura"),
    (re.compile(r"\bDURASPORTS\b"), "DURA"),
    (re.compile(r"\bDuraSports\b"), "Dura"),
    (re.compile(r"https://ibetin\.com"), "https://www.durabet.com"),
]


def replacements():
    items = list(STATIC_REPLACEMENTS)

    bot_username = os.getenv("DURA_BOT_USERNAME", "").strip().lstrip("@")
    if bot_username:
        items.extend([
            (re.compile(r"Ibtnofficialbot"), bot_username),
            (re.compile(r"ibtnofficialbot", re.I), bot_username),
        ])

    channel_url = os.getenv("DURA_CHANNEL_URL", "").strip()
    if channel_url:
        channel_suffix = channel_url.replace("https://", "").replace("http://", "")
        for old_channel in ("ibetinoffcial", "durasportsofficial"):
            items.append((re.compile(rf"https://t\.me/{old_channel}", re.I), channel_url))
            items.append((re.compile(rf"t\.me/{old_channel}", re.I), channel_suffix))
        if channel_url.startswith("https://t.me/"):
            channel_name = channel_url.rstrip("/").rsplit("/", 1)[-1]
            if channel_name:
                for old_channel in ("ibetinoffcial", "durasportsofficial"):
                    items.append((re.compile(rf"@{old_channel}", re.I), "@" + channel_name))

    return items


def patch_file(path: Path) -> bool:
    try:
        old = path.read_text(encoding="utf-8")
    except Exception:
        return False
    new = old
    for pattern, replacement in replacements():
        new = pattern.sub(replacement, new)
    if new == old:
        return False
    path.write_text(new, encoding="utf-8")
    return True


def ensure_base_schema() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                language TEXT DEFAULT 'en',
                subscribed INTEGER DEFAULT 0,
                created_at TEXT,
                last_seen TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS clicks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
                created_at TEXT
            )
            """
        )


def main() -> None:
    ensure_base_schema()

    changed = 0
    for path in ROOT.glob("*.py"):
        if path.name == Path(__file__).name:
            continue
        if patch_file(path):
            changed += 1

    os.environ.setdefault("IBETIN_HOME_URL", "https://www.durabet.com")
    os.environ.setdefault("IBETIN_MINI_APP_URL", "https://www.durabet.com")
    print(f"DURA_BRAND_BOOTSTRAP patched_files={changed}", flush=True)


if __name__ == "__main__":
    main()
