import json
import os
import sqlite3
import urllib.parse
import urllib.request

DB_PATH = os.getenv("DB_PATH", "/app/ibetin_bot_persistent/ibetin_bot.db").strip()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()


def ensure_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS creative_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT NOT NULL,
            file_unique_id TEXT NOT NULL UNIQUE,
            media_type TEXT NOT NULL,
            width INTEGER,
            height INTEGER,
            filename TEXT DEFAULT '',
            pool TEXT NOT NULL,
            created_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )
        """
    )


def image_dimensions(data: bytes):
    if len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")

    if len(data) >= 30 and data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            i += 2
            if marker in (0xD8, 0xD9):
                continue
            if i + 2 > len(data):
                break
            seglen = int.from_bytes(data[i:i+2], "big")
            if seglen < 2 or i + seglen > len(data):
                break
            if marker in {
                0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF
            } and seglen >= 7:
                h = int.from_bytes(data[i+3:i+5], "big")
                w = int.from_bytes(data[i+5:i+7], "big")
                return w, h
            i += seglen

    if len(data) >= 30 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        kind = data[12:16]
        if kind == b"VP8X" and len(data) >= 30:
            w = 1 + int.from_bytes(data[24:27], "little")
            h = 1 + int.from_bytes(data[27:30], "little")
            return w, h
    return 0, 0


def fetch_dimensions(file_id: str):
    if not BOT_TOKEN or not file_id:
        return 0, 0
    try:
        q = urllib.parse.urlencode({"file_id": file_id})
        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?{q}", timeout=20
        ) as r:
            payload = json.loads(r.read().decode("utf-8"))
        file_path = str((payload.get("result") or {}).get("file_path") or "")
        if not file_path:
            return 0, 0
        with urllib.request.urlopen(
            f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}", timeout=30
        ) as r:
            data = r.read()
        return image_dimensions(data)
    except Exception:
        return 0, 0


def classify(width: int, height: int, current: str):
    if not width or not height:
        return current
    ratio = float(width) / max(1.0, float(height))
    if ratio >= 1.35:
        return "channel"
    if ratio <= 0.88:
        return "dm"
    return "reminder"


def main():
    if not DB_PATH:
        return
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    ensure_table(conn)

    rows = conn.execute(
        """
        SELECT id, file_id, width, height, pool
        FROM creative_assets
        WHERE active = 1
        ORDER BY id ASC
        """
    ).fetchall()

    moved = 0
    repaired_dims = 0
    for row in rows:
        width = int(row["width"] or 0)
        height = int(row["height"] or 0)
        current = str(row["pool"] or "channel").strip().lower() or "channel"

        if not width or not height:
            w, h = fetch_dimensions(str(row["file_id"] or ""))
            if w and h:
                width, height = w, h
                repaired_dims += 1

        # Preserve an explicit/manual Reminder or DM assignment. Only repair
        # assets that are still sitting in Channel.
        target = classify(width, height, current) if current == "channel" else current
        if target != current or width != int(row["width"] or 0) or height != int(row["height"] or 0):
            conn.execute(
                "UPDATE creative_assets SET pool=?, width=?, height=? WHERE id=?",
                (target, width or None, height or None, int(row["id"])),
            )
        if target != current:
            moved += 1

    conn.commit()

    # If everything is landscape and all assets still landed in Channel,
    # split the latest upload batch into Reminder so Channel and Reminder
    # rotate independently. This mirrors the practical pool separation used
    # in the IBETIN creative library; Reminder creatives do not technically
    # require a square canvas to send correctly in Telegram.
    existing = {"channel": 0, "dm": 0, "reminder": 0}
    for row in conn.execute(
        """
        SELECT pool, COUNT(*) AS c
        FROM creative_assets
        WHERE active = 1
        GROUP BY pool
        """
    ):
        existing[str(row["pool"])] = int(row["c"])

    batch_split = 0
    if existing["reminder"] == 0 and existing["channel"] >= 4:
        channel_rows = conn.execute(
            """
            SELECT id
            FROM creative_assets
            WHERE active = 1 AND pool = 'channel'
            ORDER BY id ASC
            """
        ).fetchall()
        reminder_count = len(channel_rows) // 2
        reminder_ids = [int(r["id"]) for r in channel_rows[-reminder_count:]]
        if reminder_ids:
            marks = ",".join("?" for _ in reminder_ids)
            conn.execute(
                f"UPDATE creative_assets SET pool='reminder' WHERE id IN ({marks})",
                reminder_ids,
            )
            batch_split = len(reminder_ids)
            moved += batch_split
            conn.commit()

    counts = {"channel": 0, "dm": 0, "reminder": 0}
    for row in conn.execute(
        """
        SELECT pool, COUNT(*) AS c
        FROM creative_assets
        WHERE active = 1
        GROUP BY pool
        """
    ):
        counts[str(row["pool"])] = int(row["c"])

    print(
        "DURA_CREATIVE_REPAIR "
        f"moved={moved} dims_recovered={repaired_dims} batch_split={batch_split} "
        f"channel={counts['channel']} dm={counts['dm']} reminder={counts['reminder']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
