"""Safe, optional match destinations for verified IBETIN campaign leads.

Campaign links remain short Telegram /start payloads. Operators may map an
approved campaign ID to a provider match key in IBETIN_MATCH_CAMPAIGNS, e.g.
{"matchday_oct_01":"international_match_123"}. No URL from a deep link or
environment value is ever used as a destination.
"""

import json
import os
import re
from urllib.parse import urlencode


_CAMPAIGN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_MATCH_KEY = re.compile(r"^[A-Za-z0-9_.:\-]{3,180}$")


def valid_match_key(value: str) -> bool:
    return bool(_MATCH_KEY.fullmatch(str(value or "")))


def campaign_match_key(campaign: str, raw_mapping: str | None = None) -> str:
    campaign = str(campaign or "").strip().lower()
    if not _CAMPAIGN.fullmatch(campaign):
        return ""
    if raw_mapping is None:
        raw_mapping = os.getenv("IBETIN_MATCH_CAMPAIGNS", "")
    try:
        mapping = json.loads(raw_mapping or "{}")
    except (TypeError, ValueError):
        return ""
    if not isinstance(mapping, dict):
        return ""
    for name, value in mapping.items():
        if str(name).lower() != campaign or not isinstance(value, str):
            continue
        key = value.strip()
        return key if valid_match_key(key) else ""
    return ""


def match_url(live_line_url: str, match_key: str) -> str:
    """Add only a validated provider key to an already signed Live Line URL."""
    if not valid_match_key(match_key):
        return live_line_url
    return live_line_url + ("&" if "?" in live_line_url else "?") + urlencode(
        {"match": match_key}
    )
