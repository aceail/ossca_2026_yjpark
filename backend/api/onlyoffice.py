"""Sprint 34 — OnlyOffice Document Server integration.

Three endpoints:
- GET /api/tasks/{id}/files/{name}/edit-config — 브라우저가 OnlyOffice를 띄울 때
  필요한 config + JWT 발급. 사용자 토큰 필수.
- GET /api/_oo/doc?t=<jwt> — OnlyOffice DocServer 컨테이너가 docker network
  내부에서 파일을 다운로드할 때 호출. 사용자 토큰 대신 단기 JWT로 인증.
- POST /api/_oo/callback?t=<jwt> — OnlyOffice가 저장 신호를 보낼 때 호출.
  status=2 또는 6면 body.url에서 수정된 파일을 다운로드해 원본 덮어쓰기.

JWT: env TOMORROW_YOU_OO_JWT_SECRET (compose에서 OnlyOffice 컨테이너와 동일).
OnlyOffice도 JWT_ENABLED=true라 우리가 보내는 config 전체를 같은 secret으로
서명해 token 필드에 넣어야 OnlyOffice가 받아들임.
"""

from __future__ import annotations

import os
import sqlite3
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from backend.api.tasks import _load_task, _resolve_task_file, _upload_root
from backend.deps import assert_user_matches, get_db, resolve_user_from_token

router = APIRouter(prefix="/api", tags=["onlyoffice"])

EXT_DOCTYPE = {
    "docx": "word", "doc": "word", "odt": "word",
    "txt": "word", "rtf": "word", "md": "word",
    "xlsx": "cell", "xls": "cell", "ods": "cell", "csv": "cell",
    "pptx": "slide", "ppt": "slide", "odp": "slide",
}

_EDIT_TOKEN_TTL_SEC = 2 * 60 * 60  # 2시간


def _oo_secret() -> str:
    s = os.environ.get("TOMORROW_YOU_OO_JWT_SECRET") or ""
    if not s:
        raise HTTPException(
            status_code=503, detail="OnlyOffice JWT secret not configured",
        )
    return s


def _oo_public_url() -> str:
    return os.environ.get("TOMORROW_YOU_OO_PUBLIC_URL", "http://localhost:8090").rstrip("/")


def _backend_internal_url() -> str:
    return os.environ.get("TOMORROW_YOU_BACKEND_INTERNAL_URL", "http://backend:8001").rstrip("/")


def _oo_internal_url() -> str:
    """docker network 내부에서 OnlyOffice에 접근할 URL (callback host 치환용)."""
    return os.environ.get("TOMORROW_YOU_OO_INTERNAL_URL", "http://onlyoffice").rstrip("/")


def _rewrite_oo_callback_url(url: str) -> str:
    """OnlyOffice가 보낸 callback url의 host:port를 docker internal로 변환.

    OnlyOffice는 자기 외부 URL(예: http://localhost:8090/cache/...)을 callback에
    넣어 보내는데, backend 컨테이너 입장에서 localhost는 자기 자신이라 연결 거부.
    public URL prefix를 internal URL로 치환.
    """
    public = _oo_public_url()
    internal = _oo_internal_url()
    if url.startswith(public + "/"):
        return internal + url[len(public):]
    if url == public:
        return internal
    return url


def _sign_edit_token(*, user_id: str, task_id: int, filename: str) -> str:
    payload = {
        "kind": "edit",
        "user_id": user_id,
        "task_id": task_id,
        "filename": filename,
        "exp": int(
            (datetime.now(timezone.utc) + timedelta(seconds=_EDIT_TOKEN_TTL_SEC)).timestamp()
        ),
    }
    return jwt.encode(payload, _oo_secret(), algorithm="HS256")


def _verify_edit_token(token: str) -> dict:
    try:
        claims = jwt.decode(token, _oo_secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Edit token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid edit token")
    if claims.get("kind") != "edit":
        raise HTTPException(status_code=401, detail="Wrong token kind")
    return claims


def _sign_config(config: dict) -> str:
    """OnlyOffice가 JWT_ENABLED=true면 우리가 보내는 전체 config를 동일 secret으로
    서명한 token 필드를 검사. claims는 config 그 자체."""
    return jwt.encode(config, _oo_secret(), algorithm="HS256")


@router.get("/tasks/{task_id}/files/{filename}/edit-config")
def edit_config(
    task_id: int,
    filename: str,
    conn: sqlite3.Connection = Depends(get_db),
    token_user_id: str = Depends(resolve_user_from_token),
) -> dict:
    existing = _load_task(conn, task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")
    assert_user_matches(token_user_id, existing["user_id"])

    target = _resolve_task_file(existing, filename)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    ext = target.suffix.lstrip(".").lower()
    doctype = EXT_DOCTYPE.get(ext)
    if doctype is None:
        raise HTTPException(
            status_code=400, detail=f"File extension '{ext}' not editable",
        )

    mtime = int(target.stat().st_mtime)
    edit_jwt = _sign_edit_token(
        user_id=token_user_id, task_id=task_id, filename=target.name,
    )
    backend_url = _backend_internal_url()
    config = {
        "document": {
            "fileType": ext,
            # key는 파일 변경마다 달라져야 OnlyOffice가 cache invalidate
            "key": f"t{task_id}-{target.name}-{mtime}",
            "title": target.name,
            "url": f"{backend_url}/api/_oo/doc?t={edit_jwt}",
        },
        "documentType": doctype,
        "editorConfig": {
            "callbackUrl": f"{backend_url}/api/_oo/callback?t={edit_jwt}",
            "lang": "ko",
            "user": {"id": token_user_id, "name": "내 작업"},
            "customization": {"autosave": True, "forcesave": True},
        },
    }
    return {
        "documentServerUrl": _oo_public_url(),
        "config": config,
        "token": _sign_config(config),
    }


@router.get("/_oo/doc")
def oo_doc(t: str = Query(...)):
    """OnlyOffice DocServer가 docker network 내부에서 호출. user 토큰 안 받음."""
    claims = _verify_edit_token(t)
    user_id = claims["user_id"]
    task_id = int(claims["task_id"])
    filename = claims["filename"]
    base = (_upload_root() / user_id / str(task_id)).resolve()
    target = (base / filename).resolve()
    if not str(target).startswith(str(base) + os.sep) and target != base:
        raise HTTPException(status_code=400, detail="Invalid filename in token")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        path=str(target), filename=target.name,
        media_type="application/octet-stream",
    )


@router.post("/_oo/callback")
def oo_callback(
    t: str = Query(...),
    body: dict = Body(...),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """OnlyOffice가 저장 신호를 보낼 때 호출.

    status=2 (MustSave) / status=6 (MustForceSave): body.url에서 수정된 파일
    fetch해 원본 덮어쓰기. 다른 status는 ack만.

    WOPI 약속: 정상 = {"error": 0}, 실패 = {"error": 1}. HTTP 500 던지면
    OnlyOffice가 사용자에게 "시스템 파일 에러"라고 표시하니까 반드시 200으로
    {"error": 1}을 응답해야 retry/diag가 가능.
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        claims = _verify_edit_token(t)
    except HTTPException as e:
        logger.error(f"[oo-callback] token invalid: {e.detail}")
        return {"error": 1, "detail": e.detail}

    user_id = claims["user_id"]
    task_id = int(claims["task_id"])
    filename = claims["filename"]
    status = int(body.get("status") or 0)
    logger.info(
        f"[oo-callback] task={task_id} file={filename} status={status} "
        f"body_keys={list(body.keys())}"
    )

    if status not in (2, 6):
        # 다른 status (1=editing, 4=closed, 7=force-save-error) 모두 ack
        return {"error": 0}

    url = body.get("url")
    if not url:
        logger.error(f"[oo-callback] status={status} but no url in body")
        return {"error": 1, "detail": "Callback missing url"}

    base = (_upload_root() / user_id / str(task_id)).resolve()
    target = (base / filename).resolve()
    if not str(target).startswith(str(base) + os.sep) and target != base:
        logger.error(f"[oo-callback] traversal blocked filename={filename}")
        return {"error": 1, "detail": "Invalid filename in token"}
    if not (url.startswith("http://") or url.startswith("https://")):
        logger.error(f"[oo-callback] non-http url={url}")
        return {"error": 1, "detail": "Invalid callback url scheme"}

    target.parent.mkdir(parents=True, exist_ok=True)
    fetch_url = _rewrite_oo_callback_url(url)
    if fetch_url != url:
        logger.info(f"[oo-callback] rewrote url {url} → {fetch_url}")
    logger.info(f"[oo-callback] fetching modified file from {fetch_url} → {target}")
    try:
        with urllib.request.urlopen(fetch_url, timeout=60) as resp:
            with target.open("wb") as fout:
                while True:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    fout.write(chunk)
    except Exception as e:  # noqa: BLE001
        logger.exception(f"[oo-callback] fetch failed url={url}")
        return {"error": 1, "detail": f"Fetch failed: {type(e).__name__}: {e}"}

    conn.execute(
        "UPDATE Task SET updated_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), task_id),
    )
    conn.commit()
    logger.info(f"[oo-callback] saved task={task_id} file={filename} bytes={target.stat().st_size}")
    return {"error": 0}
