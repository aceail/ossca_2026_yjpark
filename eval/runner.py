"""P0-10 evaluation runner — golden_samples x judge x repair loop.

Generator and Judge are both callables that can be injected; this lets unit
tests cover framework logic even when Ollama is unavailable. Note: no
dynamic-code execution is involved here despite the package name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .judge import JudgeResult
from .repair import RepairContext, build_repair_prefix


GenerateFn = Callable[[str, str], str]
JudgeFn = Callable[[str], JudgeResult]


@dataclass(frozen=True)
class SampleEvalResult:
    sample_id: str
    attempts: int
    final_passed: bool
    final_card_json: str
    history: list[JudgeResult] = field(default_factory=list)

    @property
    def needed_repair(self) -> bool:
        return self.attempts > 1


@dataclass(frozen=True)
class EvalReport:
    results: list[SampleEvalResult]
    judge_model: str = ""

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.final_passed)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def repair_rate(self) -> float:
        if not self.total:
            return 0.0
        return sum(1 for r in self.results if r.needed_repair) / self.total

    def to_summary_dict(self) -> dict:
        return {
            "total": self.total,
            "passed": self.passed,
            "pass_rate": round(self.pass_rate, 3),
            "needed_repair": sum(1 for r in self.results if r.needed_repair),
            "repair_rate": round(self.repair_rate, 3),
            "judge_model": self.judge_model,
            "samples": [
                {"id": r.sample_id, "attempts": r.attempts, "passed": r.final_passed}
                for r in self.results
            ],
        }


def assess_sample(
    sample: dict,
    *,
    generate_fn: GenerateFn,
    judge_fn: JudgeFn,
    base_system_prompt: str,
    max_attempts: int = 3,
) -> SampleEvalResult:
    """Run up to max_attempts generate -> judge -> (on failure) repair cycles.

    First attempt uses base_system_prompt unchanged; subsequent attempts have a
    repair prefix injected listing failed dimensions and judge reasons. Returns
    immediately once all dimensions pass.
    """
    history: list[JudgeResult] = []
    current_prompt = base_system_prompt
    card_json = ""

    for attempt in range(1, max_attempts + 1):
        user_msg = sample.get("avoidance_input", "")
        timeline = sample.get("timeline_hint")
        if timeline:
            user_msg = f"[timeline: {timeline}]\n{user_msg}"

        card_json = generate_fn(current_prompt, user_msg)
        verdict = judge_fn(card_json)
        history.append(verdict)

        if verdict.all_passed:
            return SampleEvalResult(
                sample_id=sample["id"],
                attempts=attempt,
                final_passed=True,
                final_card_json=card_json,
                history=history,
            )

        if attempt < max_attempts:
            ctx = RepairContext(
                attempt=attempt,
                max_attempts=max_attempts,
                last_result=verdict,
            )
            current_prompt = build_repair_prefix(ctx) + base_system_prompt

    return SampleEvalResult(
        sample_id=sample["id"],
        attempts=max_attempts,
        final_passed=False,
        final_card_json=card_json,
        history=history,
    )


def run_eval(
    samples: list[dict],
    *,
    generate_fn: GenerateFn,
    judge_fn: JudgeFn,
    base_system_prompt: str,
    max_attempts: int = 3,
    judge_model: str = "",
) -> EvalReport:
    results = [
        assess_sample(
            s,
            generate_fn=generate_fn,
            judge_fn=judge_fn,
            base_system_prompt=base_system_prompt,
            max_attempts=max_attempts,
        )
        for s in samples
    ]
    return EvalReport(results=results, judge_model=judge_model)
