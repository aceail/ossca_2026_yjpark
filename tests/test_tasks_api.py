"""Wave 1: Tasks API + token guard."""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB_PATH = _tmp_db.name
_tmp_db.close()
os.environ["TOMORROW_YOU_DB"] = _TMP_DB_PATH

from backend.main import app
from backend.deps import get_db
from db import open_db, migrate
from persona import seed_builtin_prompts


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


def _create_user() -> tuple[str, dict]:
    r = client.post("/api/users", json={})
    d = r.json()
    return d["user_id"], {"Authorization": f"Bearer {d['device_token']}"}


class TestTasksCRUD(unittest.TestCase):
    def test_create_task_basic(self):
        user_id, h = _create_user()
        r = client.post("/api/tasks", headers=h, json={
            "user_id": user_id,
            "title": "발표자료",
            "deadline_at": "2026-05-31T23:59:00+09:00",
        })
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertEqual(body["title"], "발표자료")
        self.assertEqual(body["status"], "open")
        self.assertEqual(body["user_id"], user_id)

    def test_create_requires_token(self):
        user_id, _ = _create_user()
        r = client.post("/api/tasks", json={"user_id": user_id, "title": "x"})
        self.assertEqual(r.status_code, 401)

    def test_create_user_mismatch_forbidden(self):
        u1, _ = _create_user()
        _, h2 = _create_user()
        r = client.post("/api/tasks", headers=h2, json={"user_id": u1, "title": "x"})
        self.assertEqual(r.status_code, 403)

    def test_list_returns_only_own_tasks(self):
        u1, h1 = _create_user()
        u2, h2 = _create_user()
        client.post("/api/tasks", headers=h1, json={"user_id": u1, "title": "내 작업"})
        client.post("/api/tasks", headers=h2, json={"user_id": u2, "title": "남의 작업"})
        r = client.get(f"/api/tasks?user_id={u1}", headers=h1)
        self.assertEqual(r.status_code, 200)
        titles = [t["title"] for t in r.json()["tasks"]]
        self.assertIn("내 작업", titles)
        self.assertNotIn("남의 작업", titles)

    def test_list_status_filter(self):
        u, h = _create_user()
        r1 = client.post("/api/tasks", headers=h, json={"user_id": u, "title": "T1"})
        r2 = client.post("/api/tasks", headers=h, json={"user_id": u, "title": "T2"})
        client.patch(f"/api/tasks/{r1.json()['id']}", headers=h, json={"status": "done"})
        only_open = client.get(f"/api/tasks?user_id={u}&status=open", headers=h).json()["tasks"]
        self.assertEqual(len(only_open), 1)
        self.assertEqual(only_open[0]["id"], r2.json()["id"])

    def test_update_invalid_status_400(self):
        u, h = _create_user()
        r = client.post("/api/tasks", headers=h, json={"user_id": u, "title": "T"})
        r2 = client.patch(f"/api/tasks/{r.json()['id']}", headers=h, json={"status": "bogus"})
        self.assertEqual(r2.status_code, 400)

    def test_update_folder_path(self):
        u, h = _create_user()
        r = client.post("/api/tasks", headers=h, json={"user_id": u, "title": "T"})
        tid = r.json()["id"]
        r2 = client.patch(f"/api/tasks/{tid}", headers=h, json={"folder_path": "/tmp/x"})
        self.assertEqual(r2.json()["folder_path"], "/tmp/x")

    def test_delete_cascades_snapshots(self):
        u, h = _create_user()
        r = client.post("/api/tasks", headers=h, json={"user_id": u, "title": "T"})
        tid = r.json()["id"]
        # 스냅샷 1개 직접 INSERT (Wave 2가 이걸 만들 예정)
        c = _conn()
        try:
            c.execute(
                """INSERT INTO FolderSnapshot
                   (task_id, taken_at, file_count, total_bytes, files_json)
                   VALUES (?, '2026-05-27T00:00:00+00:00', 3, 1234, '[]')""",
                (tid,),
            )
            c.commit()
        finally:
            c.close()
        r2 = client.delete(f"/api/tasks/{tid}", headers=h)
        self.assertEqual(r2.status_code, 204)
        # 스냅샷도 cascade 삭제됐는지
        c = _conn()
        try:
            n = c.execute(
                "SELECT COUNT(*) AS n FROM FolderSnapshot WHERE task_id = ?", (tid,),
            ).fetchone()["n"]
            self.assertEqual(n, 0)
        finally:
            c.close()

    def test_snapshots_endpoint(self):
        u, h = _create_user()
        r = client.post("/api/tasks", headers=h, json={"user_id": u, "title": "T"})
        tid = r.json()["id"]
        r2 = client.get(f"/api/tasks/{tid}/snapshots", headers=h)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["snapshots"], [])

    def test_update_not_found(self):
        u, h = _create_user()
        r = client.patch("/api/tasks/99999", headers=h, json={"title": "x"})
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
