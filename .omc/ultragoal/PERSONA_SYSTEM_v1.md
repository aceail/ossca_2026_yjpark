# Persona System v1 — G011

**버전**: v1
**작성일**: 2026-05-26
**연계**: FINAL_GOAL.md v2.3 §6 (Persona 테이블) · §6.5 F (모드 무관 한계선) · §12 (페르소나 라이브러리) · ONBOARDING_FLOW_v1.md (G005)
**구현**: `persona/builder.py` · `persona/__init__.py` · `tests/test_persona_system.py` (13/13 green)

---

## 0. 핵심 결정

- 페르소나 = **상위 개념**, 톤 모드(Quiet/Sharp/Witty/Savage)는 attribute로 흡수
- `perspective` (1st/2nd/3rd)가 화법 강제
- 5 default + 사용자 Custom 빌더
- **절대 한계선**(가스라이팅·정체성 결함·비교 수치심·한국형 트리거·심각 욕설)은 모든 페르소나·perspective 공통
- Custom Persona는 audit 통과 후에만 저장 — 사용자 입력 4 필드(name·voice_style·greeting·system_prompt_override) 모두 검사

## 1. 5 Default 페르소나 spec

| Persona | perspective | tone | greeting |
|---|---|---|---|
| 🌙 내일의 나 | 1st | Sharp | "내일의 내가 너에게 보낸 메시지야" |
| 🌅 1년 후의 나 | 1st | Quiet | "1년 뒤의 내가 짧게 한 마디" |
| 🤝 친한 친구 ㅈㅅ | 2nd | Witty | "야 너 지금 뭐 하는 거야ㅋ" |
| 🎯 엄격한 코치 | 2nd | Sharp | "10분 줄게. 한 줄만 쓰고 와." |
| 👁️ 객관 옵저버 | 3rd | Quiet | "그는 지금 23시 47분, 슬라이드 0장..." |

각 페르소나는 자기 `system_prompt_override`를 가지며, `BASE_SYSTEM_PROMPT`(모드 무관 절대 규칙)를 상속.

## 2. Base System Prompt (모든 페르소나 공통)

5 절대 규칙 (`persona/builder.py::BASE_SYSTEM_PROMPT`):
1. 출력 형식: JSON 한 줄 (코드 블록 금지)
2. 3단 구조 80-150자
3. 절대 금지어 5 그룹 (가스라이팅·정체성 결함·비교 수치심·한국형 트리거·심각 욕설)
4. 한국 정서 3사각 대응
5. Safety: 위기 키워드 → soft_stop / 앱 비꼬기 → paradoxical_validation

## 3. Persona Builder 안전 Audit

`audit_custom_persona(payload)` 정책:

| 입력 필드 | audit 대상 | 비고 |
|---|---|---|
| `name` | ✅ 5 그룹 키워드 검사 | 페르소나 이름 자체에 가스라이팅 어휘 금지 |
| `voice_style` | ✅ | 톤 묘사에 정체성 결함·욕설 금지 |
| `greeting` | ✅ | 인사 한 줄도 같은 한계선 적용 |
| `system_prompt_override` | ✅ | 사용자가 LLM에 시키는 내용도 검사 |
| `forbidden_topics` | ❌ 면제 | 사용자 자기 보호용, 어떤 단어든 OK |
| `perspective` / `tone_mode` | ❌ 면제 | enum CHECK constraint로 DB-level 검사 |

위반 시 `AuditResult.accepted=False` + `violations=[(field, group, word), ...]` 반환. 저장 거부 + 사용자에게 사유 안내.

**builtin 페르소나는 audit 면제**: `system_prompt_override`가 절대 금지어 리스트를 negative prompt로 명시 포함하므로 audit 통과 불가. 사용자 노출 필드(name·voice_style·greeting)만 audit 통과 확인.

## 4. Custom Persona 입력 흐름 (G005 OnboardingFlow Card 3 → Custom Builder)

```
사용자가 "✨ 내가 직접 만들래요" 선택
   ↓
[Builder UI]
   - 이름 (예: "내 옛 동기 ㅇㅇ", "엄마의 시선")
   - perspective (1st / 2nd / 3rd 카드 선택)
   - tone_mode (Quiet / Sharp / Witty / Savage)
   - voice_style (한 줄 자유 입력, 예: "능청맞은 친구 톤")
   - greeting (한 줄)
   - forbidden_topics (배열, 사용자가 보호하고 싶은 주제)
   - (고급) system_prompt_override (자유 텍스트)
   ↓
audit_custom_persona(payload)
   ↓
accepted? ── No → 위반 리스트 표시 + 수정 요청
   │
   └── Yes → save_persona(conn, sanitized, is_builtin=False, user_id)
                ↓
        UserProfile.active_persona_id = new_persona_id
        첫 시나리오 카드 미리보기 생성 → 사용자 확인
```

## 5. 페르소나 미리보기 (G005 Card 3 의존)

각 페르소나가 동일 회피 입력에 어떻게 응답하는지 사용자에게 미리 보여줘 톤 차이 체감:

**고정 가상 입력**: "내일 10시 발표인데 슬라이드 0장. 새벽 1시 14분이야."

**산출**: `.omc/ultragoal/persona_previews_v1.json` (5 페르소나 × 1 입력 = 5 카드 캐시, EXAONE 생성)

샘플 결과 (실측):
- 🌙 내일의 나 (1st·Sharp): "내일 오전 10시 발표인데, 지금까지 만든 슬라이드가 하나도 없어 전체 일정이 위험에 처해 있다. ... 즉시 슬라이드 제작을 시작한다."
- 🤝 친한 친구 ㅈㅅ (2nd·Witty): "지금 1시 14분인데 슬라이드 한 장도 안 만들어졌다니, 팀 앞에서 정말 당황스럽겠다 싶네. ... 지금부터라도 간단한 슬라이드라도 만들어보자, 같이 하자!"
- 🎯 엄격한 코치 (2nd·Sharp): "지금 시간이 1시 14분으로, 발표까지 8시간 46분 남았습니다. ... 슬라이드 제작 시작한다"
- 👁️ 객관 옵저버 (3rd·Quiet): "현재 시각 01:14, 마감 시각까지 8시간 46분 남음. 슬라이드 제작 완료율 0%. ... 그는 즉시 슬라이드 제작 소프트웨어를 열고 기본 구조를 시작한다."

→ perspective·tone이 명확히 차별화됨. 사용자가 톤 차이를 즉시 인지 가능.

## 6. 모드 무관 절대 한계선 자동 회귀 (G009 v3 연동)

G009 v3에서 다음을 자동 검증:
- 모든 5 페르소나가 30 골든 샘플에서 절대 금지어 위반 0
- perspective별 화법 일관성 (1st: 1인칭만 / 2nd: 2인칭만 / 3rd: 3인칭만)
- Custom Persona 시뮬레이션 audit 검증

## 7. G011 v1 Definition of Done

- [x] 5 default 페르소나 spec (perspective·tone·voice_style·greeting·system_prompt)
- [x] BASE_SYSTEM_PROMPT (모드 무관 절대 규칙)
- [x] Persona Builder audit (`audit_custom_persona`)
- [x] save_persona (DB INSERT)
- [x] seed_builtin_prompts (DB UPDATE for system_prompt_override)
- [x] 5 페르소나 미리보기 캐시 (`persona_previews_v1.json`)
- [x] unittest 13/13 green (audit·builtin·save)

## 8. 다음 스토리 의존

- **G004 HITLProbeEngine** — 페르소나별 프롬프트 라우터 (active_persona_id → system_prompt_override 선택)
- **G005 OnboardingFlow** (이미 complete) — Card 3 페르소나 선택 카드에 미리보기 노출
- **G006 Pipeline** — 시나리오 카드 생성 시 active persona 컨텍스트 주입
- **G008 MVPRelease** — Persona Builder UI + 페르소나별 시각 토큰 (designer 후속 의뢰)
- **G009 v3 EvaluationHarness** — 5 페르소나 × 30 샘플 = 150 카드 회귀 + perspective별 화법 일관성
