"""ToolRouter — 입력 컨텍스트 기반 tool 선택 휴리스틱 (G010).

키워드 매핑:
  - "마감" / "시한" / "내일까지" / "일정" / "언제" → google_calendar
  - 파일명패턴 / "문서" / "PPT" / "발표" / "논문" / "파일" → local_files
  - "참고" / "예시" / "검색" / "찾아봐" / "알아봐" → web_search

각 tool 호출은 timeout 3초. 실패해도 시나리오 카드 생성 계속.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentTool:
    """선택된 tool 정보."""
    name: str
    tool_type: str
    agent_tool_id: int
    config: dict = field(default_factory=dict)


# 키워드 → tool 이름 매핑
_KEYWORD_MAP: dict[str, str] = {
    # calendar
    "마감": "google_calendar",
    "시한": "google_calendar",
    "내일까지": "google_calendar",
    "일정": "google_calendar",
    "언제": "google_calendar",
    "데드라인": "google_calendar",
    "due": "google_calendar",
    # local_files
    "문서": "local_files",
    "ppt": "local_files",
    "PPT": "local_files",
    "발표": "local_files",
    "논문": "local_files",
    "파일": "local_files",
    "슬라이드": "local_files",
    "보고서": "local_files",
    # web_search
    "참고": "web_search",
    "예시": "web_search",
    "검색": "web_search",
    "찾아봐": "web_search",
    "알아봐": "web_search",
    "레퍼런스": "web_search",
}

# tool 이름 → DB tool name(AgentTool.name) 매핑
_TOOL_DB_NAMES: dict[str, str] = {
    "google_calendar": "google_calendar.list_events",
    "local_files": "local_files.recent",
    "web_search": "web_search.brave",
}


class ToolRouter:
    """입력 컨텍스트를 분석하여 호출할 tool 목록 반환."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def route(
        self,
        input_context: str,
        user_profile: Optional[dict] = None,
        active_persona_id: Optional[int] = None,
    ) -> list[AgentTool]:
        """입력 키워드 분석 후 활성화된 tool만 반환 (중복 제거, 우선순위 순)."""
        if not input_context or not input_context.strip():
            return []

        matched_tool_names: list[str] = []
        seen: set[str] = set()

        lower_input = input_context.lower()
        for keyword, tool_name in _KEYWORD_MAP.items():
            if keyword.lower() in lower_input and tool_name not in seen:
                matched_tool_names.append(tool_name)
                seen.add(tool_name)

        result: list[AgentTool] = []
        for tool_name in matched_tool_names:
            db_name = _TOOL_DB_NAMES.get(tool_name)
            if not db_name:
                continue
            row = self._conn.execute(
                "SELECT id, name, type, config_json FROM AgentTool WHERE name = ? AND enabled = 1",
                (db_name,),
            ).fetchone()
            if row is None:
                continue
            import json
            config = json.loads(row["config_json"]) if row["config_json"] else {}
            result.append(AgentTool(
                name=row["name"],
                tool_type=row["type"],
                agent_tool_id=row["id"],
                config=config,
            ))

        return result
