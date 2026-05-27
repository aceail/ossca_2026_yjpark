"""Sprint 18 — Agent Tool Registry.

LLM이 Ollama tools API(OpenAI function-calling 호환)를 통해 자율 호출하는
함수들. 각 tool은 (name, description, parameters JSON-schema, executor)
4튜플. executor는 (conn, user_id, **kwargs) → dict 결과.

Hermes-3 / Qwen 3 / Llama 3.1 모두 이 schema 형식 지원. EXAONE은 미검증
이라 backend가 NAEIL_AGENT_MODEL 환경변수로 swap 가능.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

ToolExecutor = Callable[..., dict]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict           # JSON-schema
    executor: ToolExecutor


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_task(conn: sqlite3.Connection, user_id: str, query) -> Optional[dict]:
    """task_id(int) 또는 title 부분 일치로 task row 1개."""
    if query is None:
        return None
    try:
        tid = int(query)
        row = conn.execute(
            "SELECT * FROM Task WHERE id = ? AND user_id = ?", (tid, user_id),
        ).fetchone()
        if row:
            return dict(row)
    except (TypeError, ValueError):
        pass
    s = str(query).strip()
    if not s:
        return None
    row = conn.execute(
        """SELECT * FROM Task WHERE user_id = ? AND title LIKE ?
           ORDER BY CASE status WHEN 'open' THEN 0 WHEN 'done' THEN 1 ELSE 2 END,
                    created_at DESC LIMIT 1""",
        (user_id, f"%{s}%"),
    ).fetchone()
    return dict(row) if row else None


def _parse_deadline(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = str(value).strip()
    if not v:
        return None
    import re
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        return f"{v}T23:59:00+09:00"
    return v


# ────────────────────────────────────────────────────────────────────
# Tool executors
# ────────────────────────────────────────────────────────────────────


def _exec_create_task(conn: sqlite3.Connection, user_id: str, **kw) -> dict:
    title = str(kw.get("title", "")).strip()
    if not title:
        return {"ok": False, "error": "title required"}
    deadline = _parse_deadline(kw.get("deadline"))
    folder = kw.get("folder")
    now = _now_iso()
    cur = conn.execute(
        """INSERT INTO Task (user_id, title, deadline_at, folder_path, status,
                             created_at, updated_at)
           VALUES (?, ?, ?, ?, 'open', ?, ?)""",
        (user_id, title, deadline, folder if isinstance(folder, str) else None, now, now),
    )
    conn.commit()
    return {"ok": True, "task_id": cur.lastrowid, "title": title, "deadline": deadline}


def _exec_list_tasks(conn: sqlite3.Connection, user_id: str, **kw) -> dict:
    status = kw.get("status")
    sql = "SELECT id, title, deadline_at, folder_path, status FROM Task WHERE user_id = ?"
    args: list = [user_id]
    if status:
        sql += " AND status = ?"
        args.append(status)
    sql += " ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END, deadline_at IS NULL, deadline_at"
    rows = conn.execute(sql, args).fetchall()
    return {"ok": True, "tasks": [dict(r) for r in rows]}


def _exec_update_task(conn: sqlite3.Connection, user_id: str, **kw) -> dict:
    q = kw.get("task")
    existing = _resolve_task(conn, user_id, q)
    if not existing:
        return {"ok": False, "error": f"task '{q}' not found"}
    fields: list[str] = []
    args: list = []
    if "status" in kw and kw["status"] in ("open", "done", "abandoned"):
        fields.append("status = ?"); args.append(kw["status"])
    if "deadline" in kw:
        dl = _parse_deadline(kw["deadline"])
        if dl:
            fields.append("deadline_at = ?"); args.append(dl)
    if "folder" in kw and isinstance(kw["folder"], str):
        fields.append("folder_path = ?"); args.append(kw["folder"])
    if "new_title" in kw and str(kw["new_title"]).strip():
        fields.append("title = ?"); args.append(str(kw["new_title"]).strip())
    if not fields:
        return {"ok": False, "error": "no updatable fields"}
    fields.append("updated_at = ?"); args.append(_now_iso()); args.append(existing["id"])
    conn.execute(f"UPDATE Task SET {', '.join(fields)} WHERE id = ?", args)
    conn.commit()
    return {"ok": True, "task_id": existing["id"], "title": existing["title"]}


def _exec_delete_task(conn: sqlite3.Connection, user_id: str, **kw) -> dict:
    existing = _resolve_task(conn, user_id, kw.get("task"))
    if not existing:
        return {"ok": False, "error": "task not found"}
    conn.execute("DELETE FROM Task WHERE id = ?", (existing["id"],))
    conn.commit()
    return {"ok": True, "deleted_id": existing["id"], "title": existing["title"]}


def _exec_task_progress(conn: sqlite3.Connection, user_id: str, **kw) -> dict:
    existing = _resolve_task(conn, user_id, kw.get("task"))
    if not existing:
        return {"ok": False, "error": "task not found"}
    rows = conn.execute(
        """SELECT taken_at, file_count, total_bytes, newest_mtime FROM FolderSnapshot
           WHERE task_id = ? ORDER BY taken_at DESC LIMIT 2""",
        (existing["id"],),
    ).fetchall()
    if not rows:
        return {"ok": True, "task_id": existing["id"], "snapshots": [],
                "note": "폴더 등록되지 않았거나 아직 스캔 안 됨"}
    snaps = [dict(r) for r in rows]
    return {"ok": True, "task_id": existing["id"], "title": existing["title"],
            "folder_path": existing["folder_path"], "snapshots": snaps,
            "progressed": (len(snaps) >= 2 and snaps[0]["file_count"] > snaps[1]["file_count"])}


def _exec_recent_followups(conn: sqlite3.Connection, user_id: str, **kw) -> dict:
    limit = min(int(kw.get("limit", 5) or 5), 20)
    rows = conn.execute(
        """SELECT m.id, m.content, m.created_at, s.id AS session_id
           FROM ChatMessage m JOIN ChatSession s ON s.id = m.chat_session_id
           WHERE s.user_id = ? AND m.role = 'assistant'
           ORDER BY m.id DESC LIMIT ?""",
        (user_id, limit),
    ).fetchall()
    return {"ok": True, "messages": [dict(r) for r in rows]}


# ────────────────────────────────────────────────────────────────────
# Registry
# ────────────────────────────────────────────────────────────────────


REGISTRY: dict[str, Tool] = {
    "create_task": Tool(
        name="create_task",
        description="새 작업 + 마감일을 등록한다. 사용자가 마감 있는 일을 처음 언급할 때 호출.",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "작업 제목"},
                "deadline": {"type": "string", "description": "YYYY-MM-DD (옵션)"},
                "folder": {"type": "string", "description": "관련 폴더 절대 경로 (옵션)"},
            },
            "required": ["title"],
        },
        executor=_exec_create_task,
    ),
    "list_tasks": Tool(
        name="list_tasks",
        description="사용자의 작업 목록을 가져온다. 사용자가 '뭐 있더라', '오늘 일정' 등 물을 때.",
        parameters={
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["open", "done", "abandoned"]},
            },
        },
        executor=_exec_list_tasks,
    ),
    "update_task": Tool(
        name="update_task",
        description="기존 작업의 상태·마감·폴더·제목 변경. task는 id 또는 제목 일부.",
        parameters={
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "task id 또는 제목 일부"},
                "status": {"type": "string", "enum": ["open", "done", "abandoned"]},
                "deadline": {"type": "string", "description": "YYYY-MM-DD"},
                "folder": {"type": "string"},
                "new_title": {"type": "string"},
            },
            "required": ["task"],
        },
        executor=_exec_update_task,
    ),
    "delete_task": Tool(
        name="delete_task",
        description="작업 영구 삭제. 사용자가 '없애줘' 명시할 때만 호출.",
        parameters={
            "type": "object",
            "properties": {"task": {"type": "string"}},
            "required": ["task"],
        },
        executor=_exec_delete_task,
    ),
    "get_task_progress": Tool(
        name="get_task_progress",
        description="작업의 폴더 스냅샷 진척 확인 — 최근 2개 비교해 파일 추가 여부, mtime 변화 반환.",
        parameters={
            "type": "object",
            "properties": {"task": {"type": "string"}},
            "required": ["task"],
        },
        executor=_exec_task_progress,
    ),
    "get_recent_followups": Tool(
        name="get_recent_followups",
        description="최근 어시스턴트(follow-up·응답) 메시지 N개. 어떤 알림을 보냈는지 확인.",
        parameters={
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 20}},
        },
        executor=_exec_recent_followups,
    ),
}


def tool_schemas_for_ollama() -> list[dict]:
    """Ollama /api/chat의 tools 파라미터로 넘길 OpenAI function-calling 형식."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in REGISTRY.values()
    ]


def dispatch(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    name: str,
    arguments: Any,
) -> dict:
    """LLM이 결정한 tool_call을 안전하게 실행. 알려지지 않은 tool은 error 반환."""
    tool = REGISTRY.get(name)
    if not tool:
        return {"ok": False, "error": f"unknown tool: {name}"}
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError:
            return {"ok": False, "error": f"invalid arguments JSON for {name}"}
    if not isinstance(arguments, dict):
        arguments = {}
    try:
        return tool.executor(conn, user_id, **arguments)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"executor failed: {exc}"}
