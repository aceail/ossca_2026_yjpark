"""SessionOrchestrator — G006 AvoidanceSession Pipeline.

회피 입력 → ProbeEngine → ScenarioCard (EXAONE) → 결정 기록 흐름.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db import open_db, migrate, get_persona  # noqa: E402
from persona import seed_builtin_prompts, FORBIDDEN_GROUPS  # noqa: E402
from probe import ProbeEngine, select_active_prompt  # noqa: E402

# ────────────────────────────────────────────────────────────────────
# Safety keyword detection (§6.5 F)
# ────────────────────────────────────────────────────────────────────

SAFETY_HARD_KEYWORDS: list[str] = [
    "자해", "자살", "진짜 죽고 싶다", "약통",
    "죽고 싶다", "죽어버리고 싶다",
]

SAFETY_SOFT_MESSAGE = (
    "지금 문장은 평소보다 강한 고통 신호로 읽힙니다. "
    "오늘은 후회 시나리오 대신 부담 낮은 응답으로 전환할게요."
)

# 절대 금지어 (출력 거부용 — §6.5 F)
_FORBIDDEN_WORDS: set[str] = set()
for _words in FORBIDDEN_GROUPS.values():
    _FORBIDDEN_WORDS.update(_words)


def _is_safety_trigger(text: str) -> bool:
    """자해·자살·진짜 죽고 싶다·약통 명시 여부 검사."""
    lower = text.lower()
    return any(kw in lower for kw in SAFETY_HARD_KEYWORDS)


def _contains_forbidden(text: str) -> bool:
    """절대 금지어 포함 여부 검사."""
    return any(w in text for w in _FORBIDDEN_WORDS)


# ────────────────────────────────────────────────────────────────────
# EXAONE 호출 (urllib.request, timeout 60s)
# ────────────────────────────────────────────────────────────────────

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_MODEL = "exaone3.5:7.8b"


def _call_ollama(
    system_prompt: str,
    user_message: str,
    *,
    timeout: int = 60,
    num_predict: int = 500,
    temperature: float = 0.7,
) -> str:
    """EXAONE 호출 → 응답 텍스트 반환. 실패 시 RuntimeError."""
    payload = {
        "model": OLLAMA_MODEL,
        "system": system_prompt,
        "prompt": user_message,
        "stream": False,
        "options": {
            "num_predict": num_predict,
            "temperature": temperature,
        },
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except Exception as exc:
        raise RuntimeError(f"EXAONE 호출 실패: {exc}") from exc

    parsed = json.loads(body)
    return parsed.get("response", "")


def _parse_scenario_json(raw: str) -> dict[str, Any]:
    """LLM 응답에서 JSON 객체 추출."""
    raw = raw.strip()
    # 코드 블록 제거
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(l for l in lines if not l.startswith("```"))
    # 첫 번째 { ~ 마지막 } 추출
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"JSON 없음: {raw[:200]}")
    return json.loads(raw[start:end])


# ────────────────────────────────────────────────────────────────────
# ScenarioCard dataclass (DB row 대신 메모리 표현)
# ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ScenarioCard:
    id: int
    avoidance_session_id: int
    card_type: str
    persona_id: int | None
    persona_name: str | None
    fact: str | None
    feeling: str | None
    micro_action: str | None
    safety_message: str | None


@dataclass(frozen=True)
class ProbeQuestion:
    question_id: int
    text: str
    target_slot: str


# ────────────────────────────────────────────────────────────────────
# SessionOrchestrator
# ────────────────────────────────────────────────────────────────────

class SessionOrchestrator:
    """회피 입력 → 프로브 → 시나리오 → 결정 기록 전 파이프라인."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._probe_engine = ProbeEngine(conn)

    # ── 1. 세션 시작 ──────────────────────────────────────────────

    def start_session(
        self,
        user_id: str,
        avoidance_input: str,
        timeline_hint: str | None = None,
    ) -> int:
        """AvoidanceSession INSERT → session_id 반환."""
        now = datetime.now(timezone.utc).isoformat()
        cur = self.conn.execute(
            """INSERT INTO AvoidanceSession (user_id, avoidance_input, timeline_hint, created_at)
               VALUES (?, ?, ?, ?)""",
            (user_id, avoidance_input, timeline_hint, now),
        )
        self.conn.commit()
        return cur.lastrowid

    # ── 2. 프로브 질문 선택 ────────────────────────────────────────

    def maybe_probe(self, user_id: str) -> ProbeQuestion | None:
        """ProbeEngine.best_question 위임. Phase 2 아니면 None."""
        result = self._probe_engine.best_question(user_id)
        if result is None:
            return None
        return ProbeQuestion(
            question_id=result.question_id,
            text=result.text,
            target_slot=result.target_slot,
        )

    # ── 3. 프로브 답변 기록 ────────────────────────────────────────

    def record_probe_answer(
        self,
        user_id: str,
        question_id: int,
        session_id: int,
        answer: str,
        slot_updates: dict | None = None,
    ) -> None:
        """ProbeAnswer INSERT + UserProfile.slots_json 갱신."""
        self._probe_engine.record_answer(
            user_id=user_id,
            question_id=question_id,
            avoidance_session_id=session_id,
            answer_text=answer,
            extracted_slot_updates=slot_updates or {},
        )
        if slot_updates:
            self._update_profile_slots(user_id, slot_updates)

    def _update_profile_slots(self, user_id: str, updates: dict) -> None:
        row = self.conn.execute(
            "SELECT slots_json FROM UserProfile WHERE user_id = ?", (user_id,)
        ).fetchone()
        slots: dict = {}
        if row and row["slots_json"]:
            slots = json.loads(row["slots_json"])
        slots.update(updates)
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "UPDATE UserProfile SET slots_json = ?, updated_at = ? WHERE user_id = ?",
            (json.dumps(slots, ensure_ascii=False), now, user_id),
        )
        self.conn.commit()

    # ── 4. 시나리오 생성 ──────────────────────────────────────────

    def generate_scenario(
        self,
        user_id: str,
        session_id: int,
        avoidance_input: str,
        timeline_hint: str | None = None,
    ) -> ScenarioCard:
        """Safety 검사 → LLM 호출 → ScenarioCard INSERT."""
        # Safety 검사
        if _is_safety_trigger(avoidance_input):
            return self._insert_card(
                session_id=session_id,
                card_type="soft_stop",
                persona_id=None,
                fact=None,
                feeling=None,
                micro_action=None,
                safety_message=SAFETY_SOFT_MESSAGE,
            )

        # 활성 페르소나 프롬프트
        persona_id, system_prompt = select_active_prompt(self.conn, user_id)
        if not system_prompt:
            persona_row = get_persona(self.conn, "내일의 나")
            if persona_row:
                persona_id = persona_row["id"]
                system_prompt = persona_row["system_prompt_override"] or ""

        persona_row = self.conn.execute(
            "SELECT name FROM Persona WHERE id = ?", (persona_id,)
        ).fetchone() if persona_id else None
        persona_name = persona_row["name"] if persona_row else "내일의 나"

        # 사용자 메시지 구성
        user_msg = avoidance_input
        if timeline_hint:
            user_msg = f"[타임라인: {timeline_hint}]\n{avoidance_input}"

        # LLM 호출
        try:
            raw = _call_ollama(system_prompt or "", user_msg)
            parsed = _parse_scenario_json(raw)
        except Exception as exc:
            # LLM 실패 시 soft_stop 폴백
            return self._insert_card(
                session_id=session_id,
                card_type="soft_stop",
                persona_id=persona_id,
                fact=None,
                feeling=None,
                micro_action=None,
                safety_message=f"시나리오 생성 중 오류가 발생했습니다. ({exc})",
            )

        card_type = parsed.get("card_type", "regret")

        # soft_stop / paradoxical_validation
        if card_type in ("soft_stop", "paradoxical_validation"):
            msg = parsed.get("message", SAFETY_SOFT_MESSAGE)
            if _contains_forbidden(msg):
                msg = SAFETY_SOFT_MESSAGE
            return self._insert_card(
                session_id=session_id,
                card_type=card_type,
                persona_id=persona_id,
                fact=None,
                feeling=None,
                micro_action=None,
                safety_message=msg,
            )

        # regret / recovery
        sentences = parsed.get("sentences", {})
        fact = sentences.get("fact", "")
        feeling = sentences.get("feeling", "")
        micro_action = sentences.get("micro_action", "")

        # 금지어 포함 시 soft_stop으로 대체
        combined = f"{fact} {feeling} {micro_action}"
        if _contains_forbidden(combined):
            return self._insert_card(
                session_id=session_id,
                card_type="soft_stop",
                persona_id=persona_id,
                fact=None,
                feeling=None,
                micro_action=None,
                safety_message=SAFETY_SOFT_MESSAGE,
            )

        return self._insert_card(
            session_id=session_id,
            card_type=card_type,
            persona_id=persona_id,
            fact=fact,
            feeling=feeling,
            micro_action=micro_action,
            safety_message=None,
        )

    def _insert_card(
        self,
        *,
        session_id: int,
        card_type: str,
        persona_id: int | None,
        fact: str | None,
        feeling: str | None,
        micro_action: str | None,
        safety_message: str | None,
    ) -> ScenarioCard:
        now = datetime.now(timezone.utc).isoformat()
        cur = self.conn.execute(
            """INSERT INTO ScenarioCard
               (avoidance_session_id, card_type, persona_id, fact, feeling, micro_action,
                safety_message, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, card_type, persona_id, fact, feeling, micro_action, safety_message, now),
        )
        # AvoidanceSession.scenario_card_id 업데이트
        card_id = cur.lastrowid
        self.conn.execute(
            "UPDATE AvoidanceSession SET scenario_card_id = ? WHERE id = ?",
            (card_id, session_id),
        )
        self.conn.commit()

        persona_name: str | None = None
        if persona_id:
            row = self.conn.execute(
                "SELECT name FROM Persona WHERE id = ?", (persona_id,)
            ).fetchone()
            if row:
                persona_name = row["name"]

        return ScenarioCard(
            id=card_id,
            avoidance_session_id=session_id,
            card_type=card_type,
            persona_id=persona_id,
            persona_name=persona_name,
            fact=fact,
            feeling=feeling,
            micro_action=micro_action,
            safety_message=safety_message,
        )

    # ── 5. 결정 기록 ──────────────────────────────────────────────

    def record_decision(self, session_id: int, decision: str) -> None:
        """AvoidanceSession.user_decision 갱신."""
        self.conn.execute(
            "UPDATE AvoidanceSession SET user_decision = ? WHERE id = ?",
            (decision, session_id),
        )
        self.conn.commit()
