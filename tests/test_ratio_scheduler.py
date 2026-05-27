"""P0-11 두 얼굴 비율 스케줄러 — recommend_card_type + orchestrator 통합."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db import open_db, migrate, get_persona  # noqa: E402
from persona import seed_builtin_prompts  # noqa: E402
from pipeline import SessionOrchestrator  # noqa: E402
from regret import build_ratio_hint, recommend_card_type  # noqa: E402
from regret.ratio import RATIO_LOOKBACK  # noqa: E402


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _setup():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = open_db(Path(tmp.name))
    migrate(conn)
    seed_builtin_prompts(conn)

    user_id = "ratio-user"
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


def _seed_card(conn, user_id: str, card_type: str) -> None:
    now = _now_iso()
    cur = conn.execute(
        "INSERT INTO AvoidanceSession (user_id, avoidance_input, created_at) VALUES (?, ?, ?)",
        (user_id, "seed", now),
    )
    sid = cur.lastrowid
    conn.execute(
        """INSERT INTO ScenarioCard
           (avoidance_session_id, card_type, fact, feeling, micro_action, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (sid, card_type, "f", "e", "m", now),
    )
    conn.commit()


# ────────────────────────────────────────────────────────────────────
# recommend_card_type 단위
# ────────────────────────────────────────────────────────────────────


class TestRecommendCardType(unittest.TestCase):
    def test_insufficient_samples_returns_auto(self):
        conn, user_id = _setup()
        for _ in range(RATIO_LOOKBACK - 1):
            _seed_card(conn, user_id, "regret")
        self.assertEqual(recommend_card_type(conn, user_id), "auto")

    def test_regret_skew_recommends_recovery(self):
        conn, user_id = _setup()
        # 5개 중 4개 regret → 0.8 >= 0.7 → recovery 권장
        for _ in range(4):
            _seed_card(conn, user_id, "regret")
        _seed_card(conn, user_id, "recovery")
        self.assertEqual(recommend_card_type(conn, user_id), "recovery")

    def test_recovery_skew_recommends_regret(self):
        conn, user_id = _setup()
        for _ in range(4):
            _seed_card(conn, user_id, "recovery")
        _seed_card(conn, user_id, "regret")
        self.assertEqual(recommend_card_type(conn, user_id), "regret")

    def test_balanced_returns_auto(self):
        conn, user_id = _setup()
        # 3:2 → 0.6 < 0.7 → auto
        for _ in range(3):
            _seed_card(conn, user_id, "regret")
        for _ in range(2):
            _seed_card(conn, user_id, "recovery")
        self.assertEqual(recommend_card_type(conn, user_id), "auto")

    def test_soft_stop_excluded_from_denominator(self):
        conn, user_id = _setup()
        # regret 3 + soft_stop 2 — soft_stop은 무시 → 표본 3 < 5 → auto
        for _ in range(3):
            _seed_card(conn, user_id, "regret")
        for _ in range(2):
            _seed_card(conn, user_id, "soft_stop")
        self.assertEqual(recommend_card_type(conn, user_id), "auto")

    def test_only_latest_N_considered(self):
        conn, user_id = _setup()
        # 오래된 regret 10개 + 최근 recovery 5개 → 최근 5 = all recovery → regret 권장
        for _ in range(10):
            _seed_card(conn, user_id, "regret")
        for _ in range(5):
            _seed_card(conn, user_id, "recovery")
        self.assertEqual(recommend_card_type(conn, user_id), "regret")


# ────────────────────────────────────────────────────────────────────
# build_ratio_hint
# ────────────────────────────────────────────────────────────────────


class TestBuildRatioHint(unittest.TestCase):
    def test_auto_returns_none(self):
        self.assertIsNone(build_ratio_hint("auto"))

    def test_recovery_hint_mentions_recovery(self):
        hint = build_ratio_hint("recovery")
        self.assertIsNotNone(hint)
        self.assertIn("recovery", hint)

    def test_regret_hint_mentions_regret(self):
        hint = build_ratio_hint("regret")
        self.assertIsNotNone(hint)
        self.assertIn("regret", hint)


# ────────────────────────────────────────────────────────────────────
# Orchestrator 통합 — hint 주입 vs 안전 우선
# ────────────────────────────────────────────────────────────────────


class TestRatioHintInjection(unittest.TestCase):
    def test_regret_skew_injects_recovery_hint_into_prompt(self):
        """regret 비율이 임계 이상이면 system_prompt에 recovery 권장 hint 주입.

        ratio skew는 failure_imagery_ratio와 동치이므로 elevated가 같이 켜질 수
        있지만, ratio hint 자체는 보장돼야 한다.
        """
        conn, user_id = _setup()
        for _ in range(4):
            _seed_card(conn, user_id, "regret")
        _seed_card(conn, user_id, "recovery")

        orch = SessionOrchestrator(conn)
        sid = orch.start_session(user_id, "오늘도 미루는 중")

        captured: list[str] = []

        def fake_ollama(system_prompt, user_message, **kwargs):
            captured.append(system_prompt)
            return json.dumps({
                "card_type": "recovery",
                "sentences": {"fact": "f", "feeling": "e", "micro_action": "m"},
            }, ensure_ascii=False)

        with patch("pipeline.orchestrator._call_ollama", side_effect=fake_ollama):
            orch.generate_scenario(user_id, sid, "오늘도 미루는 중")

        self.assertTrue(captured, "LLM 호출이 일어나야 함 (high 신호 아님)")
        self.assertIn("[비율 권장]", captured[0])
        self.assertIn("recovery", captured[0])

    def test_balanced_history_does_not_inject_hint(self):
        conn, user_id = _setup()
        # 표본 부족 → auto → hint 없음
        orch = SessionOrchestrator(conn)
        sid = orch.start_session(user_id, "발표 미루는 중")

        captured: list[str] = []

        def fake_ollama(system_prompt, user_message, **kwargs):
            captured.append(system_prompt)
            return json.dumps({
                "card_type": "regret",
                "sentences": {"fact": "f", "feeling": "e", "micro_action": "m"},
            }, ensure_ascii=False)

        with patch("pipeline.orchestrator._call_ollama", side_effect=fake_ollama):
            orch.generate_scenario(user_id, sid, "발표 미루는 중")

        self.assertTrue(captured)
        self.assertNotIn("[비율 권장]", captured[0])

    def test_elevated_signal_combines_with_ratio_hint(self):
        """elevated 신호와 ratio hint는 함께 적용 — 안전 톤 + recovery 권장 동시.

        설계 노트: failure_imagery_ratio는 regret 비율과 동치이므로 ratio skew는
        대부분 elevated 신호와 함께 발생한다. ratio hint를 elevated에서 건너뛰면
        영영 적용될 일이 없다. 둘 다 적용해야 안전 톤+회복형 카드로 자연 유도.
        """
        conn, user_id = _setup()
        # regret 4 + recovery 1 → ratio 0.8 ≥ 0.7 → recovery 권장
        # 동시에 failure_imagery_ratio = 0.8 ≥ 0.6 → elevated
        for _ in range(4):
            _seed_card(conn, user_id, "regret")
        _seed_card(conn, user_id, "recovery")

        orch = SessionOrchestrator(conn)
        sid = orch.start_session(user_id, "오늘도 미루는 중")

        captured: list[str] = []

        def fake_ollama(system_prompt, user_message, **kwargs):
            captured.append(system_prompt)
            return json.dumps({
                "card_type": "recovery",
                "sentences": {"fact": "f", "feeling": "e", "micro_action": "m"},
            }, ensure_ascii=False)

        with patch("pipeline.orchestrator._call_ollama", side_effect=fake_ollama):
            orch.generate_scenario(user_id, sid, "오늘도 미루는 중")

        self.assertTrue(captured)
        self.assertIn("[안전 모드]", captured[0])
        self.assertIn("[비율 권장]", captured[0])

    def test_high_signal_blocks_ratio_hint_via_soft_stop(self):
        """high 신호는 soft_stop 강제로 LLM 호출 자체가 일어나지 않는다."""
        conn, user_id = _setup()
        # high 임계 진입 (자기비난 8회)
        conn.execute(
            "INSERT INTO AvoidanceSession (user_id, avoidance_input, created_at) VALUES (?, ?, ?)",
            (user_id, "한심 " * 8, _now_iso()),
        )
        conn.commit()

        orch = SessionOrchestrator(conn)
        sid = orch.start_session(user_id, "오늘도 미루는 중")

        with patch("pipeline.orchestrator._call_ollama") as mock_llm:
            card = orch.generate_scenario(user_id, sid, "오늘도 미루는 중")
            mock_llm.assert_not_called()

        self.assertEqual(card.card_type, "soft_stop")
        self.assertEqual(card.signal_level, "high")


if __name__ == "__main__":
    unittest.main()
