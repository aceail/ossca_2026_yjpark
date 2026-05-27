"""Sprint 11 — Chat API.

페르소나와 멀티턴 대화. 모든 메시지가 ChatMessage에 평문 저장되어
SELECT로 직접 모니터링 가능.
"""

from __future__ import annotations

import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from pipeline.chat import (
    create_chat_session,
    list_messages,
    list_sessions,
    post_user_message,
)
from backend.deps import (
    assert_user_matches,
    get_db,
    require_token,
    resolve_user_from_token,
)

router = APIRouter(prefix="/api/chat", tags=["chat"])


class CreateChatSessionRequest(BaseModel):
    user_id: str
    persona_id: Optional[int] = None
    title: Optional[str] = None


class CreateChatSessionResponse(BaseModel):
    session_id: int


class PostMessageRequest(BaseModel):
    content: str


class ChatMessageItem(BaseModel):
    id: int
    role: str
    content: str
    created_at: Optional[str] = None


class PostMessageResponse(BaseModel):
    assistant: ChatMessageItem


class ListMessagesResponse(BaseModel):
    session_id: int
    messages: list[ChatMessageItem]


class ChatSessionItem(BaseModel):
    id: int
    persona_id: Optional[int] = None
    persona_name: Optional[str] = None
    avatar_icon: Optional[str] = None
    title: Optional[str] = None
    created_at: str
    updated_at: str
    message_count: int


class ListSessionsResponse(BaseModel):
    user_id: str
    sessions: list[ChatSessionItem]


def _session_user_id(conn: sqlite3.Connection, session_id: int) -> Optional[str]:
    row = conn.execute(
        "SELECT user_id FROM ChatSession WHERE id = ?", (session_id,)
    ).fetchone()
    return row["user_id"] if row else None


@router.post("/sessions", response_model=CreateChatSessionResponse, status_code=201)
def create_session(
    body: CreateChatSessionRequest,
    conn: sqlite3.Connection = Depends(get_db),
    token_user_id: str = Depends(resolve_user_from_token),
) -> CreateChatSessionResponse:
    assert_user_matches(token_user_id, body.user_id)

    persona_id = body.persona_id
    if persona_id is None:
        row = conn.execute(
            "SELECT active_persona_id FROM UserProfile WHERE user_id = ?",
            (body.user_id,),
        ).fetchone()
        persona_id = row["active_persona_id"] if row else None

    sid = create_chat_session(
        conn, user_id=body.user_id, persona_id=persona_id, title=body.title,
    )
    return CreateChatSessionResponse(session_id=sid)


@router.get("/sessions", response_model=ListSessionsResponse)
def list_user_sessions(
    user_id: str,
    conn: sqlite3.Connection = Depends(get_db),
    token_user_id: str = Depends(resolve_user_from_token),
) -> ListSessionsResponse:
    assert_user_matches(token_user_id, user_id)
    return ListSessionsResponse(
        user_id=user_id,
        sessions=[ChatSessionItem(**s) for s in list_sessions(conn, user_id)],
    )


@router.post("/sessions/{session_id}/messages", response_model=PostMessageResponse, status_code=201)
def post_message(
    session_id: int,
    body: PostMessageRequest,
    conn: sqlite3.Connection = Depends(get_db),
    token_user_id: str = Depends(resolve_user_from_token),
) -> PostMessageResponse:
    owner = _session_user_id(conn, session_id)
    if owner is None:
        raise HTTPException(status_code=404, detail="ChatSession not found")
    assert_user_matches(token_user_id, owner)

    content = (body.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content cannot be empty")

    assistant = post_user_message(conn, session_id=session_id, content=content)
    return PostMessageResponse(assistant=ChatMessageItem(**assistant))


class BriefingResponse(BaseModel):
    sent: bool
    reason: Optional[str] = None
    session_id: Optional[int] = None
    message_id: Optional[int] = None
    content: Optional[str] = None


@router.post("/briefing", response_model=BriefingResponse)
def trigger_briefing(
    user_id: str,
    conn: sqlite3.Connection = Depends(get_db),
    token_user_id: str = Depends(resolve_user_from_token),
) -> BriefingResponse:
    """Sprint 22: 오늘 첫 브리핑 한 번만 생성. cooldown 적용. frontend가 chat
    페이지 마운트 시 한 번 호출."""
    assert_user_matches(token_user_id, user_id)
    from pipeline.briefing import generate_briefing

    result = generate_briefing(conn, user_id)
    return BriefingResponse(
        sent=result.get("sent", False),
        reason=result.get("reason"),
        session_id=result.get("session_id"),
        message_id=result.get("message_id"),
        content=result.get("content"),
    )


@router.get("/sessions/{session_id}/messages", response_model=ListMessagesResponse)
def get_messages(
    session_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    token_user_id: str = Depends(resolve_user_from_token),
) -> ListMessagesResponse:
    owner = _session_user_id(conn, session_id)
    if owner is None:
        raise HTTPException(status_code=404, detail="ChatSession not found")
    assert_user_matches(token_user_id, owner)
    return ListMessagesResponse(
        session_id=session_id,
        messages=[ChatMessageItem(**m) for m in list_messages(conn, session_id)],
    )
