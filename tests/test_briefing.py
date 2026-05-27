"""Sprint 22 — Daily Briefing 생성 + cooldown."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db import open_db, migrate, get_persona
from persona import seed_builtin_prompts
from pipeline.briefing import (
    LAST_KEY,
    _fallback_brief,
    collect_briefing_data,
    generate_briefing,
    should_brief,
)
from pipeline.memory import top_memories


def _setup():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = open_db(Path(tmp.name))
    migrate(conn)
    seed_builtin_prompts(conn)
    user_id = "brief-user"
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


def _seed_task(conn, user_id, **kw):
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """INSERT INTO Task (user_id, title, deadline_at, folder_path, status,
                             created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id, kw.get("title", "T"), kw.get("deadline_at"),
            kw.get("folder_path"), kw.get("status", "open"),
            now, now,
        ),
    )
    conn.commit()
    return cur.lastrowid


class TestCollectBriefingData(unittest.TestCase):
    def test_empty(self):
        conn, user_id = _setup()
        d = collect_briefing_data(conn, user_id)
        self.assertEqual(d["open_count"], 0)
        self.assertEqual(d["overdue"], [])

    def test_classifies_imminent_and_overdue(self):
        conn, user_id = _setup()
        now = datetime(2026, 5, 27, tzinfo=timezone.utc)
        _seed_task(conn, user_id, title="늦은", deadline_at=(now - timedelta(days=1)).isoformat())
        _seed_task(conn, user_id, title="내일", deadline_at=(now + timedelta(days=1)).isoformat())
        _seed_task(conn, user_id, title="먼", deadline_at=(now + timedelta(days=30)).isoformat())
        _seed_task(conn, user_id, title="무기한")
        d = collect_briefing_data(conn, user_id, now=now)
        self.assertEqual([t["title"] for t in d["overdue"]], ["늦은"])
        self.assertEqual([t["title"] for t in d["imminent"]], ["내일"])
        self.assertEqual(d["open_count"], 4)
        self.assertEqual(d["no_deadline_count"], 1)


class TestShouldBrief(unittest.TestCase):
    def test_true_when_no_history(self):
        conn, user_id = _setup()
        self.assertTrue(should_brief(conn, user_id))

    def test_false_when_already_today(self):
        conn, user_id = _setup()
        generate_briefing(conn, user_id)
        self.assertFalse(should_brief(conn, user_id))


class TestFallbackBrief(unittest.TestCase):
    def test_no_tasks(self):
        s = _fallback_brief({
            "today": "2026-05-27", "open_count": 0,
            "overdue": [], "imminent": [], "progressed_titles": [],
            "no_deadline_count": 0,
        })
        self.assertIn("오늘", s)
        self.assertIn("부담 없어", s)

    def test_with_overdue(self):
        s = _fallback_brief({
            "today": "2026-05-27", "open_count": 1,
            "overdue": [{"title": "발표"}], "imminent": [],
            "progressed_titles": [], "no_deadline_count": 0,
        })
        self.assertIn("⏰", s)
        self.assertIn("발표", s)


class TestGenerateBriefing(unittest.TestCase):
    def test_inserts_assistant_message(self):
        conn, user_id = _setup()
        result = generate_briefing(conn, user_id)
        self.assertTrue(result["sent"])
        n = conn.execute(
            """SELECT COUNT(*) AS n FROM ChatMessage m
               JOIN ChatSession s ON s.id = m.chat_session_id
               WHERE s.user_id = ? AND m.role = 'assistant'""",
            (user_id,),
        ).fetchone()["n"]
        self.assertEqual(n, 1)

    def test_records_cooldown(self):
        conn, user_id = _setup()
        generate_briefing(conn, user_id)
        memos = top_memories(conn, user_id, limit=10)
        self.assertTrue(any(m["key"] == LAST_KEY for m in memos))

    def test_skip_when_already_today(self):
        conn, user_id = _setup()
        generate_briefing(conn, user_id)
        result2 = generate_briefing(conn, user_id)
        self.assertFalse(result2["sent"])
        self.assertEqual(result2["reason"], "already_briefed_today")

    def test_force_bypasses_cooldown(self):
        conn, user_id = _setup()
        generate_briefing(conn, user_id)
        result2 = generate_briefing(conn, user_id, force=True)
        self.assertTrue(result2["sent"])

    def test_uses_llm_when_provided(self):
        conn, user_id = _setup()
        _seed_task(conn, user_id, title="X")
        called: dict = {"n": 0}

        def fake_llm(messages):
            called["n"] += 1
            return {"content": "📅 LLM 작성 브리핑"}

        result = generate_briefing(conn, user_id, call_fn=fake_llm)
        self.assertEqual(called["n"], 1)
        self.assertIn("LLM 작성", result["content"])

    def test_falls_back_when_llm_fails(self):
        conn, user_id = _setup()
        _seed_task(conn, user_id, title="X")

        def boom(messages):
            raise RuntimeError("ollama down")

        result = generate_briefing(conn, user_id, call_fn=boom)
        self.assertTrue(result["sent"])
        self.assertIn("오늘", result["content"])  # fallback 텍스트


if __name__ == "__main__":
    unittest.main()
