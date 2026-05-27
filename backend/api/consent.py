"""P0-15: 사용자별 외부 도구 동의 API.

GET /api/users/{user_id}/agent-consents — 외부 tool 목록 + 활성/비활성 상태.
POST /api/users/{user_id}/agent-consents/{tool_id} — 명시 동의.
DELETE /api/users/{user_id}/agent-consents/{tool_id} — 동의 철회.
"""

from __future__ import annotations

import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from agent import grant_consent, list_consents, revoke_consent
from backend.deps import get_db, require_token
from backend.schemas import (
    ConsentActionResponse,
    ConsentItem,
    ConsentListResponse,
)

router = APIRouter(tags=["consent"])


def _tool_exists(conn: sqlite3.Connection, tool_id: int) -> Optional[str]:
    row = conn.execute(
        "SELECT type FROM AgentTool WHERE id = ?", (tool_id,)
    ).fetchone()
    return row["type"] if row else None


@router.get(
    "/api/users/{user_id}/agent-consents",
    response_model=ConsentListResponse,
)
def list_user_consents(
    user_id: str,
    conn: sqlite3.Connection = Depends(get_db),
    _auth: str = Depends(require_token),
) -> ConsentListResponse:
    items = [ConsentItem(**c) for c in list_consents(conn, user_id)]
    return ConsentListResponse(user_id=user_id, consents=items)


@router.post(
    "/api/users/{user_id}/agent-consents/{tool_id}",
    response_model=ConsentActionResponse,
    status_code=201,
)
def grant_user_consent(
    user_id: str,
    tool_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    _auth: str = Depends(require_token),
) -> ConsentActionResponse:
    tool_type = _tool_exists(conn, tool_id)
    if tool_type is None:
        raise HTTPException(status_code=404, detail="AgentTool not found")
    if tool_type not in ("calendar", "files", "search"):
        raise HTTPException(
            status_code=400,
            detail="Consent applies only to external calendar/files/search tools",
        )
    grant_consent(conn, user_id, tool_id)
    return ConsentActionResponse(user_id=user_id, tool_id=tool_id, active=True)


@router.delete(
    "/api/users/{user_id}/agent-consents/{tool_id}",
    response_model=ConsentActionResponse,
)
def revoke_user_consent(
    user_id: str,
    tool_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    _auth: str = Depends(require_token),
) -> ConsentActionResponse:
    if _tool_exists(conn, tool_id) is None:
        raise HTTPException(status_code=404, detail="AgentTool not found")
    revoke_consent(conn, user_id, tool_id)
    return ConsentActionResponse(user_id=user_id, tool_id=tool_id, active=False)
