"""Sprint 12 / Wave 1 — Tasks API.

자연어 chat에서 추출되거나 명시 POST로 등록된 task. Wave 2의 FolderWatcher가
folder_path가 있는 task를 주기 스캔. Wave 3의 Followup scheduler가 deadline에
가까운 open task에 대해 chat을 자동 push.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.deps import (
    assert_user_matches,
    get_db,
    resolve_user_from_token,
)
from backend.schemas import (
    FolderSnapshotItem,
    FolderSnapshotListResponse,
    TaskCreateRequest,
    TaskListResponse,
    TaskResponse,
    TaskUpdateRequest,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

VALID_STATUSES = {"open", "done", "abandoned"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_task(row) -> TaskResponse:
    return TaskResponse(
        id=row["id"],
        user_id=row["user_id"],
        persona_id=row["persona_id"],
        title=row["title"],
        deadline_at=row["deadline_at"],
        folder_path=row["folder_path"],
        status=row["status"],
        last_followup_at=row["last_followup_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _load_task(conn: sqlite3.Connection, task_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM Task WHERE id = ?", (task_id,)).fetchone()
    return dict(row) if row else None


@router.post("", response_model=TaskResponse, status_code=201)
def create_task(
    body: TaskCreateRequest,
    conn: sqlite3.Connection = Depends(get_db),
    token_user_id: str = Depends(resolve_user_from_token),
) -> TaskResponse:
    assert_user_matches(token_user_id, body.user_id)
    now = _now_iso()
    cur = conn.execute(
        """INSERT INTO Task (user_id, persona_id, title, deadline_at, folder_path,
                             status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 'open', ?, ?)""",
        (
            body.user_id,
            body.persona_id,
            body.title.strip(),
            body.deadline_at,
            body.folder_path,
            now,
            now,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM Task WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _row_to_task(row)


@router.get("", response_model=TaskListResponse)
def list_tasks(
    user_id: str = Query(...),
    status: Optional[str] = Query(default=None),
    conn: sqlite3.Connection = Depends(get_db),
    token_user_id: str = Depends(resolve_user_from_token),
) -> TaskListResponse:
    assert_user_matches(token_user_id, user_id)
    sql = "SELECT * FROM Task WHERE user_id = ?"
    args: list = [user_id]
    if status:
        if status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid status. {VALID_STATUSES}")
        sql += " AND status = ?"
        args.append(status)
    sql += " ORDER BY deadline_at IS NULL, deadline_at ASC, created_at ASC"
    rows = conn.execute(sql, args).fetchall()
    return TaskListResponse(user_id=user_id, tasks=[_row_to_task(r) for r in rows])


@router.patch("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: int,
    body: TaskUpdateRequest,
    conn: sqlite3.Connection = Depends(get_db),
    token_user_id: str = Depends(resolve_user_from_token),
) -> TaskResponse:
    existing = _load_task(conn, task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")
    assert_user_matches(token_user_id, existing["user_id"])

    fields: list[str] = []
    args: list = []
    if body.title is not None:
        fields.append("title = ?")
        args.append(body.title.strip())
    if body.deadline_at is not None:
        fields.append("deadline_at = ?")
        args.append(body.deadline_at)
    if body.folder_path is not None:
        fields.append("folder_path = ?")
        args.append(body.folder_path)
    if body.status is not None:
        if body.status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid status. {VALID_STATUSES}")
        fields.append("status = ?")
        args.append(body.status)
    if body.persona_id is not None:
        fields.append("persona_id = ?")
        args.append(body.persona_id)

    if not fields:
        return _row_to_task(conn.execute("SELECT * FROM Task WHERE id = ?", (task_id,)).fetchone())

    fields.append("updated_at = ?")
    args.append(_now_iso())
    args.append(task_id)
    conn.execute(f"UPDATE Task SET {', '.join(fields)} WHERE id = ?", args)
    conn.commit()
    return _row_to_task(conn.execute("SELECT * FROM Task WHERE id = ?", (task_id,)).fetchone())


@router.delete("/{task_id}", status_code=204)
def delete_task(
    task_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    token_user_id: str = Depends(resolve_user_from_token),
) -> None:
    existing = _load_task(conn, task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")
    assert_user_matches(token_user_id, existing["user_id"])
    conn.execute("DELETE FROM Task WHERE id = ?", (task_id,))
    conn.commit()


@router.get("/{task_id}/snapshots", response_model=FolderSnapshotListResponse)
def list_snapshots(
    task_id: int,
    limit: int = Query(default=20, ge=1, le=200),
    conn: sqlite3.Connection = Depends(get_db),
    token_user_id: str = Depends(resolve_user_from_token),
) -> FolderSnapshotListResponse:
    existing = _load_task(conn, task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")
    assert_user_matches(token_user_id, existing["user_id"])
    rows = conn.execute(
        """SELECT id, task_id, taken_at, file_count, total_bytes, newest_mtime
           FROM FolderSnapshot WHERE task_id = ?
           ORDER BY taken_at DESC LIMIT ?""",
        (task_id, limit),
    ).fetchall()
    return FolderSnapshotListResponse(
        task_id=task_id,
        snapshots=[FolderSnapshotItem(**dict(r)) for r in rows],
    )
