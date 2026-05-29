"""Sprint 12 / Wave 1 — Tasks API.

자연어 chat에서 추출되거나 명시 POST로 등록된 task. Wave 2의 FolderWatcher가
folder_path가 있는 task를 주기 스캔. Wave 3의 Followup scheduler가 deadline에
가까운 open task에 대해 chat을 자동 push.
"""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from backend.deps import (
    assert_user_matches,
    get_db,
    resolve_user_from_token,
)
from backend.schemas import (
    FolderSnapshotItem,
    FolderSnapshotListResponse,
    TaskBlankFileRequest,
    TaskCreateRequest,
    TaskFileItem,
    TaskFileListResponse,
    TaskListResponse,
    TaskResponse,
    TaskUpdateRequest,
)
from fastapi.responses import FileResponse

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


@router.post("/_admin/trigger-followup", status_code=200)
def admin_trigger_followup(
    conn: sqlite3.Connection = Depends(get_db),
    token_user_id: str = Depends(resolve_user_from_token),
) -> dict:
    """Sprint 17 시연용 — 토큰 소유자 본인의 task만 즉시 follow-up dispatch.

    cooldown은 그대로 적용. 데모할 때 폴링을 기다리지 않게 한다.
    """
    from pipeline.followup import dispatch_due_followups

    sent = dispatch_due_followups(conn)
    # 본인 user의 결과만 필터링
    mine = [s for s in sent if s.get("user_id") == token_user_id]
    return {"sent_count": len(mine), "items": mine}


_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._\-가-힣]")
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25MB per file


def _upload_root() -> Path:
    """Resolve at call-time so tests can override TOMORROW_YOU_UPLOAD_ROOT after import."""
    return Path(os.environ.get("TOMORROW_YOU_UPLOAD_ROOT", "/data/uploads"))


def _safe_filename(raw: str) -> str:
    """Strip path components + restrict charset. Returns non-empty safe basename."""
    base = os.path.basename(raw or "")
    base = _SAFE_NAME_RE.sub("_", base).strip("._")
    return base or "file"


@router.post("/{task_id}/upload", response_model=TaskResponse)
async def upload_files(
    task_id: int,
    files: list[UploadFile] = File(...),
    conn: sqlite3.Connection = Depends(get_db),
    token_user_id: str = Depends(resolve_user_from_token),
) -> TaskResponse:
    """task에 첨부 파일 업로드. 파일은 /data/uploads/{user}/{task}/ 에 저장하고
    task.folder_path가 비어있으면 해당 디렉터리로 자동 세팅한다.

    파일 크기 제한 25MB/개. 파일명은 path traversal 방지 위해 sanitize.
    """
    existing = _load_task(conn, task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")
    assert_user_matches(token_user_id, existing["user_id"])
    if not files:
        raise HTTPException(status_code=400, detail="No files")

    dest = _upload_root() / existing["user_id"] / str(task_id)
    dest.mkdir(parents=True, exist_ok=True)

    saved: list[str] = []
    for f in files:
        name = _safe_filename(f.filename or "")
        out = dest / name
        # Avoid clobbering: append _1, _2, ... if exists
        if out.exists():
            stem, suffix = out.stem, out.suffix
            i = 1
            while out.exists():
                out = dest / f"{stem}_{i}{suffix}"
                i += 1
        size = 0
        with out.open("wb") as fout:
            while True:
                chunk = await f.read(64 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > _MAX_UPLOAD_BYTES:
                    fout.close()
                    out.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File {name} exceeds {_MAX_UPLOAD_BYTES // (1024*1024)}MB",
                    )
                fout.write(chunk)
        saved.append(out.name)

    # task.folder_path 미설정이면 자동 세팅
    if not existing.get("folder_path"):
        conn.execute(
            "UPDATE Task SET folder_path = ?, updated_at = ? WHERE id = ?",
            (str(dest), _now_iso(), task_id),
        )
    else:
        conn.execute(
            "UPDATE Task SET updated_at = ? WHERE id = ?",
            (_now_iso(), task_id),
        )
    conn.commit()
    row = conn.execute("SELECT * FROM Task WHERE id = ?", (task_id,)).fetchone()
    return _row_to_task(row)


def _resolve_task_file(existing: dict, filename: str) -> Path:
    """Resolve a per-task upload file. Validates that path stays inside the
    user/task upload directory (path traversal defense)."""
    name = _safe_filename(filename or "")
    base = (_upload_root() / existing["user_id"] / str(existing["id"])).resolve()
    target = (base / name).resolve()
    # 반드시 base 안에 있어야 함
    if not str(target).startswith(str(base) + os.sep) and target != base:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return target


@router.get("/{task_id}/files", response_model=TaskFileListResponse)
def list_task_files(
    task_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    token_user_id: str = Depends(resolve_user_from_token),
) -> TaskFileListResponse:
    """task의 업로드 디렉터리 내 파일 목록. 디렉터리 없으면 빈 list."""
    existing = _load_task(conn, task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")
    assert_user_matches(token_user_id, existing["user_id"])

    base = _upload_root() / existing["user_id"] / str(task_id)
    files: list[TaskFileItem] = []
    if base.exists() and base.is_dir():
        for p in sorted(base.iterdir()):
            if not p.is_file():
                continue
            st = p.stat()
            files.append(
                TaskFileItem(
                    name=p.name,
                    size=st.st_size,
                    mtime=datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
                )
            )
    return TaskFileListResponse(
        task_id=task_id, folder_path=existing.get("folder_path"), files=files,
    )


@router.delete("/{task_id}/files/{filename}", status_code=204)
def delete_task_file(
    task_id: int,
    filename: str,
    conn: sqlite3.Connection = Depends(get_db),
    token_user_id: str = Depends(resolve_user_from_token),
) -> None:
    """업로드된 단일 파일 삭제. 없는 파일도 204로 처리 (idempotent)."""
    existing = _load_task(conn, task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")
    assert_user_matches(token_user_id, existing["user_id"])

    target = _resolve_task_file(existing, filename)
    if target.exists() and target.is_file():
        target.unlink()
        conn.execute(
            "UPDATE Task SET updated_at = ? WHERE id = ?", (_now_iso(), task_id),
        )
        conn.commit()


@router.get("/{task_id}/files/{filename}/download")
def download_task_file(
    task_id: int,
    filename: str,
    conn: sqlite3.Connection = Depends(get_db),
    token_user_id: str = Depends(resolve_user_from_token),
):
    """업로드된 파일 다운로드. attachment Content-Disposition."""
    existing = _load_task(conn, task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")
    assert_user_matches(token_user_id, existing["user_id"])

    target = _resolve_task_file(existing, filename)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        path=str(target),
        filename=target.name,
        media_type="application/octet-stream",
    )


_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_NEW_FILE_EXTS = {"docx", "xlsx", "pptx", "md", "txt"}
_BINARY_TEMPLATE_EXTS = {"docx", "xlsx", "pptx"}


@router.post("/{task_id}/files/new")
def create_blank_file(
    task_id: int,
    body: "TaskBlankFileRequest",
    conn: sqlite3.Connection = Depends(get_db),
    token_user_id: str = Depends(resolve_user_from_token),
) -> dict:
    """task의 업로드 디렉터리에 빈 docx/xlsx/pptx/md/txt 생성."""
    existing = _load_task(conn, task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")
    assert_user_matches(token_user_id, existing["user_id"])

    ext = body.ext.lower().lstrip(".")
    if ext not in _NEW_FILE_EXTS:
        raise HTTPException(
            status_code=400, detail=f"ext must be one of {sorted(_NEW_FILE_EXTS)}",
        )

    # 파일명 sanitize + ext 강제
    base = _safe_filename(body.filename or "")
    if base.lower().endswith(f".{ext}"):
        name = base
    else:
        # 기존 확장자 떼고 새 ext 붙임
        if "." in base:
            base = base.rsplit(".", 1)[0]
        name = f"{base}.{ext}"

    dest = _upload_root() / existing["user_id"] / str(task_id)
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / name
    if out.exists():
        stem, suffix = out.stem, out.suffix
        i = 1
        while out.exists():
            out = dest / f"{stem}_{i}{suffix}"
            i += 1

    if ext in _BINARY_TEMPLATE_EXTS:
        tpl = _TEMPLATES_DIR / f"blank.{ext}"
        if not tpl.exists():
            raise HTTPException(
                status_code=503, detail=f"Template missing: blank.{ext}",
            )
        out.write_bytes(tpl.read_bytes())
    elif ext == "md":
        out.write_text("# 새 문서\n", encoding="utf-8")
    elif ext == "txt":
        out.write_text("", encoding="utf-8")

    if not existing.get("folder_path"):
        conn.execute(
            "UPDATE Task SET folder_path = ?, updated_at = ? WHERE id = ?",
            (str(dest), _now_iso(), task_id),
        )
    else:
        conn.execute(
            "UPDATE Task SET updated_at = ? WHERE id = ?",
            (_now_iso(), task_id),
        )
    conn.commit()
    row = conn.execute("SELECT * FROM Task WHERE id = ?", (task_id,)).fetchone()
    task = _row_to_task(row).model_dump()
    task["created_filename"] = out.name
    return task


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
