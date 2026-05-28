"""Sprint 28: Adaptive Self-Learning Loop — tendencies pipeline tests."""

from __future__ import annotations

import json
import sys
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
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


if __name__ == "__main__":
    unittest.main()
