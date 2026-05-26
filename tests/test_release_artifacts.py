"""G008 — Release artifact 회귀 테스트 (사용자 가이드 '하네스에 추가').

README · LICENSE · web/* · pyproject 산출물의 무결성을 unittest로 자동 검증.
G009 EvaluationHarness Tier 1 매 commit pytest와 동일 위상으로 회귀를 잡는다.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestReadme(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = PROJECT_ROOT / "README.md"
        cls.text = cls.path.read_text(encoding="utf-8")

    def test_readme_exists(self):
        self.assertTrue(self.path.exists())

    def test_readme_has_project_name(self):
        self.assertIn("내일의 너", self.text)
        self.assertIn("Tomorrow's You", self.text)

    def test_readme_has_quickstart(self):
        self.assertIn("Quickstart", self.text)
        self.assertIn("ollama", self.text.lower())

    def test_readme_has_persona_keyword(self):
        self.assertIn("페르소나", self.text)

    def test_readme_has_safety_mention(self):
        # Slow Harm 안전 시계열 명시
        self.assertTrue(
            "Slow Harm" in self.text or "safety" in self.text.lower(),
            "README에 안전성 언급이 있어야 함",
        )


class TestLicense(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = PROJECT_ROOT / "LICENSE"
        cls.text = cls.path.read_text(encoding="utf-8")

    def test_license_exists(self):
        self.assertTrue(self.path.exists())

    def test_mit_grant_present(self):
        self.assertIn("MIT License", self.text)
        self.assertIn("WITHOUT WARRANTY", self.text)

    def test_ethical_use_restriction_present(self):
        self.assertIn("Ethical Use Restriction", self.text)
        self.assertIn("Dual-Use Defense", self.text)

    def test_forbidden_dual_use_clauses(self):
        # 5 명시적 금지 조항이 모두 포함
        for marker in ["1.", "2.", "3.", "4.", "5."]:
            self.assertIn(marker, self.text)


class TestWebPrototype(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.web = PROJECT_ROOT / "web"

    def test_tokens_css_exists(self):
        self.assertTrue((self.web / "tokens.css").exists())

    def test_tokens_css_has_persona_palettes(self):
        text = (self.web / "tokens.css").read_text(encoding="utf-8")
        # 5 페르소나 색·표면 토큰 포함
        for token in ("--color-regret-bg", "--color-recovery-bg", "--color-softstop-bg",
                       "--color-paradox-bg", "--color-destruct-default", "--font-fact",
                       "--font-size-card", "--space-card-padding"):
            self.assertIn(token, text, f"tokens.css missing {token}")

    def test_tokens_css_has_motion_reduce(self):
        text = (self.web / "tokens.css").read_text(encoding="utf-8")
        self.assertIn("prefers-reduced-motion", text)

    def test_index_html_exists(self):
        self.assertTrue((self.web / "index.html").exists())

    def test_index_html_card_classes(self):
        text = (self.web / "index.html").read_text(encoding="utf-8")
        for cls in ("regret", "recovery", "softstop", "self-destruct", "tone-feedback"):
            self.assertIn(cls, text, f"index.html missing class '{cls}'")

    def test_index_html_aria_label_present(self):
        text = (self.web / "index.html").read_text(encoding="utf-8")
        self.assertIn("aria-label", text)


class TestUltragoalDocs(unittest.TestCase):
    """주요 .omc/ultragoal 산출 문서 존재 + 핵심 단어 포함."""

    BASE = PROJECT_ROOT / ".omc" / "ultragoal"

    REQUIRED_DOCS = (
        "FINAL_GOAL.md",
        "DATA_MODEL_v1.md",
        "ONBOARDING_FLOW_v1.md",
        "PERSONA_SYSTEM_v1.md",
        "PIPELINE_v1.md",
        "PROBE_ENGINE_v1.md",
        "EVAL_HARNESS_DESIGN_v1.md",
        "REGRET_FINGERPRINT_v1.md",
        "AGENT_INTEGRATIONS_v1.md",
        "UI_UX_DIRECTION_v1.md",
        "CCG_REVIEW_R2.md",
        "brief.md",
        "goals.json",
    )

    def test_all_required_docs_present(self):
        missing = [d for d in self.REQUIRED_DOCS if not (self.BASE / d).exists()]
        self.assertEqual(missing, [], f"missing ultragoal docs: {missing}")

    def test_final_goal_has_v2_3_marker(self):
        text = (self.BASE / "FINAL_GOAL.md").read_text(encoding="utf-8")
        self.assertIn("v2.3", text)
        self.assertIn("페르소나", text)
        self.assertIn("Agent", text)

    def test_goals_json_structure(self):
        data = json.loads((self.BASE / "goals.json").read_text(encoding="utf-8"))
        self.assertIn("goals", data)
        self.assertEqual(len(data["goals"]), 11)
        ids = [g["id"] for g in data["goals"]]
        for expected in ("G001-designlockdown", "G008-mvprelease",
                         "G009-evaluationharness", "G010-agentintegrations",
                         "G011-personasystem"):
            self.assertIn(expected, ids)


class TestGitignore(unittest.TestCase):
    """민감·대용량 파일이 .gitignore로 보호되는지 검증."""

    @classmethod
    def setUpClass(cls):
        cls.text = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

    def test_ollama_models_ignored(self):
        self.assertIn("ollama_models/", self.text)

    def test_local_db_ignored(self):
        self.assertIn("tomorrow_you.db", self.text)

    def test_codegraph_ignored(self):
        self.assertIn(".codegraph/", self.text)


if __name__ == "__main__":
    unittest.main()
