"""DURA-only verified entry routing for Telegram campaign links.

The public ``/start`` payload is an attribution key, never a URL. Operators
explicitly map that key to Live Line or to a provider match key in
``DURA_ENTRY_MAP``. Pending destinations survive a bot restart during mobile
verification and expire after one day.
"""

import json
import logging
import os
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_CAMPAIGN = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_MATCH_KEY = re.compile(r"[A-Za-z0-9_.:-]{1,96}\Z")
_RESERVED_LIVELINE = {"verifyliveline", "liveline", "livelineverify"}
_MAX_AGE = timedelta(hours=24)


def valid_match_key(value: str) -> str:
    key = str(value or "").strip()
    return key if _MATCH_KEY.fullmatch(key) else ""


def resolve(payload: str) -> dict[str, str]:
    """Resolve only an allowlisted destination; unknown payloads use the menu."""
    campaign = str(payload or "").strip().lower()
    if not _CAMPAIGN.fullmatch(campaign):
        return {"kind": "menu", "match_key": ""}
    if campaign in _RESERVED_LIVELINE:
        return {"kind": "liveline", "match_key": ""}

    raw = os.getenv("DURA_ENTRY_MAP", "").strip()
    if not raw:
        return {"kind": "menu", "match_key": ""}
    try:
        routes = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("DURA_ENTRY_MAP is not valid JSON; using the standard menu")
        return {"kind": "menu", "match_key": ""}
    if not isinstance(routes, dict):
        return {"kind": "menu", "match_key": ""}

    value = routes.get(campaign)
    if value == "liveline":
        return {"kind": "liveline", "match_key": ""}
    if isinstance(value, dict) and value.get("kind") == "match":
        key = valid_match_key(value.get("match_key", ""))
        if key:
            return {"kind": "match", "match_key": key}
    return {"kind": "menu", "match_key": ""}


def _connect():
    path = os.getenv("DB_PATH", "/app/ibetin_bot.db").strip() or "/app/ibetin_bot.db"
    conn = sqlite3.connect(path, timeout=2)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS dura_pending_entry (
             user_id INTEGER PRIMARY KEY,
             kind TEXT NOT NULL,
             match_key TEXT NOT NULL DEFAULT '',
             requested_at TEXT NOT NULL
        )"""
    )
    return conn


def remember(user_id: int, payload: str) -> dict[str, str]:
    """Replace an older handoff so a plain /start clears stale campaign intent."""
    entry = resolve(payload)
    try:
        with closing(_connect()) as conn, conn:
            if entry["kind"] == "menu":
                conn.execute("DELETE FROM dura_pending_entry WHERE user_id=?", (int(user_id),))
            else:
                conn.execute(
                    """INSERT INTO dura_pending_entry(user_id, kind, match_key, requested_at)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(user_id) DO UPDATE SET
                         kind=excluded.kind, match_key=excluded.match_key,
                         requested_at=excluded.requested_at""",
                    (int(user_id), entry["kind"], entry["match_key"],
                     datetime.now(timezone.utc).isoformat()),
                )
    except (OSError, sqlite3.Error):
        logger.exception("Could not save DURA entry handoff for user_id=%s", user_id)
    return entry


def consume(user_id: int) -> dict[str, str]:
    """Return a recent, valid handoff once after contact verification."""
    entry = {"kind": "menu", "match_key": ""}
    try:
        with closing(_connect()) as conn, conn:
            row = conn.execute(
                "SELECT kind, match_key, requested_at FROM dura_pending_entry WHERE user_id=?",
                (int(user_id),),
            ).fetchone()
            conn.execute("DELETE FROM dura_pending_entry WHERE user_id=?", (int(user_id),))
        if row:
            requested = datetime.fromisoformat(row["requested_at"])
            age = datetime.now(timezone.utc) - requested if requested.tzinfo else None
            if age is not None and timedelta(0) <= age <= _MAX_AGE:
                kind, key = str(row["kind"]), valid_match_key(row["match_key"])
                if kind == "liveline" or (kind == "match" and key):
                    entry = {"kind": kind, "match_key": key}
    except (OSError, sqlite3.Error, ValueError, TypeError):
        logger.exception("Could not read DURA entry handoff for user_id=%s", user_id)
    return entry
