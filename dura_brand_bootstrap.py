"""DURA production branding bootstrap.

Keeps the proven IBETIN internal module/database names unchanged while
rebranding user-visible copy and website defaults in the isolated DURA
container before the application imports the runtime.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path("/app")

STATIC_REPLACEMENTS = [
    (re.compile(r"\bIBETIN\.COM\b"), "DURABET.COM"),
    (re.compile(r"\bIBETIN\b"), "DURA"),
    (re.compile(r"\bIbetin\b"), "Dura"),
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
        items.append((re.compile(r"https://t\.me/ibetinoffcial", re.I), channel_url))
        if channel_url.startswith("https://t.me/"):
            channel_name = channel_url.rstrip("/").rsplit("/", 1)[-1]
            if channel_name:
                items.append((re.compile(r"@ibetinoffcial", re.I), "@" + channel_name))

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


def main() -> None:
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
