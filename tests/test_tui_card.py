"""G006 TUI Card Renderer 테스트 (5+)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ui.tui import render_card, CARD_WIDTH, _str_display_width  # noqa: E402


# 테스트용 mock persona dict
def _persona(name="내일의 나", icon="🌙", color="#3B6B9A", greeting="내일의 내가 너에게 보낸 메시지야"):
    return {
        "name": name,
        "avatar_icon": icon,
        "avatar_color": color,
        "greeting": greeting,
    }


class TestRenderCardRegret(unittest.TestCase):
    def setUp(self):
        self.persona = _persona()
        self.sentences = {
            "fact": "새벽 1시다. PPT 0장이다. 마감까지 9시간 남았다.",
            "feeling": "내일 발표장에서 첫 슬라이드를 못 띄우는 나.",
            "micro_action": "파일을 켠다.",
        }
        self.card = render_card("regret", self.persona, sentences=self.sentences)

    def test_avatar_icon_in_output(self):
        self.assertIn("🌙", self.card)

    def test_persona_name_in_output(self):
        self.assertIn("내일의 나", self.card)

    def test_fact_sentence_in_output(self):
        self.assertIn("PPT 0장이다", self.card)

    def test_feeling_sentence_in_output(self):
        self.assertIn("발표장에서", self.card)

    def test_micro_action_in_output(self):
        self.assertIn("파일을 켠다", self.card)

    def test_self_destruct_symbol(self):
        self.assertIn("⊗", self.card)

    def test_timer_display(self):
        self.assertIn("30초", self.card)
        self.assertIn("⏱", self.card)

    def test_box_chars_present(self):
        self.assertIn("╭", self.card)
        self.assertIn("╰", self.card)


class TestRenderCardSoftStop(unittest.TestCase):
    def setUp(self):
        self.persona = _persona()
        self.msg = "지금 문장은 강한 고통 신호로 읽힙니다."
        self.card = render_card("soft_stop", self.persona, message=self.msg)

    def test_message_in_output(self):
        self.assertIn("강한 고통 신호", self.card)

    def test_self_destruct_symbol(self):
        self.assertIn("⊗", self.card)

    def test_choices_in_output(self):
        self.assertIn("작은 행동 하나만", self.card)

    def test_no_timer_for_soft_stop(self):
        # soft_stop은 타이머 바 없음
        self.assertNotIn("⏱ 30s", self.card)


class TestRenderCardParadoxical(unittest.TestCase):
    def setUp(self):
        self.card = render_card(
            "paradoxical_validation",
            _persona(),
            message="지금 많이 힘드시군요.",
        )

    def test_message_in_output(self):
        self.assertIn("힘드시군요", self.card)

    def test_self_destruct_symbol(self):
        self.assertIn("⊗", self.card)


class TestRenderCardRecovery(unittest.TestCase):
    def setUp(self):
        self.persona = _persona(
            name="친한 친구 ㅈㅅ", icon="🤝", color="#C4935A",
            greeting="야 너 지금 뭐 하는 거야ㅋ"
        )
        self.sentences = {
            "fact": "운동복 입고 냉장고 앞에 있다.",
            "feeling": "어제 갈아입기만 했는데도 몸이 가벼웠다.",
            "micro_action": "운동복으로만 갈아입는다.",
        }
        self.card = render_card("recovery", self.persona, sentences=self.sentences)

    def test_persona_icon_in_output(self):
        self.assertIn("🤝", self.card)

    def test_greeting_in_output(self):
        self.assertIn("야 너", self.card)

    def test_micro_action_in_output(self):
        self.assertIn("갈아입는다", self.card)


class TestCardWidth(unittest.TestCase):
    def test_card_top_border_width(self):
        """카드 상단 박스 라인(ANSI 제거 후) 폭이 CARD_WIDTH 근사."""
        import re
        card = render_card(
            "regret",
            _persona(),
            sentences={"fact": "테스트", "feeling": "감정", "micro_action": "행동"},
        )
        lines = card.splitlines()
        ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
        # 첫 줄 (╭───╮)
        top_line = lines[0]
        clean = ansi_escape.sub("", top_line)
        self.assertEqual(len(clean), CARD_WIDTH)

    def test_no_persona_fallback(self):
        """persona=None 이어도 렌더링 오류 없음."""
        card = render_card(
            "regret",
            None,
            sentences={"fact": "f", "feeling": "e", "micro_action": "m"},
        )
        self.assertIn("╭", card)
        self.assertIn("⊗", card)


if __name__ == "__main__":
    unittest.main()
