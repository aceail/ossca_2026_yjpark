"""사후 회고 알림 스케줄 + RegretScore 기록 — G007."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass
class RegretReminder:
    avoidance_session_id: int
    remind_at: str         # ISO 8601
    delivered: bool = False


def schedule_reminder(
    conn: sqlite3.Connection,
    avoidance_session_id: int,
    *,
    after_hours: int = 24,
) -> RegretReminder:
    """AvoidanceSession.user_decision != 'transition'인 경우 24h 후 회고 알림 schedule.

    MVP: DB에 remind_at 컬럼이 없으므로 settings_json·간단 in-memory.
    실제 push는 G008/MVP UI에서 처리.
    """
    remind = (datetime.now(timezone.utc) + timedelta(hours=after_hours)).isoformat()
    return RegretReminder(avoidance_session_id=avoidance_session_id, remind_at=remind)


def record_regret_score(
    conn: sqlite3.Connection,
    *,
    avoidance_session_id: int,
    user_id: str,
    intensity: int,
    free_text: str | None = None,
) -> int:
    """RegretScore INSERT — intensity 0-10 CHECK constraint은 DB-level에서 보장."""
    if not 0 <= intensity <= 10:
        raise ValueError(f"intensity must be 0-10, got {intensity}")
    cur = conn.execute(
        """INSERT INTO RegretScore (avoidance_session_id, user_id, intensity, free_text, recorded_at)
           VALUES (?, ?, ?, ?, ?)""",
        (avoidance_session_id, user_id, intensity, free_text, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    return cur.lastrowid
