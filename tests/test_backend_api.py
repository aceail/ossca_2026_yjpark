"""FastAPI backend integration tests — Tomorrow's You.

DB는 tmp file, app dependency override로 격리.
핵심 endpoint 12+ 테스트. P0-8: device_token Bearer 인증 자동 첨부.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# FastAPI / httpx
from fastapi.testclient import TestClient

# DB 격리를 위해 환경변수를 먼저 설정한 후 app import
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB_PATH = _tmp_db.name
_tmp_db.close()
os.environ["TOMORROW_YOU_DB"] = _TMP_DB_PATH

from backend.main import app
from backend.deps import get_db
from db import open_db, migrate
from persona import seed_builtin_prompts


def _make_test_conn():
    conn = sqlite3.connect(_TMP_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _get_test_db():
    conn = _make_test_conn()
    try:
        yield conn
    finally:
        conn.close()


app.dependency_overrides[get_db] = _get_test_db


def setUpModule():
    # 다른 테스트 모듈과 backend.main.app 공유 — override를 자기 DB로 재설정.
    os.environ["TOMORROW_YOU_DB"] = _TMP_DB_PATH
    app.dependency_overrides[get_db] = _get_test_db
    conn = open_db(_TMP_DB_PATH)
    migrate(conn)
    seed_builtin_prompts(conn)
    conn.close()


def tearDownModule():
    try:
        os.unlink(_TMP_DB_PATH)
    except Exception:
        pass


client = TestClient(app, raise_server_exceptions=True)


# ────────────────────────────────────────────────────────────────────
# P0-8 헬퍼: 사용자 생성 + 토큰 헤더
# ────────────────────────────────────────────────────────────────────


def _create_user() -> tuple[str, dict]:
    """사용자 + 토큰 헤더 dict 반환."""
    r = client.post("/api/users", json={})
    data = r.json()
    return data["user_id"], {"Authorization": f"Bearer {data['device_token']}"}


def _default_persona_id() -> int:
    # 인증 없이도 listing은 가능해야 한다고 보면 좋지만, 현재는 토큰 필요.
    # 가장 빠른 방법: 새 사용자 + 토큰으로 조회.
    _, h = _create_user()
    return client.get("/api/personas", headers=h).json()[0]["id"]


# ────────────────────────────────────────────────────────────────────
# Health
# ────────────────────────────────────────────────────────────────────


class TestHealth(unittest.TestCase):
    def test_health(self):
        r = client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")


# ────────────────────────────────────────────────────────────────────
# Users
# ────────────────────────────────────────────────────────────────────


class TestUsers(unittest.TestCase):
    def test_create_user_returns_token(self):
        r = client.post("/api/users", json={})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("user_id", data)
        self.assertIn("device_token", data)
        self.assertGreaterEqual(len(data["device_token"]), 32)

    def test_get_user_profile_requires_token(self):
        user_id, _ = _create_user()
        r = client.get(f"/api/users/{user_id}/profile")
        self.assertEqual(r.status_code, 401)

    def test_get_user_profile_with_token(self):
        user_id, h = _create_user()
        r = client.get(f"/api/users/{user_id}/profile", headers=h)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["user_id"], user_id)

    def test_get_user_profile_wrong_token(self):
        user_id, _ = _create_user()
        _, other_h = _create_user()
        r = client.get(f"/api/users/{user_id}/profile", headers=other_h)
        self.assertEqual(r.status_code, 401)


# ────────────────────────────────────────────────────────────────────
# Personas
# ────────────────────────────────────────────────────────────────────


class TestPersonas(unittest.TestCase):
    def test_list_personas_default(self):
        _, h = _create_user()
        r = client.get("/api/personas", headers=h)
        self.assertEqual(r.status_code, 200)
        names = [p["name"] for p in r.json()]
        self.assertIn("내일의 나", names)

    def test_list_personas_requires_token(self):
        r = client.get("/api/personas")
        self.assertEqual(r.status_code, 401)

    def test_list_personas_with_user(self):
        user_id, h = _create_user()
        r = client.get(f"/api/personas?user_id={user_id}", headers=h)
        self.assertEqual(r.status_code, 200)

    def test_list_personas_user_mismatch_forbidden(self):
        user_id, _ = _create_user()
        _, other_h = _create_user()
        r = client.get(f"/api/personas?user_id={user_id}", headers=other_h)
        self.assertEqual(r.status_code, 403)

    def test_create_custom_persona_audit_pass(self):
        user_id, h = _create_user()
        r = client.post("/api/personas/custom", headers=h, json={
            "user_id": user_id,
            "name": "나만의 친구",
            "perspective": "2nd",
            "tone_mode": "Witty",
            "voice_style": "친근하고 가벼운 톤",
            "greeting": "야, 뭐해?",
            "forbidden_topics": ["부모님"],
        })
        self.assertEqual(r.status_code, 201)

    def test_create_custom_persona_audit_fail(self):
        user_id, h = _create_user()
        r = client.post("/api/personas/custom", headers=h, json={
            "user_id": user_id,
            "name": "게으름뱅이 코치",
            "perspective": "2nd",
            "tone_mode": "Sharp",
            "voice_style": "직접적",
            "greeting": "일어나라",
        })
        self.assertEqual(r.status_code, 400)
        self.assertIn("violations", r.json()["detail"])

    def test_set_active_persona(self):
        user_id, h = _create_user()
        persona_id = client.get("/api/personas", headers=h).json()[0]["id"]
        r = client.post(
            f"/api/users/{user_id}/active-persona",
            headers=h,
            json={"persona_id": persona_id},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["active_persona_id"], persona_id)


# ────────────────────────────────────────────────────────────────────
# Onboarding
# ────────────────────────────────────────────────────────────────────


class TestOnboarding(unittest.TestCase):
    def test_onboarding_basic(self):
        user_id, h = _create_user()
        persona_id = client.get("/api/personas", headers=h).json()[0]["id"]
        r = client.post("/api/onboarding", headers=h, json={
            "user_id": user_id,
            "trigger_category": "업무",
            "avoidance_destination": "유튜브",
            "persona_id": persona_id,
        })
        self.assertEqual(r.status_code, 200)
        self.assertGreater(r.json()["completion_percent"], 0)

    def test_onboarding_sensitive_fear_anchor(self):
        user_id, h = _create_user()
        persona_id = client.get("/api/personas", headers=h).json()[0]["id"]
        client.post("/api/onboarding", headers=h, json={
            "user_id": user_id,
            "trigger_category": "학업",
            "avoidance_destination": "게임",
            "persona_id": persona_id,
            "fear_anchor": "부모의 기대와 다른 모습이 되는 것",
        })
        profile = client.get(f"/api/users/{user_id}/profile", headers=h).json()
        self.assertIn("부모의 기대와 다른 모습", profile["forbidden_topics"])


# ────────────────────────────────────────────────────────────────────
# Sessions
# ────────────────────────────────────────────────────────────────────


class TestSessions(unittest.TestCase):
    def _setup(self) -> tuple[str, dict]:
        user_id, h = _create_user()
        persona_id = client.get("/api/personas", headers=h).json()[0]["id"]
        client.post("/api/onboarding", headers=h, json={
            "user_id": user_id,
            "trigger_category": "업무",
            "avoidance_destination": "SNS",
            "persona_id": persona_id,
        })
        return user_id, h

    def test_create_session(self):
        user_id, h = self._setup()
        r = client.post("/api/sessions", headers=h, json={
            "user_id": user_id,
            "avoidance_input": "보고서 써야 하는데 유튜브 보는 중",
        })
        self.assertEqual(r.status_code, 201)

    def test_create_session_requires_token(self):
        user_id, _ = self._setup()
        r = client.post("/api/sessions", json={
            "user_id": user_id,
            "avoidance_input": "토큰 없음",
        })
        self.assertEqual(r.status_code, 401)

    def test_probe_endpoint(self):
        user_id, h = self._setup()
        r = client.post("/api/sessions", headers=h, json={
            "user_id": user_id,
            "avoidance_input": "발표 자료 못 만들고 있음",
        })
        sid = r.json()["session_id"]
        r2 = client.get(f"/api/sessions/{sid}/probe", headers=h)
        self.assertEqual(r2.status_code, 200)
        self.assertIn("question_id", r2.json())

    def test_decision_delete_cascade(self):
        user_id, h = self._setup()
        r = client.post("/api/sessions", headers=h, json={
            "user_id": user_id,
            "avoidance_input": "청소 미루는 중",
        })
        sid = r.json()["session_id"]
        r2 = client.post(f"/api/sessions/{sid}/decision", headers=h, json={"decision": "delete"})
        self.assertEqual(r2.status_code, 200)
        # 세션 재조회 시 토큰 검증 단계에서 미존재 → 401
        r3 = client.get(f"/api/sessions/{sid}/probe", headers=h)
        self.assertEqual(r3.status_code, 401)

    def test_delete_session_endpoint(self):
        user_id, h = self._setup()
        r = client.post("/api/sessions", headers=h, json={
            "user_id": user_id,
            "avoidance_input": "이메일 답장 못 하는 중",
        })
        sid = r.json()["session_id"]
        r2 = client.delete(f"/api/sessions/{sid}", headers=h)
        self.assertEqual(r2.status_code, 200)


# ────────────────────────────────────────────────────────────────────
# Regret
# ────────────────────────────────────────────────────────────────────


class TestRegret(unittest.TestCase):
    def _create_session(self) -> tuple[str, dict, int]:
        user_id, h = _create_user()
        persona_id = client.get("/api/personas", headers=h).json()[0]["id"]
        client.post("/api/onboarding", headers=h, json={
            "user_id": user_id,
            "trigger_category": "업무",
            "avoidance_destination": "SNS",
            "persona_id": persona_id,
        })
        r = client.post("/api/sessions", headers=h, json={
            "user_id": user_id,
            "avoidance_input": "숙제 안 하고 있음",
        })
        return user_id, h, r.json()["session_id"]

    def _create_scenario_card(self) -> tuple[dict, int]:
        _, h, sid = self._create_session()
        conn = _make_test_conn()
        cur = conn.execute(
            """INSERT INTO ScenarioCard
               (avoidance_session_id, card_type, fact, feeling, micro_action, created_at)
               VALUES (?, 'regret', 'fact', 'feeling', 'action', '2026-01-01T00:00:00+00:00')""",
            (sid,),
        )
        conn.commit()
        cid = cur.lastrowid
        conn.close()
        return h, cid

    def test_regret_record(self):
        _, h, sid = self._create_session()
        r = client.post(f"/api/sessions/{sid}/regret", headers=h, json={
            "intensity": 7,
            "free_text": "또 이랬네",
        })
        self.assertEqual(r.status_code, 201)

    def test_card_accuracy(self):
        h, cid = self._create_scenario_card()
        r = client.post(f"/api/scenario-cards/{cid}/accuracy", headers=h, json={"accuracy": 4})
        self.assertEqual(r.status_code, 201)

    def test_return_intent(self):
        h, cid = self._create_scenario_card()
        r = client.post(f"/api/scenario-cards/{cid}/return-intent", headers=h, json={"intent": 5})
        self.assertEqual(r.status_code, 201)


# ────────────────────────────────────────────────────────────────────
# Safety
# ────────────────────────────────────────────────────────────────────


class TestSafety(unittest.TestCase):
    def test_safety_trend_empty(self):
        user_id, h = _create_user()
        r = client.get(f"/api/users/{user_id}/safety-trend", headers=h)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["user_id"], user_id)

    def test_safety_snapshot_refresh(self):
        user_id, h = _create_user()
        r = client.post(f"/api/users/{user_id}/safety-snapshot/refresh", headers=h)
        self.assertEqual(r.status_code, 200)


# ────────────────────────────────────────────────────────────────────
# Tone Feedback
# ────────────────────────────────────────────────────────────────────


class TestToneFeedback(unittest.TestCase):
    def _create_card(self) -> tuple[dict, int]:
        user_id, h = _create_user()
        persona_id = client.get("/api/personas", headers=h).json()[0]["id"]
        client.post("/api/onboarding", headers=h, json={
            "user_id": user_id,
            "trigger_category": "업무",
            "avoidance_destination": "웹툰",
            "persona_id": persona_id,
        })
        r = client.post("/api/sessions", headers=h, json={
            "user_id": user_id,
            "avoidance_input": "코딩 안 함",
        })
        sid = r.json()["session_id"]
        conn = _make_test_conn()
        cur = conn.execute(
            """INSERT INTO ScenarioCard
               (avoidance_session_id, card_type, fact, feeling, micro_action, created_at)
               VALUES (?, 'regret', 'f', 'f', 'a', datetime('now'))""",
            (sid,),
        )
        conn.commit()
        cid = cur.lastrowid
        conn.close()
        return h, cid

    def test_tone_feedback(self):
        h, cid = self._create_card()
        r = client.post(f"/api/scenario-cards/{cid}/tone-feedback", headers=h, json={"kind": "too_hard"})
        self.assertEqual(r.status_code, 201)

    def test_tone_feedback_invalid_kind(self):
        h, cid = self._create_card()
        r = client.post(f"/api/scenario-cards/{cid}/tone-feedback", headers=h, json={"kind": "invalid_kind"})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
