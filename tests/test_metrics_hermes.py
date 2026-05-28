"""Hermes 액션/포맷 메트릭 단위 테스트.

6개 필수 시나리오:
1. test_perfect_match: 모든 기대 필드 일치 → tool_call_accuracy == 1.0
2. test_type_mismatch: 타입 불일치 → type_match_rate < 1.0, tool_call_accuracy 0
3. test_partial_field_match: 일부 필드 일치 → field_match_rate < 1.0
4. test_response_format_valid_json: 유효한 JSON → json_valid True
5. test_response_format_thinking_leak: thinking leak 감지 → no_thinking_leak False
6. test_summarize_pass_rate: 10 샘플 중 7개 통과 → pass_rate 0.7
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from eval.metrics_hermes import (  # noqa: E402
    score_action_extraction,
    score_response_format,
    summarize_metrics,
)


class TestScoreActionExtraction(unittest.TestCase):
    def test_perfect_match(self):
        """모든 기대 필드가 일치 → tool_call_accuracy == 1.0"""
        actual = [
            {
                "type": "create_task",
                "title": "완료: 슬라이드 첫 장 작성",
                "deadline": "2026-05-29",
                "folder_path": "Work/Slides",
                "status": "pending",
            }
        ]
        expected = [
            {
                "type": "create_task",
                "title_contains": "슬라이드",
                "deadline_starts_with": "2026-05-29",
                "folder_contains": "Slides",
                "status_equals": "pending",
            }
        ]
        result = score_action_extraction(actual, expected)
        self.assertEqual(result["tool_call_accuracy"], 1.0)
        self.assertTrue(result["passed"])
        self.assertTrue(result["count_match"])

    def test_type_mismatch(self):
        """타입 불일치 → tool_call_accuracy 0, type_match_rate < 1.0"""
        actual = [
            {
                "type": "update_task",
                "title": "작업 업데이트",
            }
        ]
        expected = [
            {
                "type": "create_task",
                "title_contains": "작업",
            }
        ]
        result = score_action_extraction(actual, expected)
        self.assertEqual(result["tool_call_accuracy"], 0.0)
        self.assertFalse(result["passed"])

    def test_partial_field_match(self):
        """일부 필드 일치: title OK, deadline 불일치 → field_match_rate < 1.0"""
        actual = [
            {
                "type": "create_task",
                "title": "슬라이드 작성",
                "deadline": "2026-05-30",
            }
        ]
        expected = [
            {
                "type": "create_task",
                "title_contains": "슬라이드",
                "deadline_starts_with": "2026-05-29",
            }
        ]
        result = score_action_extraction(actual, expected)
        self.assertLess(result["field_match_rate"], 1.0)
        self.assertEqual(result["tool_call_accuracy"], 0.0)

    def test_no_expected_actions(self):
        """기대 액션 없음 → 모두 일치"""
        actual = [{"type": "create_task", "title": "작업"}]
        expected = []
        result = score_action_extraction(actual, expected)
        self.assertFalse(result["count_match"])
        self.assertEqual(result["tool_call_accuracy"], 0.0)

    def test_count_mismatch(self):
        """액션 개수 불일치 → count_match False, tool_call_accuracy 0"""
        actual = [
            {"type": "create_task", "title": "작업 1"},
            {"type": "create_task", "title": "작업 2"},
        ]
        expected = [
            {"type": "create_task", "title_contains": "작업 1"}
        ]
        result = score_action_extraction(actual, expected)
        self.assertFalse(result["count_match"])
        self.assertEqual(result["tool_call_accuracy"], 0.0)

    def test_case_insensitive_title_match(self):
        """제목 대소문자 무시 매칭"""
        actual = [
            {
                "type": "create_task",
                "title": "REVIEW PPT SLIDES",
            }
        ]
        expected = [
            {
                "type": "create_task",
                "title_contains": "ppt slides",
            }
        ]
        result = score_action_extraction(actual, expected)
        self.assertEqual(result["tool_call_accuracy"], 1.0)

    def test_deadline_with_timestamp(self):
        """deadline이 timestamp 형식일 때 날짜 추출 확인"""
        actual = [
            {
                "type": "create_task",
                "title": "작업",
                "deadline": "2026-05-29T15:30:00+09:00",
            }
        ]
        expected = [
            {
                "type": "create_task",
                "title_contains": "작업",
                "deadline_starts_with": "2026-05-29",
            }
        ]
        result = score_action_extraction(actual, expected)
        self.assertEqual(result["tool_call_accuracy"], 1.0)


class TestScoreResponseFormat(unittest.TestCase):
    def test_response_format_valid_json(self):
        """유효한 JSON 포함 → json_valid True, passed True"""
        content = '{"status": "success", "message": "작업 생성됨"}'
        result = score_response_format(content)
        self.assertTrue(result["json_valid"])
        self.assertTrue(result["no_thinking_leak"])
        self.assertTrue(result["passed"])

    def test_response_format_invalid_json(self):
        """유효하지 않은 JSON → json_valid False"""
        content = '{"status": "success", "message": "작업" incomplete}'
        result = score_response_format(content)
        self.assertFalse(result["json_valid"])
        self.assertFalse(result["passed"])

    def test_response_format_thinking_leak_okay(self):
        """thinking leak 감지: 'Okay' 시작 → no_thinking_leak False"""
        content = 'Okay, let me create this task. {"status": "success"}'
        result = score_response_format(content)
        self.assertFalse(result["no_thinking_leak"])
        self.assertFalse(result["passed"])

    def test_response_format_thinking_leak_let_me(self):
        """thinking leak 감지: 'Let me' 시작"""
        content = "Let me think about this. <json>...</json>"
        result = score_response_format(content)
        self.assertFalse(result["no_thinking_leak"])

    def test_response_format_thinking_leak_i_need(self):
        """thinking leak 감지: 'I need to' 시작"""
        content = "I need to check the schedule first. {}"
        result = score_response_format(content)
        self.assertFalse(result["no_thinking_leak"])

    def test_response_format_thinking_leak_think_tag(self):
        """thinking leak 감지: '<think>' 시작"""
        content = "<think>Let me process this</think>{\n}"
        result = score_response_format(content)
        self.assertFalse(result["no_thinking_leak"])

    def test_response_format_thinking_leak_first(self):
        """thinking leak 감지: 'First, ' 시작"""
        content = "First, I need to understand this. {}"
        result = score_response_format(content)
        self.assertFalse(result["no_thinking_leak"])

    def test_response_format_thinking_leak_the_user(self):
        """thinking leak 감지: 'The user' 시작"""
        content = "The user asked for a task. {}"
        result = score_response_format(content)
        self.assertFalse(result["no_thinking_leak"])

    def test_response_format_thinking_leak_looking_at(self):
        """thinking leak 감지: 'Looking at' 시작"""
        content = "Looking at the request... {}"
        result = score_response_format(content)
        self.assertFalse(result["no_thinking_leak"])

    def test_response_format_json_after_whitespace(self):
        """JSON이 공백 후에 있어도 인식"""
        content = "  \n  \n  {\n    \"status\": \"ok\"\n  }"
        result = score_response_format(content)
        self.assertTrue(result["json_valid"])
        self.assertTrue(result["no_thinking_leak"])
        self.assertTrue(result["passed"])

    def test_response_format_clean_korean(self):
        """깨끗한 JSON (thinking leak 없음) → passed True"""
        content = '{"작업": "슬라이드", "상태": "완료"}'
        result = score_response_format(content)
        self.assertTrue(result["json_valid"])
        self.assertTrue(result["no_thinking_leak"])
        self.assertTrue(result["passed"])


class TestSummarizeMetrics(unittest.TestCase):
    def test_summarize_pass_rate(self):
        """10 샘플, 7개 통과 (tool_call_accuracy == 1.0) → pass_rate 0.7"""
        per_sample = []
        for i in range(10):
            passed = i < 7  # 0-6 통과, 7-9 실패
            per_sample.append({
                "extraction": {
                    "tool_call_accuracy": 1.0 if passed else 0.0,
                    "field_match_rate": 1.0 if passed else 0.5,
                },
                "format": {
                    "json_valid": True,
                    "no_thinking_leak": True,
                }
            })
        result = summarize_metrics(per_sample)
        self.assertEqual(result["n"], 10)
        self.assertEqual(result["pass_count"], 7)
        self.assertAlmostEqual(result["pass_rate"], 0.7)

    def test_summarize_empty(self):
        """빈 샘플 리스트 → 0으로 채움"""
        result = summarize_metrics([])
        self.assertEqual(result["n"], 0)
        self.assertEqual(result["pass_count"], 0)
        self.assertEqual(result["pass_rate"], 0.0)
        self.assertEqual(result["format_compliance_rate"], 0.0)

    def test_summarize_all_pass(self):
        """모든 샘플 통과 → pass_rate 1.0"""
        per_sample = []
        for i in range(5):
            per_sample.append({
                "extraction": {
                    "tool_call_accuracy": 1.0,
                    "field_match_rate": 1.0,
                },
                "format": {
                    "json_valid": True,
                    "no_thinking_leak": True,
                }
            })
        result = summarize_metrics(per_sample)
        self.assertEqual(result["pass_rate"], 1.0)
        self.assertEqual(result["format_compliance_rate"], 1.0)

    def test_summarize_format_compliance(self):
        """형식 규정 준수율 계산"""
        per_sample = [
            {
                "extraction": {"tool_call_accuracy": 1.0, "field_match_rate": 1.0},
                "format": {"json_valid": True, "no_thinking_leak": True},
            },
            {
                "extraction": {"tool_call_accuracy": 0.0, "field_match_rate": 0.5},
                "format": {"json_valid": False, "no_thinking_leak": True},
            },
            {
                "extraction": {"tool_call_accuracy": 1.0, "field_match_rate": 1.0},
                "format": {"json_valid": True, "no_thinking_leak": False},
            },
        ]
        result = summarize_metrics(per_sample)
        # 첫 샘플만 json_valid AND no_thinking_leak 모두 True
        self.assertAlmostEqual(result["format_compliance_rate"], 1.0 / 3)

    def test_summarize_avg_field_match_rate(self):
        """평균 field_match_rate 계산"""
        per_sample = [
            {
                "extraction": {"tool_call_accuracy": 0.0, "field_match_rate": 0.5},
                "format": {"json_valid": True, "no_thinking_leak": True},
            },
            {
                "extraction": {"tool_call_accuracy": 0.0, "field_match_rate": 0.8},
                "format": {"json_valid": True, "no_thinking_leak": True},
            },
        ]
        result = summarize_metrics(per_sample)
        # (0.5 + 0.8) / 2 = 0.65
        self.assertAlmostEqual(result["avg_field_match_rate"], 0.65)


if __name__ == "__main__":
    unittest.main()
