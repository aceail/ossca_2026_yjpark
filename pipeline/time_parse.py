"""Sprint 40 — 한국어 자연어 시간 표현 → ISO timestamp (KST).

Backend가 LLM의 deadline_at 추출을 정규식 결과로 덮어쓰는 데 쓴다.
정규식이 None을 반환하면 LLM 값 유지.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

_KST = timezone(timedelta(hours=9))

# 한국어 시간 표현 매핑
_PERIOD_HOURS = {
    "새벽": 4,
    "아침": 9,
    "오전": 10,
    "정오": 12,
    "낮": 14,
    "오후": 14,
    "저녁": 18,
    "밤": 21,
}

_RELATIVE_DAY = {
    "오늘": 0,
    "내일": 1,
    "모레": 2,
    "글피": 3,
}

# (월~일) 요일 → datetime weekday 0~6
_WEEKDAYS = {
    "월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6,
}


def _today_kst(now: datetime) -> datetime:
    """now를 KST 자정 기준 시각으로 정규화."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    n_kst = now.astimezone(_KST)
    return n_kst.replace(hour=0, minute=0, second=0, microsecond=0)


def _to_iso(dt: datetime) -> str:
    return dt.astimezone(_KST).isoformat()


def parse_natural_deadline(text: str, now: datetime) -> Optional[str]:
    """한국어 텍스트에서 deadline 추출. 못 잡으면 None.

    우선순위: 명시적 시각 표현 > 상대 날짜 키워드 > None
    """
    if not text:
        return None
    base = _today_kst(now)
    now_kst = _ensure_kst(now)
    explicit_today = "오늘" in text

    # 1. "HH:MM" (24h colon) — word boundary 없이 숫자:숫자 패턴
    m = re.search(r"([01]?\d|2[0-3]):([0-5]\d)", text)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        target = base + timedelta(hours=h, minutes=mi)
        if target < now_kst and not explicit_today:
            target += timedelta(days=1)
        return _to_iso(target)

    # 2. "오전/오후 + N시[분]"
    m = re.search(r"(오전|오후)\s*(\d{1,2})\s*시\s*(\d{1,2})?\s*분?", text)
    if m:
        period, h_str, min_str = m.group(1), m.group(2), m.group(3)
        h = int(h_str)
        if period == "오후" and h < 12:
            h += 12
        elif period == "오전" and h == 12:
            h = 0
        mi = int(min_str) if min_str else 0
        target = base + timedelta(hours=h, minutes=mi)
        if target < now_kst and not explicit_today:
            target += timedelta(days=1)
        return _to_iso(target)

    # 3. "N시" (no period)
    m = re.search(r"(\d{1,2})\s*시(?:[간까-])?", text)
    if m:
        h = int(m.group(1))
        if 0 <= h <= 23:
            target = base + timedelta(hours=h)
            if target < now_kst and not explicit_today:
                target += timedelta(days=1)
            return _to_iso(target)

    # 4. 상대 날짜 + 시간대 (예: "오늘 저녁", "내일 정오") — 반드시 둘 다 있어야 매칭
    for kw_day, off in _RELATIVE_DAY.items():
        if kw_day in text:
            for kw_period, hour in _PERIOD_HOURS.items():
                if kw_period in text:
                    target = base + timedelta(days=off, hours=hour)
                    return _to_iso(target)
            # 시간대 없는 상대날짜만 있는 경우 (예: "모레 안에")
            target = base + timedelta(days=off, hours=23, minutes=59)
            return _to_iso(target)

    # 5. "다음주 + 요일" 또는 "이번주 + 요일"
    m = re.search(r"(다음주|이번주)\s*(월|화|수|목|금|토|일)", text)
    if m:
        scope, day = m.group(1), m.group(2)
        target_wd = _WEEKDAYS[day]
        current_wd = now_kst.weekday()
        offset = (target_wd - current_wd) % 7

        if scope == "이번주" and offset == 0:
            # 이번주 같은 요일: 정확히 7일 뒤 (다음주 같은 요일)
            offset = 7
        elif scope == "다음주" and offset == 0:
            # 다음주 같은 요일: 정확히 7일 뒤
            offset = 7
        elif scope == "다음주":
            # 다음주 다른 요일: offset이 이미 양수이고 "다음주"이므로 추가 검사 불필요
            # (현재 요일 이후의 요일은 자동으로 다음 등장)
            pass

        target = base + timedelta(days=offset, hours=23, minutes=59)
        return _to_iso(target)

    return None


def _ensure_kst(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_KST)
