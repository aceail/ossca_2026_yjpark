"""P0-15 agent tool consent gate — v0.3 sprint 8."""

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

from agent import (
    grant_consent,
    has_consent,
    list_consents,
    revoke_consent,
    ToolRouter,
)


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
    # 다른 모듈이 같은 backend.main.app을 import하면서
    # dependency_overrides[get_db]를 자기 DB로 덮어썼을 수 있으므로,
    # 본 모듈의 첫 테스트 직전에 자기 DB로 다시 set한다.
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


def _tool_id(name: str) -> int:
    c = _conn()
    try:
        row = c.execute("SELECT id FROM AgentTool WHERE name = ?", (name,)).fetchone()
        return row["id"]
    finally:
        c.close()


# ────────────────────────────────────────────────────────────────────
# Unit: grant / revoke / has
# ────────────────────────────────────────────────────────────────────


class TestConsentUnit(unittest.TestCase):
    def test_default_no_consent(self):
        user_id, _ = _create_user()
        c = _conn()
        try:
            tid = _tool_id("google_calendar.list_events")
            self.assertFalse(has_consent(c, user_id, tid))
        finally:
            c.close()

    def test_grant_then_has(self):
        user_id, _ = _create_user()
        c = _conn()
        try:
            tid = _tool_id("web_search.brave")
            grant_consent(c, user_id, tid)
            self.assertTrue(has_consent(c, user_id, tid))
        finally:
            c.close()

    def test_revoke_clears_consent(self):
        user_id, _ = _create_user()
        c = _conn()
        try:
            tid = _tool_id("local_files.recent")
            grant_consent(c, user_id, tid)
            revoke_consent(c, user_id, tid)
            self.assertFalse(has_consent(c, user_id, tid))
        finally:
            c.close()

    def test_re_grant_after_revoke(self):
        user_id, _ = _create_user()
        c = _conn()
        try:
            tid = _tool_id("web_search.brave")
            grant_consent(c, user_id, tid)
            revoke_consent(c, user_id, tid)
            grant_consent(c, user_id, tid)
            self.assertTrue(has_consent(c, user_id, tid))
        finally:
            c.close()

    def test_list_consents_includes_all_external(self):
        user_id, _ = _create_user()
        c = _conn()
        try:
            items = list_consents(c, user_id)
            names = {it["tool_name"] for it in items}
            self.assertIn("google_calendar.list_events", names)
            self.assertIn("web_search.brave", names)
            self.assertIn("local_files.recent", names)
            # 모두 미동의 상태
            self.assertTrue(all(not it["active"] for it in items))
        finally:
            c.close()


# ────────────────────────────────────────────────────────────────────
# ToolRouter consent gate
# ────────────────────────────────────────────────────────────────────


class TestToolRouterConsentGate(unittest.TestCase):
    def test_user_id_none_skips_gate(self):
        c = _conn()
        try:
            router = ToolRouter(c)
            tools = router.route("내일까지 보고서 마감")
            # 동의 없이도 매칭 (backward compat — 내부 호출 시)
            names = [t.name for t in tools]
            self.assertIn("google_calendar.list_events", names)
        finally:
            c.close()

    def test_user_id_with_no_consent_returns_empty(self):
        user_id, _ = _create_user()
        c = _conn()
        try:
            router = ToolRouter(c)
            tools = router.route("내일까지 보고서 마감", user_id=user_id)
            self.assertEqual(tools, [])
        finally:
            c.close()

    def test_user_id_with_consent_returns_tool(self):
        user_id, _ = _create_user()
        c = _conn()
        try:
            tid = _tool_id("google_calendar.list_events")
            grant_consent(c, user_id, tid)
            router = ToolRouter(c)
            tools = router.route("내일까지 보고서 마감", user_id=user_id)
            names = [t.name for t in tools]
            self.assertIn("google_calendar.list_events", names)
        finally:
            c.close()

    def test_partial_consent_returns_only_granted(self):
        user_id, _ = _create_user()
        c = _conn()
        try:
            grant_consent(c, user_id, _tool_id("web_search.brave"))
            router = ToolRouter(c)
            # 마감 → calendar(미동의), 검색 → web_search(동의)
            tools = router.route("마감 전에 자료 검색하자", user_id=user_id)
            names = [t.name for t in tools]
            self.assertIn("web_search.brave", names)
            self.assertNotIn("google_calendar.list_events", names)
        finally:
            c.close()


# ────────────────────────────────────────────────────────────────────
# Consent API
# ────────────────────────────────────────────────────────────────────


class TestConsentAPI(unittest.TestCase):
    def test_list_endpoint_returns_all_tools(self):
        user_id, h = _create_user()
        r = client.get(f"/api/users/{user_id}/agent-consents", headers=h)
        self.assertEqual(r.status_code, 200)
        names = {it["tool_name"] for it in r.json()["consents"]}
        self.assertIn("google_calendar.list_events", names)

    def test_grant_then_revoke(self):
        user_id, h = _create_user()
        tid = _tool_id("web_search.brave")
        r = client.post(f"/api/users/{user_id}/agent-consents/{tid}", headers=h)
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.json()["active"])
        r2 = client.delete(f"/api/users/{user_id}/agent-consents/{tid}", headers=h)
        self.assertEqual(r2.status_code, 200)
        self.assertFalse(r2.json()["active"])

    def test_grant_unknown_tool_404(self):
        user_id, h = _create_user()
        r = client.post(f"/api/users/{user_id}/agent-consents/99999", headers=h)
        self.assertEqual(r.status_code, 404)

    def test_consent_requires_token(self):
        user_id, _ = _create_user()
        tid = _tool_id("web_search.brave")
        r = client.post(f"/api/users/{user_id}/agent-consents/{tid}")
        self.assertEqual(r.status_code, 401)


if __name__ == "__main__":
    unittest.main()
