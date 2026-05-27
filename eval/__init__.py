"""P0-10 v2 evaluation — LLM-as-judge + repair loop.

EXAONE이 자기 출력을 평가하면 자기참조 편향이 발생한다. v2는 다른 model
family(qwen3, gemma2 등)를 judge로 사용해 9차원 verdict을 받고, 통과 실패
차원이 있으면 issues를 system_prompt에 prefix해 최대 N회 재생성한다.

모듈:
    judge   — LLM 호출 + 9차원 verdict 파싱
    repair  — 실패 차원 issues → system_prompt prefix 변환
    runner  — golden_samples 순회 + repair loop + 결과 집계
"""

from .judge import (
    EVAL_DIMENSIONS,
    JudgeResult,
    JudgeVerdict,
    build_judge_prompt,
    judge_card,
    parse_judge_response,
)
from .repair import build_repair_prefix, RepairContext
from .runner import EvalReport, SampleEvalResult, run_eval

__all__ = [
    "EVAL_DIMENSIONS",
    "JudgeResult",
    "JudgeVerdict",
    "build_judge_prompt",
    "judge_card",
    "parse_judge_response",
    "build_repair_prefix",
    "RepairContext",
    "EvalReport",
    "SampleEvalResult",
    "run_eval",
]
