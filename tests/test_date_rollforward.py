"""Sprint 16 — LLM 학습 cutoff(2023 등) 과거 연도 자동 roll-forward."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.chat import _parse_deadline_to_iso, _roll_forward_if_past


def _today_kst():
    return (datetime.now(timezone.utc) + timedelta(hours=9)).date()


class TestRollForward(unittest.TestCase):
    def test_past_year_rolls_to_future(self):
        """LLM이 '2023-12-31'을 줘도 오늘 이후로 굴림."""
        result = _roll_forward_if_past("2023-12-31")
        out_date = datetime.fromisoformat(result).date()
        self.assertGreaterEqual(out_date, _today_kst())
        self.assertEqual(out_date.month, 12)
        self.assertEqual(out_date.day, 31)

    def test_future_year_preserved(self):
        future = (_today_kst() + timedelta(days=180)).isoformat()
        self.assertEqual(_roll_forward_if_past(future), future)

    def test_today_preserved(self):
        today_str = _today_kst().isoformat()
        self.assertEqual(_roll_forward_if_past(today_str), today_str)

    def test_recent_past_within_30d_preserved(self):
        """30일 이내 과거는 안 굴림 — 사용자가 정말 과거를 말했을 수 있음."""
        recent = (_today_kst() - timedelta(days=10)).isoformat()
        self.assertEqual(_roll_forward_if_past(recent), recent)

    def test_invalid_input_preserved(self):
        self.assertEqual(_roll_forward_if_past("bad-input"), "bad-input")


class TestParseDeadlineUsesRollForward(unittest.TestCase):
    def test_parses_yyyy_mm_dd_with_rollforward(self):
        out = _parse_deadline_to_iso("2023-06-19")
        self.assertIsNotNone(out)
        date_part = out.split("T")[0]
        out_date = datetime.fromisoformat(date_part).date()
        self.assertGreaterEqual(out_date, _today_kst())
        self.assertEqual(out_date.month, 6)
        self.assertEqual(out_date.day, 19)

    def test_full_iso_rolls_forward_date_part_only(self):
        out = _parse_deadline_to_iso("2023-10-06T23:59:00+09:00")
        self.assertIn("23:59:00+09:00", out)
        date_part = out.split("T")[0]
        out_date = datetime.fromisoformat(date_part).date()
        self.assertGreaterEqual(out_date, _today_kst())


if __name__ == "__main__":
    unittest.main()
