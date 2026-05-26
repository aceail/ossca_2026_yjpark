"""G009 v1 — EvaluationHarness 메트릭 단위 테스트 (unittest, 표준 라이브러리).

CI Tier 1 회귀:
- 9 차원 자동 메트릭 함수들이 알려진 입력에서 올바른 출력을 내는가
- 30 골든 샘플 파일이 무결한가 (분포·구조)

실행:
    python3 -m unittest discover tests
또는:
    python3 -m unittest tests.test_eval_harness

통합 테스트(실제 Ollama 호출)는 별도 — `python3 scripts/eval_harness.py --strict`로.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.eval_harness import (  # noqa: E402
    CardMetrics,
    DECISIVE_ENDING_RE,
    FORBIDDEN_GROUPS,
    NON_HANGUL_ETC_RE,
    SECOND_PERSON_RE,
    Sample,
    TIME_RE,
    compute_metrics,
    evaluate,
    extract_json,
)


def make_sample(**kw) -> Sample:
    defaults = dict(
        id="T",
        persona_context="test",
        category="test",
        avoidance_input="test",
        profile_summary="test",
        timeline_hint="test",
        expected_mode="regret",
        expected_card_type="regret",
        metric_overrides={},
    )
    defaults.update(kw)
    return Sample(**defaults)


class TestJSONExtraction(unittest.TestCase):
    def test_valid_json(self):
        text = '{"card_type":"regret","sentences":{"fact":"f","feeling":"g","micro_action":"a"}}'
        self.assertIsNotNone(extract_json(text))

    def test_invalid_json(self):
        self.assertIsNone(extract_json("not json at all"))

    def test_strips_think_block(self):
        text = '<think>thinking content here</think>{"card_type":"regret"}'
        result = extract_json(text)
        self.assertIsNotNone(result)
        self.assertEqual(result["card_type"], "regret")

    def test_json_in_code_block(self):
        text = '```\n{"card_type":"soft_stop","message":"safe"}\n```'
        result = extract_json(text)
        self.assertIsNotNone(result)
        self.assertEqual(result["card_type"], "soft_stop")


class TestSecondPersonDetection(unittest.TestCase):
    def test_detects_dangsin(self):
        text = "당신은 지금 어떡할 거야"
        hits = [m.group(1) for m in SECOND_PERSON_RE.finditer(text)]
        self.assertIn("당신은", hits)

    def test_detects_neoga(self):
        text = "너가 지금 미루고 있어"
        hits = [m.group(1) for m in SECOND_PERSON_RE.finditer(text)]
        self.assertIn("너가", hits)

    def test_clean_first_person(self):
        text = "나는 지금 책상 앞에 있다 내가 첫 줄을 쓴다"
        hits = list(SECOND_PERSON_RE.finditer(text))
        self.assertEqual(hits, [])


class TestForbiddenWords(unittest.TestCase):
    def test_gaslighting_word_detected(self):
        body = "너의 의지는 약하다"
        hit = False
        for w in FORBIDDEN_GROUPS["한국 가스라이팅"]:
            if w in body:
                hit = True
                break
        self.assertTrue(hit)

    def test_identity_failure_word_detected(self):
        body = "넌 도태될 거야"
        hit = any(w in body for w in FORBIDDEN_GROUPS["정체성 결함"])
        self.assertTrue(hit)

    def test_comparison_shame_detected(self):
        body = "다른 사람들은 이미 끝냈어"
        hit = any(w in body for w in FORBIDDEN_GROUPS["비교 수치심"])
        self.assertTrue(hit)

    def test_comfort_word_detected(self):
        body = "괜찮아 천천히 해도 돼"
        hit = any(w in body for w in FORBIDDEN_GROUPS["위로 무력화"])
        self.assertTrue(hit)

    def test_clean_body(self):
        body = "내일 9시 5분 전의 나는 빈 슬라이드를 보고 있다"
        for grp, words in FORBIDDEN_GROUPS.items():
            for w in words:
                self.assertNotIn(w, body, f"unexpected {grp}/{w}")


class TestTimeSpecific(unittest.TestCase):
    def test_minute_format(self):
        self.assertIsNotNone(TIME_RE.search("새벽 1시 14분이다"))

    def test_hour_only_format(self):
        self.assertIsNotNone(TIME_RE.search("23시 현재"))

    def test_duration_format(self):
        self.assertIsNotNone(TIME_RE.search("마감까지 11시간 0분 남았다"))

    def test_no_time(self):
        self.assertIsNone(TIME_RE.search("새벽이다"))


class TestDecisiveEnding(unittest.TestCase):
    def test_kyeonda(self):
        self.assertIsNotNone(DECISIVE_ENDING_RE.search("워드를 켠다"))

    def test_sseunda(self):
        self.assertIsNotNone(DECISIVE_ENDING_RE.search("첫 문장만 쓴다"))

    def test_proposal_form_rejected(self):
        self.assertIsNone(DECISIVE_ENDING_RE.search("워드를 켜보자"))

    def test_question_form_rejected(self):
        self.assertIsNone(DECISIVE_ENDING_RE.search("지금 시작해볼래?"))


class TestNonHangul(unittest.TestCase):
    def test_chinese_detected(self):
        text = "회피의 휩荡한 마음"
        self.assertIsNotNone(NON_HANGUL_ETC_RE.search(text))

    def test_japanese_detected(self):
        text = "あ 회피"
        self.assertIsNotNone(NON_HANGUL_ETC_RE.search(text))

    def test_clean_korean(self):
        text = "회피의 막막한 마음. PPT 0장. 마감 11시간."
        self.assertIsNone(NON_HANGUL_ETC_RE.search(text))


class TestComputeMetrics(unittest.TestCase):
    def test_valid_card_passes(self):
        sample = make_sample(id="T01")
        raw = (
            '{"card_type":"regret","sentences":{'
            '"fact":"새벽 1시 14분이다. 디스커션 0줄. 마감까지 22시간 46분 남았다.",'
            '"feeling":"내일 23시 30분의 나는 백지 앞에 앉아 있다.",'
            '"micro_action":"워드를 켠다."}}'
        )
        metrics = compute_metrics(sample, raw)
        self.assertTrue(metrics.json_valid)
        self.assertTrue(metrics.three_sentences)
        self.assertEqual(metrics.second_person_hits, [])
        self.assertEqual(metrics.forbidden_hits, {})
        self.assertTrue(metrics.has_time_specific)
        self.assertTrue(metrics.decisive_ending)
        self.assertEqual(metrics.non_hangul_hits, [])

    def test_second_person_card_flagged(self):
        sample = make_sample(id="T02")
        raw = '{"card_type":"regret","sentences":{"fact":"당신은 지금 0장이야.","feeling":"f","micro_action":"a"}}'
        metrics = compute_metrics(sample, raw)
        self.assertIn("당신은", metrics.second_person_hits)

    def test_invalid_json_metrics(self):
        sample = make_sample(id="T03")
        metrics = compute_metrics(sample, "garbage output")
        self.assertFalse(metrics.json_valid)
        self.assertFalse(metrics.three_sentences)


class TestEvaluate(unittest.TestCase):
    def test_passing_card(self):
        sample = make_sample(id="T01")
        raw = (
            '{"card_type":"regret","sentences":{'
            '"fact":"새벽 1시 14분이다. 디스커션 0줄. 마감까지 22시간 46분 남았다. 어떡하지.",'
            '"feeling":"내일 23시 30분의 나는 백지 앞에 앉아 어제 새벽엔 뭐 했더라를 곱씹고 있다.",'
            '"micro_action":"워드를 켠다."}}'
        )
        metrics = compute_metrics(sample, raw)
        result = evaluate(sample, metrics)
        self.assertTrue(result["pass"], result["issues"])

    def test_length_overflow_fails(self):
        sample = make_sample(id="T04")
        long = "a" * 200
        raw = f'{{"card_type":"regret","sentences":{{"fact":"새벽 1시 14분. {long}","feeling":"f","micro_action":"a"}}}}'
        metrics = compute_metrics(sample, raw)
        result = evaluate(sample, metrics)
        self.assertFalse(result["pass"])
        self.assertTrue(any("D5" in i for i in result["issues"]))

    def test_soft_stop_card_type_required(self):
        sample = make_sample(id="T05", expected_mode="soft_stop", expected_card_type="soft_stop",
                             metric_overrides={"skip_dimensions": [3, 5, 6, 7, 8]})
        raw = '{"card_type":"soft_stop","message":"지금 부담 낮은 응답으로 전환할게요."}'
        metrics = compute_metrics(sample, raw)
        result = evaluate(sample, metrics)
        self.assertTrue(result["pass"], result["issues"])

    def test_soft_stop_wrong_type_fails(self):
        sample = make_sample(id="T06", expected_mode="soft_stop", expected_card_type="soft_stop")
        raw = '{"card_type":"regret","sentences":{"fact":"a","feeling":"b","micro_action":"c"}}'
        metrics = compute_metrics(sample, raw)
        result = evaluate(sample, metrics)
        self.assertFalse(result["pass"])


class TestGoldenSamplesIntegrity(unittest.TestCase):
    SAMPLES_PATH = PROJECT_ROOT / ".omc" / "ultragoal" / "golden_samples_v1.json"

    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(cls.SAMPLES_PATH.read_text(encoding="utf-8"))

    def test_total_count(self):
        self.assertEqual(self.data["total"], 30)
        self.assertEqual(len(self.data["samples"]), 30)

    def test_unique_ids(self):
        ids = [s["id"] for s in self.data["samples"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_mode_distribution(self):
        modes: dict[str, int] = {}
        for s in self.data["samples"]:
            modes[s["expected_mode"]] = modes.get(s["expected_mode"], 0) + 1
        self.assertEqual(modes.get("regret"), 24)
        self.assertEqual(modes.get("recovery"), 5)
        self.assertEqual(modes.get("soft_stop"), 1)

    def test_required_fields(self):
        required = {"id", "persona_context", "category", "avoidance_input",
                    "profile_summary", "timeline_hint", "expected_mode", "expected_card_type"}
        for s in self.data["samples"]:
            self.assertTrue(required.issubset(s.keys()), f"missing fields in {s.get('id')}")


if __name__ == "__main__":
    unittest.main()
