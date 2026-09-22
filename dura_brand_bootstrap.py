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

REPLACEMENTS = [
    (re.compile(r"\bIBETIN\.COM\b"), "DURABET.COM"),
    (re.compile(r"\bIBETIN\b"), "DURA"),
    (re.compile(r"\bIbetin\b"), "Dura"),
    (re.compile(r"https://ibetin\.com"), "https://www.durabet.com"),
]

# Do not touch identifiers like IBETIN_HOME_URL or ibetin_leads: word
# boundaries intentionally leave those internal compatibility names intact.
def patch_file(path: Path) -> bool:
    try:
        old = path.read_text(encoding="utf-8")
    except Exception:
        return False
    new = old
    for pattern, replacement in REPLACEMENTS:
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

    # DURA uses durabet.com for its Mini App/site destination.
    os.environ.setdefault("IBETIN_HOME_URL", "https://www.durabet.com")
    os.environ.setdefault("IBETIN_MINI_APP_URL", "https://www.durabet.com")
    print(f"DURA_BRAND_BOOTSTRAP patched_files={changed}", flush=True)


if __name__ == "__main__":
    main()
