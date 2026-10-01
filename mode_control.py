"""Persistent, bot-local mode state for the four brand bots.

This library does not control Telegram Ads. A Full switch may be made while
ads are running. Integration must gate every bot-owned public route and
outgoing message; external betting websites remain outside bot control.
"""

from __future__ import annotations

import sqlite3
import posixpath
import os
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone


LIVE_LINE = "liveline"
FULL = "full"
BRANDS = frozenset({"fantzo", "ibetin", "dura", "betroxy"})
PERSISTENT_DB_ROOT = "/data"


def is_persistent_mode_path(db_path: str) -> bool:
    """Only the Railway volume can retain a clean switch after a restart."""
    if not db_path or not db_path.startswith("/"):
        return False
    normalized = posixpath.normpath(db_path)
    return (normalized != PERSISTENT_DB_ROOT
            and posixpath.commonpath((normalized, PERSISTENT_DB_ROOT))
            == PERSISTENT_DB_ROOT)


def is_persistent_volume_mounted(
    root: str = PERSISTENT_DB_ROOT,
    mountinfo_path: str = "/proc/self/mountinfo",
) -> bool:
    """Require a real mount at the Railway volume path, not a plain folder."""
    root = posixpath.normpath(root)
    try:
        with open(mountinfo_path, encoding="utf-8", errors="replace") as info:
            for line in info:
                fields = line.split(" - ", 1)[0].split()
                if len(fields) >= 5 and posixpath.normpath(fields[4]) == root:
                    return True
        return False
    except OSError:
        # Non-Linux staging environments may lack /proc; ismount still
        # distinguishes a mounted filesystem from an ordinary directory.
        return os.path.ismount(root)


@dataclass(frozen=True)
class ModeState:
    mode: str
    revision: int
    updated_at: str


class ModeStore:
    def __init__(self, db_path: str, brand: str):
        if brand not in BRANDS:
            raise ValueError("Unknown bot brand")
        self.db_path = db_path
        self.brand = brand
        self._ensure_table()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=20)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_table(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS bot_mode ("
                "brand TEXT PRIMARY KEY, mode TEXT NOT NULL, "
                "revision INTEGER NOT NULL, updated_at TEXT NOT NULL)"
            )

    def state(self) -> ModeState:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT mode,revision,updated_at FROM bot_mode WHERE brand=?",
                (self.brand,),
            ).fetchone()
        if row is None:
            # Preserve the bot's existing behavior during a code release. The
            # operator must explicitly turn on Live Line mode.
            return ModeState(FULL, 0, "")
        mode = str(row["mode"])
        if mode not in {LIVE_LINE, FULL}:
            raise RuntimeError("Invalid persisted mode")
        return ModeState(mode, int(row["revision"]), str(row["updated_at"]))

    def switch(self, mode: str) -> ModeState:
        if mode not in {LIVE_LINE, FULL}:
            raise ValueError("Unsupported mode")
        now = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT revision FROM bot_mode WHERE brand=?", (self.brand,)
            ).fetchone()
            revision = (int(row[0]) if row else 0) + 1
            conn.execute(
                "INSERT INTO bot_mode (brand,mode,revision,updated_at) "
                "VALUES (?,?,?,?) ON CONFLICT(brand) DO UPDATE SET "
                "mode=excluded.mode,revision=excluded.revision,"
                "updated_at=excluded.updated_at",
                (self.brand, mode, revision, now),
            )
        return ModeState(mode, revision, now)



def parse_admin_mode_request(
    user_id: int, admin_user_id, args: list[str]
) -> str | None:
    """None means the caller gets no response, including invalid admins.

    ``admin_user_id`` is one admin id or a collection of admin ids.
    """
    if isinstance(admin_user_id, (set, frozenset, list, tuple)):
        admins = {int(a) for a in admin_user_id if a}
    else:
        admins = {int(admin_user_id)} if admin_user_id else set()
    if not admins or user_id not in admins:
        return None
    if not args:
        return "status"
    if len(args) != 1 or args[0].lower() not in {LIVE_LINE, FULL, "status"}:
        return "usage"
    return args[0].lower()


def http_route(mode: str, method: str, path: str) -> str:
    """Return pass/scores/scores_api/scores_auth/redirect/deny for bot routes.

    In Live Line mode the runtime lets "redirect"/"deny" requests through
    only for a signed, verified user; everyone else is sent to the public
    scores page. The provider webhook and relay retain the current feed.
    """
    if mode == FULL:
        return "pass"
    if mode != LIVE_LINE:
        return "deny"
    method = method.upper()
    if method == "GET" and path == "/scores":
        return "scores"
    if method == "GET" and path == "/scores/api":
        return "scores_api"
    if method == "GET" and path in {
        "/health", "/report-metrics",
    }:
        return "pass"
    if method == "POST" and path.rstrip("/") == "/roanuz/match/feed/v1":
        return "pass"
    if method == "POST" and path == "/scores/auth":
        return "scores_auth"
    return "redirect" if method == "GET" else "deny"
