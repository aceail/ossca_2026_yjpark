"""Users API router."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from backend.schemas import (
    CreateUserRequest,
    CreateUserResponse,
    UserProfileResponse,
)
from backend.deps import get_db

router = APIRouter(prefix="/api/users", tags=["users"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("", response_model=CreateUserResponse)
def create_user(
    _body: CreateUserRequest,
    conn: sqlite3.Connection = Depends(get_db),
) -> CreateUserResponse:
    """새 User + UserProfile 생성. default persona = '내일의 나'."""
    user_id = str(uuid.uuid4())
    now = _now()

    conn.execute(
        "INSERT INTO User (id, created_at, last_seen_at) VALUES (?, ?, ?)",
        (user_id, now, now),
    )

    # default persona (내일의 나) lookup
    default_persona = conn.execute(
        "SELECT id FROM Persona WHERE name = ? AND created_by_user IS NULL",
        ("내일의 나",),
    ).fetchone()
    default_persona_id = default_persona["id"] if default_persona else None

    conn.execute(
        """INSERT INTO UserProfile (user_id, slots_json, completion_percent,
           forbidden_topics_json, active_persona_id, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, "{}", 0.0, "[]", default_persona_id, now),
    )
    conn.commit()

    return CreateUserResponse(user_id=user_id)


@router.get("/{user_id}/profile", response_model=UserProfileResponse)
def get_user_profile(
    user_id: str,
    conn: sqlite3.Connection = Depends(get_db),
) -> UserProfileResponse:
    """UserProfile + active_persona 정보 join."""
    row = conn.execute(
        """SELECT up.*, p.name AS persona_name, p.avatar_icon, p.avatar_color
           FROM UserProfile up
           LEFT JOIN Persona p ON up.active_persona_id = p.id
           WHERE up.user_id = ?""",
        (user_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User profile not found")

    slots = {}
    if row["slots_json"]:
        try:
            slots = json.loads(row["slots_json"])
        except Exception:
            slots = {}

    forbidden: list[str] = []
    if row["forbidden_topics_json"]:
        try:
            forbidden = json.loads(row["forbidden_topics_json"])
        except Exception:
            forbidden = []

    return UserProfileResponse(
        user_id=user_id,
        slots_json=slots,
        completion_percent=row["completion_percent"] or 0.0,
        forbidden_topics=forbidden,
        active_persona_id=row["active_persona_id"],
        active_persona_name=row["persona_name"],
        active_persona_icon=row["avatar_icon"],
        active_persona_color=row["avatar_color"],
    )
