"""Onboarding Flow Simulator — G005.

5 카드 진행을 텍스트 시뮬레이션. 사용자 입력 받지 않고 hardcoded 선택으로
UserProfile JSON 초기화 흐름 검증.

Usage:
    python3 scripts/onboarding_simulator.py [--deep] [--out path]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_PERSONAS = {
    "persona_morning_self": {"name": "내일의 나", "perspective": "1st", "tone_mode": "Sharp", "icon": "🌙"},
    "persona_year_later": {"name": "1년 후의 나", "perspective": "1st", "tone_mode": "Quiet", "icon": "🌅"},
    "persona_close_friend": {"name": "친한 친구 ㅈㅅ", "perspective": "2nd", "tone_mode": "Witty", "icon": "🤝"},
    "persona_strict_coach": {"name": "엄격한 코치", "perspective": "2nd", "tone_mode": "Sharp", "icon": "🎯"},
    "persona_observer": {"name": "객관 옵저버", "perspective": "3rd", "tone_mode": "Quiet", "icon": "👁️"},
}

KOREAN_TRIGGER_OPTIONS = [
    "글쓰기·논문·보고서", "발표·PPT·프레젠테이션", "이메일·연락·답장",
    "공부·시험 준비", "운동·습관 만들기", "정리·청소·집안일",
    "의사결정·결단", "행정·서류·세금", "관계·사과·고백", "기타",
]

KOREAN_AVOIDANCE_OPTIONS = [
    "유튜브·릴스·쇼츠", "잠·침대·휴식", "SNS·인스타·X",
    "음식·간식·배달", "게임", "넷플릭스·OTT",
    "인터넷 서핑·뉴스", "기타",
]

FEAR_ANCHOR_OPTIONS = [
    "나를 한심하게 보는 옛 동기",
    "내가 따라잡지 못한 친구",
    "어쩐지 잘 살고 있는 그 사람",
    "부모의 기대와 다른 모습",  # ⚠️ sensitive
    "어제의 나",
    "내가 약속한 미래의 나",
    "없음·건너뛰기",
]

RECOVERY_QUICK = [
    "첫 문장 쓰기", "운동복 갈아입기", "한 페이지만 읽기", "메시지 한 줄 보내기",
]

SENSITIVE_FEAR_ANCHORS = {"부모의 기대와 다른 모습": "부모 기대"}


def sensitive_topic_audit(fear_value: str | None) -> list[str]:
    """선택된 fear_anchor가 한국형 수치심 트리거 sensitive 주제면 forbidden_topics에 자동 추가."""
    forbidden = []
    if fear_value and fear_value in SENSITIVE_FEAR_ANCHORS:
        forbidden.append(SENSITIVE_FEAR_ANCHORS[fear_value])
    return forbidden


def build_profile(
    trigger: str,
    avoidance: str,
    persona_id: str,
    fear: str | None = None,
    recovery: str | None = None,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    slots = {
        "trigger_category": {"value": trigger, "confidence": 1.0, "source": "onboarding_card_1"},
        "avoidance_destination": {"value": avoidance, "confidence": 1.0, "source": "onboarding_card_2"},
        "active_persona_id": {"value": persona_id, "confidence": 1.0, "source": "onboarding_card_3"},
    }
    filled = 3
    if fear:
        slots["fear_anchor"] = {"value": fear, "confidence": 0.7, "source": "onboarding_card_4", "optional": True}
        filled += 1
    if recovery:
        slots["recovery_pattern"] = {"value": recovery, "confidence": 0.7, "source": "onboarding_card_5", "optional": True}
        filled += 1
    total_slots = 5
    forbidden = sensitive_topic_audit(fear)
    return {
        "user_id": f"local-{uuid4().hex[:8]}",
        "created_at": now,
        "slots": slots,
        "completion_percent": round(filled / total_slots * 100, 1),
        "forbidden_topics": forbidden,
        "preferred_tone_mode_attribute": None,
    }


def render_persona_preview(persona_id: str, sample_avoidance: str) -> str:
    p = DEFAULT_PERSONAS[persona_id]
    return f"{p['icon']} {p['name']} ({p['perspective']}, {p['tone_mode']}) — 미리보기 캐시는 G011에서 생성"


def render_first_scenario_placeholder(profile: dict, sample_avoidance: str) -> str:
    persona_id = profile["slots"]["active_persona_id"]["value"]
    p = DEFAULT_PERSONAS.get(persona_id, {"name": "(unknown)", "icon": "?"})
    return (
        f"\n────────── 첫 시나리오 미리보기 ──────────\n"
        f"{p['icon']} {p['name']}\n"
        f"(실제 카드 본문은 G011 PersonaSystem 완성 후 EXAONE Witty 톤으로 생성)\n"
        f"입력 샘플: {sample_avoidance}\n"
        f"forbidden_topics: {profile['forbidden_topics']}\n"
        f"────────────────────────────────────────\n"
    )


def simulate(deep: bool = False) -> dict:
    print("=" * 60)
    print("Onboarding Flow Simulator — G005")
    print("=" * 60)
    print()
    print("● Welcome — '5장만 카드를 골라주세요. 60초/120초 분기'")
    print()

    trigger = KOREAN_TRIGGER_OPTIONS[0]
    print(f"● Card 1/5 — 트리거 카테고리 선택: {trigger}")

    avoidance = KOREAN_AVOIDANCE_OPTIONS[0]
    print(f"● Card 2/5 — 회피처 선택: {avoidance}")

    persona_id = "persona_morning_self"
    print(f"● Card 3/5 — 페르소나 선택: {render_persona_preview(persona_id, '내일 발표 슬라이드 0장')}")

    fear: str | None = None
    recovery: str | None = None

    if deep:
        print()
        print("● Branch — Deep mode 선택")
        fear = FEAR_ANCHOR_OPTIONS[3]  # sensitive '부모의 기대'
        print(f"● Card 4/5 — 두려움 앵커: {fear}  ⚠️ sensitive — forbidden_topics에 자동 추가")
        recovery = RECOVERY_QUICK[0]
        print(f"● Card 5/5 — 회복 패턴: {recovery}")
    else:
        print()
        print("● Branch — ESCape (60초, 3 카드만)")

    profile = build_profile(trigger, avoidance, persona_id, fear, recovery)
    print()
    print("● UserProfile 초기화 완료:")
    print(json.dumps(profile, indent=2, ensure_ascii=False))
    print(render_first_scenario_placeholder(profile, "내일 발표인데 슬라이드 0장. 새벽 1시야."))
    return profile


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deep", action="store_true", help="Deep mode (5 카드 모두)")
    parser.add_argument("--out", default=str(PROJECT_ROOT / ".omc" / "ultragoal" / "onboarding_sim_profile.json"))
    args = parser.parse_args()
    profile = simulate(deep=args.deep)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
