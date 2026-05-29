"""Sprint 39 — /clicked + /snooze endpoints."""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB_PATH = _tmp_db.name
_tmp_db.close()
os.environ["TOMORROW_YOU_DB"] = _TMP_DB_PATH

from fastapi.testclient import TestClient

from backend.deps import get_db
from backend.main import app
from db import migrate, open_db


def _conn():
    c = sqlite3.connect(_TMP_DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def _get_db():
    c = _conn()
    try:
        yield c
    finally:
        c.close()


app.dependency_overrides[get_db] = _get_db


def setUpModule():
    c = open_db(_TMP_DB_PATH)
    migrate(c)
    c.execute(
        "INSERT INTO User (id, created_at) VALUES ('u1', '2026-05-29')"
    )
    c.execute(
        "INSERT INTO NotificationLog (user_id, key, kind, title, body, sent_at) "
        "VALUES ('u1','k1','deadline','t','b','2026-05-29T00:00:00+00:00')"
    )
    c.commit()
    c.close()


def tearDownModule():
    try:
        os.unlink(_TMP_DB_PATH)
    except OSError:
        pass


client = TestClient(app, raise_server_exceptions=True)


class TestClickEndpoint(unittest.TestCase):
    def test_records_action(self):
        r = client.post("/api/push/1/clicked", json={"action": "done"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["updated"], 1)
        c = _conn()
        row = c.execute(
            "SELECT clicked_at, click_action FROM NotificationLog WHERE id=1"
        ).fetchone()
        self.assertIsNotNone(row["clicked_at"])
        self.assertEqual(row["click_action"], "done")
        c.close()

    def test_second_call_no_op(self):
        # 이미 위 test_records_action 에서 1번 기록됨. 두 번째는 0건 update.
        r = client.post("/api/push/1/clicked", json={"action": "open"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["updated"], 0)


class TestSnoozeEndpoint(unittest.TestCase):
    def test_sets_snooze_until(self):
        r = client.post("/api/push/1/snooze")
        self.assertEqual(r.status_code, 200)
        c = _conn()
        row = c.execute(
            "SELECT snooze_until FROM NotificationLog WHERE id=1"
        ).fetchone()
        self.assertIsNotNone(row["snooze_until"])
        c.close()


if __name__ == "__main__":
    unittest.main()
