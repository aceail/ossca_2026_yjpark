"""Sprint 14 — End-to-end golden-path integration scenario.

README "사용 흐름" 7단계가 진짜 동작하는지 단일 테스트로 증명한다.
LLM 호출은 mock — Ollama 없이도 돌게 해서 CI/멘토 어필에 신뢰 가능.

시나리오:
  1. 새 사용자 + device token 발급
  2. chat에 "5월 31일까지 발표자료" 자연어 입력 → create_task action
  3. /tasks에서 카드 1개 확인
  4. chat에서 "발표자료 폴더는 <tmp>" → set_folder action
  5. 임시 디렉토리에 파일 생성 → folder watcher 수동 호출 → FolderSnapshot 1개
  6. 파일 추가 → 두 번째 스냅샷 → progress 감지
  7. follow-up dispatcher 호출 (now = D-1 시점) → assistant 메시지 INSERT
  8. chat에서 "발표자료 다 했어" → update_status done → /tasks 0건
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB_PATH = _tmp_db.name
_tmp_db.close()
os.environ["TOMORROW_YOU_DB"] = _TMP_DB_PATH
os.environ["NAEIL_DISABLE_WATCH"] = "1"
os.environ["NAEIL_DISABLE_FOLLOWUP"] = "1"

from backend.main import app
from backend.deps import get_db
from db import open_db, migrate
from persona import seed_builtin_prompts
from pipeline.folder_watch import scan_open_tasks
from pipeline.followup import dispatch_due_followups


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_TMP_DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def _get_test_db():
    c = _conn()
    try:
        yield c
    finally:
        c.close()


app.dependency_overrides[get_db] = _get_test_db


def setUpModule():
    os.environ["TOMORROW_YOU_DB"] = _TMP_DB_PATH
    app.dependency_overrides[get_db] = _get_test_db
    c = open_db(_TMP_DB_PATH)
    migrate(c)
    seed_builtin_prompts(c)
    c.close()


def tearDownModule():
    try:
        os.unlink(_TMP_DB_PATH)
    except Exception:
        pass


client = TestClient(app, raise_server_exceptions=True)


class TestEndToEndGoldenPath(unittest.TestCase):
    def test_seven_step_flow(self):
        # 1. 사용자 + token
        r = client.post("/api/users", json={})
        self.assertEqual(r.status_code, 200)
        user_id = r.json()["user_id"]
        headers = {"Authorization": f"Bearer {r.json()['device_token']}"}

        # 채팅 세션 1개
        chat_create = client.post(
            "/api/chat/sessions",
            headers=headers,
            json={"user_id": user_id},
        )
        self.assertEqual(chat_create.status_code, 201)
        sid = chat_create.json()["session_id"]

        # 2. 자연어 마감 등록 — LLM이 create_task action 응답
        mock_create = json.dumps({
            "speak": "5/31 발표자료 박았어",
            "actions": [{
                "type": "create_task",
                "title": "발표자료",
                "deadline": "2026-05-31",
            }],
        }, ensure_ascii=False)
        with patch("pipeline.chat._call_ollama_chat", return_value=mock_create):
            msg = client.post(
                f"/api/chat/sessions/{sid}/messages",
                headers=headers,
                json={"content": "5월 31일까지 발표자료 다 만들어야해"},
            )
        self.assertEqual(msg.status_code, 201)
        self.assertIn("발표자료", msg.json()["assistant"]["content"])

        # 3. /tasks 목록 확인
        tasks = client.get(f"/api/tasks?user_id={user_id}", headers=headers).json()
        self.assertEqual(len(tasks["tasks"]), 1)
        task_id = tasks["tasks"][0]["id"]
        self.assertEqual(tasks["tasks"][0]["title"], "발표자료")
        self.assertIsNotNone(tasks["tasks"][0]["deadline_at"])

        # 4. 자연어 폴더 등록
        with tempfile.TemporaryDirectory() as folder:
            mock_setfolder = json.dumps({
                "speak": f"폴더 등록했어: {folder}",
                "actions": [{
                    "type": "set_folder",
                    "task": "발표자료",
                    "folder": folder,
                }],
            }, ensure_ascii=False)
            with patch("pipeline.chat._call_ollama_chat", return_value=mock_setfolder):
                client.post(
                    f"/api/chat/sessions/{sid}/messages",
                    headers=headers,
                    json={"content": f"발표자료 폴더는 {folder}야"},
                )

            row = client.get(f"/api/tasks?user_id={user_id}", headers=headers).json()
            self.assertEqual(row["tasks"][0]["folder_path"], folder)

            # 5. 첫 스냅샷
            Path(folder, "outline.md").write_text("초안")
            c = _conn()
            try:
                self.assertEqual(scan_open_tasks(c), 1)
            finally:
                c.close()

            # 6. 진척 감지 — 두 번째 파일 + 스냅샷
            import time
            time.sleep(0.05)
            Path(folder, "section1.md").write_text("본문 1장")
            c = _conn()
            try:
                self.assertEqual(scan_open_tasks(c), 1)
                snaps = client.get(
                    f"/api/tasks/{task_id}/snapshots", headers=headers,
                ).json()["snapshots"]
                self.assertEqual(len(snaps), 2)
                self.assertGreater(snaps[0]["file_count"], snaps[1]["file_count"])
            finally:
                c.close()

            # 7. follow-up dispatch — D-1 시점 가정
            now = datetime(2026, 5, 30, 0, 0, tzinfo=timezone.utc)
            # deadline_at은 2026-05-31T23:59+09:00 → UTC 14:59
            # (deadline - now).days = 1 → D-1
            c = _conn()
            try:
                sent = dispatch_due_followups(c, now=now)
                self.assertEqual(len(sent), 1)
                self.assertEqual(sent[0]["task_id"], task_id)
                # 진척 있으므로 sharp 톤 (D-1 progressed=True)
                self.assertEqual(sent[0]["tone"], "sharp")
            finally:
                c.close()

            # 8. 자연어 완료 처리
            mock_done = json.dumps({
                "speak": "오, 다 했구나",
                "actions": [{"type": "update_status", "task": "발표자료", "status": "done"}],
            }, ensure_ascii=False)
            with patch("pipeline.chat._call_ollama_chat", return_value=mock_done):
                client.post(
                    f"/api/chat/sessions/{sid}/messages",
                    headers=headers,
                    json={"content": "발표자료 다 했어"},
                )

            open_tasks = client.get(
                f"/api/tasks?user_id={user_id}&status=open", headers=headers,
            ).json()["tasks"]
            self.assertEqual(len(open_tasks), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
