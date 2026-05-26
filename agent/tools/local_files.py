"""LocalFilesTool — read-only 로컬 파일 스캔 어댑터 (G010).

사용자가 지정한 폴더에서 최근 수정 파일을 조회.
write 액션 (파일 생성·수정·삭제) 은 영구 비목표 (FINAL_GOAL.md §11).
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


_TOOL_DB_NAME = "local_files.recent"

# 키워드 → 파일 확장자 필터 매핑
_CATEGORY_FILTERS: dict[str, list[str]] = {
    "ppt": [".pptx", ".key", ".ppt"],
    "PPT": [".pptx", ".key", ".ppt"],
    "발표": [".pptx", ".key", ".ppt"],
    "논문": [".tex", ".docx", ".pdf"],
    "보고서": [".docx", ".pdf", ".hwp"],
}


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


def _resolve_extensions(category_keyword: Optional[str]) -> Optional[list[str]]:
    """카테고리 키워드에서 파일 확장자 필터 반환. 없으면 None (전체)."""
    if category_keyword is None:
        return None
    for key, exts in _CATEGORY_FILTERS.items():
        if key.lower() in category_keyword.lower():
            return exts
    return None


class LocalFilesTool:
    """로컬 파일 시스템 read-only 스캔 어댑터."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        user_id: str,
        watched_dirs: list[str],
    ) -> None:
        self._conn = conn
        self._user_id = user_id
        self._watched_dirs = [Path(d) for d in watched_dirs]

    def recent_files(
        self,
        category_keyword: Optional[str] = None,
        hours: int = 72,
    ) -> list[dict]:
        """최근 N시간 이내 수정된 파일 목록 반환.

        category_keyword 예:
          - "PPT" / "발표" → .pptx, .key 필터
          - "논문" → .tex, .docx 필터
          - None → 전체 파일

        반환 dict 필드: path, name, size_bytes, modified_at(ISO), extension
        """
        tool_id = _get_tool_id(self._conn)
        input_data = {
            "category_keyword": category_keyword,
            "hours": hours,
            "watched_dirs": [str(d) for d in self._watched_dirs],
        }
        start_time = time.monotonic()

        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            extensions = _resolve_extensions(category_keyword)
            result: list[dict] = []

            for watched_dir in self._watched_dirs:
                if not watched_dir.exists() or not watched_dir.is_dir():
                    continue
                for entry in watched_dir.rglob("*"):
                    if not entry.is_file():
                        continue
                    if extensions and entry.suffix.lower() not in [e.lower() for e in extensions]:
                        continue
                    try:
                        mtime = entry.stat().st_mtime
                        modified_at = datetime.fromtimestamp(mtime, tz=timezone.utc)
                        if modified_at < cutoff:
                            continue
                        result.append({
                            "path": str(entry),
                            "name": entry.name,
                            "size_bytes": entry.stat().st_size,
                            "modified_at": modified_at.isoformat(),
                            "extension": entry.suffix.lower(),
                        })
                    except OSError:
                        continue

            result.sort(key=lambda f: f["modified_at"], reverse=True)

            latency_ms = int((time.monotonic() - start_time) * 1000)
            if tool_id is not None:
                _log_invocation(
                    self._conn, self._user_id, tool_id,
                    input_data, {"files": result, "count": len(result)}, latency_ms, None,
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
