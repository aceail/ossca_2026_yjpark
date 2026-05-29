"""Sprint 39 — Smart Push Notifications."""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db import migrate, open_db


def _setup():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = open_db(Path(tmp.name))
    migrate(conn)
    user_id = "n-user"
    now_iso = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO User (id, created_at, last_seen_at) VALUES (?, ?, ?)",
        (user_id, now_iso, now_iso),
    )
    conn.commit()
    return conn, user_id


class TestMigration018(unittest.TestCase):
    def test_notification_log_table_created(self):
        conn, _ = _setup()
        row = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='NotificationLog'"
        ).fetchone()
        self.assertIsNotNone(row)

    def test_unique_dedup_index_blocks_same_day_duplicate(self):
        conn, uid = _setup()
        now = "2026-05-29T10:00:00+00:00"
        same_day = "2026-05-29T15:00:00+00:00"
        conn.execute(
            "INSERT INTO NotificationLog "
            "(user_id, key, kind, title, body, sent_at) "
            "VALUES (?, 'k1', 'deadline', 't', 'b', ?)",
            (uid, now),
        )
        conn.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO NotificationLog "
                "(user_id, key, kind, title, body, sent_at) "
                "VALUES (?, 'k1', 'deadline', 't', 'b', ?)",
                (uid, same_day),
            )


if __name__ == "__main__":
    unittest.main()
