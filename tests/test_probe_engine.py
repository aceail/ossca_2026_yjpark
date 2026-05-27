"""G004 HITLProbeEngine — Phase router, scoring, cooldown, active prompt selector."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db import open_db, migrate, get_persona  # noqa: E402
from probe import Phase, PhaseRouter, ProbeEngine, select_active_prompt  # noqa: E402


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TestPhaseRouter(unittest.TestCase):
    def setUp(self):
        self.router = PhaseRouter()

    def test_onboarding_when_session_count_low(self):
        self.assertEqual(self.router.route(completion_percent=20.0, session_count=2), Phase.ONBOARDING)

    def test_adaptive_when_mid_range(self):
        self.assertEqual(self.router.route(completion_percent=60.0, session_count=8), Phase.ADAPTIVE)

    def test_passive_when_completion_high(self):
        self.assertEqual(self.router.route(completion_percent=85.0, session_count=20), Phase.PASSIVE)

    def test_boundary_at_threshold(self):
        self.assertEqual(self.router.route(completion_percent=80.0, session_count=10), Phase.PASSIVE)


class TestProbeEngine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.conn = open_db(self.db_path)
        migrate(self.conn)
        self.conn.execute("INSERT INTO User (id, created_at) VALUES (?, ?)", ("local-test", now_iso()))
        # UserProfile with 1 slot filled, completion 20%
        persona = get_persona(self.conn, "내일의 나")
        self.conn.execute(
            """INSERT INTO UserProfile
               (user_id, slots_json, completion_percent, forbidden_topics_json, active_persona_id, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                "local-test",
                json.dumps({"trigger_category": {"value": "글쓰기", "confidence": 1.0}}),
                20.0,
                json.dumps([]),
                persona["id"],
                now_iso(),
            ),
        )
        # 6 AvoidanceSession (session count 6 → Phase ADAPTIVE)
        for _ in range(6):
            self.conn.execute(
                "INSERT INTO AvoidanceSession (user_id, avoidance_input, created_at) VALUES (?, ?, ?)",
                ("local-test", "x", now_iso()),
            )
        self.conn.commit()
        self.engine = ProbeEngine(self.conn)

    def tearDown(self):
        self.conn.close()
        self.db_path.unlink(missing_ok=True)
        for suffix in ("-wal", "-shm"):
            Path(str(self.db_path) + suffix).unlink(missing_ok=True)

    def test_phase_adaptive_returns_question(self):
        # 002_seed_probe_questions가 필요한데, 1차 마이그레이션엔 없음 → 수동 시드
        self.conn.execute(
            "INSERT INTO ProbeQuestion (text, target_slot, expected_information_gain, enabled, version, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("regret recall test", "regret_recall", 0.8, 1, "v1", now_iso()),
        )
        self.conn.execute(
            "INSERT INTO ProbeQuestion (text, target_slot, expected_information_gain, enabled, version, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("trigger known test", "trigger_category", 0.5, 1, "v1", now_iso()),
        )
        self.conn.commit()
        best = self.engine.best_question(user_id="local-test")
        self.assertIsNotNone(best)
        # missing slot (regret_recall) > filled slot (trigger_category)
        self.assertEqual(best.target_slot, "regret_recall")

    def test_cooldown_blocks_next_question(self):
        # 질문 1개 시드
        cur = self.conn.execute(
            "INSERT INTO ProbeQuestion (text, target_slot, expected_information_gain, enabled, version, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("q1", "regret_recall", 0.5, 1, "v1", now_iso()),
        )
        qid = cur.lastrowid
        # 사용자가 skip → cooldown 진입
        self.engine.skip_today("local-test", qid)
        # best_question은 None 반환
        best = self.engine.best_question(user_id="local-test")
        self.assertIsNone(best, "cooldown 동안 질문 X")

    def test_passive_phase_returns_none(self):
        # 프로필 완성도 85% → Phase PASSIVE
        self.conn.execute(
            "UPDATE UserProfile SET completion_percent = 85.0 WHERE user_id = ?", ("local-test",)
        )
        self.conn.execute(
            "INSERT INTO ProbeQuestion (text, target_slot, expected_information_gain, enabled, version, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("x", "y", 0.5, 1, "v1", now_iso()),
        )
        self.conn.commit()
        self.assertIsNone(self.engine.best_question(user_id="local-test"))


class TestActivePromptSelector(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.conn = open_db(self.db_path)
        migrate(self.conn)
        # seed builtin prompts
        from persona import seed_builtin_prompts
        seed_builtin_prompts(self.conn)
        self.conn.execute("INSERT INTO User (id, created_at) VALUES (?, ?)", ("u1", now_iso()))
        persona = get_persona(self.conn, "친한 친구")
        self.conn.execute(
            """INSERT INTO UserProfile
               (user_id, slots_json, completion_percent, forbidden_topics_json, active_persona_id, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("u1", "{}", 60.0, "[]", persona["id"], now_iso()),
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        self.db_path.unlink(missing_ok=True)
        for suffix in ("-wal", "-shm"):
            Path(str(self.db_path) + suffix).unlink(missing_ok=True)

    def test_returns_persona_system_prompt(self):
        pid, prompt = select_active_prompt(self.conn, "u1")
        self.assertIsNotNone(pid)
        self.assertIsNotNone(prompt)
        self.assertIn("친구", prompt)

    def test_no_profile_returns_none(self):
        pid, prompt = select_active_prompt(self.conn, "unknown-user")
        self.assertIsNone(pid)
        self.assertIsNone(prompt)


class TestSeededProbeQuestions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.conn = open_db(self.db_path)
        migrate(self.conn)

    def tearDown(self):
        self.conn.close()
        self.db_path.unlink(missing_ok=True)
        for suffix in ("-wal", "-shm"):
            Path(str(self.db_path) + suffix).unlink(missing_ok=True)

    def test_002_seed_12_questions(self):
        # 002_seed_probe_questions.sql 적용 확인
        row = self.conn.execute("SELECT COUNT(*) AS n FROM ProbeQuestion WHERE enabled = 1").fetchone()
        self.assertEqual(row["n"], 12)


if __name__ == "__main__":
    unittest.main()
