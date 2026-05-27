"""Sessions API router."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from pipeline import SessionOrchestrator
from backend.schemas import (
    CreateSessionRequest,
    CreateSessionResponse,
    ProbeQuestionResponse,
    ProbeAnswerRequest,
    ProbeAnswerResponse,
    ScenarioCardResponse,
    PersonaInfo,
    DecisionRequest,
    DecisionResponse,
)
from backend.deps import (
    assert_user_matches,
    get_db,
    require_token_for_session,
    resolve_user_from_token,
)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _get_orchestrator(conn: sqlite3.Connection) -> SessionOrchestrator:
    return SessionOrchestrator(conn)


@router.post("", response_model=CreateSessionResponse, status_code=201)
def create_session(
    body: CreateSessionRequest,
    conn: sqlite3.Connection = Depends(get_db),
    token_user_id: str = Depends(resolve_user_from_token),
) -> CreateSessionResponse:
    """SessionOrchestrator.start_session → session_id 반환."""
    assert_user_matches(token_user_id, body.user_id)
    # user 존재 확인
    user = conn.execute("SELECT id FROM User WHERE id = ?", (body.user_id,)).fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    orch = _get_orchestrator(conn)
    session_id = orch.start_session(
        body.user_id,
        body.avoidance_input,
        timeline_hint=body.timeline_hint,
    )
    return CreateSessionResponse(session_id=session_id)


@router.get("/{session_id}/probe", response_model=ProbeQuestionResponse)
def get_probe(
    session_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    _auth: str = Depends(require_token_for_session),
) -> ProbeQuestionResponse:
    """orchestrator.maybe_probe → 질문 또는 null."""
    sess = conn.execute(
        "SELECT user_id FROM AvoidanceSession WHERE id = ?", (session_id,)
    ).fetchone()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    orch = _get_orchestrator(conn)
    q = orch.maybe_probe(sess["user_id"])
    if q is None:
        return ProbeQuestionResponse()
    return ProbeQuestionResponse(
        question_id=q.question_id,
        text=q.text,
        target_slot=q.target_slot,
    )


@router.post("/{session_id}/probe-answer", response_model=ProbeAnswerResponse)
def submit_probe_answer(
    session_id: int,
    body: ProbeAnswerRequest,
    conn: sqlite3.Connection = Depends(get_db),
    _auth: str = Depends(require_token_for_session),
) -> ProbeAnswerResponse:
    """record_probe_answer 또는 skip_today."""
    sess = conn.execute(
        "SELECT user_id FROM AvoidanceSession WHERE id = ?", (session_id,)
    ).fetchone()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    orch = _get_orchestrator(conn)
    user_id = sess["user_id"]

    if body.skip:
        # skip_today: answer_text = "__skip__"
        orch.record_probe_answer(
            user_id=user_id,
            question_id=body.question_id,
            session_id=session_id,
            answer="__skip__",
        )
    else:
        if not body.answer_text:
            raise HTTPException(status_code=400, detail="answer_text required when not skipping")
        orch.record_probe_answer(
            user_id=user_id,
            question_id=body.question_id,
            session_id=session_id,
            answer=body.answer_text,
            slot_updates=body.slot_updates,
        )
    return ProbeAnswerResponse(recorded=True)


@router.post("/{session_id}/scenario", response_model=ScenarioCardResponse)
def generate_scenario(
    session_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    _auth: str = Depends(require_token_for_session),
) -> ScenarioCardResponse:
    """orchestrator.generate_scenario → ScenarioCard. Ollama timeout 60s."""
    sess = conn.execute(
        "SELECT user_id, avoidance_input, timeline_hint FROM AvoidanceSession WHERE id = ?", (session_id,)
    ).fetchone()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    timeline_hint = sess["timeline_hint"] if "timeline_hint" in sess.keys() else None
    orch = _get_orchestrator(conn)
    card = orch.generate_scenario(
        user_id=sess["user_id"],
        session_id=session_id,
        avoidance_input=sess["avoidance_input"],
        timeline_hint=timeline_hint,
    )

    # persona info — id/perspective/tone/greeting까지 채움 (frontend 호환)
    persona_info = PersonaInfo(name=card.persona_name or "내일의 나")
    if card.persona_id:
        p_row = conn.execute(
            "SELECT id, name, perspective, tone_mode, greeting, avatar_icon, avatar_color "
            "FROM Persona WHERE id = ?",
            (card.persona_id,),
        ).fetchone()
        if p_row:
            persona_info = PersonaInfo(
                id=p_row["id"],
                name=p_row["name"] or card.persona_name or "내일의 나",
                perspective=p_row["perspective"],
                tone_mode=p_row["tone_mode"],
                greeting=p_row["greeting"],
                icon=p_row["avatar_icon"],
                color=p_row["avatar_color"],
            )

    # ToolInvocation audit log (세션-레벨, 시나리오 생성 감사)
    tool_row = conn.execute(
        "SELECT id FROM AgentTool WHERE name = 'scenario_generator'"
    ).fetchone()
    if not tool_row:
        cur_tool = conn.execute(
            "INSERT INTO AgentTool (name, type, enabled, config_json, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
            ("scenario_generator", "llm", 1, "{}"),
        )
        tool_id = cur_tool.lastrowid
    else:
        tool_id = tool_row["id"]

    conn.execute(
        """INSERT INTO ToolInvocation
           (user_id, avoidance_session_id, persona_id, agent_tool_id,
            input_json, output_json, latency_ms, invoked_at, prompt_version_id)
           VALUES (?, ?, ?, ?, ?, ?, NULL, datetime('now'), ?)""",
        (
            sess["user_id"],
            session_id,
            card.persona_id,
            tool_id,
            f'{{"action":"generate_scenario","session_id":{session_id}}}',
            f'{{"card_id":{card.id},"card_type":"{card.card_type}"}}',
            card.prompt_version_id,
        ),
    )
    conn.commit()

    return ScenarioCardResponse(
        card_id=card.id,
        card_type=card.card_type,
        sentences={
            "fact": card.fact,
            "feeling": card.feeling,
            "micro_action": card.micro_action,
        },
        safety_message=card.safety_message,
        persona=persona_info,
        signal_level=card.signal_level,
        moral_licensing_nudge=card.moral_licensing_nudge,
    )


@router.post("/{session_id}/decision", response_model=DecisionResponse)
def record_decision(
    session_id: int,
    body: DecisionRequest,
    conn: sqlite3.Connection = Depends(get_db),
    _auth: str = Depends(require_token_for_session),
) -> DecisionResponse:
    """결정 기록. 'delete'면 cascade 삭제."""
    sess = conn.execute(
        "SELECT id FROM AvoidanceSession WHERE id = ?", (session_id,)
    ).fetchone()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    valid_decisions = {"transition", "continue", "report", "delete"}
    if body.decision not in valid_decisions:
        raise HTTPException(status_code=400, detail=f"Invalid decision. Must be one of {valid_decisions}")

    if body.decision == "delete":
        # Self-Destruct cascade
        conn.execute("DELETE FROM AvoidanceSession WHERE id = ?", (session_id,))
        conn.commit()
        return DecisionResponse(session_id=session_id, decision="delete", deleted=True)

    orch = _get_orchestrator(conn)
    orch.record_decision(session_id, body.decision)
    return DecisionResponse(session_id=session_id, decision=body.decision)


@router.delete("/{session_id}", response_model=DecisionResponse)
def delete_session(
    session_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    _auth: str = Depends(require_token_for_session),
) -> DecisionResponse:
    """Self-Destruct cascade — AvoidanceSession + ScenarioCard + ToolInvocation 삭제."""
    sess = conn.execute(
        "SELECT id FROM AvoidanceSession WHERE id = ?", (session_id,)
    ).fetchone()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    conn.execute("DELETE FROM AvoidanceSession WHERE id = ?", (session_id,))
    conn.commit()
    return DecisionResponse(session_id=session_id, decision="delete", deleted=True)
