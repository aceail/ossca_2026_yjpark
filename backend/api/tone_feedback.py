"""Tone Feedback API router."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from backend.schemas import ToneFeedbackRequest, ToneFeedbackResponse
from backend.deps import get_db

router = APIRouter(tags=["tone_feedback"])

VALID_KINDS = {
    "too_hard",
    "too_parent",
    "too_office",
    "too_therapist",
    "too_general",
    "need_starter",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/api/scenario-cards/{card_id}/tone-feedback", response_model=ToneFeedbackResponse, status_code=201)
def submit_tone_feedback(
    card_id: int,
    body: ToneFeedbackRequest,
    conn: sqlite3.Connection = Depends(get_db),
) -> ToneFeedbackResponse:
    """톤 피드백 저장 — EvaluationResult metrics_json에 누적."""
    if body.kind not in VALID_KINDS:
        raise HTTPException(status_code=400, detail=f"Invalid kind. Must be one of {VALID_KINDS}")

    card = conn.execute(
        "SELECT avoidance_session_id, model_run_id FROM ScenarioCard WHERE id = ?",
        (card_id,),
    ).fetchone()
    if not card:
        raise HTTPException(status_code=404, detail="ScenarioCard not found")

    # model_run_id 확보 (없으면 임시 생성)
    mrid = card["model_run_id"]
    if mrid is None:
        cur = conn.execute(
            "INSERT INTO ModelRun (model_name, ran_at) VALUES (?, ?)",
            ("tone_feedback_eval", _now()),
        )
        mrid = cur.lastrowid

    # ToolInvocation audit log
    sess_id = card["avoidance_session_id"]
    sess = conn.execute("SELECT user_id FROM AvoidanceSession WHERE id = ?", (sess_id,)).fetchone()
    user_id = sess["user_id"] if sess else None

    tool_row = conn.execute("SELECT id FROM AgentTool WHERE name = 'tone_feedback'").fetchone()
    if not tool_row:
        cur_tool = conn.execute(
            "INSERT INTO AgentTool (name, type, enabled, config_json, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
            ("tone_feedback", "feedback", 1, "{}"),
        )
        tool_id = cur_tool.lastrowid
    else:
        tool_id = tool_row["id"]

    conn.execute(
        """INSERT INTO ToolInvocation
           (user_id, avoidance_session_id, persona_id, agent_tool_id,
            input_json, output_json, latency_ms, invoked_at)
           VALUES (?, ?, NULL, ?, ?, ?, NULL, datetime('now'))""",
        (
            user_id,
            sess_id,
            tool_id,
            json.dumps({"action": "tone_feedback", "card_id": card_id, "kind": body.kind}),
            "{}",
        ),
    )

    # EvaluationResult metrics_json에 tone_feedback 누적
    sample_id = f"tone_{card_id}"
    conn.execute(
        """INSERT INTO EvaluationResult
           (sample_id, model_run_id, scenario_card_id, pass, issues_json, metrics_json, evaluated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            sample_id,
            mrid,
            card_id,
            0,
            json.dumps([], ensure_ascii=False),
            json.dumps({"tone_feedback": body.kind}, ensure_ascii=False),
            _now(),
        ),
    )
    conn.commit()

    return ToneFeedbackResponse(card_id=card_id, kind=body.kind, recorded=True)
