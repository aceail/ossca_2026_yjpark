"""Sprint 28: Adaptive Self-Learning Loop — tendencies pipeline tests."""

from __future__ import annotations

import json
import sys
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db import open_db, migrate
from persona import seed_builtin_prompts


def _fresh_conn() -> sqlite3.Connection:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = open_db(Path(tmp.name))
    migrate(conn)
    seed_builtin_prompts(conn)
    return conn


def _insert_user(conn: sqlite3.Connection, user_id: str) -> None:
    conn.execute(
        "INSERT INTO User (id, created_at) VALUES (?, ?)",
        (user_id, "2026-05-01T00:00:00Z"),
    )
    conn.commit()


class TestExtractFeaturesShape(unittest.TestCase):
    def test_no_data_returns_dict_with_nulls(self):
        from pipeline.tendencies import extract_features

        conn = _fresh_conn()
        _insert_user(conn, "u-empty")
        now = datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc)
        out = extract_features(conn, "u-empty", now=now)
        self.assertIsInstance(out, dict)
        # All defined keys exist even when there's no data.
        for k in (
            "chat_count_7d",
            "avg_deadline_buffer_days",
            "peak_hour_histogram",
            "sharp_then_progress_ratio",
            "gentle_then_progress_ratio",
            "snapshot_growth_pattern",
        ):
            self.assertIn(k, out)


class TestDeadlineBuffer(unittest.TestCase):
    def setUp(self):
        self.conn = _fresh_conn()
        _insert_user(self.conn, "u-buf")
        # 3 closed tasks. last_followup_at vs updated_at gap → buffer.
        now = datetime(2026, 5, 28, tzinfo=timezone.utc)
        for i, (status, last_fu_offset, closed_offset) in enumerate([
            ("done", 5, 1),       # last followup 5d ago, closed 1d ago → buf=4
            ("done", 7, 5),       # buf=2
            ("abandoned", 4, 1),  # buf=3
        ]):
            last_fu = (now - timedelta(days=last_fu_offset)).isoformat()
            closed_at = (now - timedelta(days=closed_offset)).isoformat()
            deadline = (now + timedelta(days=10)).isoformat()
            self.conn.execute(
                "INSERT INTO Task (user_id, title, deadline_at, status, "
                "created_at, updated_at, last_followup_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("u-buf", f"t{i}", deadline, status,
                 last_fu, closed_at, last_fu),
            )
        self.conn.commit()
        self.now = now

    def test_avg_deadline_buffer_days_mean_of_closed_tasks(self):
        from pipeline.tendencies import extract_features
        out = extract_features(self.conn, "u-buf", now=self.now)
        self.assertAlmostEqual(out["avg_deadline_buffer_days"], 3.0, places=1)

    def test_below_three_closed_returns_none(self):
        from pipeline.tendencies import extract_features
        _insert_user(self.conn, "u-buf-thin")
        out = extract_features(self.conn, "u-buf-thin", now=self.now)
        self.assertIsNone(out["avg_deadline_buffer_days"])


class TestChatStatistics(unittest.TestCase):
    def setUp(self):
        self.conn = _fresh_conn()
        _insert_user(self.conn, "u-chat")
        # 5 chat messages in the last 7 days (KST hours 13–15).
        now = datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc)
        sess = self.conn.execute(
            "INSERT INTO ChatSession (user_id, persona_id, created_at, updated_at)"
            " VALUES (?, NULL, ?, ?)",
            ("u-chat", now.isoformat(), now.isoformat()),
        ).lastrowid
        # KST = UTC+9. 13–15 KST = 04–06 UTC.
        for i, h in enumerate([4, 5, 5, 5, 6]):
            t = (now - timedelta(days=i, hours=0, minutes=0)).replace(hour=h)
            self.conn.execute(
                "INSERT INTO ChatMessage (chat_session_id, role, content, created_at)"
                " VALUES (?, 'user', ?, ?)",
                (sess, f"msg{i}", t.isoformat()),
            )
        self.conn.commit()
        self.now = now

    def test_chat_count_7d_counts_recent_user_messages(self):
        from pipeline.tendencies import extract_features
        out = extract_features(self.conn, "u-chat", now=self.now)
        self.assertEqual(out["chat_count_7d"], 5)

    def test_peak_hour_histogram_is_24_buckets_kst(self):
        from pipeline.tendencies import extract_features
        out = extract_features(self.conn, "u-chat", now=self.now)
        hist = out["peak_hour_histogram"]
        self.assertIsInstance(hist, list)
        self.assertEqual(len(hist), 24)
        # 4 UTC = 13 KST, 5 UTC = 14 KST, 6 UTC = 15 KST.
        self.assertEqual(hist[13], 1)
        self.assertEqual(hist[14], 3)
        self.assertEqual(hist[15], 1)
        self.assertEqual(sum(hist), 5)


if __name__ == "__main__":
    unittest.main()
