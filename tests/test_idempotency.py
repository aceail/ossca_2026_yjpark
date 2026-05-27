"""P0-16 Idempotency-Key 캐시 — v0.3 sprint 9."""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
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
from backend.idempotency import check_idempotency, store_idempotency
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


# ────────────────────────────────────────────────────────────────────
# Unit
# ────────────────────────────────────────────────────────────────────


class TestIdempotencyUnit(unittest.TestCase):
    def test_check_empty_key_returns_none(self):
        c = _conn()
        try:
            self.assertIsNone(
                check_idempotency(c, user_id="u", endpoint="POST /x", key=None),
            )
            self.assertIsNone(
                check_idempotency(c, user_id="u", endpoint="POST /x", key=""),
            )
        finally:
            c.close()

    def test_store_then_check_round_trip(self):
        user_id, _ = _create_user()
        c = _conn()
        try:
            store_idempotency(
                c,
                user_id=user_id,
                endpoint="POST /test",
                key="abc-123",
                response={"hello": "world", "n": 42},
            )
            got = check_idempotency(
                c, user_id=user_id, endpoint="POST /test", key="abc-123",
            )
            self.assertEqual(got, {"hello": "world", "n": 42})
        finally:
            c.close()

    def test_endpoint_isolation(self):
        user_id, _ = _create_user()
        c = _conn()
        try:
            store_idempotency(c, user_id=user_id, endpoint="POST /A", key="k", response={"a": 1})
            self.assertIsNone(
                check_idempotency(c, user_id=user_id, endpoint="POST /B", key="k"),
            )
        finally:
            c.close()

    def test_user_isolation(self):
        u1, _ = _create_user()
        u2, _ = _create_user()
        c = _conn()
        try:
            store_idempotency(c, user_id=u1, endpoint="POST /X", key="k", response={"v": 1})
            self.assertIsNone(
                check_idempotency(c, user_id=u2, endpoint="POST /X", key="k"),
            )
        finally:
            c.close()

    def test_expired_entries_treated_as_miss(self):
        user_id, _ = _create_user()
        c = _conn()
        try:
            # 25h 전 시점으로 직접 INSERT
            old_ts = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
            c.execute(
                """INSERT INTO IdempotencyKey
                   (user_id, endpoint, key, response_json, status_code, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, "POST /old", "k", '{"v":1}', 200, old_ts),
            )
            c.commit()
            self.assertIsNone(
                check_idempotency(c, user_id=user_id, endpoint="POST /old", key="k"),
            )
        finally:
            c.close()

    def test_store_is_first_writer_wins(self):
        """같은 (user, endpoint, key)로 두 번 store하면 첫 응답이 보존된다."""
        user_id, _ = _create_user()
        c = _conn()
        try:
            store_idempotency(c, user_id=user_id, endpoint="POST /Y", key="k", response={"first": True})
            store_idempotency(c, user_id=user_id, endpoint="POST /Y", key="k", response={"first": False})
            got = check_idempotency(c, user_id=user_id, endpoint="POST /Y", key="k")
            self.assertEqual(got, {"first": True})
        finally:
            c.close()


# ────────────────────────────────────────────────────────────────────
# API: POST /api/sessions
# ────────────────────────────────────────────────────────────────────


class TestSessionsIdempotency(unittest.TestCase):
    def test_same_key_returns_same_session_id(self):
        user_id, h = _create_user()
        h_with_key = {**h, "Idempotency-Key": "session-key-1"}

        r1 = client.post("/api/sessions", headers=h_with_key, json={
            "user_id": user_id,
            "avoidance_input": "보고서 미루는 중",
        })
        r2 = client.post("/api/sessions", headers=h_with_key, json={
            "user_id": user_id,
            "avoidance_input": "보고서 미루는 중",
        })
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)
        self.assertEqual(r1.json()["session_id"], r2.json()["session_id"])

        # DB에 row 하나만 존재
        c = _conn()
        try:
            n = c.execute(
                "SELECT COUNT(*) AS n FROM AvoidanceSession WHERE user_id = ?",
                (user_id,),
            ).fetchone()["n"]
            self.assertEqual(n, 1)
        finally:
            c.close()

    def test_no_key_does_not_cache(self):
        user_id, h = _create_user()
        r1 = client.post("/api/sessions", headers=h, json={
            "user_id": user_id,
            "avoidance_input": "코딩 미루는 중",
        })
        r2 = client.post("/api/sessions", headers=h, json={
            "user_id": user_id,
            "avoidance_input": "코딩 미루는 중",
        })
        self.assertNotEqual(r1.json()["session_id"], r2.json()["session_id"])

    def test_different_keys_create_distinct_sessions(self):
        user_id, h = _create_user()
        r1 = client.post(
            "/api/sessions",
            headers={**h, "Idempotency-Key": "k-A"},
            json={"user_id": user_id, "avoidance_input": "발표 미루는 중"},
        )
        r2 = client.post(
            "/api/sessions",
            headers={**h, "Idempotency-Key": "k-B"},
            json={"user_id": user_id, "avoidance_input": "발표 미루는 중"},
        )
        self.assertNotEqual(r1.json()["session_id"], r2.json()["session_id"])


if __name__ == "__main__":
    unittest.main()
