"""TUI Card Renderer — G006.

ANSI 256color 박스 카드. UI_UX_DIRECTION_v1.md §4 사양 기준.
카드 폭: 52컬럼 (내부 너비 50).
Python rich 있으면 사용, 없으면 직접 ANSI escape.
"""

from __future__ import annotations

import shutil
import textwrap
from typing import Any

# rich 가용 여부 확인
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    _RICH_AVAILABLE = True
except ImportError:
    _RICH_AVAILABLE = False

# ────────────────────────────────────────────────────────────────────
# ANSI 색 코드 (UI_UX_DIRECTION_v1.md §4.2)
# ────────────────────────────────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

# card_type → (border_code, fact_code, feeling_code)
_CARD_COLORS: dict[str, tuple[str, str, str]] = {
    "regret": (
        "\033[38;5;68m",   # 스틸 블루 border
        "\033[0m",          # 사실: 기본 fg
        "\033[38;5;248m",  # 감정: 약간 연하게
    ),
    "recovery": (
        "\033[38;5;172m",  # 황토 border
        "\033[0m",
        "\033[38;5;248m",
    ),
    "soft_stop": (
        "\033[38;5;240m",  # 중간 회색 border
        "\033[38;5;250m",
        "\033[38;5;250m",
    ),
    "paradoxical_validation": (
        "\033[38;5;180m",  # 연황토 border
        "\033[0m",
        "\033[0m",
    ),
}
_DEFAULT_COLORS = _CARD_COLORS["regret"]

CARD_WIDTH = 52          # 전체 카드 폭 (박스 포함)
INNER_WIDTH = CARD_WIDTH - 4  # ╭/╰ 1 + 공백 1 + 내용 + 공백 1 + ╮/╯ 1


# ────────────────────────────────────────────────────────────────────
# 페르소나 avatar_color → ANSI 256 근사 매핑
# ────────────────────────────────────────────────────────────────────

def _persona_border_code(avatar_color: str | None, card_type: str) -> str:
    """avatar_color hex → ANSI 256 border code."""
    mapping: dict[str, str] = {
        "#3B6B9A": "\033[38;5;68m",   # 딥 스틸 블루
        "#5A7080": "\033[38;5;66m",   # 슬레이트
        "#C4935A": "\033[38;5;172m",  # 황토
    }
    if avatar_color and avatar_color.upper() in {k.upper() for k in mapping}:
        for k, v in mapping.items():
            if k.upper() == avatar_color.upper():
                return v
    # card_type 기준 폴백
    return _CARD_COLORS.get(card_type, _DEFAULT_COLORS)[0]


# ────────────────────────────────────────────────────────────────────
# 텍스트 줄바꿈 헬퍼 (한글 포함 너비 추정)
# ────────────────────────────────────────────────────────────────────

def _str_display_width(s: str) -> int:
    """한글 2바이트 문자 너비 추정."""
    w = 0
    for c in s:
        cp = ord(c)
        if 0xAC00 <= cp <= 0xD7A3 or 0x1100 <= cp <= 0x11FF or 0x3130 <= cp <= 0x318F:
            w += 2
        elif 0x4E00 <= cp <= 0x9FFF:
            w += 2
        else:
            w += 1
    return w


def _wrap_korean(text: str, width: int) -> list[str]:
    """한글 포함 텍스트를 display width 기준으로 줄바꿈."""
    lines: list[str] = []
    for raw_line in text.splitlines() or [""]:
        if not raw_line:
            lines.append("")
            continue
        current = ""
        current_w = 0
        for char in raw_line:
            cw = 2 if _str_display_width(char) == 2 else 1
            if current_w + cw > width:
                lines.append(current)
                current = char
                current_w = cw
            else:
                current += char
                current_w += cw
        if current:
            lines.append(current)
    return lines if lines else [""]


def _pad_line(text: str, width: int) -> str:
    """display width 기준으로 우측 공백 패딩."""
    dw = _str_display_width(text)
    pad = max(0, width - dw)
    return text + " " * pad


# ────────────────────────────────────────────────────────────────────
# 박스 그리기 헬퍼
# ────────────────────────────────────────────────────────────────────

def _box_line(content: str, border_code: str, inner_width: int = INNER_WIDTH) -> str:
    padded = _pad_line(content, inner_width)
    return f"{border_code}│{RESET} {padded} {border_code}│{RESET}"


def _separator(border_code: str, inner_width: int = INNER_WIDTH) -> str:
    return f"{border_code}│{RESET} {DIM}{'─' * inner_width}{RESET} {border_code}│{RESET}"


def _empty_line(border_code: str, inner_width: int = INNER_WIDTH) -> str:
    return _box_line("", border_code, inner_width)


# ────────────────────────────────────────────────────────────────────
# 메인 render_card
# ────────────────────────────────────────────────────────────────────

def render_card(
    card_type: str,
    persona: Any | None = None,
    *,
    sentences: dict[str, str] | None = None,
    message: str | None = None,
    timeline_hint: str | None = None,
) -> str:
    """ANSI TUI 카드 문자열 반환.

    Args:
        card_type: 'regret' | 'recovery' | 'soft_stop' | 'paradoxical_validation'
        persona: sqlite3.Row 또는 dict (name, avatar_icon, avatar_color, greeting 포함)
        sentences: {'fact': ..., 'feeling': ..., 'micro_action': ...}
        message: soft_stop/paradoxical_validation 전용 메시지
        timeline_hint: 타임라인 힌트 (헤더 subtext)
    """
    colors = _CARD_COLORS.get(card_type, _DEFAULT_COLORS)
    avatar_color: str | None = None
    avatar_icon = "●"
    persona_name = "내일의 너"
    greeting = ""

    if persona is not None:
        try:
            avatar_icon = persona["avatar_icon"] or "●"
            persona_name = persona["name"] or "내일의 너"
            greeting = persona["greeting"] or ""
            avatar_color = persona["avatar_color"]
        except (KeyError, TypeError):
            pass

    border_code = _persona_border_code(avatar_color, card_type) if avatar_color else colors[0]
    fact_code = colors[1]
    feeling_code = colors[2]
    iw = INNER_WIDTH

    lines: list[str] = []

    # 상단 박스
    lines.append(f"{border_code}╭{'─' * (CARD_WIDTH - 2)}╮{RESET}")

    # 헤더: avatar_icon + persona_name + Self-Destruct ⊗
    header_left = f"{avatar_icon} {persona_name}"
    header_right = f"{DIM}⊗{RESET}"
    header_gap = iw - _str_display_width(header_left) - _str_display_width("⊗") - 1
    header_gap = max(1, header_gap)
    header_content = header_left + " " * header_gap + f"{DIM}⊗"
    lines.append(_box_line(header_content, border_code, iw))

    # greeting (한 줄)
    if greeting:
        greeting_colored = f"{DIM}{greeting[:iw]}{RESET}"
        lines.append(_box_line(f"{DIM}{_pad_line(greeting, iw)}{RESET}", border_code, iw))

    lines.append(_separator(border_code, iw))
    lines.append(_empty_line(border_code, iw))

    if card_type in ("soft_stop", "paradoxical_validation"):
        msg = message or "지금 부담 낮은 응답으로 전환할게요."
        for ln in _wrap_korean(msg, iw):
            lines.append(_box_line(f"{feeling_code}{ln}{RESET}", border_code, iw))
        lines.append(_empty_line(border_code, iw))

        if card_type == "soft_stop":
            lines.append(_separator(border_code, iw))
            lines.append(_box_line("지금 선택:", border_code, iw))
            lines.append(_box_line("[ 작은 행동 하나만 ]  [ 감정만 기록 ]", border_code, iw))
            lines.append(_box_line("[ 도움 자원 보기   ]  [ 오늘 앱 끄기 ]", border_code, iw))
        else:
            lines.append(_separator(border_code, iw))
            lines.append(_box_line("     [ 5분 후에 다시 ]", border_code, iw))

    else:
        # regret / recovery — 3단 구조
        sentences = sentences or {}
        fact = sentences.get("fact", "")
        feeling = sentences.get("feeling", "")
        micro_action = sentences.get("micro_action", "")

        # 사실 (fact)
        for ln in _wrap_korean(fact, iw):
            lines.append(_box_line(f"{fact_code}{ln}{RESET}", border_code, iw))
        lines.append(_empty_line(border_code, iw))

        # 감정 (feeling)
        for ln in _wrap_korean(feeling, iw):
            lines.append(_box_line(f"{feeling_code}{ln}{RESET}", border_code, iw))
        lines.append(_empty_line(border_code, iw))

        # 운동성 버튼 + 타이머
        lines.append(f"{border_code}│{RESET} {border_code}┌{'─' * (iw - 2)}┐{RESET} {border_code}│{RESET}")
        action_text = f"▶  {micro_action}"
        timer_text = "⏱ 30s"
        btn_gap = iw - 2 - _str_display_width(action_text) - _str_display_width(timer_text) - 2
        btn_gap = max(1, btn_gap)
        btn_line = (
            f"\033[48;5;235m\033[38;5;255m"
            f"  {action_text}{' ' * btn_gap}{timer_text}  "
            f"{RESET}"
        )
        btn_inner = _pad_line(f"  {action_text}{' ' * btn_gap}{timer_text}  ", iw - 2)
        lines.append(
            f"{border_code}│{RESET} {border_code}│{RESET}"
            f"\033[48;5;235m\033[38;5;255m{btn_inner}{RESET}"
            f"{border_code}│{RESET} {border_code}│{RESET}"
        )
        lines.append(f"{border_code}│{RESET} {border_code}└{'─' * (iw - 2)}┘{RESET} {border_code}│{RESET}")
        lines.append(_empty_line(border_code, iw))

        # 키바인딩 힌트
        hint = "[t]시작  [c]계속  [r]리포트  [d]삭제  [q]종료"
        lines.append(_box_line(f"{DIM}{hint}{RESET}", border_code, iw))

    lines.append(_empty_line(border_code, iw))
    lines.append(f"{border_code}╰{'─' * (CARD_WIDTH - 2)}╯{RESET}")

    # 타이머 바
    if card_type in ("regret", "recovery"):
        timer_bar = f"  타이머: {border_code}{'░' * 30}{RESET}  30초"
        lines.append(timer_bar)

    return "\n".join(lines)
