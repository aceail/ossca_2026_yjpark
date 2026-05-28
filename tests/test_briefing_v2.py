"""Sprint 31 — Smart Briefing 2.0: momentum/tendencies/RAG signals."""

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
from pipeline.briefing import (
    TONE_LINES,
    _compute_momentum,
    _fallback_brief,
    _render_brief_lines,
    build_briefing_prompt,
    collect_briefing_data,
    generate_briefing,
)


def _setup():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = open_db(Path(tmp.name))
    migrate(conn)
    user_id = "brief2-user"
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO User (id, created_at, last_seen_at) VALUES (?, ?, ?)",
        (user_id, now, now),
    )
    conn.commit()
    return conn, user_id


def _seed_task(conn, user_id, **kw):
    now = kw.get("now") or datetime.now(timezone.utc).isoformat()
    updated = kw.get("updated_at") or now
    cur = conn.execute(
        """INSERT INTO Task (user_id, title, deadline_at, folder_path, status,
                             created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id, kw.get("title", "T"), kw.get("deadline_at"),
            kw.get("folder_path"), kw.get("status", "open"),
            now, updated,
        ),
    )
    conn.commit()
    return cur.lastrowid


def _seed_chat_session(conn, user_id):
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """INSERT INTO ChatSession (user_id, persona_id, title, created_at, updated_at)
           VALUES (?, NULL, 't', ?, ?)""",
        (user_id, now, now),
    )
    conn.commit()
    return cur.lastrowid


def _seed_chat_message(conn, sid, *, when: datetime, role="user"):
    conn.execute(
        """INSERT INTO ChatMessage (chat_session_id, role, content, created_at)
           VALUES (?, ?, 'x', ?)""",
        (sid, role, when.isoformat()),
    )
    conn.commit()


class TestComputeMomentum(unittest.TestCase):
    def test_streak_continuous(self):
        conn, user_id = _setup()
        now = datetime(2026, 5, 28, 12, 0, tzinfo=timezone.utc)
        sid = _seed_chat_session(conn, user_id)
        for delta in range(3):
            day = now - timedelta(days=delta)
            for _ in range(3):
                _seed_chat_message(conn, sid, when=day)
        m = _compute_momentum(conn, user_id, now=now)
        self.assertEqual(m["streak_days"], 3)
        self.assertIsNotNone(m["last_active_date"])

    def test_streak_broken_yesterday(self):
        conn, user_id = _setup()
        now = datetime(2026, 5, 28, 12, 0, tzinfo=timezone.utc)
        sid = _seed_chat_session(conn, user_id)
        for _ in range(3):
            _seed_chat_message(conn, sid, when=now)
        m = _compute_momentum(conn, user_id, now=now)
        self.assertEqual(m["streak_days"], 1)

    def test_streak_zero_when_no_activity(self):
        conn, user_id = _setup()
        now = datetime(2026, 5, 28, 12, 0, tzinfo=timezone.utc)
        m = _compute_momentum(conn, user_id, now=now)
        self.assertEqual(m["streak_days"], 0)
        self.assertIsNone(m["last_active_date"])

    def test_streak_respects_kst_boundary(self):
        """자정 직후(05-28 00:30 KST = 05-27 15:30 UTC)에 어제 늦은 활동이
        오늘 KST 활동으로 잘못 잡히지 않아야 함."""
        conn, user_id = _setup()
        # 2026-05-28 00:30 KST = 2026-05-27 15:30 UTC — 호출 시각
        now = datetime(2026, 5, 27, 15, 30, tzinfo=timezone.utc)
        sid = _seed_chat_session(conn, user_id)
        # 2026-05-27 23:00 KST = 2026-05-27 14:00 UTC — 어제 KST 활동
        yesterday_kst_evening = datetime(2026, 5, 27, 14, 0, tzinfo=timezone.utc)
        for _ in range(3):
            _seed_chat_message(conn, sid, when=yesterday_kst_evening)
        m = _compute_momentum(conn, user_id, now=now)
        # 오늘(05-28 KST) 활동 0, 어제(05-27 KST) 활성 → streak=1 (어제만)
        # 하지만 streak는 오늘부터 거꾸로 — 오늘 비활성이면 streak=0
        self.assertEqual(m["streak_days"], 0)

    def test_stagnant_open_task_listed(self):
        conn, user_id = _setup()
        now = datetime(2026, 5, 28, 12, 0, tzinfo=timezone.utc)
        old = (now - timedelta(days=7)).isoformat()
        _seed_task(conn, user_id, title="옛 task",
                   now=old, updated_at=old, status="open")
        m = _compute_momentum(conn, user_id, now=now)
        self.assertEqual(len(m["stagnant_tasks"]), 1)
        self.assertEqual(m["stagnant_tasks"][0]["title"], "옛 task")
        self.assertGreaterEqual(m["stagnant_tasks"][0]["days"], 6)


class TestCollectBriefingDataV2(unittest.TestCase):
    def test_includes_new_keys(self):
        conn, user_id = _setup()
        d = collect_briefing_data(conn, user_id)
        self.assertIn("momentum", d)
        self.assertIn("tendencies", d)
        self.assertIn("rag_recalls", d)
        self.assertEqual(d["tendencies"], {})

    def test_rag_recalls_empty_when_no_open_tasks(self):
        conn, user_id = _setup()
        d = collect_briefing_data(conn, user_id)
        self.assertEqual(d["rag_recalls"], [])


class TestRenderBriefLines(unittest.TestCase):
    def test_skips_empty_dimensions(self):
        data = {"today": "2026-05-28", "open_count": 0}
        lines = _render_brief_lines(data)
        joined = "\n".join(lines)
        self.assertNotIn("🔥", joined)
        self.assertNotIn("⏳", joined)
        self.assertNotIn("💭", joined)
        self.assertIn("부담 없어", joined)

    def test_streak_line_when_streak_ge_2(self):
        data = {
            "today": "2026-05-28", "open_count": 2,
            "momentum": {"streak_days": 4, "stagnant_tasks": []},
        }
        lines = _render_brief_lines(data)
        self.assertTrue(any("🔥 4일" in l for l in lines))

    def test_stagnant_when_streak_zero_and_stagnant_exists(self):
        data = {
            "today": "2026-05-28", "open_count": 1,
            "momentum": {
                "streak_days": 0,
                "stagnant_tasks": [{"title": "보고서", "days": 8}],
            },
        }
        lines = _render_brief_lines(data)
        self.assertTrue(any("보고서" in l and "8일" in l for l in lines))

    def test_recall_line_when_recalls_exist(self):
        data = {
            "today": "2026-05-28", "open_count": 1,
            "rag_recalls": [{"kind": "chat", "content": "예전에 비슷한 마감"}],
        }
        lines = _render_brief_lines(data)
        self.assertTrue(any("💭" in l and "예전에" in l for l in lines))

    def test_tone_savage_applied(self):
        data = {
            "today": "2026-05-28", "open_count": 3,
            "overdue": [{"title": "X"}],
            "tendencies": {"tone_preference": "savage"},
        }
        lines = _render_brief_lines(data)
        self.assertEqual(lines[-1], TONE_LINES["savage"])

    def test_tone_defaults_quiet(self):
        data = {
            "today": "2026-05-28", "open_count": 2,
            "overdue": [{"title": "X"}],
        }
        lines = _render_brief_lines(data)
        self.assertEqual(lines[-1], TONE_LINES["quiet"])


class TestGenerateBriefingIntegration(unittest.TestCase):
    def test_prompt_carries_all_v2_signals(self):
        conn, user_id = _setup()
        _seed_task(conn, user_id, title="작업1", status="open")
        # Seed tendencies via raw memory write
        conn.execute(
            """INSERT INTO UserMemory (user_id, key, value, salience, source,
                                       created_at, updated_at)
               VALUES (?, 'adaptive_tendencies',
                       '{"tone_preference":"savage","peak_hour":15}', 1,
                       'adaptive', ?, ?)""",
            (user_id, "2026-05-28", "2026-05-28"),
        )
        conn.commit()

        captured: dict = {"prompt": None}

        def fake_llm(messages):
            captured["prompt"] = messages[0]["content"]
            return {"content": "📅 LLM brief"}

        result = generate_briefing(conn, user_id, call_fn=fake_llm)
        self.assertTrue(result["sent"])
        prompt = captured["prompt"]
        self.assertIsNotNone(prompt)
        self.assertIn("savage", prompt)
        self.assertIn("momentum", prompt)
        self.assertIn("rag_recalls", prompt)
        self.assertIn("tendencies", prompt)


class TestBuildBriefingPrompt(unittest.TestCase):
    def test_tone_directive_present(self):
        prompt = build_briefing_prompt({"tendencies": {"tone_preference": "witty"}})
        self.assertIn("witty", prompt)

    def test_default_tone_when_missing(self):
        prompt = build_briefing_prompt({})
        self.assertIn("quiet", prompt)


if __name__ == "__main__":
    unittest.main()
