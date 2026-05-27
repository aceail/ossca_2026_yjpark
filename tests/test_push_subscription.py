"""Wave 6 — Push subscription API + dry-run send."""

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
os.environ["NAEIL_DISABLE_WATCH"] = "1"
os.environ["NAEIL_DISABLE_FOLLOWUP"] = "1"

from backend.main import app
from backend.deps import get_db
from backend.push import push_enabled, send_push_to_user, list_active_subscriptions
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
# Migration 014
# ────────────────────────────────────────────────────────────────────


class TestMigration(unittest.TestCase):
    def test_push_subscription_table_exists(self):
        c = _conn()
        try:
            cols = {r["name"] for r in c.execute("PRAGMA table_info(PushSubscription)").fetchall()}
            self.assertIn("endpoint", cols)
            self.assertIn("p256dh", cols)
            self.assertIn("auth", cols)
            self.assertIn("enabled", cols)
        finally:
            c.close()


# ────────────────────────────────────────────────────────────────────
# API
# ────────────────────────────────────────────────────────────────────


class TestSubscriptionAPI(unittest.TestCase):
    def test_vapid_key_endpoint_reports_disabled_when_no_env(self):
        os.environ.pop("NAEIL_VAPID_PUBLIC_KEY", None)
        r = client.get("/api/push/vapid-public-key")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["enabled"])

    def test_vapid_key_endpoint_reports_enabled_when_set(self):
        os.environ["NAEIL_VAPID_PUBLIC_KEY"] = "test-pub-key"
        try:
            r = client.get("/api/push/vapid-public-key")
            self.assertTrue(r.json()["enabled"])
            self.assertEqual(r.json()["vapid_public_key"], "test-pub-key")
        finally:
            os.environ.pop("NAEIL_VAPID_PUBLIC_KEY", None)

    def test_create_subscription_idempotent(self):
        uid, h = _create_user()
        body = {
            "user_id": uid,
            "endpoint": "https://fcm.googleapis.com/fcm/send/EXAMPLE",
            "p256dh": "p256dh-A",
            "auth": "auth-A",
        }
        r1 = client.post("/api/push/subscriptions", headers=h, json=body)
        r2 = client.post("/api/push/subscriptions", headers=h, json={**body, "p256dh": "p256dh-B"})
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)
        # 같은 endpoint 재요청 → UNIQUE 충돌 안 나야 함 (upsert)
        c = _conn()
        try:
            n = c.execute(
                "SELECT COUNT(*) AS n FROM PushSubscription WHERE user_id = ?", (uid,)
            ).fetchone()["n"]
            self.assertEqual(n, 1)
            new_p256 = c.execute(
                "SELECT p256dh FROM PushSubscription WHERE user_id = ?", (uid,)
            ).fetchone()["p256dh"]
            self.assertEqual(new_p256, "p256dh-B")
        finally:
            c.close()

    def test_create_requires_token(self):
        r = client.post("/api/push/subscriptions", json={
            "user_id": "x", "endpoint": "e", "p256dh": "p", "auth": "a",
        })
        self.assertEqual(r.status_code, 401)

    def test_user_mismatch_forbidden(self):
        u1, _ = _create_user()
        _, h2 = _create_user()
        r = client.post("/api/push/subscriptions", headers=h2, json={
            "user_id": u1, "endpoint": "e", "p256dh": "p", "auth": "a",
        })
        self.assertEqual(r.status_code, 403)

    def test_list_and_delete(self):
        uid, h = _create_user()
        r1 = client.post("/api/push/subscriptions", headers=h, json={
            "user_id": uid, "endpoint": "ep1", "p256dh": "p", "auth": "a",
        })
        sub_id = r1.json()["id"]
        lst = client.get(f"/api/push/users/{uid}/subscriptions", headers=h)
        self.assertEqual(lst.status_code, 200)
        self.assertEqual(len(lst.json()["subscriptions"]), 1)
        dl = client.delete(f"/api/push/subscriptions/{sub_id}", headers=h)
        self.assertEqual(dl.status_code, 204)
        lst2 = client.get(f"/api/push/users/{uid}/subscriptions", headers=h)
        self.assertEqual(len(lst2.json()["subscriptions"]), 0)


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────


class TestPushHelpers(unittest.TestCase):
    def test_push_enabled_false_without_env(self):
        os.environ.pop("NAEIL_VAPID_PRIVATE_KEY", None)
        os.environ.pop("NAEIL_VAPID_PUBLIC_KEY", None)
        self.assertFalse(push_enabled())

    def test_send_to_user_zero_when_dry_run(self):
        uid, h = _create_user()
        client.post("/api/push/subscriptions", headers=h, json={
            "user_id": uid, "endpoint": "ep", "p256dh": "p", "auth": "a",
        })
        c = _conn()
        try:
            sent = send_push_to_user(c, user_id=uid, title="t", body="b")
            self.assertEqual(sent, 0)  # dry-run
        finally:
            c.close()

    def test_list_active_subscriptions_filters_disabled(self):
        uid, h = _create_user()
        client.post("/api/push/subscriptions", headers=h, json={
            "user_id": uid, "endpoint": "ep1", "p256dh": "p", "auth": "a",
        })
        # 두 번째 구독은 직접 disable
        c = _conn()
        try:
            c.execute(
                """INSERT INTO PushSubscription
                   (user_id, endpoint, p256dh, auth, enabled, created_at)
                   VALUES (?, ?, ?, ?, 0, datetime('now'))""",
                (uid, "ep2", "p2", "a2"),
            )
            c.commit()
            active = list_active_subscriptions(c, uid)
            self.assertEqual(len(active), 1)
            self.assertEqual(active[0]["endpoint"], "ep1")
        finally:
            c.close()


if __name__ == "__main__":
    unittest.main()
