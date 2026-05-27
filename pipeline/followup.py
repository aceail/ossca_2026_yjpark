"""Wave 3 — Follow-up dispatcher.

매 cycle (default 1h)마다:
  1. open task 순회
  2. task별 days_until_deadline + 폴더 진척 + Slow Harm 신호 측정
  3. followup_tone.decide_followup → 메시지 생성
  4. 같은 사용자의 ChatSession이 있으면 그곳에, 없으면 새 세션 생성
  5. assistant message INSERT (사용자가 다음 chat 열 때 보임)
  6. Task.last_followup_at 업데이트

Wave 5에서 push 알림(VAPID)도 같은 dispatch 시점에 발송.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from pipeline.chat import _record_message, create_chat_session  # noqa: WPS437
from pipeline.followup_tone import decide_followup
from regret import compute_signal_level


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _days_until(deadline_iso: Optional[str], now: datetime) -> Optional[int]:
    """timedelta.days: 23h 후 → 0 (오늘), 25h 후 → 1 (내일), 2h 전 → -1.

    이 정의가 사용자 직관과 가장 잘 맞고 follow-up tone matrix와도 일치.
    """
    dt = _parse_iso(deadline_iso)
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (dt - now).days


def _hours_since(iso: Optional[str], now: datetime) -> Optional[float]:
    dt = _parse_iso(iso)
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0.0, (now - dt).total_seconds() / 3600)


def _detect_progress(conn: sqlite3.Connection, task_id: int) -> bool:
    """최근 2개 FolderSnapshot 비교 — file_count or newest_mtime 증가면 True.

    스냅샷이 0개나 1개면 False (변화 판단 불가 → 추궁 톤이 default).
    """
    rows = conn.execute(
        """SELECT file_count, total_bytes, newest_mtime FROM FolderSnapshot
           WHERE task_id = ? ORDER BY taken_at DESC LIMIT 2""",
        (task_id,),
    ).fetchall()
    if len(rows) < 2:
        return False
    cur, prev = rows[0], rows[1]
    if cur["file_count"] > prev["file_count"]:
        return True
    if cur["total_bytes"] > prev["total_bytes"]:
        return True
    if cur["newest_mtime"] and prev["newest_mtime"] and cur["newest_mtime"] > prev["newest_mtime"]:
        return True
    return False


def _latest_chat_session(conn: sqlite3.Connection, user_id: str) -> Optional[int]:
    row = conn.execute(
        """SELECT id FROM ChatSession WHERE user_id = ?
           ORDER BY updated_at DESC LIMIT 1""",
        (user_id,),
    ).fetchone()
    return row["id"] if row else None


def _persona_tone_for_task(conn: sqlite3.Connection, task_row: sqlite3.Row) -> Optional[str]:
    persona_id = task_row["persona_id"]
    if not persona_id:
        # task에 persona 없으면 user의 active persona 사용
        prof = conn.execute(
            "SELECT active_persona_id FROM UserProfile WHERE user_id = ?",
            (task_row["user_id"],),
        ).fetchone()
        persona_id = prof["active_persona_id"] if prof else None
    if not persona_id:
        return None
    row = conn.execute(
        "SELECT tone_mode FROM Persona WHERE id = ?", (persona_id,),
    ).fetchone()
    return row["tone_mode"] if row else None


def _persona_id_for_task(conn: sqlite3.Connection, task_row: sqlite3.Row) -> Optional[int]:
    if task_row["persona_id"]:
        return task_row["persona_id"]
    prof = conn.execute(
        "SELECT active_persona_id FROM UserProfile WHERE user_id = ?",
        (task_row["user_id"],),
    ).fetchone()
    return prof["active_persona_id"] if prof else None


def dispatch_due_followups(
    conn: sqlite3.Connection,
    *,
    now: Optional[datetime] = None,
) -> list[dict]:
    """모든 open task를 검사해 due한 것에 follow-up 메시지를 INSERT.

    Returns: 발송된 follow-up 목록 ({task_id, user_id, tone, message}).
    """
    now = now or _now_utc()
    tasks = conn.execute(
        """SELECT id, user_id, title, deadline_at, persona_id, last_followup_at
           FROM Task WHERE status = 'open'"""
    ).fetchall()

    sent: list[dict] = []
    for t in tasks:
        days = _days_until(t["deadline_at"], now)
        last_h = _hours_since(t["last_followup_at"], now)
        progressed = _detect_progress(conn, t["id"])
        signal = compute_signal_level(conn, t["user_id"], now=now)
        persona_tone = _persona_tone_for_task(conn, t)

        decision = decide_followup(
            title=t["title"],
            days_until_deadline=days,
            last_followup_hours_ago=last_h,
            progressed=progressed,
            signal_level=signal,
            persona_tone=persona_tone,
        )
        if not decision.should_send:
            continue

        # 메시지를 ChatSession에 INSERT (없으면 생성)
        session_id = _latest_chat_session(conn, t["user_id"])
        if session_id is None:
            persona_id = _persona_id_for_task(conn, t)
            session_id = create_chat_session(
                conn,
                user_id=t["user_id"],
                persona_id=persona_id,
                title=f"follow-up: {t['title']}",
            )

        _record_message(conn, session_id, "assistant", decision.message)
        conn.execute(
            "UPDATE Task SET last_followup_at = ?, updated_at = ? WHERE id = ?",
            (now.isoformat(), now.isoformat(), t["id"]),
        )
        conn.commit()

        sent.append({
            "task_id": t["id"],
            "user_id": t["user_id"],
            "session_id": session_id,
            "tone": decision.tone,
            "message": decision.message,
        })

    return sent
