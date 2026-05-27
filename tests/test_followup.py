"""Wave 3 — Tone matrix + dispatch_due_followups integration."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db import open_db, migrate, get_persona  # noqa: E402
from persona import seed_builtin_prompts  # noqa: E402
from pipeline.followup import dispatch_due_followups, _days_until  # noqa: E402
from pipeline.followup_tone import decide_followup  # noqa: E402


# ────────────────────────────────────────────────────────────────────
# Tone matrix
# ────────────────────────────────────────────────────────────────────


class TestToneMatrix(unittest.TestCase):
    def test_high_signal_skips(self):
        d = decide_followup(
            title="T", days_until_deadline=1, last_followup_hours_ago=None,
            progressed=False, signal_level="high",
        )
        self.assertFalse(d.should_send)

    def test_elevated_forces_quiet(self):
        d = decide_followup(
            title="T", days_until_deadline=0, last_followup_hours_ago=None,
            progressed=False, signal_level="elevated",
        )
        self.assertTrue(d.should_send)
        self.assertEqual(d.tone, "quiet")

    def test_d_minus_3_witty_when_normal(self):
        d = decide_followup(
            title="T", days_until_deadline=3, last_followup_hours_ago=None,
            progressed=True, signal_level="normal",
        )
        self.assertTrue(d.should_send)
        self.assertEqual(d.tone, "witty")
        self.assertEqual(d.cooldown_hours, 24)

    def test_d_minus_1_sharp_progressed(self):
        d = decide_followup(
            title="T", days_until_deadline=1, last_followup_hours_ago=None,
            progressed=True, signal_level="normal",
        )
        self.assertEqual(d.tone, "sharp")
        self.assertEqual(d.cooldown_hours, 6)

    def test_d_zero_savage_when_stuck(self):
        d = decide_followup(
            title="T", days_until_deadline=0, last_followup_hours_ago=None,
            progressed=False, signal_level="normal",
        )
        self.assertEqual(d.tone, "savage")
        self.assertEqual(d.cooldown_hours, 2)

    def test_d_zero_sharp_when_progressed(self):
        d = decide_followup(
            title="T", days_until_deadline=0, last_followup_hours_ago=None,
            progressed=True, signal_level="normal",
        )
        self.assertEqual(d.tone, "sharp")

    def test_cooldown_blocks(self):
        d = decide_followup(
            title="T", days_until_deadline=1, last_followup_hours_ago=2.0,
            progressed=False, signal_level="normal",
        )
        self.assertFalse(d.should_send)

    def test_far_future_quiet_skip(self):
        d = decide_followup(
            title="T", days_until_deadline=10, last_followup_hours_ago=None,
            progressed=False, signal_level="normal",
        )
        self.assertFalse(d.should_send)

    def test_no_deadline_daily_quiet_or_witty(self):
        d = decide_followup(
            title="T", days_until_deadline=None, last_followup_hours_ago=None,
            progressed=False, signal_level="normal",
        )
        self.assertTrue(d.should_send)
        self.assertIn(d.tone, ("witty", "quiet"))

    def test_persona_quiet_overrides(self):
        d = decide_followup(
            title="T", days_until_deadline=0, last_followup_hours_ago=None,
            progressed=False, signal_level="normal",
            persona_tone="Quiet",
        )
        self.assertEqual(d.tone, "quiet")

    def test_past_deadline_quiet_recap(self):
        d = decide_followup(
            title="T", days_until_deadline=-1, last_followup_hours_ago=None,
            progressed=False, signal_level="normal",
        )
        self.assertEqual(d.tone, "quiet")
        self.assertIn("지났", d.message)


# ────────────────────────────────────────────────────────────────────
# _days_until utility
# ────────────────────────────────────────────────────────────────────


class TestDaysUntil(unittest.TestCase):
    def test_one_day_in_future(self):
        now = datetime(2026, 5, 27, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(_days_until("2026-05-28T00:00:00+00:00", now), 1)

    def test_today(self):
        now = datetime(2026, 5, 27, 1, 0, tzinfo=timezone.utc)
        self.assertEqual(_days_until("2026-05-27T23:00:00+00:00", now), 0)

    def test_past(self):
        now = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(_days_until("2026-05-26T00:00:00+00:00", now), -2)

    def test_none(self):
        self.assertIsNone(_days_until(None, datetime.now(timezone.utc)))


# ────────────────────────────────────────────────────────────────────
# dispatch_due_followups
# ────────────────────────────────────────────────────────────────────


def _setup_db_with_user() -> tuple[sqlite3.Connection, str]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = open_db(Path(tmp.name))
    migrate(conn)
    seed_builtin_prompts(conn)
    user_id = "fu-user"
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO User (id, created_at, last_seen_at) VALUES (?, ?, ?)",
        (user_id, now, now),
    )
    persona = get_persona(conn, "내일의 나")
    conn.execute(
        """INSERT OR IGNORE INTO UserProfile
           (user_id, slots_json, completion_percent, active_persona_id, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, "{}", 0.0, persona["id"] if persona else None, now),
    )
    conn.commit()
    return conn, user_id


def _make_task(conn, user_id, *, deadline_at=None, last_followup_at=None) -> int:
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """INSERT INTO Task (user_id, title, deadline_at, last_followup_at, status,
                             created_at, updated_at)
           VALUES (?, ?, ?, ?, 'open', ?, ?)""",
        (user_id, "발표자료", deadline_at, last_followup_at, now, now),
    )
    conn.commit()
    return cur.lastrowid


class TestDispatch(unittest.TestCase):
    def test_due_d_minus_1_sends(self):
        conn, user_id = _setup_db_with_user()
        now = datetime(2026, 5, 27, 0, 0, tzinfo=timezone.utc)
        deadline = (now + timedelta(days=1, hours=1)).isoformat()
        _make_task(conn, user_id, deadline_at=deadline)
        sent = dispatch_due_followups(conn, now=now)
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["tone"], "sharp")
        # message stored in ChatMessage
        n = conn.execute("SELECT COUNT(*) AS n FROM ChatMessage").fetchone()["n"]
        self.assertEqual(n, 1)

    def test_too_far_skip(self):
        conn, user_id = _setup_db_with_user()
        now = datetime(2026, 5, 27, 0, 0, tzinfo=timezone.utc)
        deadline = (now + timedelta(days=10)).isoformat()
        _make_task(conn, user_id, deadline_at=deadline)
        self.assertEqual(dispatch_due_followups(conn, now=now), [])

    def test_recent_followup_blocked_by_cooldown(self):
        conn, user_id = _setup_db_with_user()
        now = datetime(2026, 5, 27, 0, 0, tzinfo=timezone.utc)
        deadline = (now + timedelta(days=1, hours=1)).isoformat()  # D-1 → 6h cooldown
        last = (now - timedelta(hours=2)).isoformat()
        _make_task(conn, user_id, deadline_at=deadline, last_followup_at=last)
        self.assertEqual(dispatch_due_followups(conn, now=now), [])

    def test_updates_last_followup_at(self):
        conn, user_id = _setup_db_with_user()
        now = datetime(2026, 5, 27, 0, 0, tzinfo=timezone.utc)
        deadline = (now + timedelta(days=1, hours=1)).isoformat()
        tid = _make_task(conn, user_id, deadline_at=deadline)
        dispatch_due_followups(conn, now=now)
        row = conn.execute(
            "SELECT last_followup_at FROM Task WHERE id = ?", (tid,)
        ).fetchone()
        self.assertIsNotNone(row["last_followup_at"])

    def test_creates_session_if_none(self):
        conn, user_id = _setup_db_with_user()
        now = datetime(2026, 5, 27, 0, 0, tzinfo=timezone.utc)
        deadline = (now + timedelta(days=1, hours=1)).isoformat()
        _make_task(conn, user_id, deadline_at=deadline)
        # 처음엔 세션 0개
        before = conn.execute("SELECT COUNT(*) AS n FROM ChatSession").fetchone()["n"]
        self.assertEqual(before, 0)
        dispatch_due_followups(conn, now=now)
        after = conn.execute("SELECT COUNT(*) AS n FROM ChatSession").fetchone()["n"]
        self.assertEqual(after, 1)

    def test_high_signal_user_no_dispatch(self):
        conn, user_id = _setup_db_with_user()
        now = datetime(2026, 5, 27, 0, 0, tzinfo=timezone.utc)
        # 자기비난 누적 → high
        for _ in range(8):
            conn.execute(
                "INSERT INTO AvoidanceSession (user_id, avoidance_input, created_at) VALUES (?, ?, ?)",
                (user_id, "한심 " * 2, now.isoformat()),
            )
        conn.commit()
        deadline = (now + timedelta(hours=12)).isoformat()
        _make_task(conn, user_id, deadline_at=deadline)
        self.assertEqual(dispatch_due_followups(conn, now=now), [])


if __name__ == "__main__":
    unittest.main()
