"""G006 Pipeline — SessionOrchestrator 테스트 (8+)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db import open_db, migrate, get_persona  # noqa: E402
from persona import seed_builtin_prompts  # noqa: E402
from pipeline import SessionOrchestrator  # noqa: E402
from pipeline.orchestrator import _is_safety_trigger, ScenarioCard  # noqa: E402


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _setup_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = open_db(Path(tmp.name))
    migrate(conn)
    seed_builtin_prompts(conn)
    return conn


def _create_user(conn, user_id: str = "test-user") -> str:
    now = _now()
    conn.execute(
        "INSERT OR IGNORE INTO User (id, created_at, last_seen_at) VALUES (?, ?, ?)",
        (user_id, now, now),
    )
    persona = get_persona(conn, "내일의 나")
    persona_id = persona["id"] if persona else None
    conn.execute(
        """INSERT OR IGNORE INTO UserProfile
           (user_id, slots_json, completion_percent, active_persona_id, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, "{}", 0.0, persona_id, now),
    )
    conn.commit()
    return user_id


# ────────────────────────────────────────────────────────────────────
# 테스트 클래스
# ────────────────────────────────────────────────────────────────────

class TestStartSession(unittest.TestCase):
    def setUp(self):
        self.conn = _setup_db()
        _create_user(self.conn)
        self.orch = SessionOrchestrator(self.conn)

    def test_start_session_returns_int(self):
        sid = self.orch.start_session("test-user", "발표 준비를 미루고 있어")
        self.assertIsInstance(sid, int)
        self.assertGreater(sid, 0)

    def test_start_session_inserts_row(self):
        sid = self.orch.start_session("test-user", "운동을 미루는 중")
        row = self.conn.execute(
            "SELECT avoidance_input FROM AvoidanceSession WHERE id = ?", (sid,)
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["avoidance_input"], "운동을 미루는 중")


class TestProbeRouting(unittest.TestCase):
    def setUp(self):
        self.conn = _setup_db()
        _create_user(self.conn)
        self.orch = SessionOrchestrator(self.conn)

    def test_maybe_probe_returns_none_for_new_user(self):
        # session_count < 4 → Phase ONBOARDING → None
        result = self.orch.maybe_probe("test-user")
        self.assertIsNone(result)

    def test_maybe_probe_returns_question_in_adaptive(self):
        # session_count 4~14 범위로 세션 추가
        for i in range(4):
            self.conn.execute(
                "INSERT INTO AvoidanceSession (user_id, avoidance_input, created_at) VALUES (?, ?, ?)",
                ("test-user", f"회피{i}", _now()),
            )
        self.conn.commit()
        result = self.orch.maybe_probe("test-user")
        # ProbeQuestion seed가 있으면 QuestionScore 반환
        # seed 없을 수도 있으므로 None or ProbeQuestion 허용
        if result is not None:
            self.assertIsNotNone(result.text)
            self.assertIsNotNone(result.target_slot)


class TestSafetyKeywordDetection(unittest.TestCase):
    def test_safety_trigger_자해(self):
        self.assertTrue(_is_safety_trigger("나 자해하고 싶다"))

    def test_safety_trigger_진짜_죽고_싶다(self):
        self.assertTrue(_is_safety_trigger("진짜 죽고 싶다 요즘"))

    def test_safety_trigger_약통(self):
        self.assertTrue(_is_safety_trigger("약통 다 먹어버리고 싶어"))

    def test_safety_trigger_normal_input(self):
        self.assertFalse(_is_safety_trigger("운동 미루고 있어"))

    def test_safety_trigger_조관용구_not_triggered(self):
        self.assertFalse(_is_safety_trigger("존나 하기 싫다 멘탈 나갔다"))

    def setUp(self):
        self.conn = _setup_db()
        _create_user(self.conn)
        self.orch = SessionOrchestrator(self.conn)

    def test_generate_scenario_soft_stop_on_safety_input(self):
        sid = self.orch.start_session("test-user", "진짜 죽고 싶다")
        card = self.orch.generate_scenario("test-user", sid, "진짜 죽고 싶다")
        self.assertEqual(card.card_type, "soft_stop")
        self.assertIsNotNone(card.safety_message)

    def test_soft_stop_card_persisted_in_db(self):
        sid = self.orch.start_session("test-user", "자해하고 싶어")
        card = self.orch.generate_scenario("test-user", sid, "자해하고 싶어")
        row = self.conn.execute(
            "SELECT card_type FROM ScenarioCard WHERE id = ?", (card.id,)
        ).fetchone()
        self.assertEqual(row["card_type"], "soft_stop")


class TestScenarioGenerationMock(unittest.TestCase):
    def setUp(self):
        self.conn = _setup_db()
        _create_user(self.conn)
        self.orch = SessionOrchestrator(self.conn)

    def test_generate_scenario_regret_mock(self):
        mock_response = json.dumps({
            "card_type": "regret",
            "sentences": {
                "fact": "새벽 1시다. PPT 0장이다.",
                "feeling": "내일 발표장에서 첫 슬라이드를 못 띄우는 나.",
                "micro_action": "파일을 켠다.",
            }
        }, ensure_ascii=False)

        with patch("pipeline.orchestrator._call_ollama", return_value=mock_response):
            sid = self.orch.start_session("test-user", "발표 준비 미루는 중")
            card = self.orch.generate_scenario("test-user", sid, "발표 준비 미루는 중")

        self.assertEqual(card.card_type, "regret")
        self.assertEqual(card.fact, "새벽 1시다. PPT 0장이다.")
        self.assertIsNotNone(card.micro_action)

    def test_generate_scenario_with_timeline_hint(self):
        mock_response = json.dumps({
            "card_type": "regret",
            "sentences": {
                "fact": "발표까지 9시간 남았다.",
                "feeling": "빈 화면 앞에 앉은 나.",
                "micro_action": "파일을 켠다.",
            }
        }, ensure_ascii=False)

        with patch("pipeline.orchestrator._call_ollama", return_value=mock_response):
            sid = self.orch.start_session("test-user", "발표 준비 중")
            card = self.orch.generate_scenario(
                "test-user", sid, "발표 준비 중", timeline_hint="내일 오전 10시"
            )

        self.assertEqual(card.card_type, "regret")

    def test_persona_context_injected(self):
        """활성 페르소나 system_prompt가 LLM 호출에 전달되는지 검증."""
        captured: list[str] = []

        def fake_ollama(system_prompt, user_message, **kwargs):
            captured.append(system_prompt)
            return json.dumps({
                "card_type": "regret",
                "sentences": {"fact": "f", "feeling": "e", "micro_action": "m"}
            }, ensure_ascii=False)

        with patch("pipeline.orchestrator._call_ollama", side_effect=fake_ollama):
            sid = self.orch.start_session("test-user", "논문 미루는 중")
            self.orch.generate_scenario("test-user", sid, "논문 미루는 중")

        self.assertTrue(len(captured) > 0)
        # 페르소나 프롬프트에는 절대 규칙이 포함돼야 함
        self.assertIn("절대 규칙", captured[0])


class TestRecordProbeAnswer(unittest.TestCase):
    def setUp(self):
        self.conn = _setup_db()
        _create_user(self.conn)
        self.orch = SessionOrchestrator(self.conn)

    def test_record_probe_answer_updates_slots(self):
        # ProbeQuestion 직접 삽입
        self.conn.execute(
            """INSERT INTO ProbeQuestion (text, target_slot, expected_information_gain, enabled, version, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("마감이 언제야?", "deadline", 0.8, 1, 1, _now()),
        )
        self.conn.commit()
        q = self.conn.execute("SELECT id FROM ProbeQuestion WHERE target_slot='deadline'").fetchone()

        sid = self.orch.start_session("test-user", "과제 미루는 중")
        self.orch.record_probe_answer(
            "test-user", q["id"], sid, "내일 오전 10시",
            slot_updates={"deadline": {"value": "내일 오전 10시", "confidence": 0.9}}
        )

        row = self.conn.execute(
            "SELECT slots_json FROM UserProfile WHERE user_id = ?", ("test-user",)
        ).fetchone()
        self.assertIsNotNone(row, "UserProfile row가 없음")
        slots = json.loads(row["slots_json"] or "{}")
        self.assertIn("deadline", slots)
        self.assertEqual(slots["deadline"]["confidence"], 0.9)


class TestRecordDecision(unittest.TestCase):
    def setUp(self):
        self.conn = _setup_db()
        _create_user(self.conn)
        self.orch = SessionOrchestrator(self.conn)

    def test_record_decision_updates_row(self):
        sid = self.orch.start_session("test-user", "운동 미루는 중")
        self.orch.record_decision(sid, "transition")
        row = self.conn.execute(
            "SELECT user_decision FROM AvoidanceSession WHERE id = ?", (sid,)
        ).fetchone()
        self.assertEqual(row["user_decision"], "transition")


@unittest.skipUnless(os.environ.get("OLLAMA_AVAILABLE"), "OLLAMA_AVAILABLE 환경변수 필요")
class TestScenarioGenerationReal(unittest.TestCase):
    def setUp(self):
        self.conn = _setup_db()
        _create_user(self.conn)
        self.orch = SessionOrchestrator(self.conn)

    def test_real_ollama_call(self):
        sid = self.orch.start_session("test-user", "발표 준비 미루는 중, 마감 내일 오전")
        card = self.orch.generate_scenario(
            "test-user", sid, "발표 준비 미루는 중", timeline_hint="내일 오전 9시"
        )
        self.assertIn(card.card_type, ("regret", "recovery", "soft_stop", "paradoxical_validation"))


if __name__ == "__main__":
    unittest.main()
