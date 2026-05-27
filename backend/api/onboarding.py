"""Onboarding API router."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from backend.schemas import OnboardingRequest, OnboardingResponse
from backend.deps import assert_user_matches, get_db, resolve_user_from_token

router = APIRouter(tags=["onboarding"])

# sensitive fear_anchor 키워드 — forbidden_topics 자동 추가
SENSITIVE_FEAR_ANCHORS = [
    "부모의 기대와 다른 모습",
    "부모의 기대",
    "부모 기대",
]

# 온보딩 슬롯 완성도 계산
_SLOT_WEIGHTS = {
    "trigger_category": 20,
    "avoidance_destination": 20,
    "persona_id": 20,
    "fear_anchor": 20,
    "recovery_pattern": 20,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _calc_completion(slots: dict) -> float:
    total = sum(w for slot, w in _SLOT_WEIGHTS.items() if slots.get(slot))
    return float(total)


@router.post("/api/onboarding", response_model=OnboardingResponse)
def submit_onboarding(
    body: OnboardingRequest,
    conn: sqlite3.Connection = Depends(get_db),
    token_user_id: str = Depends(resolve_user_from_token),
) -> OnboardingResponse:
    """UserProfile.slots_json 갱신 + completion_percent 계산."""
    assert_user_matches(token_user_id, body.user_id)
    profile = conn.execute(
        "SELECT slots_json, forbidden_topics_json FROM UserProfile WHERE user_id = ?",
        (body.user_id,),
    ).fetchone()
    if not profile:
        raise HTTPException(status_code=404, detail="User profile not found")

    # 기존 슬롯 로드
    slots: dict = {}
    if profile["slots_json"]:
        try:
            slots = json.loads(profile["slots_json"])
        except Exception:
            slots = {}

    # 슬롯 갱신
    new_slots = {
        "trigger_category": body.trigger_category,
        "avoidance_destination": body.avoidance_destination,
        "persona_id": body.persona_id,
    }
    if body.fear_anchor:
        new_slots["fear_anchor"] = body.fear_anchor
    if body.recovery_pattern:
        new_slots["recovery_pattern"] = body.recovery_pattern

    slots.update(new_slots)

    # persona 업데이트
    p = conn.execute("SELECT id FROM Persona WHERE id = ?", (body.persona_id,)).fetchone()
    if not p:
        raise HTTPException(status_code=404, detail="Persona not found")

    # completion_percent 계산
    completion = _calc_completion(slots)

    # forbidden_topics 자동 추가 (sensitive fear_anchor)
    forbidden: list[str] = []
    if profile["forbidden_topics_json"]:
        try:
            forbidden = json.loads(profile["forbidden_topics_json"])
        except Exception:
            forbidden = []

    if body.fear_anchor:
        for sensitive in SENSITIVE_FEAR_ANCHORS:
            if sensitive in body.fear_anchor and sensitive not in forbidden:
                forbidden.append(sensitive)
                break

    conn.execute(
        """UPDATE UserProfile
           SET slots_json = ?, completion_percent = ?, forbidden_topics_json = ?,
               active_persona_id = ?, updated_at = ?
           WHERE user_id = ?""",
        (
            json.dumps(slots, ensure_ascii=False),
            completion,
            json.dumps(forbidden, ensure_ascii=False),
            body.persona_id,
            _now(),
            body.user_id,
        ),
    )
    conn.commit()

    return OnboardingResponse(
        user_id=body.user_id,
        completion_percent=completion,
        slots_updated=new_slots,
    )
