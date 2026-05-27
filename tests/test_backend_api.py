"""FastAPI backend integration tests — Tomorrow's You.

DB는 tmp file, app dependency override로 격리.
핵심 endpoint 12+ 테스트.
"""

from __future__ import annotations

import json
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
    """테스트용 격리 DB connection."""
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


# dependency override
app.dependency_overrides[get_db] = _get_test_db


def setUpModule():
    """전체 테스트 시작 전 DB 초기화."""
    conn = open_db(_TMP_DB_PATH)
    migrate(conn)
    seed_builtin_prompts(conn)
    conn.close()


def tearDownModule():
    """테스트 후 tmp DB 삭제."""
    try:
        os.unlink(_TMP_DB_PATH)
    except Exception:
        pass


client = TestClient(app, raise_server_exceptions=True)


class TestHealth(unittest.TestCase):
    def test_health(self):
        r = client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")


class TestUsers(unittest.TestCase):
    def test_create_user(self):
        """POST /api/users → user_id 반환."""
        r = client.post("/api/users", json={})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("user_id", data)
        self.assertIsInstance(data["user_id"], str)

    def test_get_user_profile(self):
        """GET /api/users/{user_id}/profile → UserProfile."""
        r = client.post("/api/users", json={})
        user_id = r.json()["user_id"]

        r2 = client.get(f"/api/users/{user_id}/profile")
        self.assertEqual(r2.status_code, 200)
        data = r2.json()
        self.assertEqual(data["user_id"], user_id)
        self.assertIn("completion_percent", data)

    def test_get_profile_not_found(self):
        r = client.get("/api/users/nonexistent-user/profile")
        self.assertEqual(r.status_code, 404)


class TestPersonas(unittest.TestCase):
    def test_list_personas_default(self):
        """GET /api/personas → 5 default 페르소나."""
        r = client.get("/api/personas")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertGreaterEqual(len(data), 5)
        names = [p["name"] for p in data]
        self.assertIn("내일의 나", names)

    def test_list_personas_with_user(self):
        """GET /api/personas?user_id=X → 5 default + 커스텀."""
        r = client.post("/api/users", json={})
        user_id = r.json()["user_id"]
        r2 = client.get(f"/api/personas?user_id={user_id}")
        self.assertEqual(r2.status_code, 200)

    def test_create_custom_persona_audit_pass(self):
        """POST /api/personas/custom — audit 통과 시 201 + persona_id."""
        r = client.post("/api/users", json={})
        user_id = r.json()["user_id"]

        r2 = client.post("/api/personas/custom", json={
            "user_id": user_id,
            "name": "나만의 친구",
            "perspective": "2nd",
            "tone_mode": "Witty",
            "voice_style": "친근하고 가벼운 톤",
            "greeting": "야, 뭐해?",
            "forbidden_topics": ["부모님"],
        })
        self.assertEqual(r2.status_code, 201)
        self.assertIn("persona_id", r2.json())

    def test_create_custom_persona_audit_fail(self):
        """POST /api/personas/custom — audit 실패 시 400 + violations."""
        r = client.post("/api/users", json={})
        user_id = r.json()["user_id"]

        r2 = client.post("/api/personas/custom", json={
            "user_id": user_id,
            "name": "게으름뱅이 코치",  # '게으름' 위반
            "perspective": "2nd",
            "tone_mode": "Sharp",
            "voice_style": "직접적",
            "greeting": "일어나라",
        })
        self.assertEqual(r2.status_code, 400)
        detail = r2.json()["detail"]
        self.assertIn("violations", detail)

    def test_set_active_persona(self):
        """POST /api/users/{user_id}/active-persona."""
        r = client.post("/api/users", json={})
        user_id = r.json()["user_id"]

        # default persona id
        personas = client.get("/api/personas").json()
        persona_id = personas[0]["id"]

        r2 = client.post(f"/api/users/{user_id}/active-persona", json={"persona_id": persona_id})
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["active_persona_id"], persona_id)


class TestOnboarding(unittest.TestCase):
    def _create_user(self) -> str:
        return client.post("/api/users", json={}).json()["user_id"]

    def _default_persona_id(self) -> int:
        return client.get("/api/personas").json()[0]["id"]

    def test_onboarding_basic(self):
        """POST /api/onboarding — slots 갱신 + completion_percent."""
        user_id = self._create_user()
        persona_id = self._default_persona_id()

        r = client.post("/api/onboarding", json={
            "user_id": user_id,
            "trigger_category": "업무",
            "avoidance_destination": "유튜브",
            "persona_id": persona_id,
        })
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertGreater(data["completion_percent"], 0)

    def test_onboarding_sensitive_fear_anchor(self):
        """fear_anchor에 '부모의 기대' 포함 시 forbidden_topics 자동 추가."""
        user_id = self._create_user()
        persona_id = self._default_persona_id()

        client.post("/api/onboarding", json={
            "user_id": user_id,
            "trigger_category": "학업",
            "avoidance_destination": "게임",
            "persona_id": persona_id,
            "fear_anchor": "부모의 기대와 다른 모습이 되는 것",
        })

        profile = client.get(f"/api/users/{user_id}/profile").json()
        self.assertIn("부모의 기대와 다른 모습", profile["forbidden_topics"])


class TestSessions(unittest.TestCase):
    def _setup(self):
        r = client.post("/api/users", json={})
        user_id = r.json()["user_id"]
        personas = client.get("/api/personas").json()
        persona_id = personas[0]["id"]
        client.post("/api/onboarding", json={
            "user_id": user_id,
            "trigger_category": "업무",
            "avoidance_destination": "SNS",
            "persona_id": persona_id,
        })
        return user_id

    def test_create_session(self):
        """POST /api/sessions → session_id."""
        user_id = self._setup()
        r = client.post("/api/sessions", json={
            "user_id": user_id,
            "avoidance_input": "보고서 써야 하는데 유튜브 보는 중",
        })
        self.assertEqual(r.status_code, 201)
        self.assertIn("session_id", r.json())

    def test_probe_endpoint(self):
        """GET /api/sessions/{id}/probe → question or null."""
        user_id = self._setup()
        r = client.post("/api/sessions", json={
            "user_id": user_id,
            "avoidance_input": "발표 자료 못 만들고 있음",
        })
        session_id = r.json()["session_id"]
        r2 = client.get(f"/api/sessions/{session_id}/probe")
        self.assertEqual(r2.status_code, 200)
        # question_id가 있거나 없거나 (Phase에 따라)
        data = r2.json()
        self.assertIn("question_id", data)

    def test_decision_delete_cascade(self):
        """POST /api/sessions/{id}/decision decision=delete → 세션 삭제."""
        user_id = self._setup()
        r = client.post("/api/sessions", json={
            "user_id": user_id,
            "avoidance_input": "청소 미루는 중",
        })
        session_id = r.json()["session_id"]

        r2 = client.post(f"/api/sessions/{session_id}/decision", json={"decision": "delete"})
        self.assertEqual(r2.status_code, 200)
        self.assertTrue(r2.json()["deleted"])

        # 세션 재조회 시 404
        r3 = client.get(f"/api/sessions/{session_id}/probe")
        self.assertEqual(r3.status_code, 404)

    def test_delete_session_endpoint(self):
        """DELETE /api/sessions/{id} — Self-Destruct cascade."""
        user_id = self._setup()
        r = client.post("/api/sessions", json={
            "user_id": user_id,
            "avoidance_input": "이메일 답장 못 하는 중",
        })
        session_id = r.json()["session_id"]

        r2 = client.delete(f"/api/sessions/{session_id}")
        self.assertEqual(r2.status_code, 200)
        self.assertTrue(r2.json()["deleted"])


class TestRegret(unittest.TestCase):
    def _create_session(self) -> tuple[str, int]:
        r = client.post("/api/users", json={})
        user_id = r.json()["user_id"]
        personas = client.get("/api/personas").json()
        client.post("/api/onboarding", json={
            "user_id": user_id,
            "trigger_category": "업무",
            "avoidance_destination": "SNS",
            "persona_id": personas[0]["id"],
        })
        r2 = client.post("/api/sessions", json={
            "user_id": user_id,
            "avoidance_input": "숙제 안 하고 있음",
        })
        return user_id, r2.json()["session_id"]

    def test_regret_record(self):
        """POST /api/sessions/{id}/regret → regret_id."""
        _, session_id = self._create_session()
        r = client.post(f"/api/sessions/{session_id}/regret", json={
            "intensity": 7,
            "free_text": "또 이랬네",
        })
        self.assertEqual(r.status_code, 201)
        self.assertIn("regret_id", r.json())

    def _create_scenario_card(self) -> tuple[int, int]:
        """시나리오 카드를 직접 DB에 삽입해 card_id 반환."""
        _, session_id = self._create_session()
        conn = _make_test_conn()
        now = "2026-01-01T00:00:00+00:00"
        cur = conn.execute(
            """INSERT INTO ScenarioCard
               (avoidance_session_id, card_type, fact, feeling, micro_action, created_at)
               VALUES (?, 'regret', 'fact', 'feeling', 'action', ?)""",
            (session_id, now),
        )
        conn.commit()
        card_id = cur.lastrowid
        conn.close()
        return session_id, card_id

    def test_card_accuracy(self):
        """POST /api/scenario-cards/{id}/accuracy → evaluation_id."""
        _, card_id = self._create_scenario_card()
        r = client.post(f"/api/scenario-cards/{card_id}/accuracy", json={"accuracy": 4})
        self.assertEqual(r.status_code, 201)
        self.assertIn("evaluation_id", r.json())

    def test_return_intent(self):
        """POST /api/scenario-cards/{id}/return-intent → evaluation_id."""
        _, card_id = self._create_scenario_card()
        r = client.post(f"/api/scenario-cards/{card_id}/return-intent", json={"intent": 5})
        self.assertEqual(r.status_code, 201)
        self.assertIn("evaluation_id", r.json())


class TestSafety(unittest.TestCase):
    def _create_user(self) -> str:
        return client.post("/api/users", json={}).json()["user_id"]

    def test_safety_trend_empty(self):
        """GET /api/users/{id}/safety-trend → 빈 weeks."""
        user_id = self._create_user()
        r = client.get(f"/api/users/{user_id}/safety-trend")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["user_id"], user_id)
        self.assertIsInstance(r.json()["weeks"], list)

    def test_safety_snapshot_refresh(self):
        """POST /api/users/{id}/safety-snapshot/refresh."""
        user_id = self._create_user()
        r = client.post(f"/api/users/{user_id}/safety-snapshot/refresh")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["refreshed"])


class TestToneFeedback(unittest.TestCase):
    def _create_card(self) -> int:
        r = client.post("/api/users", json={})
        user_id = r.json()["user_id"]
        personas = client.get("/api/personas").json()
        client.post("/api/onboarding", json={
            "user_id": user_id,
            "trigger_category": "업무",
            "avoidance_destination": "웹툰",
            "persona_id": personas[0]["id"],
        })
        r2 = client.post("/api/sessions", json={
            "user_id": user_id,
            "avoidance_input": "코딩 안 함",
        })
        session_id = r2.json()["session_id"]
        conn = _make_test_conn()
        cur = conn.execute(
            """INSERT INTO ScenarioCard
               (avoidance_session_id, card_type, fact, feeling, micro_action, created_at)
               VALUES (?, 'regret', 'f', 'f', 'a', datetime('now'))""",
            (session_id,),
        )
        conn.commit()
        card_id = cur.lastrowid
        conn.close()
        return card_id

    def test_tone_feedback(self):
        """POST /api/scenario-cards/{id}/tone-feedback → recorded."""
        card_id = self._create_card()
        r = client.post(f"/api/scenario-cards/{card_id}/tone-feedback", json={"kind": "too_hard"})
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.json()["recorded"])

    def test_tone_feedback_invalid_kind(self):
        """잘못된 kind → 400."""
        card_id = self._create_card()
        r = client.post(f"/api/scenario-cards/{card_id}/tone-feedback", json={"kind": "invalid_kind"})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
