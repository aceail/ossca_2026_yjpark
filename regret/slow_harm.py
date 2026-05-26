"""Slow Harm 시계열 모니터 — G007 / FINAL_GOAL v2 §5.5.

급성 위기(자해 키워드)뿐 아니라 저강도 만성 손상을 시계열로 추적:
- 자기 비난 언어 빈도 (사용자 자유 텍스트에서)
- 미래 상상 시 실패 이미지 디폴트화 비율 (시나리오 카드 card_type 비율)
- 미루기를 정체성 결함으로 해석하는 표현 카운트 ("또 이러네" 등)
- 앱 켜기 전 긴장도 자기보고 (별도 사용자 입력)
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


SELF_BLAME_WORDS = ["한심", "쓰레기", "병신", "또 이러네", "나는 안 돼", "역시"]
IDENTITY_FAILURE_PHRASES = ["또 이러네", "원래 그런", "어차피", "나는 늘"]


def week_start_iso(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(timezone.utc)
    monday = dt - timedelta(days=dt.weekday())
    return monday.strftime("%Y-W%V")


@dataclass
class SlowHarmMonitor:
    user_id: str

    def collect_user_text(self, conn: sqlite3.Connection, since_iso: str) -> list[str]:
        rows = conn.execute(
            "SELECT avoidance_input FROM AvoidanceSession WHERE user_id = ? AND created_at >= ?",
            (self.user_id, since_iso),
        ).fetchall()
        texts = [r["avoidance_input"] for r in rows]
        prows = conn.execute(
            "SELECT answer_text FROM ProbeAnswer WHERE user_id = ? AND answer_text != '__skip__' AND answered_at >= ?",
            (self.user_id, since_iso),
        ).fetchall()
        texts.extend(r["answer_text"] for r in prows)
        free_rows = conn.execute(
            "SELECT free_text FROM RegretScore WHERE user_id = ? AND recorded_at >= ? AND free_text IS NOT NULL",
            (self.user_id, since_iso),
        ).fetchall()
        texts.extend(r["free_text"] for r in free_rows if r["free_text"])
        return texts

    def count_blame(self, texts: list[str]) -> int:
        return sum(text.count(word) for text in texts for word in SELF_BLAME_WORDS)

    def count_identity_failure(self, texts: list[str]) -> int:
        return sum(text.count(p) for text in texts for p in IDENTITY_FAILURE_PHRASES)

    def failure_imagery_ratio(self, conn: sqlite3.Connection, since_iso: str) -> float:
        """주간 regret 카드 비율 (regret / (regret + recovery))."""
        rows = conn.execute(
            """SELECT card_type, COUNT(*) AS n FROM ScenarioCard sc
               JOIN AvoidanceSession a ON sc.avoidance_session_id = a.id
               WHERE a.user_id = ? AND sc.created_at >= ?
               GROUP BY card_type""",
            (self.user_id, since_iso),
        ).fetchall()
        counts = {r["card_type"]: r["n"] for r in rows}
        regret = counts.get("regret", 0)
        recovery = counts.get("recovery", 0)
        denom = regret + recovery
        return regret / denom if denom else 0.0


def build_weekly_snapshot(
    conn: sqlite3.Connection,
    user_id: str,
    *,
    week_anchor: datetime | None = None,
    pre_card_tension_self_report: float | None = None,
) -> int:
    """현재 주의 SafetyHarmTimeSeries snapshot INSERT (UPSERT)."""
    anchor = week_anchor or datetime.now(timezone.utc)
    week = week_start_iso(anchor)
    since = (anchor - timedelta(days=7)).isoformat()
    monitor = SlowHarmMonitor(user_id=user_id)
    texts = monitor.collect_user_text(conn, since)
    blame = monitor.count_blame(texts)
    identity_fail = monitor.count_identity_failure(texts)
    failure_ratio = monitor.failure_imagery_ratio(conn, since)

    conn.execute(
        """INSERT INTO SafetyHarmTimeSeries
           (user_id, week_start, self_blame_word_count, failure_imagery_ratio,
            identity_failure_phrases_count, pre_card_tension_self_report, snapshot_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(user_id, week_start) DO UPDATE SET
             self_blame_word_count = excluded.self_blame_word_count,
             failure_imagery_ratio = excluded.failure_imagery_ratio,
             identity_failure_phrases_count = excluded.identity_failure_phrases_count,
             pre_card_tension_self_report = COALESCE(excluded.pre_card_tension_self_report, SafetyHarmTimeSeries.pre_card_tension_self_report),
             snapshot_at = excluded.snapshot_at""",
        (
            user_id, week, blame, failure_ratio, identity_fail,
            pre_card_tension_self_report, datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM SafetyHarmTimeSeries WHERE user_id = ? AND week_start = ?",
        (user_id, week),
    ).fetchone()
    return row["id"]
