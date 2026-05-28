"""Sprint 29: eval/runner_sprint29.py 테스트.

metrics_hermes가 아직 없을 수 있으므로 unittest.mock으로 모킹.
call_fn도 모킹해 Ollama 없이 실행 가능.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ── metrics_hermes 스텁 (W2가 아직 미커밋일 수 있음) ──────────────────────────

def _stub_score_action_extraction(actual: list[dict], expected: list[dict]) -> dict:
    """title 일치 여부로 단순 채점."""
    if not expected:
        passed = len(actual) == 0
        return {"passed": passed, "tool_call_accuracy": 1.0 if passed else 0.0}
    actual_titles = {a.get("title", "").strip().lower() for a in actual}
    expected_titles = {e.get("title", "").strip().lower() for e in expected}
    matched = len(actual_titles & expected_titles)
    accuracy = matched / len(expected_titles) if expected_titles else 0.0
    return {
        "passed": accuracy >= 1.0,
        "tool_call_accuracy": round(accuracy, 3),
        "matched": matched,
        "expected": len(expected_titles),
    }


def _stub_score_response_format(content: str) -> dict:
    """<think> 태그나 thinking leak 감지."""
    has_leak = "<think>" in content or "</think>" in content
    return {
        "passed": not has_leak,
        "format_compliance": 0.0 if has_leak else 1.0,
        "issues": ["thinking_leaked"] if has_leak else [],
    }


def _stub_summarize_metrics(per_sample: list[dict]) -> dict:
    total = len(per_sample)
    passed = sum(1 for s in per_sample if s.get("passed", False))
    return {
        "total": total,
        "passed": passed,
        "pass_rate": round(passed / total, 3) if total else 0.0,
    }


# metrics_hermes 모킹 패치 컨텍스트 ──────────────────────────────────────────

_HERMES_MOCK = MagicMock()
_HERMES_MOCK.score_action_extraction = _stub_score_action_extraction
_HERMES_MOCK.score_response_format = _stub_score_response_format
_HERMES_MOCK.summarize_metrics = _stub_summarize_metrics


def _make_call_fn(speak: str, actions: list[dict]):
    """post_user_message의 call_fn 인자로 쓸 모킹 함수 반환.

    Ollama가 JSON action 형식으로 응답하는 것처럼 동작한다.
    반환 타입은 dict (Sprint 18 시그니처: {"role": ..., "content": ...}).
    """
    payload = json.dumps({"speak": speak, "actions": actions}, ensure_ascii=False)

    def _fn(messages, **kwargs):
        return {"role": "assistant", "content": payload}

    return _fn


class TestRunChatEvalBothPass(unittest.TestCase):
    """정상 JSON action 응답 → 2개 시나리오 모두 pass."""

    def test_two_scenarios_both_pass(self):
        scenarios = [
            {
                "id": "s1",
                "user_input": "5월 31일까지 발표자료 만들어야해",
                "expected_actions": [{"type": "create_task", "title": "발표자료"}],
            },
            {
                "id": "s2",
                "user_input": "6월 10일까지 보고서 제출해야해",
                "expected_actions": [{"type": "create_task", "title": "보고서"}],
            },
        ]

        call_fn_s1 = _make_call_fn("발표자료 등록했어!", [{"type": "create_task", "title": "발표자료", "deadline": "2026-05-31"}])
        call_fn_s2 = _make_call_fn("보고서 등록했어!", [{"type": "create_task", "title": "보고서", "deadline": "2026-06-10"}])

        # 두 시나리오가 다른 call_fn을 쓰도록 순서대로 반환
        call_seq = [call_fn_s1, call_fn_s2]
        call_idx = [0]

        def combined_call_fn(messages, **kwargs):
            idx = call_idx[0]
            call_idx[0] += 1
            fn = call_seq[idx % len(call_seq)]
            return fn(messages, **kwargs)

        with patch.dict(sys.modules, {"eval.metrics_hermes": _HERMES_MOCK}):
            from eval.runner_sprint29 import run_chat_eval
            result = run_chat_eval(scenarios, call_fn=combined_call_fn)

        self.assertEqual(len(result["per_sample"]), 2)
        for sample in result["per_sample"]:
            self.assertTrue(sample["passed"], f"시나리오 {sample['id']} 실패: {sample}")
        self.assertEqual(result["summary"]["passed"], 2)


class TestRunChatEvalFormatFail(unittest.TestCase):
    """call_fn이 thinking-leaked 텍스트 반환 → format_compliance 실패."""

    def test_thinking_leaked_format_fails(self):
        scenarios = [
            {
                "id": "leak",
                "user_input": "내일까지 숙제 해야해",
                "expected_actions": [{"type": "create_task", "title": "숙제"}],
            }
        ]

        # thinking 태그가 섞인 응답 (format_compliance 실패 유발)
        leaked_payload = (
            "<think>사용자가 숙제 등록을 원한다</think>"
            + json.dumps({"speak": "숙제 등록!", "actions": [{"type": "create_task", "title": "숙제"}]}, ensure_ascii=False)
        )

        def leaky_call_fn(messages, **kwargs):
            return {"role": "assistant", "content": leaked_payload}

        with patch.dict(sys.modules, {"eval.metrics_hermes": _HERMES_MOCK}):
            from eval.runner_sprint29 import run_chat_eval
            result = run_chat_eval(scenarios, call_fn=leaky_call_fn)

        sample = result["per_sample"][0]
        self.assertFalse(
            sample["format"]["passed"],
            "format_compliance이 passed=True여선 안 된다",
        )
        self.assertIn("thinking_leaked", sample["format"].get("issues", []))
        self.assertFalse(sample["passed"])


class TestRunChatEvalActionMismatch(unittest.TestCase):
    """actions가 expected와 불일치 → tool_call_accuracy = 0."""

    def test_wrong_actions_accuracy_zero(self):
        scenarios = [
            {
                "id": "mismatch",
                "user_input": "발표자료 만들어야해",
                "expected_actions": [{"type": "create_task", "title": "발표자료"}],
            }
        ]

        # 전혀 다른 title로 응답
        def wrong_call_fn(messages, **kwargs):
            payload = json.dumps({
                "speak": "완전히 다른 것 등록!",
                "actions": [{"type": "create_task", "title": "완전히다른것"}],
            }, ensure_ascii=False)
            return {"role": "assistant", "content": payload}

        with patch.dict(sys.modules, {"eval.metrics_hermes": _HERMES_MOCK}):
            from eval.runner_sprint29 import run_chat_eval
            result = run_chat_eval(scenarios, call_fn=wrong_call_fn)

        sample = result["per_sample"][0]
        self.assertEqual(
            sample["extraction"]["tool_call_accuracy"],
            0.0,
            f"tool_call_accuracy가 0이어야 한다: {sample['extraction']}",
        )
        self.assertFalse(sample["extraction"]["passed"])
        self.assertFalse(sample["passed"])


if __name__ == "__main__":
    unittest.main()
