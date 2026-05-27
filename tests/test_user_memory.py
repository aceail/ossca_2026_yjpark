"""Sprint 20 — UserMemory CRUD + tool dispatch + system_prompt inject."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db import open_db, migrate, get_persona
from persona import seed_builtin_prompts
from pipeline.chat import (
    _persona_system_prompt_with_memory,
    create_chat_session,
    post_user_message,
)
from pipeline.memory import (
    format_for_prompt,
    forget,
    recall,
    top_memories,
    upsert_memory,
)
from pipeline.tools import REGISTRY, dispatch


def _setup():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = open_db(Path(tmp.name))
    migrate(conn)
    seed_builtin_prompts(conn)
    user_id = "mem-2-user"
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


# ────────────────────────────────────────────────────────────────────
# CRUD
# ────────────────────────────────────────────────────────────────────


class TestMemoryCRUD(unittest.TestCase):
    def test_upsert_insert_then_update_increments_salience(self):
        conn, user_id = _setup()
        upsert_memory(conn, user_id=user_id, key="멘토 미팅", value="매주 금요일")
        upsert_memory(conn, user_id=user_id, key="멘토 미팅", value="매주 금요일 오후 3시")
        memos = top_memories(conn, user_id)
        self.assertEqual(len(memos), 1)
        self.assertEqual(memos[0]["value"], "매주 금요일 오후 3시")
        self.assertGreaterEqual(memos[0]["salience"], 2)

    def test_recall_finds_by_key_or_value(self):
        conn, user_id = _setup()
        upsert_memory(conn, user_id=user_id, key="favorite_food", value="라면")
        upsert_memory(conn, user_id=user_id, key="sport", value="달리기 매일 아침")
        by_key = recall(conn, user_id, query="favorite")
        by_val = recall(conn, user_id, query="달리기")
        self.assertEqual(len(by_key), 1)
        self.assertEqual(len(by_val), 1)

    def test_forget_removes(self):
        conn, user_id = _setup()
        upsert_memory(conn, user_id=user_id, key="k1", value="v1")
        self.assertTrue(forget(conn, user_id, key="k1"))
        self.assertEqual(top_memories(conn, user_id), [])

    def test_top_orders_by_salience_then_recency(self):
        conn, user_id = _setup()
        upsert_memory(conn, user_id=user_id, key="A", value="va")
        upsert_memory(conn, user_id=user_id, key="A", value="va")  # salience += 1
        upsert_memory(conn, user_id=user_id, key="B", value="vb")  # salience = 1
        memos = top_memories(conn, user_id, limit=10)
        self.assertEqual(memos[0]["key"], "A")
        self.assertEqual(memos[1]["key"], "B")

    def test_user_isolation(self):
        conn, user_id = _setup()
        upsert_memory(conn, user_id=user_id, key="k", value="v")
        # 다른 user
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO User (id, created_at, last_seen_at) VALUES (?, ?, ?)",
            ("other", now, now),
        )
        conn.commit()
        self.assertEqual(top_memories(conn, "other"), [])


# ────────────────────────────────────────────────────────────────────
# Tool dispatch
# ────────────────────────────────────────────────────────────────────


class TestRememberRecallTool(unittest.TestCase):
    def test_registered(self):
        for name in ("remember", "recall", "forget"):
            self.assertIn(name, REGISTRY)

    def test_remember_dispatch(self):
        conn, user_id = _setup()
        out = dispatch(conn, user_id=user_id, name="remember",
                       arguments={"key": "마감 패턴", "value": "보통 D-1에 폭주"})
        self.assertTrue(out["ok"])
        memos = top_memories(conn, user_id)
        self.assertEqual(memos[0]["key"], "마감 패턴")

    def test_recall_dispatch(self):
        conn, user_id = _setup()
        upsert_memory(conn, user_id=user_id, key="favorite_drink", value="아메리카노")
        out = dispatch(conn, user_id=user_id, name="recall",
                       arguments={"query": "drink"})
        self.assertTrue(out["ok"])
        self.assertEqual(len(out["hits"]), 1)

    def test_remember_validates_inputs(self):
        conn, user_id = _setup()
        out = dispatch(conn, user_id=user_id, name="remember",
                       arguments={"key": "  ", "value": "v"})
        self.assertFalse(out["ok"])


# ────────────────────────────────────────────────────────────────────
# system_prompt inject
# ────────────────────────────────────────────────────────────────────


class TestSystemPromptMemoryInject(unittest.TestCase):
    def test_format_empty(self):
        self.assertEqual(format_for_prompt([]), "")

    def test_format_lines(self):
        s = format_for_prompt([{"key": "k", "value": "v"}])
        self.assertIn("k: v", s)
        self.assertIn("기억하는 것들", s)

    def test_persona_prompt_includes_memory(self):
        conn, user_id = _setup()
        upsert_memory(conn, user_id=user_id, key="멘토 미팅", value="매주 금요일 3시")
        prompt = _persona_system_prompt_with_memory(conn, None, user_id)
        self.assertIn("멘토 미팅: 매주 금요일 3시", prompt)

    def test_persona_prompt_no_memory(self):
        conn, user_id = _setup()
        prompt = _persona_system_prompt_with_memory(conn, None, user_id)
        self.assertNotIn("기억하는 것들", prompt)


# ────────────────────────────────────────────────────────────────────
# E2E: LLM이 remember tool 호출 → 이후 호출 시 system prompt에 자동 inject
# ────────────────────────────────────────────────────────────────────


class TestMemoryE2E(unittest.TestCase):
    def test_remember_then_visible_in_next_call(self):
        conn, user_id = _setup()
        sid = create_chat_session(conn, user_id=user_id, persona_id=None)
        responses = [
            {"role": "assistant", "content": "",
             "tool_calls": [{"function": {"name": "remember",
                                          "arguments": {"key": "선호 톤", "value": "직설"}}}]},
            {"role": "assistant", "content": "기억해뒀어."},
        ]
        idx = {"i": 0}
        def fake_call(messages, tools=None):
            i = idx["i"]; idx["i"] += 1
            return responses[i]
        with patch("pipeline.chat._call_ollama_chat", side_effect=fake_call):
            post_user_message(conn, session_id=sid, content="앞으로 직설로 말해줘")
        # 다음 호출의 system prompt에 memory가 들어있어야
        captured: list[str] = []
        def fake_inspect(messages, tools=None):
            captured.append(messages[0]["content"])
            return {"role": "assistant", "content": "ok"}
        with patch("pipeline.chat._call_ollama_chat", side_effect=fake_inspect):
            post_user_message(conn, session_id=sid, content="안녕")
        self.assertTrue(captured)
        self.assertIn("선호 톤: 직설", captured[0])


if __name__ == "__main__":
    unittest.main()
