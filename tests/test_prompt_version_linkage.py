"""P0-12 PromptVersion 실 사용 연결 — v0.3 sprint 6."""

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

from db import open_db, migrate, get_persona, upsert_prompt_version  # noqa: E402
from persona import seed_builtin_prompts  # noqa: E402
from pipeline import SessionOrchestrator  # noqa: E402


def _setup():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = open_db(Path(tmp.name))
    migrate(conn)
    seed_builtin_prompts(conn)
    return conn


def _create_user(conn, user_id="pv-user"):
    now = datetime.now(timezone.utc).isoformat()
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
    return user_id


# ────────────────────────────────────────────────────────────────────
# upsert_prompt_version 단위
# ────────────────────────────────────────────────────────────────────


class TestUpsertPromptVersion(unittest.TestCase):
    def test_same_input_returns_same_id(self):
        conn = _setup()
        id1 = upsert_prompt_version(conn, name="persona_1", system_prompt="prompt body")
        id2 = upsert_prompt_version(conn, name="persona_1", system_prompt="prompt body")
        self.assertEqual(id1, id2)

    def test_different_prompt_yields_different_version(self):
        conn = _setup()
        id1 = upsert_prompt_version(conn, name="persona_1", system_prompt="version A")
        id2 = upsert_prompt_version(conn, name="persona_1", system_prompt="version B")
        self.assertNotEqual(id1, id2)

    def test_different_name_isolates(self):
        conn = _setup()
        id1 = upsert_prompt_version(conn, name="persona_1", system_prompt="same")
        id2 = upsert_prompt_version(conn, name="persona_2", system_prompt="same")
        self.assertNotEqual(id1, id2)

    def test_version_is_12char_hex(self):
        conn = _setup()
        upsert_prompt_version(conn, name="p", system_prompt="x")
        row = conn.execute("SELECT version FROM PromptVersion WHERE name = 'p'").fetchone()
        self.assertEqual(len(row["version"]), 12)
        int(row["version"], 16)  # hex parse 가능해야


# ────────────────────────────────────────────────────────────────────
# 마이그레이션 008: ToolInvocation에 prompt_version_id 컬럼
# ────────────────────────────────────────────────────────────────────


class TestMigration008(unittest.TestCase):
    def test_tool_invocation_has_prompt_version_id(self):
        conn = _setup()
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(ToolInvocation)").fetchall()}
        self.assertIn("prompt_version_id", cols)


# ────────────────────────────────────────────────────────────────────
# Orchestrator 통합: generate_scenario → ScenarioCard.prompt_version_id 채워짐
# ────────────────────────────────────────────────────────────────────


class TestGenerateScenarioPromptVersionLinkage(unittest.TestCase):
    def test_card_carries_prompt_version_id(self):
        conn = _setup()
        user_id = _create_user(conn)
        orch = SessionOrchestrator(conn)
        sid = orch.start_session(user_id, "발표 미루는 중")

        mock = json.dumps({
            "card_type": "regret",
            "sentences": {"fact": "f", "feeling": "e", "micro_action": "m"},
        }, ensure_ascii=False)
        with patch("pipeline.orchestrator._call_ollama", return_value=mock):
            card = orch.generate_scenario(user_id, sid, "발표 미루는 중")

        self.assertIsNotNone(card.prompt_version_id)
        row = conn.execute(
            "SELECT system_prompt FROM PromptVersion WHERE id = ?",
            (card.prompt_version_id,),
        ).fetchone()
        self.assertIsNotNone(row)
        # persona system_prompt에는 절대 규칙이 들어가 있어야
        self.assertIn("절대 규칙", row["system_prompt"])

    def test_repeated_generation_reuses_same_prompt_version(self):
        """같은 페르소나·같은 system_prompt면 같은 PromptVersion.id 재사용.

        mock을 paradoxical_validation으로 두어 failure_imagery_ratio 분모(regret+recovery)
        에 영향을 주지 않게 하고, 두 호출 모두 normal 신호 + 같은 system_prompt가 보장됨.
        """
        conn = _setup()
        user_id = _create_user(conn)
        orch = SessionOrchestrator(conn)

        mock = json.dumps({
            "card_type": "paradoxical_validation",
            "message": "지금 많이 힘드시군요.",
        }, ensure_ascii=False)

        with patch("pipeline.orchestrator._call_ollama", return_value=mock):
            sid1 = orch.start_session(user_id, "한 번")
            card1 = orch.generate_scenario(user_id, sid1, "한 번")
            sid2 = orch.start_session(user_id, "두 번")
            card2 = orch.generate_scenario(user_id, sid2, "두 번")

        self.assertIsNotNone(card1.prompt_version_id)
        self.assertEqual(card1.prompt_version_id, card2.prompt_version_id)

    def test_elevated_signal_changes_prompt_version(self):
        """elevated 신호로 prefix가 추가되면 system_prompt가 달라져 새 version.

        normal_card는 paradoxical_validation mock으로 만들어 failure_imagery_ratio
        분모에 영향을 주지 않게 — 그래야 두 번째 호출이 high가 아닌 elevated로 분류됨.
        """
        conn = _setup()
        user_id = _create_user(conn)
        orch = SessionOrchestrator(conn)

        mock_paradox = json.dumps({
            "card_type": "paradoxical_validation",
            "message": "괜찮아요.",
        }, ensure_ascii=False)
        mock_regret = json.dumps({
            "card_type": "regret",
            "sentences": {"fact": "f", "feeling": "e", "micro_action": "m"},
        }, ensure_ascii=False)

        # normal 신호 카드 (paradox라 failure_ratio 분모에서 제외)
        with patch("pipeline.orchestrator._call_ollama", return_value=mock_paradox):
            sid = orch.start_session(user_id, "발표 미루는 중")
            normal_card = orch.generate_scenario(user_id, sid, "발표 미루는 중")

        # elevated 신호 유도 — blame 3 (high 임계 8 미만)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO AvoidanceSession (user_id, avoidance_input, created_at) VALUES (?, ?, ?)",
            (user_id, "한심 한심 한심", now),
        )
        conn.commit()

        with patch("pipeline.orchestrator._call_ollama", return_value=mock_regret):
            sid2 = orch.start_session(user_id, "또 미룬다")
            elev_card = orch.generate_scenario(user_id, sid2, "또 미룬다")

        self.assertEqual(normal_card.signal_level, "normal")
        self.assertEqual(elev_card.signal_level, "elevated")
        self.assertNotEqual(normal_card.prompt_version_id, elev_card.prompt_version_id)


if __name__ == "__main__":
    unittest.main()
