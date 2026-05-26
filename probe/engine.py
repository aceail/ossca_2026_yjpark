"""HITL Probe Engine v1 — G004.

Phase 1/2/3 router + heuristic information-gain scoring + cooldown +
페르소나-aware active prompt selector.

Phase 1 Onboarding: G005가 처리 (이 모듈 활성 X)
Phase 2 Adaptive Probing: 세션 4~15회 또는 프로필 완성도 < 80%
Phase 3 Passive Inference: 프로필 완성도 ≥ 80%, HITL 최소화

휴리스틱 점수 (FINAL_GOAL v2.3 §8 OSSCA 기여 2번):
    score = missing_slot_weight + low_confidence + recent_regret_error
            + scenario_relevance - fatigue_penalty
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum


COOLDOWN_HOURS_DEFAULT = 24


class Phase(str, Enum):
    ONBOARDING = "phase1_onboarding"
    ADAPTIVE = "phase2_adaptive"
    PASSIVE = "phase3_passive"


@dataclass
class QuestionScore:
    question_id: int
    text: str
    target_slot: str
    score: float
    components: dict


# ────────────────────────────────────────────────────────────────────
# Phase Router
# ────────────────────────────────────────────────────────────────────

class PhaseRouter:
    """프로필 완성도 + 세션 카운트로 Phase 결정."""

    def __init__(
        self,
        adaptive_session_min: int = 4,
        adaptive_session_max: int = 15,
        passive_completion_threshold: float = 80.0,
    ):
        self.adaptive_session_min = adaptive_session_min
        self.adaptive_session_max = adaptive_session_max
        self.passive_completion_threshold = passive_completion_threshold

    def route(self, *, completion_percent: float, session_count: int) -> Phase:
        if completion_percent >= self.passive_completion_threshold:
            return Phase.PASSIVE
        if session_count < self.adaptive_session_min:
            return Phase.ONBOARDING
        return Phase.ADAPTIVE


# ────────────────────────────────────────────────────────────────────
# Cooldown
# ────────────────────────────────────────────────────────────────────

def is_in_cooldown(last_skip_at: str | None, hours: int = COOLDOWN_HOURS_DEFAULT) -> bool:
    if not last_skip_at:
        return False
    try:
        last = datetime.fromisoformat(last_skip_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    return datetime.now(timezone.utc) - last < timedelta(hours=hours)


# ────────────────────────────────────────────────────────────────────
# Active prompt selector (페르소나-aware)
# ────────────────────────────────────────────────────────────────────

def select_active_prompt(
    conn: sqlite3.Connection,
    user_id: str,
) -> tuple[int | None, str | None]:
    """UserProfile.active_persona_id → Persona.system_prompt_override 반환."""
    row = conn.execute(
        """SELECT p.id, p.system_prompt_override
           FROM UserProfile up
           JOIN Persona p ON p.id = up.active_persona_id
           WHERE up.user_id = ?""",
        (user_id,),
    ).fetchone()
    if not row:
        return None, None
    return row[0] if not isinstance(row, sqlite3.Row) else row["id"], row[1] if not isinstance(row, sqlite3.Row) else row["system_prompt_override"]


# ────────────────────────────────────────────────────────────────────
# Probe Engine — 휴리스틱 점수
# ────────────────────────────────────────────────────────────────────

class ProbeEngine:
    """ProbeQuestion 점수 계산 + 최적 질문 선택 + Phase 라우팅."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        phase_router: PhaseRouter | None = None,
        cooldown_hours: int = COOLDOWN_HOURS_DEFAULT,
    ):
        self.conn = conn
        self.phase_router = phase_router or PhaseRouter()
        self.cooldown_hours = cooldown_hours

    def _profile_slots(self, user_id: str) -> dict:
        row = self.conn.execute(
            "SELECT slots_json, completion_percent FROM UserProfile WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            return {"slots": {}, "completion_percent": 0.0}
        return {
            "slots": json.loads(row["slots_json"] or "{}"),
            "completion_percent": row["completion_percent"] or 0.0,
        }

    def _session_count(self, user_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM AvoidanceSession WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return row["n"] if row else 0

    def _recent_question_fatigue(self, user_id: str, hours: int = 12) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM ProbeAnswer WHERE user_id = ? AND answered_at >= ?",
            (user_id, cutoff),
        ).fetchone()
        return row["n"] if row else 0

    def score_question(
        self,
        *,
        question: sqlite3.Row,
        slots: dict,
        fatigue_recent_count: int,
    ) -> QuestionScore:
        target = question["target_slot"]
        slot_data = slots.get(target) or {}
        missing = 0.0 if slot_data else 1.0
        confidence = slot_data.get("confidence", 0.0) if isinstance(slot_data, dict) else 0.0
        low_conf = max(0.0, 0.8 - confidence) if slot_data else 0.0
        ig = float(question["expected_information_gain"] or 0.0)
        fatigue_penalty = min(0.5, fatigue_recent_count * 0.15)
        score = (
            1.0 * missing            # weight: missing slot
            + 0.7 * low_conf         # weight: low confidence existing slot
            + 0.5 * ig               # weight: prior expected info gain
            - 1.0 * fatigue_penalty
        )
        return QuestionScore(
            question_id=question["id"],
            text=question["text"],
            target_slot=target,
            score=round(score, 4),
            components={
                "missing": missing,
                "low_confidence": low_conf,
                "expected_ig": ig,
                "fatigue_penalty": fatigue_penalty,
            },
        )

    def best_question(self, user_id: str) -> QuestionScore | None:
        """Phase 2 활성 시 가장 높은 점수의 질문 1개 반환. Phase 1/3이면 None."""
        profile = self._profile_slots(user_id)
        session_count = self._session_count(user_id)
        phase = self.phase_router.route(
            completion_percent=profile["completion_percent"],
            session_count=session_count,
        )
        if phase != Phase.ADAPTIVE:
            return None
        # cooldown: 가장 최근 skip 응답
        last_skip = self.conn.execute(
            """SELECT MAX(answered_at) AS t FROM ProbeAnswer
               WHERE user_id = ? AND answer_text = '__skip__'""",
            (user_id,),
        ).fetchone()
        if last_skip and last_skip["t"] and is_in_cooldown(last_skip["t"], self.cooldown_hours):
            return None
        questions = self.conn.execute(
            "SELECT id, text, target_slot, expected_information_gain FROM ProbeQuestion WHERE enabled = 1"
        ).fetchall()
        if not questions:
            return None
        fatigue = self._recent_question_fatigue(user_id)
        scored = [self.score_question(question=q, slots=profile["slots"], fatigue_recent_count=fatigue) for q in questions]
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[0] if scored else None

    def record_answer(
        self,
        *,
        user_id: str,
        question_id: int,
        avoidance_session_id: int | None,
        answer_text: str,
        extracted_slot_updates: dict | None = None,
    ) -> int:
        cur = self.conn.execute(
            """INSERT INTO ProbeAnswer
               (user_id, avoidance_session_id, probe_question_id, answer_text, extracted_slot_updates_json, answered_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                avoidance_session_id,
                question_id,
                answer_text,
                json.dumps(extracted_slot_updates or {}, ensure_ascii=False),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def skip_today(self, user_id: str, question_id: int) -> None:
        """사용자가 '오늘은 묻지 않기' 선택 → cooldown 진입."""
        self.record_answer(
            user_id=user_id,
            question_id=question_id,
            avoidance_session_id=None,
            answer_text="__skip__",
        )
