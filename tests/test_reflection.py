"""Sprint 21 — Weekly self-reflection."""

from __future__ import annotations

import json
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
from pipeline.memory import top_memories, upsert_memory
from pipeline.reflection import (
    LAST_KEY,
    build_reflection_prompt,
    collect_evidence,
    parse_reflection_response,
    run_reflection,
    run_reflection_for_all,
)


def _setup():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = open_db(Path(tmp.name))
    migrate(conn)
    seed_builtin_prompts(conn)
    user_id = "ref-user"
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


def _seed_chat(conn, user_id, content="발표자료 막막해"):
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """INSERT INTO ChatSession (user_id, persona_id, created_at, updated_at)
           VALUES (?, NULL, ?, ?)""",
        (user_id, now, now),
    )
    sid = cur.lastrowid
    conn.execute(
        """INSERT INTO ChatMessage (chat_session_id, role, content, created_at)
           VALUES (?, 'user', ?, ?)""",
        (sid, content, now),
    )
    conn.commit()


def _seed_task(conn, user_id, **kw):
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO Task (user_id, title, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, kw.get("title", "T"), kw.get("status", "open"), now, now),
    )
    conn.commit()


# ────────────────────────────────────────────────────────────────────
# Parsing
# ────────────────────────────────────────────────────────────────────


class TestParseReflection(unittest.TestCase):
    def test_valid_response(self):
        raw = json.dumps({"memories": [{"key": "k", "value": "v"}]}, ensure_ascii=False)
        out = parse_reflection_response(raw)
        self.assertEqual(out, [{"key": "k", "value": "v"}])

    def test_empty_memories(self):
        self.assertEqual(parse_reflection_response('{"memories":[]}'), [])

    def test_malformed(self):
        self.assertEqual(parse_reflection_response("not json"), [])

    def test_filters_missing_fields(self):
        raw = json.dumps({"memories": [{"key": "", "value": "x"}, {"key": "y", "value": ""}]})
        self.assertEqual(parse_reflection_response(raw), [])


# ────────────────────────────────────────────────────────────────────
# Evidence collection
# ────────────────────────────────────────────────────────────────────


class TestCollectEvidence(unittest.TestCase):
    def test_empty(self):
        conn, user_id = _setup()
        ev = collect_evidence(conn, user_id, since=datetime.now(timezone.utc) - timedelta(days=7))
        self.assertEqual(ev["task_count"], 0)
        self.assertEqual(ev["message_count"], 0)

    def test_counts_tasks_and_messages(self):
        conn, user_id = _setup()
        _seed_chat(conn, user_id)
        _seed_task(conn, user_id, status="done")
        _seed_task(conn, user_id, status="open")
        ev = collect_evidence(conn, user_id, since=datetime.now(timezone.utc) - timedelta(days=7))
        self.assertEqual(ev["task_count"], 2)
        self.assertEqual(ev["done_count"], 1)
        self.assertEqual(ev["message_count"], 1)
        self.assertEqual(ev["user_message_count"], 1)


# ────────────────────────────────────────────────────────────────────
# run_reflection
# ────────────────────────────────────────────────────────────────────


class TestRunReflection(unittest.TestCase):
    def test_skips_when_no_data(self):
        conn, user_id = _setup()
        out = run_reflection(conn, user_id, call_fn=lambda msgs: {"content": "{}"})
        self.assertFalse(out["ran"])
        self.assertEqual(out["reason"], "no_data")

    def test_runs_and_adds_memory(self):
        conn, user_id = _setup()
        _seed_chat(conn, user_id, "발표자료 D-1 박살남")
        _seed_task(conn, user_id, title="발표자료", status="done")
        mock_msg = {
            "content": json.dumps({
                "memories": [
                    {"key": "마감 패턴", "value": "D-1에 폭주, D-0 새벽까지"},
                ],
            }, ensure_ascii=False),
        }
        out = run_reflection(conn, user_id, call_fn=lambda msgs: mock_msg)
        self.assertTrue(out["ran"])
        self.assertEqual(out["added"], 1)
        memos = top_memories(conn, user_id, limit=10)
        keys = {m["key"] for m in memos}
        self.assertIn("마감 패턴", keys)
        self.assertIn(LAST_KEY, keys)

    def test_cooldown_blocks(self):
        conn, user_id = _setup()
        _seed_chat(conn, user_id)
        run_reflection(conn, user_id, call_fn=lambda msgs: {"content": '{"memories":[]}'})
        out2 = run_reflection(conn, user_id, call_fn=lambda msgs: {"content": '{"memories":[]}'})
        self.assertFalse(out2["ran"])
        self.assertEqual(out2["reason"], "cooldown")

    def test_llm_exception_graceful(self):
        conn, user_id = _setup()
        _seed_chat(conn, user_id)

        def boom(msgs):
            raise RuntimeError("ollama down")

        out = run_reflection(conn, user_id, call_fn=boom)
        self.assertFalse(out["ran"])
        # cooldown은 기록되어 다음 즉시 재시도 막힘
        memos = top_memories(conn, user_id, limit=10)
        self.assertTrue(any(m["key"] == LAST_KEY for m in memos))


class TestRunForAll(unittest.TestCase):
    def test_iterates_users(self):
        conn, user_id = _setup()
        # 두번째 user
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO User (id, created_at, last_seen_at) VALUES (?, ?, ?)",
            ("user-b", now, now),
        )
        conn.commit()
        results = run_reflection_for_all(
            conn, call_fn=lambda msgs: {"content": '{"memories":[]}'},
        )
        ids = {r["user_id"] for r in results}
        self.assertEqual(ids, {user_id, "user-b"})


# ────────────────────────────────────────────────────────────────────
# Prompt builder
# ────────────────────────────────────────────────────────────────────


class TestBuildPrompt(unittest.TestCase):
    def test_includes_evidence_and_existing(self):
        ev = {"task_count": 3, "done_count": 1}
        existing = [{"key": "foo", "value": "bar"}]
        p = build_reflection_prompt(ev, existing)
        self.assertIn("foo: bar", p)
        self.assertIn("task_count", p)
        self.assertIn("memories", p)


if __name__ == "__main__":
    unittest.main()
