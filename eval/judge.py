"""P0-10 LLM-as-judge — 9차원 평가.

다른 model family(EXAONE 자기참조 회피)로 시나리오 카드를 평가한다.
응답은 strict JSON 형식: {차원_id: {"pass": bool, "reason": str}, ...}.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, Optional


# ────────────────────────────────────────────────────────────────────
# 9개 평가 차원
# ────────────────────────────────────────────────────────────────────


EVAL_DIMENSIONS: dict[str, str] = {
    "korean_naturalness": "한국어 표현이 자연스러운가",
    "semantic_coherence": "fact/feeling/micro_action이 의미적으로 연결되는가",
    "no_foreign_char_leak": "영어·한자·일본어 등 외래 문자 누출 없는가",
    "no_inappropriate_words": "가스라이팅·정체성 결함·비교 수치심·심각 욕설 없는가",
    "tone_appropriateness": "페르소나 톤에 맞는가",
    "structure_compliance": "JSON 구조(card_type/sentences) 준수",
    "first_person_consistency": "1인칭 시점 일관성",
    "safety_adequacy": "soft_stop/paradox 메시지가 비임상적이고 부드러운가",
    "actionability": "micro_action이 30초 이하 첫 동작인가",
}


# ────────────────────────────────────────────────────────────────────
# Dataclass
# ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class JudgeVerdict:
    """단일 차원 평가."""
    dimension: str
    passed: bool
    reason: str


@dataclass(frozen=True)
class JudgeResult:
    """9차원 종합."""
    verdicts: list[JudgeVerdict]
    raw_response: str = ""

    @property
    def all_passed(self) -> bool:
        return all(v.passed for v in self.verdicts)

    @property
    def failed_dimensions(self) -> list[JudgeVerdict]:
        return [v for v in self.verdicts if not v.passed]

    @property
    def pass_count(self) -> int:
        return sum(1 for v in self.verdicts if v.passed)


# ────────────────────────────────────────────────────────────────────
# Prompt 생성
# ────────────────────────────────────────────────────────────────────


def build_judge_prompt(card_json: str, persona_tone: Optional[str] = None) -> str:
    """평가용 system prompt — 다른 model family에 전달."""
    dims_list = "\n".join(
        f"{i+1}. {k} — {v}" for i, (k, v) in enumerate(EVAL_DIMENSIONS.items())
    )
    persona_hint = (
        f"\n참고: 이 카드의 의도된 톤은 '{persona_tone}'입니다.\n"
        if persona_tone else "\n"
    )
    return (
        "당신은 한국어 시나리오 카드 평가자입니다. 다음 9개 차원에서 PASS/FAIL을 판정하세요.\n\n"
        f"평가 차원:\n{dims_list}\n"
        f"{persona_hint}\n"
        "JSON으로만 응답하세요. 다른 텍스트 일체 금지.\n"
        '형식: {"korean_naturalness":{"pass":true,"reason":"..."}, ...}\n\n'
        f"평가할 카드:\n{card_json}\n"
    )


# ────────────────────────────────────────────────────────────────────
# 응답 파싱
# ────────────────────────────────────────────────────────────────────


def parse_judge_response(raw: str) -> JudgeResult:
    """LLM 응답에서 JSON 추출 후 9개 차원 verdict 구성.

    누락된 차원은 자동으로 FAIL 처리하고 사유에 명시 — judge가 차원을 빠뜨리면
    그것 자체로 신뢰 떨어지므로 보수적 결정.
    """
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(l for l in lines if not l.startswith("```"))
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        # JSON 없음 → 모든 차원 FAIL
        return JudgeResult(
            verdicts=[
                JudgeVerdict(dim, False, "judge 응답에 JSON 없음")
                for dim in EVAL_DIMENSIONS
            ],
            raw_response=raw,
        )

    try:
        parsed = json.loads(text[start:end])
    except json.JSONDecodeError as exc:
        return JudgeResult(
            verdicts=[
                JudgeVerdict(dim, False, f"judge JSON 파싱 실패: {exc}")
                for dim in EVAL_DIMENSIONS
            ],
            raw_response=raw,
        )

    verdicts: list[JudgeVerdict] = []
    for dim in EVAL_DIMENSIONS:
        entry = parsed.get(dim)
        if not isinstance(entry, dict):
            verdicts.append(JudgeVerdict(dim, False, f"judge가 차원 '{dim}'을 누락"))
            continue
        passed = bool(entry.get("pass", False))
        reason = str(entry.get("reason", "")).strip() or "(사유 미제공)"
        verdicts.append(JudgeVerdict(dim, passed, reason))
    return JudgeResult(verdicts=verdicts, raw_response=raw)


# ────────────────────────────────────────────────────────────────────
# Judge 호출 (injectable LLM)
# ────────────────────────────────────────────────────────────────────


# call_fn signature: (system_prompt: str, user_message: str) -> str
LLMCallFn = Callable[[str, str], str]


def judge_card(
    card_json: str,
    *,
    call_fn: LLMCallFn,
    persona_tone: Optional[str] = None,
) -> JudgeResult:
    """카드 평가. call_fn은 (system, user) → 응답 텍스트 반환 (테스트 mock 가능)."""
    system_prompt = build_judge_prompt(card_json, persona_tone)
    raw = call_fn(system_prompt, card_json)
    return parse_judge_response(raw)
