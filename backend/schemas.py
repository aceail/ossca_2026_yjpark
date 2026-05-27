"""Pydantic v2 request/response schemas — Tomorrow's You Backend."""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


# ── Users ─────────────────────────────────────────────────────────────

class CreateUserRequest(BaseModel):
    pass  # 빈 body {}


class CreateUserResponse(BaseModel):
    user_id: str


class UserProfileResponse(BaseModel):
    user_id: str
    slots_json: Optional[dict] = None
    completion_percent: float = 0.0
    forbidden_topics: list[str] = Field(default_factory=list)
    active_persona_id: Optional[int] = None
    active_persona_name: Optional[str] = None
    active_persona_icon: Optional[str] = None
    active_persona_color: Optional[str] = None


# ── Personas ──────────────────────────────────────────────────────────

class PersonaResponse(BaseModel):
    id: int
    name: str
    perspective: str
    tone_mode: str
    voice_style: Optional[str] = None
    greeting: Optional[str] = None
    forbidden_topics: list[str] = Field(default_factory=list)
    system_prompt_override: Optional[str] = None
    avatar_color: Optional[str] = None
    avatar_icon: Optional[str] = None
    is_builtin: bool


class CreateCustomPersonaRequest(BaseModel):
    user_id: str
    name: str
    perspective: str  # 1st / 2nd / 3rd
    tone_mode: str    # Quiet / Sharp / Witty / Savage
    voice_style: Optional[str] = None
    greeting: Optional[str] = None
    forbidden_topics: list[str] = Field(default_factory=list)
    system_prompt_override: Optional[str] = None
    avatar_color: Optional[str] = None
    avatar_icon: Optional[str] = None


class CreateCustomPersonaResponse(BaseModel):
    persona_id: int


class AuditViolation(BaseModel):
    field: str
    group: str
    word: str


class CustomPersonaAuditFailResponse(BaseModel):
    detail: str
    violations: list[AuditViolation]


class SetActivePersonaRequest(BaseModel):
    persona_id: int


class SetActivePersonaResponse(BaseModel):
    user_id: str
    active_persona_id: int


# ── Onboarding ────────────────────────────────────────────────────────

class OnboardingRequest(BaseModel):
    user_id: str
    trigger_category: str
    avoidance_destination: str
    persona_id: int
    fear_anchor: Optional[str] = None
    recovery_pattern: Optional[str] = None


class OnboardingResponse(BaseModel):
    user_id: str
    completion_percent: float
    slots_updated: dict[str, Any]


# ── Sessions ──────────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    user_id: str
    avoidance_input: str
    timeline_hint: Optional[str] = None


class CreateSessionResponse(BaseModel):
    session_id: int


class ProbeQuestionResponse(BaseModel):
    question_id: Optional[int] = None
    text: Optional[str] = None
    target_slot: Optional[str] = None


class ProbeAnswerRequest(BaseModel):
    question_id: int
    answer_text: Optional[str] = None
    slot_updates: Optional[dict[str, Any]] = None
    skip: bool = False


class ProbeAnswerResponse(BaseModel):
    recorded: bool


class PersonaInfo(BaseModel):
    id: Optional[int] = None
    name: str
    perspective: Optional[str] = None      # '1st' | '2nd' | '3rd'
    tone_mode: Optional[str] = None        # 'Quiet' | 'Sharp' | 'Witty' | 'Savage'
    greeting: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None


class ScenarioCardResponse(BaseModel):
    card_id: int
    card_type: str
    sentences: dict[str, Optional[str]]  # fact, feeling, micro_action
    safety_message: Optional[str] = None
    persona: PersonaInfo


class DecisionRequest(BaseModel):
    decision: str  # transition | continue | report | delete


class DecisionResponse(BaseModel):
    session_id: int
    decision: str
    deleted: bool = False


# ── Regret ────────────────────────────────────────────────────────────

class RegretRequest(BaseModel):
    intensity: int = Field(ge=0, le=10)
    free_text: Optional[str] = None


class RegretResponse(BaseModel):
    regret_id: int


class CardAccuracyRequest(BaseModel):
    accuracy: int = Field(ge=1, le=5)


class CardAccuracyResponse(BaseModel):
    evaluation_id: int


class ReturnIntentRequest(BaseModel):
    intent: int = Field(ge=1, le=5)


class ReturnIntentResponse(BaseModel):
    evaluation_id: int


# ── Safety ────────────────────────────────────────────────────────────

class SafetySnapshotItem(BaseModel):
    week_start: str
    self_blame_word_count: int
    failure_imagery_ratio: float
    identity_failure_phrases_count: int
    pre_card_tension_self_report: Optional[float] = None


class SafetyTrendResponse(BaseModel):
    user_id: str
    weeks: list[SafetySnapshotItem]


class SafetySnapshotRefreshResponse(BaseModel):
    user_id: str
    week_start: str
    refreshed: bool


# ── Tone Feedback ─────────────────────────────────────────────────────

class ToneFeedbackRequest(BaseModel):
    kind: str  # too_hard | too_parent | too_office | too_therapist | too_general | need_starter


class ToneFeedbackResponse(BaseModel):
    card_id: int
    kind: str
    recorded: bool
