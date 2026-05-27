"""Personas API router."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

import persona as persona_mod
from backend.schemas import (
    CreateCustomPersonaRequest,
    CreateCustomPersonaResponse,
    AuditViolation,
    PersonaResponse,
    SetActivePersonaRequest,
    SetActivePersonaResponse,
)
from backend.deps import get_db

router = APIRouter(tags=["personas"])

_PREVIEWS_PATH = Path(__file__).resolve().parent.parent.parent / ".omc" / "ultragoal" / "persona_previews_v1.json"
_PREVIEWS_CACHE: dict | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_persona(row) -> PersonaResponse:
    forbidden: list[str] = []
    if row["forbidden_topics_json"]:
        try:
            forbidden = json.loads(row["forbidden_topics_json"])
        except Exception:
            forbidden = []
    return PersonaResponse(
        id=row["id"],
        name=row["name"],
        perspective=row["perspective"],
        tone_mode=row["tone_mode"],
        voice_style=row["voice_style"],
        greeting=row["greeting"],
        forbidden_topics=forbidden,
        system_prompt_override=row["system_prompt_override"],
        avatar_color=row["avatar_color"],
        avatar_icon=row["avatar_icon"],
        is_builtin=bool(row["is_builtin"]),
    )


@router.get("/api/personas", response_model=list[PersonaResponse])
def list_personas(
    user_id: str | None = Query(default=None),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[PersonaResponse]:
    """5 default 페르소나 + 사용자 커스텀."""
    rows = conn.execute(
        "SELECT * FROM Persona WHERE is_builtin = 1 ORDER BY id"
    ).fetchall()
    result = [_row_to_persona(r) for r in rows]

    if user_id:
        custom_rows = conn.execute(
            "SELECT * FROM Persona WHERE created_by_user = ? ORDER BY id",
            (user_id,),
        ).fetchall()
        result.extend(_row_to_persona(r) for r in custom_rows)

    return result


@router.post("/api/personas/custom", response_model=CreateCustomPersonaResponse, status_code=201)
def create_custom_persona(
    body: CreateCustomPersonaRequest,
    conn: sqlite3.Connection = Depends(get_db),
) -> CreateCustomPersonaResponse:
    """커스텀 페르소나 생성. audit 통과 후 save_persona."""
    payload = {
        "name": body.name,
        "perspective": body.perspective,
        "tone_mode": body.tone_mode,
        "voice_style": body.voice_style or "",
        "greeting": body.greeting or "",
        "forbidden_topics": body.forbidden_topics,
        "system_prompt_override": body.system_prompt_override or "",
        "avatar_color": body.avatar_color,
        "avatar_icon": body.avatar_icon,
    }

    audit = persona_mod.audit_custom_persona(payload)
    if not audit.accepted:
        violations = [
            AuditViolation(field=v[0], group=v[1], word=v[2])
            for v in audit.violations
        ]
        raise HTTPException(
            status_code=400,
            detail={
                "message": "절대 한계선 위반으로 저장이 거부되었습니다.",
                "violations": [v.model_dump() for v in violations],
            },
        )

    spec = {
        "name": body.name,
        "perspective": body.perspective,
        "tone_mode": body.tone_mode,
        "voice_style": body.voice_style or "",
        "greeting": body.greeting or "",
        "forbidden_topics": body.forbidden_topics,
        "system_prompt_override": body.system_prompt_override or "",
        "avatar_color": body.avatar_color,
        "avatar_icon": body.avatar_icon,
    }
    persona_id = persona_mod.save_persona(conn, spec, is_builtin=False, user_id=body.user_id)
    return CreateCustomPersonaResponse(persona_id=persona_id)


@router.get("/api/personas/previews")
def get_persona_previews() -> dict:
    """persona_previews_v1.json 캐시 반환."""
    global _PREVIEWS_CACHE
    if _PREVIEWS_CACHE is None:
        if _PREVIEWS_PATH.exists():
            with open(_PREVIEWS_PATH, encoding="utf-8") as f:
                _PREVIEWS_CACHE = json.load(f)
        else:
            _PREVIEWS_CACHE = {}
    return _PREVIEWS_CACHE


@router.post("/api/users/{user_id}/active-persona", response_model=SetActivePersonaResponse)
def set_active_persona(
    user_id: str,
    body: SetActivePersonaRequest,
    conn: sqlite3.Connection = Depends(get_db),
) -> SetActivePersonaResponse:
    """UserProfile.active_persona_id 갱신."""
    # persona 존재 확인
    p = conn.execute("SELECT id FROM Persona WHERE id = ?", (body.persona_id,)).fetchone()
    if not p:
        raise HTTPException(status_code=404, detail="Persona not found")

    profile = conn.execute("SELECT user_id FROM UserProfile WHERE user_id = ?", (user_id,)).fetchone()
    if not profile:
        raise HTTPException(status_code=404, detail="User profile not found")

    conn.execute(
        "UPDATE UserProfile SET active_persona_id = ?, updated_at = ? WHERE user_id = ?",
        (body.persona_id, _now(), user_id),
    )
    conn.commit()
    return SetActivePersonaResponse(user_id=user_id, active_persona_id=body.persona_id)
