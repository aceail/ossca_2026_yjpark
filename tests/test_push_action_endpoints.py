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

from fastapi.testclient import TestClient

from backend.deps import get_db
from backend.main import app
from db import migrate, open_db


client = TestClient(app, raise_server_exceptions=True)


class _BaseNotifTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self._tmp_db = tmp.name
        c = open_db(Path(self._tmp_db))
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
        self._prev_override = app.dependency_overrides.get(get_db)

        def _local_get_db():
            cc = sqlite3.connect(self._tmp_db, check_same_thread=False)
            cc.row_factory = sqlite3.Row
            try:
                yield cc
            finally:
                cc.close()

        app.dependency_overrides[get_db] = _local_get_db

    def tearDown(self):
        if self._prev_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = self._prev_override
        try:
            os.unlink(self._tmp_db)
        except OSError:
            pass

    def _conn(self):
        c = sqlite3.connect(self._tmp_db, check_same_thread=False)
        c.row_factory = sqlite3.Row
        return c


class TestClickEndpoint(_BaseNotifTest):
    def test_records_action(self):
        r = client.post("/api/push/1/clicked", json={"action": "done"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["updated"], 1)
        c = self._conn()
        row = c.execute(
            "SELECT clicked_at, click_action FROM NotificationLog WHERE id=1"
        ).fetchone()
        self.assertIsNotNone(row["clicked_at"])
        self.assertEqual(row["click_action"], "done")
        c.close()

    def test_second_call_no_op(self):
        # First click — mark as clicked
        r1 = client.post("/api/push/1/clicked", json={"action": "done"})
        self.assertEqual(r1.status_code, 200, r1.text)
        self.assertEqual(r1.json()["updated"], 1)
        # Second click — already clicked, should be no-op
        r2 = client.post("/api/push/1/clicked", json={"action": "open"})
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["updated"], 0)


class TestSnoozeEndpoint(_BaseNotifTest):
    def test_sets_snooze_until(self):
        r = client.post("/api/push/1/snooze")
        self.assertEqual(r.status_code, 200)
        c = self._conn()
        row = c.execute(
            "SELECT snooze_until FROM NotificationLog WHERE id=1"
        ).fetchone()
        self.assertIsNotNone(row["snooze_until"])
        c.close()


if __name__ == "__main__":
    unittest.main()
