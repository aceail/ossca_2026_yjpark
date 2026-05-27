"""Wave 1: LLM action 추출 + Task INSERT 통합."""

from __future__ import annotations

import json
import sys
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db import open_db, migrate, get_persona  # noqa: E402
from persona import seed_builtin_prompts  # noqa: E402
from pipeline.chat import (  # noqa: E402
    _execute_actions,
    _parse_deadline_to_iso,
    _try_parse_action_response,
    create_chat_session,
    post_user_message,
)


def _setup():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = open_db(Path(tmp.name))
    migrate(conn)
    seed_builtin_prompts(conn)
    user_id = "chat-actions-user"
    from datetime import datetime, timezone
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


class TestParseActionResponse(unittest.TestCase):
    def test_plain_text_returns_none(self):
        self.assertIsNone(_try_parse_action_response("그냥 평문 응답이야"))

    def test_empty_returns_none(self):
        self.assertIsNone(_try_parse_action_response(""))
        self.assertIsNone(_try_parse_action_response("   "))

    def test_valid_json_with_actions(self):
        raw = json.dumps({
            "speak": "5/31 발표자료 캘린더에 박았어",
            "actions": [{"type": "create_task", "title": "발표자료", "deadline": "2026-05-31"}],
        }, ensure_ascii=False)
        out = _try_parse_action_response(raw)
        self.assertIsNotNone(out)
        self.assertEqual(out["speak"], "5/31 발표자료 캘린더에 박았어")
        self.assertEqual(out["actions"][0]["title"], "발표자료")

    def test_speak_only_no_actions(self):
        raw = json.dumps({"speak": "hi"}, ensure_ascii=False)
        out = _try_parse_action_response(raw)
        self.assertEqual(out["speak"], "hi")
        self.assertEqual(out["actions"], [])

    def test_malformed_json_returns_none(self):
        self.assertIsNone(_try_parse_action_response('{"speak": "broken'))


class TestParseDeadline(unittest.TestCase):
    def test_yyyy_mm_dd_becomes_eod_kst(self):
        self.assertEqual(_parse_deadline_to_iso("2026-05-31"), "2026-05-31T23:59:00+09:00")

    def test_full_iso_preserved(self):
        v = "2026-05-31T14:30:00+09:00"
        self.assertEqual(_parse_deadline_to_iso(v), v)

    def test_none_or_empty(self):
        self.assertIsNone(_parse_deadline_to_iso(None))
        self.assertIsNone(_parse_deadline_to_iso(""))
        self.assertIsNone(_parse_deadline_to_iso("   "))


class TestExecuteActions(unittest.TestCase):
    def test_create_task_inserts_row(self):
        conn, user_id = _setup()
        lines = _execute_actions(
            conn,
            user_id=user_id,
            actions=[{"type": "create_task", "title": "발표자료", "deadline": "2026-05-31"}],
        )
        self.assertEqual(len(lines), 1)
        self.assertIn("발표자료", lines[0])
        row = conn.execute(
            "SELECT title, deadline_at FROM Task WHERE user_id = ?", (user_id,)
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["title"], "발표자료")
        self.assertEqual(row["deadline_at"], "2026-05-31T23:59:00+09:00")

    def test_unknown_action_silently_skipped(self):
        conn, user_id = _setup()
        lines = _execute_actions(
            conn,
            user_id=user_id,
            actions=[{"type": "do_something_weird", "data": 42}],
        )
        self.assertEqual(lines, [])
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM Task WHERE user_id = ?", (user_id,)
        ).fetchone()["n"]
        self.assertEqual(n, 0)

    def test_create_task_without_title_skipped(self):
        conn, user_id = _setup()
        lines = _execute_actions(
            conn,
            user_id=user_id,
            actions=[{"type": "create_task", "title": "   ", "deadline": "2026-05-31"}],
        )
        self.assertEqual(lines, [])


class TestPostUserMessageActionsIntegration(unittest.TestCase):
    def test_llm_returns_json_action_triggers_task_insert(self):
        conn, user_id = _setup()
        sid = create_chat_session(conn, user_id=user_id, persona_id=None)

        mock_reply = json.dumps({
            "speak": "5/31 발표자료 박았어. 폴더 알려줘?",
            "actions": [{"type": "create_task", "title": "발표자료", "deadline": "2026-05-31"}],
        }, ensure_ascii=False)

        with patch("pipeline.chat._call_ollama_chat", return_value=mock_reply):
            result = post_user_message(
                conn, session_id=sid, content="나 5/31까지 발표자료 다 만들어야해",
            )

        self.assertIn("발표자료", result["content"])
        self.assertIn("✅", result["content"])
        # Task가 실제로 들어갔는지
        row = conn.execute(
            "SELECT title FROM Task WHERE user_id = ?", (user_id,)
        ).fetchone()
        self.assertEqual(row["title"], "발표자료")

    def test_llm_plain_text_response_no_actions(self):
        conn, user_id = _setup()
        sid = create_chat_session(conn, user_id=user_id, persona_id=None)
        with patch("pipeline.chat._call_ollama_chat", return_value="그냥 평범한 응답이야"):
            result = post_user_message(conn, session_id=sid, content="안녕")
        self.assertEqual(result["content"], "그냥 평범한 응답이야")
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM Task WHERE user_id = ?", (user_id,)
        ).fetchone()["n"]
        self.assertEqual(n, 0)


if __name__ == "__main__":
    unittest.main()
