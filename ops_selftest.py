import sqlite3
import tempfile
from pathlib import Path

import bot as core
import fantzo_ops as ops


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    source = root / "fantzo_test.db"
    backups = root / "backups"

    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE sample(id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO sample(value) VALUES('ok')")

    core.DB_PATH = str(source)
    ops.BACKUP_DIR = backups

    created = ops.create_backup()
    assert created.exists(), "backup file was not created"

    with sqlite3.connect(created) as conn:
        check = conn.execute("PRAGMA quick_check").fetchone()[0]
        count = conn.execute("SELECT COUNT(*) FROM sample").fetchone()[0]

    assert str(check).lower() == "ok", check
    assert count == 1, count
    assert len(list(backups.glob("fantzo_bot_*.db"))) == 1

print("Fantzo ops self-test passed: SQLite backup + integrity check OK")
