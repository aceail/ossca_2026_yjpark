"""Sprint 19 — Chat FTS5 search_memory tool."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db import open_db, migrate, get_persona
from persona import seed_builtin_prompts
from pipeline.chat import create_chat_session, _record_message
from pipeline.tools import REGISTRY, dispatch


def _setup():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = open_db(Path(tmp.name))
    migrate(conn)
    seed_builtin_prompts(conn)
    user_id = "mem-user"
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
    sid = create_chat_session(conn, user_id=user_id, persona_id=None)
    return conn, user_id, sid


class TestFtsIndex(unittest.TestCase):
    def test_fts_table_exists_after_migration(self):
        conn, _, _ = _setup()
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='ChatMessageFts'"
        ).fetchall()
        self.assertTrue(any(r["name"] == "ChatMessageFts" for r in rows))

    def test_insert_triggers_fts_sync(self):
        conn, _, sid = _setup()
        _record_message(conn, sid, "user", "발표자료 만들어야 하는데 막막해")
        rows = conn.execute(
            "SELECT rowid FROM ChatMessageFts WHERE content MATCH '발표자료'"
        ).fetchall()
        self.assertEqual(len(rows), 1)

    def test_delete_triggers_fts_removal(self):
        conn, _, sid = _setup()
        _record_message(conn, sid, "user", "임시 메시지")
        conn.execute("DELETE FROM ChatMessage WHERE content = '임시 메시지'")
        conn.commit()
        rows = conn.execute(
            "SELECT rowid FROM ChatMessageFts WHERE content MATCH '임시'"
        ).fetchall()
        self.assertEqual(len(rows), 0)


class TestSearchMemoryTool(unittest.TestCase):
    def test_registered_in_registry(self):
        self.assertIn("search_memory", REGISTRY)

    def test_search_finds_matching_message(self):
        conn, user_id, sid = _setup()
        _record_message(conn, sid, "user", "발표자료 D-3에 하기로 했어")
        _record_message(conn, sid, "user", "회의 노트는 OneDrive에 있어")
        out = dispatch(conn, user_id=user_id, name="search_memory",
                       arguments={"query": "발표자료"})
        self.assertTrue(out["ok"])
        self.assertEqual(len(out["hits"]), 1)
        self.assertIn("발표자료", out["hits"][0]["content"])

    def test_search_empty_query_fails(self):
        conn, user_id, _ = _setup()
        out = dispatch(conn, user_id=user_id, name="search_memory",
                       arguments={"query": "   "})
        self.assertFalse(out["ok"])

    def test_search_isolates_users(self):
        conn, user_id, sid = _setup()
        _record_message(conn, sid, "user", "secret stuff")
        # 다른 user 추가
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO User (id, created_at, last_seen_at) VALUES (?, ?, ?)",
            ("other-user", now, now),
        )
        conn.commit()
        out = dispatch(conn, user_id="other-user", name="search_memory",
                       arguments={"query": "secret"})
        self.assertEqual(out["hits"], [])

    def test_search_role_filter(self):
        conn, user_id, sid = _setup()
        _record_message(conn, sid, "user", "user-side note 발표")
        _record_message(conn, sid, "assistant", "assistant-side 발표 응답")
        only_user = dispatch(conn, user_id=user_id, name="search_memory",
                             arguments={"query": "발표", "role": "user"})
        self.assertTrue(all(h["role"] == "user" for h in only_user["hits"]))
        only_asst = dispatch(conn, user_id=user_id, name="search_memory",
                             arguments={"query": "발표", "role": "assistant"})
        self.assertTrue(all(h["role"] == "assistant" for h in only_asst["hits"]))


if __name__ == "__main__":
    unittest.main()
