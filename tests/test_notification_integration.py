"""Sprint 39 — push notification end-to-end."""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db import migrate, open_db

_TEMP_DBS: list[str] = []


def _open():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False); tmp.close()
    _TEMP_DBS.append(tmp.name)
    conn = open_db(Path(tmp.name)); migrate(conn)
    now_iso = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO User (id, created_at) VALUES ('u1', ?)",
        (now_iso,),
    )
    conn.commit()
    return conn


def tearDownModule():
    for p in _TEMP_DBS:
        try:
            os.unlink(p)
        except OSError:
            pass


class TestNotificationCycle(unittest.TestCase):
    def test_send_then_repeat_blocked(self):
        from pipeline.notifications import send_pending
        conn = _open()
        now = datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc)
        conn.execute(
            "INSERT INTO Task (user_id, title, deadline_at, status, "
            "created_at, updated_at) "
            "VALUES ('u1', '발표', ?, 'open', ?, ?)",
            ((now + timedelta(days=1)).isoformat(),
             now.isoformat(), now.isoformat()),
        )
        conn.commit()
        pushed = []
        def fake(c, u, p):
            pushed.append(p); return 1
        # 1차 send
        r1 = send_pending(conn, "u1", now=now, push_fn=fake)
        self.assertEqual(r1["count"], 1)
        # 같은 날 다시 시도하면 cooldown으로 0건
        r2 = send_pending(conn, "u1", now=now + timedelta(hours=2), push_fn=fake)
        self.assertEqual(r2["count"], 0)

    def test_snooze_redispatches_after_delay(self):
        from pipeline.notifications import redispatch_snoozed, send_pending
        conn = _open()
        now = datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc)
        conn.execute(
            "INSERT INTO Task (user_id, title, deadline_at, status, "
            "created_at, updated_at) "
            "VALUES ('u1','X', ?, 'open', ?, ?)",
            ((now + timedelta(days=1)).isoformat(),
             now.isoformat(), now.isoformat()),
        )
        conn.commit()
        sent = []
        def fake(c, u, p):
            sent.append(p); return 1
        res = send_pending(conn, "u1", now=now, push_fn=fake)
        nid = res["sent"][0]["id"]
        conn.execute(
            "UPDATE NotificationLog SET snooze_until = ? WHERE id = ?",
            ((now + timedelta(minutes=30)).isoformat(), nid),
        )
        conn.commit()
        later = now + timedelta(minutes=31)
        n = redispatch_snoozed(conn, now=later, push_fn=fake)
        self.assertEqual(n, 1)
        self.assertEqual(len(sent), 2)


if __name__ == "__main__":
    unittest.main()
