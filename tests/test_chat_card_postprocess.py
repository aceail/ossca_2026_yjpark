"""Sprint 40 — chat card JSON post-process tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.chat import _postprocess_recovery_card


class TestPostprocess(unittest.TestCase):
    def test_passes_through_no_json(self):
        text = "그냥 답변입니다."
        self.assertEqual(_postprocess_recovery_card(text), text)

    def test_converts_recovery_json_to_prefix_lines(self):
        text = '안녕하세요. {"card_type":"recovery","sentences":{"fact":"오늘 마감","feeling":"내일 아침","micro_action":"지금 시작"}}'
        out = _postprocess_recovery_card(text)
        self.assertIn("🪞", out)
        self.assertIn("🫧", out)
        self.assertIn("👣", out)
        # JSON 블록은 제거됨
        self.assertNotIn("card_type", out)

    def test_non_recovery_card_type_passes_through(self):
        text = '{"card_type":"regret","sentences":{}}'
        out = _postprocess_recovery_card(text)
        self.assertEqual(out, text)

    def test_invalid_json_passes_through(self):
        text = '{"card_type":"recovery" broken'
        out = _postprocess_recovery_card(text)
        self.assertEqual(out, text)


if __name__ == "__main__":
    unittest.main()
