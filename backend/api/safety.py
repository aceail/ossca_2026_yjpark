"""Safety API router."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from regret import build_weekly_snapshot, compute_signal_level, week_start_iso
from backend.schemas import (
    SafetyTrendResponse,
    SafetySnapshotItem,
    SafetySnapshotRefreshResponse,
)
from backend.deps import get_db, require_token

router = APIRouter(tags=["safety"])


@router.get("/api/users/{user_id}/safety-trend", response_model=SafetyTrendResponse)
def get_safety_trend(
    user_id: str,
    conn: sqlite3.Connection = Depends(get_db),
    _auth: str = Depends(require_token),
) -> SafetyTrendResponse:
    """최근 8주 SafetyHarmTimeSeries 반환."""
    user = conn.execute("SELECT id FROM User WHERE id = ?", (user_id,)).fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    rows = conn.execute(
        """SELECT week_start, self_blame_word_count, failure_imagery_ratio,
                  identity_failure_phrases_count, pre_card_tension_self_report
           FROM SafetyHarmTimeSeries
           WHERE user_id = ?
           ORDER BY week_start DESC
           LIMIT 8""",
        (user_id,),
    ).fetchall()

    weeks = [
        SafetySnapshotItem(
            week_start=r["week_start"],
            self_blame_word_count=r["self_blame_word_count"] or 0,
            failure_imagery_ratio=r["failure_imagery_ratio"] or 0.0,
            identity_failure_phrases_count=r["identity_failure_phrases_count"] or 0,
            pre_card_tension_self_report=r["pre_card_tension_self_report"],
        )
        for r in rows
    ]
    signal = compute_signal_level(conn, user_id)
    return SafetyTrendResponse(user_id=user_id, weeks=weeks, signal_level=signal)


@router.post("/api/users/{user_id}/safety-snapshot/refresh", response_model=SafetySnapshotRefreshResponse)
def refresh_safety_snapshot(
    user_id: str,
    conn: sqlite3.Connection = Depends(get_db),
    _auth: str = Depends(require_token),
) -> SafetySnapshotRefreshResponse:
    """build_weekly_snapshot 호출."""
    user = conn.execute("SELECT id FROM User WHERE id = ?", (user_id,)).fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    build_weekly_snapshot(conn, user_id)
    week = week_start_iso()
    return SafetySnapshotRefreshResponse(user_id=user_id, week_start=week, refreshed=True)
