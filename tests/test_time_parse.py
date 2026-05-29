"""Sprint 40 — Korean deadline parser tests."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.time_parse import parse_natural_deadline


def _kst(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone(timedelta(hours=9)))


class TestTimeParse(unittest.TestCase):
    def setUp(self):
        # 2026-05-29 (Fri) 10:00 KST = 2026-05-29 01:00 UTC
        self.now = datetime(2026, 5, 29, 1, 0, tzinfo=timezone.utc)

    def test_24h_colon_format(self):
        r = parse_natural_deadline("18:30까지 보고서", self.now)
        self.assertIsNotNone(r)
        self.assertTrue(r.startswith("2026-05-29T18:30"))

    def test_24h_n_si_today(self):
        r = parse_natural_deadline("오늘 18시까지", self.now)
        self.assertIsNotNone(r)
        self.assertTrue(r.startswith("2026-05-29T18:00"))

    def test_n_si_alone(self):
        r = parse_natural_deadline("15시", self.now)
        self.assertIsNotNone(r)
        self.assertTrue(r.startswith("2026-05-29T15:00"))

    def test_ohu_n_si(self):
        r = parse_natural_deadline("오후 6시까지", self.now)
        self.assertIsNotNone(r)
        self.assertTrue(r.startswith("2026-05-29T18:00"))

    def test_ojeon_n_si(self):
        r = parse_natural_deadline("오전 9시 30분", self.now)
        # 10시 현재 시각보다 과거 → 다음날
        self.assertIsNotNone(r)
        self.assertTrue(r.startswith("2026-05-30T09:30"))

    def test_naeil_jeongo(self):
        r = parse_natural_deadline("내일 정오까지", self.now)
        self.assertIsNotNone(r)
        self.assertTrue(r.startswith("2026-05-30T12:00"))

    def test_oneul_jeonyok(self):
        r = parse_natural_deadline("오늘 저녁", self.now)
        self.assertIsNotNone(r)
        self.assertTrue(r.startswith("2026-05-29T18:00"))

    def test_modae(self):
        r = parse_natural_deadline("모레 안에", self.now)
        # 시간대 없으면 23:59
        self.assertIsNotNone(r)
        self.assertTrue(r.startswith("2026-05-31T23:59"))

    def test_next_week_weekday(self):
        # 2026-05-29 금. 다음주 월 = 2026-06-01
        r = parse_natural_deadline("다음주 월요일까지", self.now)
        self.assertIsNotNone(r)
        self.assertTrue(r.startswith("2026-06-01"))

    def test_no_time_returns_none(self):
        r = parse_natural_deadline("뭔가 해야해", self.now)
        self.assertIsNone(r)

    def test_24h_past_today_rolls_to_tomorrow(self):
        # 현재 10시. "8시" → 이미 지남 → 다음날 8시.
        r = parse_natural_deadline("8시까지", self.now)
        self.assertIsNotNone(r)
        self.assertTrue(r.startswith("2026-05-30T08:00"))

    def test_empty_string(self):
        self.assertIsNone(parse_natural_deadline("", self.now))


if __name__ == "__main__":
    unittest.main()
