"""P0-9 Slow Harm signal_level 등급화 + P0-24 Moral Licensing 너지 — v0.3 sprint 1."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db import open_db, migrate, get_persona  # noqa: E402
from persona import seed_builtin_prompts  # noqa: E402
from pipeline import SessionOrchestrator  # noqa: E402
from pipeline.orchestrator import (  # noqa: E402
    MORAL_LICENSING_NUDGE,
    MORAL_LICENSING_THRESHOLD,
)
from regret import compute_signal_level  # noqa: E402


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _setup() -> tuple:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = open_db(Path(tmp.name))
    migrate(conn)
    seed_builtin_prompts(conn)

    user_id = "signal-user"
    now = _now_iso()
    conn.execute(
        "INSERT OR IGNORE INTO User (id, created_at, last_seen_at) VALUES (?, ?, ?)",
        (user_id, now, now),
    )
    persona = get_persona(conn, "내일의 나")
    conn.execute(
        """INSERT OR IGNORE INTO UserProfile
           (user_id, slots_json, completion_percent, active_persona_id, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, "{}", 0.0, persona["id"] if persona else None, now),
    )
    conn.commit()
    return conn, user_id


def _seed_avoidance(conn, user_id: str, text: str, when: datetime | None = None) -> int:
    ts = (when or datetime.now(timezone.utc)).isoformat()
    cur = conn.execute(
        "INSERT INTO AvoidanceSession (user_id, avoidance_input, created_at) VALUES (?, ?, ?)",
        (user_id, text, ts),
    )
    conn.commit()
    return cur.lastrowid


# ────────────────────────────────────────────────────────────────────
# P0-9: compute_signal_level 등급화
# ────────────────────────────────────────────────────────────────────


class TestComputeSignalLevel(unittest.TestCase):
    def test_no_data_returns_normal(self):
        conn, user_id = _setup()
        self.assertEqual(compute_signal_level(conn, user_id), "normal")

    def test_below_elevated_threshold_returns_normal(self):
        conn, user_id = _setup()
        # blame 2 < 3 (한심 x2), identity 1 < 2 (원래 그런 x1 — blame 리스트엔 없음)
        _seed_avoidance(conn, user_id, "오늘 한심하다. 한심하다.")
        _seed_avoidance(conn, user_id, "원래 그런 거지 뭐")
        self.assertEqual(compute_signal_level(conn, user_id), "normal")

    def test_blame_at_elevated_threshold(self):
        conn, user_id = _setup()
        # blame 3 → elevated 진입
        _seed_avoidance(conn, user_id, "한심 한심 한심")
        self.assertEqual(compute_signal_level(conn, user_id), "elevated")

    def test_identity_failure_triggers_elevated(self):
        conn, user_id = _setup()
        # identity 2 → elevated
        _seed_avoidance(conn, user_id, "어차피 안 돼. 원래 그런 사람이야.")
        self.assertEqual(compute_signal_level(conn, user_id), "elevated")

    def test_blame_burst_triggers_high(self):
        conn, user_id = _setup()
        # blame 8 → high
        _seed_avoidance(conn, user_id, "한심 " * 8)
        self.assertEqual(compute_signal_level(conn, user_id), "high")

    def test_decision_asymmetry_high_wins_over_elevated(self):
        conn, user_id = _setup()
        # blame 8 (high) + identity 2 (elevated) → high 우선
        _seed_avoidance(conn, user_id, "한심 " * 8 + " 어차피 원래 그런")
        self.assertEqual(compute_signal_level(conn, user_id), "high")


# ────────────────────────────────────────────────────────────────────
# P0-9: generate_scenario 직전 신호 게이트
# ────────────────────────────────────────────────────────────────────


class TestGenerateScenarioSlowHarmGate(unittest.TestCase):
    def test_high_signal_forces_soft_stop_without_llm(self):
        conn, user_id = _setup()
        # 누적 자기비난으로 high 신호
        _seed_avoidance(conn, user_id, "한심 " * 8)

        orch = SessionOrchestrator(conn)
        sid = orch.start_session(user_id, "오늘 또 미뤘다")

        # LLM 호출이 일어나선 안 됨
        with patch("pipeline.orchestrator._call_ollama") as mock_llm:
            card = orch.generate_scenario(user_id, sid, "오늘 또 미뤘다")
            mock_llm.assert_not_called()

        self.assertEqual(card.card_type, "soft_stop")
        self.assertEqual(card.signal_level, "high")
        self.assertIsNotNone(card.safety_message)

    def test_elevated_signal_injects_safety_prefix_to_prompt(self):
        conn, user_id = _setup()
        # elevated 신호 (blame 3)
        _seed_avoidance(conn, user_id, "한심 한심 한심")

        orch = SessionOrchestrator(conn)
        sid = orch.start_session(user_id, "운동 미루는 중")

        captured: list[str] = []

        def fake_ollama(system_prompt, user_message, **kwargs):
            captured.append(system_prompt)
            return json.dumps({
                "card_type": "regret",
                "sentences": {"fact": "f", "feeling": "e", "micro_action": "m"},
            }, ensure_ascii=False)

        with patch("pipeline.orchestrator._call_ollama", side_effect=fake_ollama):
            card = orch.generate_scenario(user_id, sid, "운동 미루는 중")

        self.assertEqual(card.signal_level, "elevated")
        self.assertTrue(captured)
        self.assertIn("[안전 모드]", captured[0])

    def test_normal_signal_does_not_inject_prefix(self):
        conn, user_id = _setup()
        orch = SessionOrchestrator(conn)
        sid = orch.start_session(user_id, "발표 준비 미루는 중")

        captured: list[str] = []

        def fake_ollama(system_prompt, user_message, **kwargs):
            captured.append(system_prompt)
            return json.dumps({
                "card_type": "regret",
                "sentences": {"fact": "f", "feeling": "e", "micro_action": "m"},
            }, ensure_ascii=False)

        with patch("pipeline.orchestrator._call_ollama", side_effect=fake_ollama):
            card = orch.generate_scenario(user_id, sid, "발표 준비 미루는 중")

        self.assertEqual(card.signal_level, "normal")
        self.assertTrue(captured)
        self.assertNotIn("[안전 모드]", captured[0])


# ────────────────────────────────────────────────────────────────────
# P0-24: Moral Licensing 너지 (24h 사용 빈도)
# ────────────────────────────────────────────────────────────────────


class TestMoralLicensingNudge(unittest.TestCase):
    def _generate_once(self, conn, user_id: str):
        orch = SessionOrchestrator(conn)
        sid = orch.start_session(user_id, "오늘 또 미뤘다")
        mock_resp = json.dumps({
            "card_type": "regret",
            "sentences": {"fact": "f", "feeling": "e", "micro_action": "m"},
        }, ensure_ascii=False)
        with patch("pipeline.orchestrator._call_ollama", return_value=mock_resp):
            return orch.generate_scenario(user_id, sid, "오늘 또 미뤘다")

    def test_below_threshold_no_nudge(self):
        conn, user_id = _setup()
        # 4번 (임계 5 미만)
        for _ in range(MORAL_LICENSING_THRESHOLD - 2):
            _seed_avoidance(conn, user_id, "테스트 회피")

        card = self._generate_once(conn, user_id)
        # 자기자신 세션 1개 + 4개 = 5 → 임계 도달 (경계 테스트)
        # 실제로는 _generate_once 안의 start_session도 24h 카운트에 포함됨
        # 따라서 임계 미만을 명시적으로 보장: 4-1=3개만 seed
        # (위 루프는 3번 돔: 5-2=3)
        # → seeded 3 + this session 1 = 4 < 5 → nudge None
        self.assertIsNone(card.moral_licensing_nudge)

    def test_at_threshold_triggers_nudge(self):
        conn, user_id = _setup()
        # 사전 4개 + 본 세션 1개 = 5 → 임계 도달
        for _ in range(MORAL_LICENSING_THRESHOLD - 1):
            _seed_avoidance(conn, user_id, "테스트 회피")

        card = self._generate_once(conn, user_id)
        self.assertEqual(card.moral_licensing_nudge, MORAL_LICENSING_NUDGE)

    def test_old_sessions_outside_24h_not_counted(self):
        conn, user_id = _setup()
        # 25시간 전 5개 (24h 윈도우 밖)
        long_ago = datetime.now(timezone.utc) - timedelta(hours=25)
        for _ in range(MORAL_LICENSING_THRESHOLD):
            _seed_avoidance(conn, user_id, "오래된 회피", when=long_ago)

        card = self._generate_once(conn, user_id)
        # 본 세션 1개만 24h 내 → nudge None
        self.assertIsNone(card.moral_licensing_nudge)


if __name__ == "__main__":
    unittest.main()
