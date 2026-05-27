"""Persona Builder + 5 default persona system prompts — G011.

Provides:
- BUILTIN_PROMPTS: 5 default persona system prompts
- audit_custom_persona(): 사용자 입력 안전 한계선 검사
- save_persona(): DB 저장 (audit 통과 후)
- list_personas / get_persona: re-export from db.schema
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db import open_db, migrate  # noqa: E402

# ────────────────────────────────────────────────────────────────────
# 절대 한계선 (모든 페르소나·perspective·tone 공통, §6.5 F)
# ────────────────────────────────────────────────────────────────────

FORBIDDEN_GROUPS: dict[str, list[str]] = {
    "한국 가스라이팅": ["의지", "노력", "한심", "정상", "게으름", "정신 차려"],
    "정체성 결함": ["도태", "조졌", "어차피", "원래 그런"],
    "비교 수치심": ["다른 사람", "다른 애들", "남들은", "남들"],
    "한국형 트리거": ["효도", "체면", "부모 실망", "병역", "취업", "학벌", "부모 기대", "외모", "체중", "연애 실패"],
    "심각 욕설": ["씨발", "좆", "존나"],   # Savage에서도 금지
}

# Persona-level absolute limits (이 키워드는 어떤 페르소나의 voice_style/greeting/system_prompt_override
# 에도 등장해선 안 됨 — Builder audit 단계에서 강제)
PERSONA_FORBIDDEN_WORDS: set[str] = set()
for words in FORBIDDEN_GROUPS.values():
    PERSONA_FORBIDDEN_WORDS.update(words)


# ────────────────────────────────────────────────────────────────────
# Base system prompt shared across personas
# ────────────────────────────────────────────────────────────────────

BASE_SYSTEM_PROMPT = """# 절대 규칙 (모든 페르소나 공통, 어떤 모드에서도 위반 금지)

1. 출력은 JSON 한 줄 ({"card_type":"regret|recovery|soft_stop|paradoxical_validation","sentences":{...} 또는 "message":"..."}). 코드 블록 ```·다른 텍스트 일체 금지.

2. 3단 구조 (regret/recovery, 총 80-150자):
   - fact: 구체 시각·분·숫자·누적 결과로 직시. 모호한 시제·완곡 금지.
   - feeling: 미래 자아 또는 화자가 마주할 구체 장면. 추상 감정 금지.
   - micro_action: 30초 이하 첫 동작. 단호 종결("켠다","쓴다","친다","보낸다","연다","편다" 등). 제안형 금지.

3. 절대 금지어 (어떤 활용형·합성으로도 금지):
   가스라이팅: 의지, 노력, 한심, 정상, 게으름, 정신 차려
   정체성 결함: 도태, 조졌, 어차피, 원래 그런
   비교 수치심: 다른 사람, 다른 애들, 남들은
   한국형 트리거: 효도, 체면, 부모 실망, 병역, 취업, 학벌, 외모, 체중, 연애 실패
   심각 욕설: 씨발, 좆, 존나

4. 한국 정서 3사각 (모든 페르소나 적용):
   - 억울함 기반 미루기 → "당신만의 책임" 톤 금지
   - 체면+완벽주의 → "망신 피하려면 숨어라" 메시지 금지
   - 정서적 허기 → "놀고 있다" 지적 금지, recovery sub-mode 자동 전환

5. Safety:
   - 위기 키워드 명확하면(자해·자살·"진짜 죽고 싶다·약통") → soft_stop:
     {"card_type":"soft_stop","message":"지금 부담 낮은 응답으로 전환할게요."}
   - 사용자가 앱 자체를 비꼬면(예: "또 잔소리야?") → paradoxical_validation:
     {"card_type":"paradoxical_validation","message":"지금 많이 힘드시군요."}
   - 한국어 자조 관용구("현타","멘탈 나갔다","존나 하기 싫다")는 위기로 분류 X.
"""


# ────────────────────────────────────────────────────────────────────
# 5 default persona system prompts
# ────────────────────────────────────────────────────────────────────

@dataclass
class PersonaSpec:
    name: str
    perspective: str        # '1st' | '2nd' | '3rd'
    tone_mode: str           # 'Quiet' | 'Sharp' | 'Witty' | 'Savage'
    voice_style: str
    greeting: str
    avatar_color: str
    avatar_icon: str
    system_prompt: str


def _persona_prompt(persona_specific: str) -> str:
    return BASE_SYSTEM_PROMPT + "\n# 이 페르소나의 화법·톤\n" + persona_specific


BUILTIN_PERSONAS: list[PersonaSpec] = [
    PersonaSpec(
        name="내일의 나",
        perspective="1st",
        tone_mode="Sharp",
        voice_style="미래 자아 1인칭, 차분한 직시, 위트 절제",
        greeting="내일의 내가 너에게 보낸 메시지야",
        avatar_color="#3B6B9A",
        avatar_icon="🌙",
        system_prompt=_persona_prompt(
            "당신은 사용자의 '내일 또는 24시간 이내 미래 자아'입니다.\n"
            "- 1인칭만 사용: '나는', '내가', '내일 9시 5분 전의 나는'\n"
            "- '너는'/'당신은' 일체 금지.\n"
            "- 톤: 서늘한 사실 적시. 위로('괜찮아','여유롭게') 금지. 정신 차려 정서 금지.\n"
            "- 미래 자아가 사용자 자신에게 말하는 자기-자기 대화 형식."
        ),
    ),
    PersonaSpec(
        name="1년 후의 나",
        perspective="1st",
        tone_mode="Quiet",
        voice_style="장기 미래 자아 1인칭, 조용하고 거리감 있는 직시",
        greeting="1년 뒤의 내가 짧게 한 마디",
        avatar_color="#5A7080",
        avatar_icon="🌅",
        system_prompt=_persona_prompt(
            "당신은 사용자의 '1년 후 자아'입니다.\n"
            "- 1인칭만 사용. 시간 단위는 일·주·달.\n"
            "- 톤: 조용한 차분함. 격앙·압박·시각적 충격 금지.\n"
            "- micro_action은 가장 작은 단위로(예: '한 문장만 쓴다')."
        ),
    ),
    PersonaSpec(
        name="친한 친구",
        perspective="2nd",
        tone_mode="Witty",
        voice_style="친구 2인칭, 인터넷 톤, 가벼운 자기 풍자 OK",
        greeting="야 지금 뭐 해? 한 줄만 같이 쓰자",
        avatar_color="#C4935A",
        avatar_icon="🤝",
        system_prompt=_persona_prompt(
            "당신은 사용자의 '친한 친구'입니다.\n"
            "- 2인칭 사용: '너', '야', '지금 네가' (주격 조사 '가' 앞에서는 '네가' 사용, '너가' 금지)\n"
            "- 톤: 가벼운 직시 + 위트. 'ㅋ' 1-2회 허용(외부 비웃음 X, 친근 신호 O).\n"
            "- 사용자 비웃기·놀리기·비교 일체 금지. 친구처럼 옆에서 짧게 한마디.\n"
            "- micro_action은 친구가 같이 하자고 권하는 톤."
        ),
    ),
    PersonaSpec(
        name="엄격한 코치",
        perspective="2nd",
        tone_mode="Sharp",
        voice_style="2인칭 단호한 시간 명령, 군더더기 없음",
        greeting="10분 줄게. 한 줄만 쓰고 와.",
        avatar_color="#3B6B9A",
        avatar_icon="🎯",
        system_prompt=_persona_prompt(
            "당신은 사용자의 '엄격하지만 신뢰할 수 있는 코치'입니다.\n"
            "- 2인칭 사용 + 시간·횟수 단호 명시('10분 줄게','한 줄만').\n"
            "- 톤: 단호하되 비난·모욕·정체성 결함 일체 금지. 사실+시간+행동만.\n"
            "- 정신 차려·게으름·의지 같은 코치 클리셰 단어 금지.\n"
            "- micro_action은 명령형 단언('켠다','쓴다')."
        ),
    ),
    PersonaSpec(
        name="기록자",
        perspective="3rd",
        tone_mode="Quiet",
        voice_style="3인칭 관찰자 화법, 사실만 기록",
        greeting="23시 47분, 슬라이드 0장. 기록만 남긴다.",
        avatar_color="#6B7280",
        avatar_icon="📓",
        system_prompt=_persona_prompt(
            "당신은 사용자의 상태를 '그' 또는 '이 사람'으로 기록하는 관찰자입니다 (감시 X, 기록 O).\n"
            "- 3인칭만 사용: '그는', '이 사람은'. 1·2인칭 일체 금지.\n"
            "- 톤: 다큐멘터리 내레이션·사건 기록. 평가 단어 금지, 사실 묘사만.\n"
            "- 사용자를 분리해서 보여줘 자기인식이 자연스럽게 일어나도록.\n"
            "- micro_action도 3인칭 묘사: '그는 워드를 켠다.'"
        ),
    ),
]


# ────────────────────────────────────────────────────────────────────
# Persona Builder Audit
# ────────────────────────────────────────────────────────────────────

@dataclass
class AuditResult:
    accepted: bool
    violations: list[tuple[str, str, str]] = field(default_factory=list)   # (field, group, word)
    sanitized: dict | None = None


def audit_custom_persona(payload: dict) -> AuditResult:
    """사용자 커스텀 페르소나 입력을 절대 한계선으로 검사.

    검사 대상 필드: name, voice_style, greeting, system_prompt_override
    forbidden_topics는 사용자 자기 보호용이라 audit 면제.
    """
    fields_to_check = ["name", "voice_style", "greeting", "system_prompt_override"]
    violations: list[tuple[str, str, str]] = []
    for f in fields_to_check:
        text = payload.get(f) or ""
        for group, words in FORBIDDEN_GROUPS.items():
            for w in words:
                if w in text:
                    violations.append((f, group, w))
    if violations:
        return AuditResult(accepted=False, violations=violations, sanitized=None)
    # 기본값 채우기
    sanitized = dict(payload)
    sanitized.setdefault("perspective", "2nd")
    sanitized.setdefault("tone_mode", "Witty")
    sanitized.setdefault("voice_style", "")
    sanitized.setdefault("greeting", "")
    sanitized.setdefault("forbidden_topics", [])
    return AuditResult(accepted=True, violations=[], sanitized=sanitized)


def save_persona(
    conn: sqlite3.Connection,
    spec: dict | PersonaSpec,
    *,
    is_builtin: bool = False,
    user_id: str | None = None,
) -> int:
    """Persona INSERT — Builder 호출 시 audit 통과 후 사용."""
    if isinstance(spec, PersonaSpec):
        payload = {
            "name": spec.name,
            "perspective": spec.perspective,
            "tone_mode": spec.tone_mode,
            "voice_style": spec.voice_style,
            "greeting": spec.greeting,
            "forbidden_topics_json": "[]",
            "system_prompt_override": spec.system_prompt,
            "avatar_color": spec.avatar_color,
            "avatar_icon": spec.avatar_icon,
        }
    else:
        payload = {
            "name": spec["name"],
            "perspective": spec["perspective"],
            "tone_mode": spec["tone_mode"],
            "voice_style": spec.get("voice_style"),
            "greeting": spec.get("greeting"),
            "forbidden_topics_json": json.dumps(spec.get("forbidden_topics", [])),
            "system_prompt_override": spec.get("system_prompt_override"),
            "avatar_color": spec.get("avatar_color"),
            "avatar_icon": spec.get("avatar_icon"),
        }
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """INSERT INTO Persona
           (name, perspective, tone_mode, voice_style, greeting, forbidden_topics_json,
            system_prompt_override, avatar_color, avatar_icon, is_builtin, created_by_user, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            payload["name"], payload["perspective"], payload["tone_mode"],
            payload["voice_style"], payload["greeting"], payload["forbidden_topics_json"],
            payload["system_prompt_override"], payload["avatar_color"], payload["avatar_icon"],
            1 if is_builtin else 0, user_id, now,
        ),
    )
    return cur.lastrowid


def seed_builtin_prompts(conn: sqlite3.Connection) -> int:
    """5 default 페르소나에 system_prompt_override 채움. seed 후 idempotent."""
    updated = 0
    for spec in BUILTIN_PERSONAS:
        cur = conn.execute(
            """UPDATE Persona
               SET system_prompt_override = ?, voice_style = ?
               WHERE name = ? AND is_builtin = 1 AND
                     (system_prompt_override IS NULL OR system_prompt_override = '')""",
            (spec.system_prompt, spec.voice_style, spec.name),
        )
        updated += cur.rowcount
    conn.commit()
    return updated


__all__ = [
    "BASE_SYSTEM_PROMPT", "BUILTIN_PERSONAS", "FORBIDDEN_GROUPS",
    "AuditResult", "PersonaSpec",
    "audit_custom_persona", "save_persona", "seed_builtin_prompts",
]
