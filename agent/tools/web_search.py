"""WebSearchTool — read-only 웹 검색 어댑터 (G010, 선택적 활성화).

현재 구현: mock/placeholder.
  - 사용자가 명시적으로 활성화한 경우에만 동작 (AgentTool.enabled = 1).
  - query를 받아 mock result 3건 반환.

TODO(향후 라운드):
  Brave Search API 또는 SearXNG 어댑터 실제 연동.
  Search 쿼리는 user-agent 익명화, referer 제거 (FINAL_GOAL.md §15 프라이버시 가드).

write 액션 금지 (FINAL_GOAL.md §11).
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from typing import Optional


_TOOL_DB_NAME = "web_search.brave"


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


class WebSearchTool:
    """웹 검색 read-only 어댑터.

    현재는 mock 구현. 사용자가 명시적으로 활성화한 경우에만 사용.
    """

    def __init__(self, conn: sqlite3.Connection, user_id: str) -> None:
        self._conn = conn
        self._user_id = user_id

    def search(self, query: str, max_results: int = 3) -> list[dict]:
        """웹 검색 수행 (mock).

        반환 dict 필드: title, url, snippet, rank
        모든 호출은 ToolInvocation에 자동 로그.
        """
        tool_id = _get_tool_id(self._conn)
        input_data = {"query": query, "max_results": max_results}
        start_time = time.monotonic()

        try:
            results = self._mock_search(query, max_results)

            latency_ms = int((time.monotonic() - start_time) * 1000)
            if tool_id is not None:
                _log_invocation(
                    self._conn, self._user_id, tool_id,
                    input_data, {"results": results, "count": len(results)}, latency_ms, None,
                )
            return results

        except Exception as exc:
            latency_ms = int((time.monotonic() - start_time) * 1000)
            if tool_id is not None:
                _log_invocation(
                    self._conn, self._user_id, tool_id,
                    input_data, None, latency_ms, str(exc),
                )
            return []

    def _mock_search(self, query: str, max_results: int) -> list[dict]:
        mock_results = [
            {
                "title": f"{query} — 참고 자료 1",
                "url": "https://example.com/ref1",
                "snippet": f"'{query}'에 관한 첫 번째 참고 문서입니다. 핵심 개념과 예시를 포함합니다.",
                "rank": 1,
            },
            {
                "title": f"{query} 실전 가이드",
                "url": "https://example.com/ref2",
                "snippet": f"'{query}' 실무 적용 사례와 단계별 가이드를 제공합니다.",
                "rank": 2,
            },
            {
                "title": f"{query} 관련 최신 동향",
                "url": "https://example.com/ref3",
                "snippet": f"'{query}' 분야의 최신 연구 및 트렌드를 정리한 문서입니다.",
                "rank": 3,
            },
        ]
        return mock_results[:max_results]
