"""Sprint 18 — Tool registry + ReAct loop."""

from __future__ import annotations

import json
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
from pipeline.chat import create_chat_session, post_user_message
from pipeline.tools import REGISTRY, dispatch, tool_schemas_for_ollama


def _setup():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = open_db(Path(tmp.name))
    migrate(conn)
    seed_builtin_prompts(conn)
    user_id = "react-user"
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
# Tool schema
# ────────────────────────────────────────────────────────────────────


class TestToolSchema(unittest.TestCase):
    def test_registry_has_core_tools(self):
        names = set(REGISTRY.keys())
        for must in ("create_task", "list_tasks", "update_task",
                     "delete_task", "get_task_progress", "get_recent_followups"):
            self.assertIn(must, names)

    def test_ollama_schema_format(self):
        schemas = tool_schemas_for_ollama()
        self.assertTrue(schemas)
        for s in schemas:
            self.assertEqual(s["type"], "function")
            self.assertIn("name", s["function"])
            self.assertIn("description", s["function"])
            self.assertIn("parameters", s["function"])


# ────────────────────────────────────────────────────────────────────
# dispatch — direct executor
# ────────────────────────────────────────────────────────────────────


class TestDispatch(unittest.TestCase):
    def test_unknown_tool(self):
        conn, user_id = _setup()
        out = dispatch(conn, user_id=user_id, name="nope", arguments={})
        self.assertFalse(out["ok"])

    def test_create_then_list(self):
        conn, user_id = _setup()
        r1 = dispatch(conn, user_id=user_id, name="create_task",
                      arguments={"title": "발표자료", "deadline": "2026-12-01"})
        self.assertTrue(r1["ok"])
        r2 = dispatch(conn, user_id=user_id, name="list_tasks", arguments={"status": "open"})
        self.assertTrue(r2["ok"])
        titles = [t["title"] for t in r2["tasks"]]
        self.assertIn("발표자료", titles)

    def test_arguments_as_json_string(self):
        conn, user_id = _setup()
        out = dispatch(conn, user_id=user_id, name="create_task",
                       arguments='{"title": "회의록"}')
        self.assertTrue(out["ok"])

    def test_update_resolves_by_title(self):
        conn, user_id = _setup()
        dispatch(conn, user_id=user_id, name="create_task", arguments={"title": "보고서"})
        r = dispatch(conn, user_id=user_id, name="update_task",
                     arguments={"task": "보고서", "status": "done"})
        self.assertTrue(r["ok"])
        row = conn.execute("SELECT status FROM Task WHERE user_id = ?", (user_id,)).fetchone()
        self.assertEqual(row["status"], "done")

    def test_task_progress_no_snapshot(self):
        conn, user_id = _setup()
        dispatch(conn, user_id=user_id, name="create_task", arguments={"title": "T"})
        r = dispatch(conn, user_id=user_id, name="get_task_progress", arguments={"task": "T"})
        self.assertTrue(r["ok"])
        self.assertEqual(r["snapshots"], [])


# ────────────────────────────────────────────────────────────────────
# ReAct loop
# ────────────────────────────────────────────────────────────────────


class TestReActLoop(unittest.TestCase):
    def test_single_tool_call_round(self):
        conn, user_id = _setup()
        sid = create_chat_session(conn, user_id=user_id, persona_id=None)

        responses = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "function": {
                        "name": "create_task",
                        "arguments": {"title": "발표자료", "deadline": "2026-12-01"},
                    },
                }],
            },
            {"role": "assistant", "content": "발표자료 박았어."},
        ]
        idx = {"i": 0}

        def fake_call(messages, tools=None):
            i = idx["i"]; idx["i"] += 1
            return responses[i]

        with patch("pipeline.chat._call_ollama_chat", side_effect=fake_call):
            result = post_user_message(
                conn, session_id=sid,
                content="12월 1일까지 발표자료 만들어야해",
            )

        self.assertEqual(result["tool_calls"], 1)
        self.assertIn("발표자료", result["content"])
        row = conn.execute(
            "SELECT title FROM Task WHERE user_id = ?", (user_id,)
        ).fetchone()
        self.assertEqual(row["title"], "발표자료")

    def test_no_tool_calls_plain_content(self):
        conn, user_id = _setup()
        sid = create_chat_session(conn, user_id=user_id, persona_id=None)

        def fake_call(messages, tools=None):
            return {"role": "assistant", "content": "안녕"}

        with patch("pipeline.chat._call_ollama_chat", side_effect=fake_call):
            result = post_user_message(conn, session_id=sid, content="안녕")

        self.assertEqual(result["content"], "안녕")
        self.assertEqual(result["tool_calls"], 0)

    def test_multi_round_two_tools_then_summary(self):
        conn, user_id = _setup()
        dispatch(conn, user_id=user_id, name="create_task", arguments={"title": "발표자료"})
        sid = create_chat_session(conn, user_id=user_id, persona_id=None)

        responses = [
            {"role": "assistant", "content": "",
             "tool_calls": [{"function": {"name": "list_tasks", "arguments": {"status": "open"}}}]},
            {"role": "assistant", "content": "",
             "tool_calls": [{"function": {"name": "get_task_progress", "arguments": {"task": "발표자료"}}}]},
            {"role": "assistant", "content": "발표자료 폴더 등록 안 됐어."},
        ]
        idx = {"i": 0}

        def fake_call(messages, tools=None):
            i = idx["i"]; idx["i"] += 1
            return responses[i]

        with patch("pipeline.chat._call_ollama_chat", side_effect=fake_call):
            result = post_user_message(
                conn, session_id=sid, content="발표자료 어떻게 됐어?",
            )

        self.assertEqual(result["tool_calls"], 2)
        self.assertIn("발표자료", result["content"])

    def test_legacy_json_action_fallback(self):
        conn, user_id = _setup()
        sid = create_chat_session(conn, user_id=user_id, persona_id=None)
        legacy = json.dumps({
            "speak": "5/31 발표자료 박았어",
            "actions": [
                {"type": "create_task", "title": "발표자료", "deadline": "2026-05-31"},
            ],
        }, ensure_ascii=False)

        def fake_call(messages, tools=None):
            return {"role": "assistant", "content": legacy}

        with patch("pipeline.chat._call_ollama_chat", side_effect=fake_call):
            result = post_user_message(
                conn, session_id=sid, content="5/31 발표자료 만들어야해",
            )

        self.assertIn("발표자료", result["content"])
        row = conn.execute(
            "SELECT title FROM Task WHERE user_id = ?", (user_id,)
        ).fetchone()
        self.assertEqual(row["title"], "발표자료")


if __name__ == "__main__":
    unittest.main()
