"""GoogleCalendarTool — read-only Google Calendar 어댑터 (G010).

현재 구현: mock/placeholder.
  - ExternalIntegration에 google_calendar 토큰이 있으면 mock 일정 3개 반환.
  - 토큰 없으면 빈 list 반환.

TODO(향후 라운드):
  실제 OAuth 2.0 로컬 콜백 흐름 (127.0.0.1:random_port) + Google Calendar API v3
  events.list 연동. 토큰 갱신(refresh) 로직 포함.

write 액션 (일정 추가·수정·삭제) 은 영구 비목표 (FINAL_GOAL.md §11).
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from agent.integrations import get_integration


_TOOL_DB_NAME = "google_calendar.list_events"


def _log_invocation(
    conn: sqlite3.Connection,
    user_id: str,
    agent_tool_id: int,
    input_data: dict,
    output_data: Optional[dict],
    latency_ms: int,
    error: Optional[str],
) -> None:
    conn.execute(
        """
        INSERT INTO ToolInvocation
            (user_id, agent_tool_id, input_json, output_json, latency_ms, error, invoked_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            agent_tool_id,
            json.dumps(input_data, ensure_ascii=False),
            json.dumps(output_data, ensure_ascii=False) if output_data is not None else None,
            latency_ms,
            error,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def _get_tool_id(conn: sqlite3.Connection) -> Optional[int]:
    row = conn.execute(
        "SELECT id FROM AgentTool WHERE name = ?", (_TOOL_DB_NAME,)
    ).fetchone()
    return row["id"] if row else None


class GoogleCalendarTool:
    """Google Calendar read-only 어댑터.

    현재는 mock 구현. 실제 OAuth는 향후 라운드에서 구현.
    """

    def __init__(self, conn: sqlite3.Connection, user_id: str) -> None:
        self._conn = conn
        self._user_id = user_id
        self._integration = get_integration(conn, user_id, "google_calendar")

    def list_upcoming_events(self, days: int = 7) -> list[dict]:
        """다가올 일정 조회 (mock).

        토큰이 있으면 mock 일정 3개 반환.
        토큰 없으면 빈 list 반환.
        모든 호출은 ToolInvocation에 자동 로그.
        """
        tool_id = _get_tool_id(self._conn)
        input_data = {"days": days, "user_id": self._user_id}
        start_time = time.monotonic()

        try:
            if self._integration is None:
                result: list[dict] = []
            else:
                result = self._mock_events(days)

            latency_ms = int((time.monotonic() - start_time) * 1000)
            if tool_id is not None:
                _log_invocation(
                    self._conn, self._user_id, tool_id,
                    input_data, {"events": result}, latency_ms, None,
                )
            return result

        except Exception as exc:
            latency_ms = int((time.monotonic() - start_time) * 1000)
            if tool_id is not None:
                _log_invocation(
                    self._conn, self._user_id, tool_id,
                    input_data, None, latency_ms, str(exc),
                )
            return []

    def _mock_events(self, days: int) -> list[dict]:
        now = datetime.now(timezone.utc)
        return [
            {
                "id": "mock_event_1",
                "summary": "팀 미팅",
                "start": (now + timedelta(hours=22, minutes=46)).isoformat(),
                "end": (now + timedelta(hours=23, minutes=46)).isoformat(),
                "description": "주간 팀 스탠드업",
            },
            {
                "id": "mock_event_2",
                "summary": "프로젝트 마감",
                "start": (now + timedelta(days=2)).isoformat(),
                "end": (now + timedelta(days=2, hours=1)).isoformat(),
                "description": "OSSCA G010 산출물 제출",
            },
            {
                "id": "mock_event_3",
                "summary": "주간 회고",
                "start": (now + timedelta(days=5)).isoformat(),
                "end": (now + timedelta(days=5, hours=1)).isoformat(),
                "description": "이번 주 작업 회고",
            },
        ]
