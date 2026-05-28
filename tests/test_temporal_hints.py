"""Sprint 25 — relative time → absolute date hint injection."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.chat import _build_temporal_hints


def _today():
    return (datetime.now(timezone.utc) + timedelta(hours=9)).date()


class TestTemporalHints(unittest.TestCase):
    def test_no_relative_word(self):
        self.assertEqual(_build_temporal_hints("그냥 안녕 메시지"), "")

    def test_empty(self):
        self.assertEqual(_build_temporal_hints(""), "")

    def test_today_maps_to_today(self):
        h = _build_temporal_hints("오늘 9시 30분에 미팅")
        self.assertIn("오늘 = " + _today().isoformat(), h)
        self.assertIn("강제 매핑", h)

    def test_tomorrow_maps_to_today_plus_1(self):
        h = _build_temporal_hints("내일까지 보고서")
        expected = (_today() + timedelta(days=1)).isoformat()
        self.assertIn("내일 = " + expected, h)

    def test_day_after_tomorrow(self):
        h = _build_temporal_hints("모레 일정")
        expected = (_today() + timedelta(days=2)).isoformat()
        self.assertIn("모레 = " + expected, h)

    def test_this_week(self):
        h = _build_temporal_hints("이번주 안에 끝내야해")
        self.assertIn("이번주 끝", h)

    def test_next_week(self):
        h = _build_temporal_hints("다음주 화요일까지")
        self.assertIn("다음주 시작", h)
        self.assertIn("다음 화요일", h)

    def test_specific_weekday(self):
        h = _build_temporal_hints("금요일까지 끝내야해")
        self.assertIn("다음 금요일", h)

    def test_multiple_mentions(self):
        h = _build_temporal_hints("오늘 회의, 내일 발표")
        self.assertIn("오늘 = ", h)
        self.assertIn("내일 = ", h)


if __name__ == "__main__":
    unittest.main()
