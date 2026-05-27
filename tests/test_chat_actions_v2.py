"""Sprint 13 — 확장 chat actions (set_folder/update_status/update_deadline/update_title)."""

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
from pipeline.chat import (
    _execute_actions,
    _resolve_task_by_hint,
    create_chat_session,
    post_user_message,
)


def _setup():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = open_db(Path(tmp.name))
    migrate(conn)
    seed_builtin_prompts(conn)
    user_id = "act-v2-user"
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


def _make_task(conn, user_id, title, **kw):
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """INSERT INTO Task (user_id, title, deadline_at, folder_path, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            title,
            kw.get("deadline_at"),
            kw.get("folder_path"),
            kw.get("status", "open"),
            now,
            now,
        ),
    )
    conn.commit()
    return cur.lastrowid


# ────────────────────────────────────────────────────────────────────
# Task hint resolver
# ────────────────────────────────────────────────────────────────────


class TestResolveTask(unittest.TestCase):
    def test_resolve_by_int_id(self):
        conn, user_id = _setup()
        tid = _make_task(conn, user_id, "발표자료")
        row = _resolve_task_by_hint(conn, user_id=user_id, hint=tid)
        self.assertEqual(row["id"], tid)

    def test_resolve_by_substring(self):
        conn, user_id = _setup()
        tid = _make_task(conn, user_id, "OSSCA 발표자료")
        row = _resolve_task_by_hint(conn, user_id=user_id, hint="발표")
        self.assertEqual(row["id"], tid)

    def test_resolve_prefers_open_status(self):
        conn, user_id = _setup()
        old = _make_task(conn, user_id, "보고서", status="done")
        new = _make_task(conn, user_id, "보고서 v2", status="open")
        row = _resolve_task_by_hint(conn, user_id=user_id, hint="보고서")
        # open이 우선이라 v2 (open)이 매칭
        self.assertEqual(row["id"], new)

    def test_resolve_returns_none_for_no_match(self):
        conn, user_id = _setup()
        _make_task(conn, user_id, "발표자료")
        self.assertIsNone(_resolve_task_by_hint(conn, user_id=user_id, hint="없는것"))

    def test_resolve_returns_none_for_other_user(self):
        conn, user_id = _setup()
        _make_task(conn, user_id, "내거")
        row = _resolve_task_by_hint(conn, user_id="other-user", hint="내거")
        self.assertIsNone(row)


# ────────────────────────────────────────────────────────────────────
# Action dispatch
# ────────────────────────────────────────────────────────────────────


class TestSetFolderAction(unittest.TestCase):
    def test_sets_folder(self):
        conn, user_id = _setup()
        _make_task(conn, user_id, "발표자료")
        lines = _execute_actions(conn, user_id=user_id, actions=[
            {"type": "set_folder", "task": "발표", "folder": "/Users/yj/work"},
        ])
        self.assertEqual(len(lines), 1)
        self.assertIn("/Users/yj/work", lines[0])
        row = conn.execute(
            "SELECT folder_path FROM Task WHERE user_id = ?", (user_id,)
        ).fetchone()
        self.assertEqual(row["folder_path"], "/Users/yj/work")

    def test_missing_task_warns(self):
        conn, user_id = _setup()
        lines = _execute_actions(conn, user_id=user_id, actions=[
            {"type": "set_folder", "task": "없음", "folder": "/x"},
        ])
        self.assertEqual(len(lines), 1)
        self.assertIn("⚠", lines[0])

    def test_empty_folder_warns(self):
        conn, user_id = _setup()
        _make_task(conn, user_id, "T")
        lines = _execute_actions(conn, user_id=user_id, actions=[
            {"type": "set_folder", "task": "T", "folder": "   "},
        ])
        self.assertIn("⚠", lines[0])


class TestUpdateStatusAction(unittest.TestCase):
    def test_mark_done(self):
        conn, user_id = _setup()
        tid = _make_task(conn, user_id, "발표자료")
        _execute_actions(conn, user_id=user_id, actions=[
            {"type": "update_status", "task": "발표", "status": "done"},
        ])
        row = conn.execute("SELECT status FROM Task WHERE id = ?", (tid,)).fetchone()
        self.assertEqual(row["status"], "done")

    def test_invalid_status_warns(self):
        conn, user_id = _setup()
        _make_task(conn, user_id, "T")
        lines = _execute_actions(conn, user_id=user_id, actions=[
            {"type": "update_status", "task": "T", "status": "weird"},
        ])
        self.assertIn("⚠", lines[0])

    def test_reopen_from_done(self):
        conn, user_id = _setup()
        tid = _make_task(conn, user_id, "T", status="done")
        _execute_actions(conn, user_id=user_id, actions=[
            {"type": "update_status", "task": "T", "status": "open"},
        ])
        row = conn.execute("SELECT status FROM Task WHERE id = ?", (tid,)).fetchone()
        self.assertEqual(row["status"], "open")


class TestUpdateDeadlineAction(unittest.TestCase):
    def test_changes_deadline(self):
        conn, user_id = _setup()
        tid = _make_task(conn, user_id, "T", deadline_at="2026-05-31T23:59:00+09:00")
        _execute_actions(conn, user_id=user_id, actions=[
            {"type": "update_deadline", "task": "T", "deadline": "2026-06-15"},
        ])
        row = conn.execute("SELECT deadline_at FROM Task WHERE id = ?", (tid,)).fetchone()
        self.assertEqual(row["deadline_at"], "2026-06-15T23:59:00+09:00")

    def test_invalid_deadline_warns(self):
        conn, user_id = _setup()
        _make_task(conn, user_id, "T")
        lines = _execute_actions(conn, user_id=user_id, actions=[
            {"type": "update_deadline", "task": "T", "deadline": ""},
        ])
        self.assertIn("⚠", lines[0])


class TestUpdateTitleAction(unittest.TestCase):
    def test_changes_title(self):
        conn, user_id = _setup()
        tid = _make_task(conn, user_id, "PPT")
        _execute_actions(conn, user_id=user_id, actions=[
            {"type": "update_title", "task": "PPT", "new_title": "OSSCA 발표"},
        ])
        row = conn.execute("SELECT title FROM Task WHERE id = ?", (tid,)).fetchone()
        self.assertEqual(row["title"], "OSSCA 발표")


# ────────────────────────────────────────────────────────────────────
# Multi-action + post_user_message integration
# ────────────────────────────────────────────────────────────────────


class TestMultiActionOneShot(unittest.TestCase):
    def test_create_and_set_folder_same_message(self):
        conn, user_id = _setup()
        sid = create_chat_session(conn, user_id=user_id, persona_id=None)
        mock = json.dumps({
            "speak": "발표자료 등록하고 폴더도 잡았어",
            "actions": [
                {"type": "create_task", "title": "발표자료", "deadline": "2026-05-31"},
                {"type": "set_folder", "task": "발표자료", "folder": "/Users/yj/Desktop/work"},
            ],
        }, ensure_ascii=False)

        with patch("pipeline.chat._call_ollama_chat", return_value=mock):
            result = post_user_message(
                conn, session_id=sid,
                content="5월 31일까지 발표자료. 폴더는 ~/Desktop/work",
            )

        self.assertIn("발표자료", result["content"])
        self.assertIn("/Users/yj/Desktop/work", result["content"])

        row = conn.execute(
            "SELECT title, deadline_at, folder_path FROM Task WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        self.assertEqual(row["title"], "발표자료")
        self.assertEqual(row["folder_path"], "/Users/yj/Desktop/work")
        self.assertTrue(row["deadline_at"].startswith("2026-05-31"))


if __name__ == "__main__":
    unittest.main()
