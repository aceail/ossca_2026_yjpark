"""P0-10 repair loop — 평가 실패 차원의 issues를 system_prompt에 prefix.

LLM이 자기 출력의 문제점을 명시적으로 인지한 상태로 재생성하게 만든다.
재시도 횟수는 호출자가 관리.
"""

from __future__ import annotations

from dataclasses import dataclass

from .judge import JudgeResult


@dataclass(frozen=True)
class RepairContext:
    attempt: int            # 1-indexed
    max_attempts: int
    last_result: JudgeResult


def build_repair_prefix(ctx: RepairContext) -> str:
    """system_prompt 상단에 prepend할 안내 텍스트.

    실패 차원만 골라 한 줄씩 명시 — judge 사유 그대로 인용해 LLM이 무엇을 고쳐야
    하는지 분명하게 한다.
    """
    failures = ctx.last_result.failed_dimensions
    if not failures:
        return ""
    bullets = "\n".join(
        f"- {v.dimension}: {v.reason}" for v in failures
    )
    return (
        f"[자동 평가 재시도 {ctx.attempt}/{ctx.max_attempts}] "
        "이전 응답이 다음 차원에서 실패했습니다. 이번엔 반드시 이 문제들을 모두 해결하세요:\n"
        f"{bullets}\n\n"
    )
