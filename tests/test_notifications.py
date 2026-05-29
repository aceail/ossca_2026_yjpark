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


def _seed_task(conn, user_id, **kw):
    now = kw.get("now") or datetime.now(timezone.utc).isoformat()
    updated = kw.get("updated_at") or now
    cur = conn.execute(
        "INSERT INTO Task (user_id, title, deadline_at, folder_path, status, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, kw.get("title", "T"), kw.get("deadline_at"),
         kw.get("folder_path"), kw.get("status", "open"), now, updated),
    )
    conn.commit()
    return cur.lastrowid


def _seed_prefs(conn, user_id, prefs):
    import json as _j
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO UserMemory (user_id, key, value, salience, source, "
        "created_at, updated_at) VALUES (?, ?, ?, 1, 'settings', ?, ?)",
        (user_id, "notification_prefs", _j.dumps(prefs), now, now),
    )
    conn.commit()


class TestComputeDueNotifications(unittest.TestCase):
    def test_imminent_deadline_triggers(self):
        from pipeline.notifications import compute_due_notifications
        conn, uid = _setup()
        now = datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc)
        _seed_task(conn, uid, title="발표",
                   deadline_at=(now + timedelta(days=1)).isoformat())
        out = compute_due_notifications(conn, uid, now=now)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["kind"], "deadline")
        self.assertIn("발표", out[0]["title"])

    def test_distant_deadline_skipped(self):
        from pipeline.notifications import compute_due_notifications
        conn, uid = _setup()
        now = datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc)
        _seed_task(conn, uid, title="먼",
                   deadline_at=(now + timedelta(days=30)).isoformat())
        out = compute_due_notifications(conn, uid, now=now)
        self.assertEqual(out, [])

    def test_momentum_stall_picks_oldest_one(self):
        from pipeline.notifications import compute_due_notifications
        conn, uid = _setup()
        now = datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc)
        for i, days in enumerate([7, 6, 8]):
            t = (now - timedelta(days=days)).isoformat()
            _seed_task(conn, uid, title=f"old{i}", now=t, updated_at=t,
                       status="open")
        out = compute_due_notifications(conn, uid, now=now)
        self.assertTrue(any(c["kind"] == "momentum" for c in out))
        moms = [c for c in out if c["kind"] == "momentum"]
        self.assertEqual(len(moms), 1)
        self.assertIn("old2", moms[0]["title"])  # 8일짜리가 가장 오래됨

    def test_quiet_hours_blocks_all(self):
        from pipeline.notifications import compute_due_notifications
        conn, uid = _setup()
        _seed_prefs(conn, uid, {"quiet_start": 22, "quiet_end": 8})
        # 23:00 KST = 14:00 UTC
        now = datetime(2026, 5, 29, 14, 0, tzinfo=timezone.utc)
        _seed_task(conn, uid, title="x",
                   deadline_at=(now + timedelta(days=1)).isoformat())
        out = compute_due_notifications(conn, uid, now=now)
        self.assertEqual(out, [])

    def test_max_per_day_cap(self):
        from pipeline.notifications import compute_due_notifications
        conn, uid = _setup()
        _seed_prefs(conn, uid, {"max_per_day": 1})
        now = datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc)
        for i in range(3):
            _seed_task(conn, uid, title=f"t{i}",
                       deadline_at=(now + timedelta(days=1, hours=i)).isoformat())
        out = compute_due_notifications(conn, uid, now=now)
        self.assertEqual(len(out), 1)

    def test_cooldown_blocks_same_key(self):
        from pipeline.notifications import compute_due_notifications
        conn, uid = _setup()
        now = datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc)
        tid = _seed_task(conn, uid, title="발표",
                         deadline_at=(now + timedelta(days=1)).isoformat())
        conn.execute(
            "INSERT INTO NotificationLog "
            "(user_id, key, kind, title, body, sent_at) "
            "VALUES (?, ?, 'deadline', 't', 'b', ?)",
            (uid, f"deadline-task-{tid}", now.isoformat()),
        )
        conn.commit()
        out = compute_due_notifications(conn, uid, now=now)
        self.assertEqual(out, [])


class TestSendPending(unittest.TestCase):
    def test_send_pending_inserts_log_and_calls_push(self):
        from pipeline.notifications import send_pending
        conn, uid = _setup()
        now = datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc)
        _seed_task(conn, uid, title="X",
                   deadline_at=(now + timedelta(days=1)).isoformat())
        called = {"n": 0, "payloads": []}
        def fake_push(c, u, p):
            called["n"] += 1
            called["payloads"].append(p)
            return 2
        res = send_pending(conn, uid, now=now, push_fn=fake_push)
        self.assertEqual(res["count"], 1)
        self.assertEqual(called["n"], 1)
        row = conn.execute("SELECT * FROM NotificationLog").fetchone()
        self.assertEqual(row["dispatched"], 2)
        self.assertEqual(called["payloads"][0]["data"]["notification_id"], row["id"])


class TestRedispatchSnoozed(unittest.TestCase):
    def test_redispatch_when_snooze_expired(self):
        from pipeline.notifications import redispatch_snoozed
        conn, uid = _setup()
        now = datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc)
        conn.execute(
            "INSERT INTO NotificationLog "
            "(user_id, key, kind, title, body, sent_at, snooze_until) "
            "VALUES (?, 'k', 'deadline', 'snz', 'b', ?, ?)",
            (uid, now.isoformat(), (now - timedelta(minutes=1)).isoformat()),
        )
        conn.commit()
        called = {"n": 0}
        def fake_push(c, u, p):
            called["n"] += 1
            return 1
        n = redispatch_snoozed(conn, now=now, push_fn=fake_push)
        self.assertEqual(n, 1)
        self.assertEqual(called["n"], 1)
        row = conn.execute(
            "SELECT snooze_until FROM NotificationLog"
        ).fetchone()
        self.assertIsNone(row["snooze_until"])


if __name__ == "__main__":
    unittest.main()
