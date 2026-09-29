"""Fantzo-only checks for metadata attached to uploaded creatives."""

import re


_FOREIGN_BRAND = re.compile(
    r"(?<![a-z0-9])(?:ibetin[a-z]*|ibtn|betroxy[a-z]*|durabet[a-z]*|dura)(?![a-z0-9])",
    re.IGNORECASE,
)


def has_foreign_brand(text: str) -> bool:
    return bool(_FOREIGN_BRAND.search(str(text or "")))
