"""Regret API router."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from regret import record_regret_score, record_card_accuracy, record_return_intent
from backend.schemas import (
    RegretRequest,
    RegretResponse,
    CardAccuracyRequest,
    CardAccuracyResponse,
    ReturnIntentRequest,
    ReturnIntentResponse,
)
from backend.deps import get_db

router = APIRouter(tags=["regret"])


@router.post("/api/sessions/{session_id}/regret", response_model=RegretResponse, status_code=201)
def submit_regret(
    session_id: int,
    body: RegretRequest,
    conn: sqlite3.Connection = Depends(get_db),
) -> RegretResponse:
    """RegretScore INSERT."""
    sess = conn.execute(
        "SELECT user_id FROM AvoidanceSession WHERE id = ?", (session_id,)
    ).fetchone()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    regret_id = record_regret_score(
        conn,
        avoidance_session_id=session_id,
        user_id=sess["user_id"],
        intensity=body.intensity,
        free_text=body.free_text,
    )
    return RegretResponse(regret_id=regret_id)


@router.post("/api/scenario-cards/{card_id}/accuracy", response_model=CardAccuracyResponse, status_code=201)
def submit_card_accuracy(
    card_id: int,
    body: CardAccuracyRequest,
    conn: sqlite3.Connection = Depends(get_db),
) -> CardAccuracyResponse:
    """카드 정확도 self-rating (1-5)."""
    try:
        eval_id = record_card_accuracy(conn, scenario_card_id=card_id, accuracy_score=body.accuracy)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return CardAccuracyResponse(evaluation_id=eval_id)


@router.post("/api/scenario-cards/{card_id}/return-intent", response_model=ReturnIntentResponse, status_code=201)
def submit_return_intent(
    card_id: int,
    body: ReturnIntentRequest,
    conn: sqlite3.Connection = Depends(get_db),
) -> ReturnIntentResponse:
    """다음 사용 의향 1-5."""
    try:
        eval_id = record_return_intent(conn, scenario_card_id=card_id, intent_score=body.intent)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return ReturnIntentResponse(evaluation_id=eval_id)
