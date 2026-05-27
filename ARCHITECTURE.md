# Architecture — Tomorrow's You

**버전**: v0.2 architecture (UI 라운드 진행 중)
**연계**: FINAL_GOAL.md v2.3 · DATA_MODEL_v1.md · AGENT_INTEGRATIONS_v1.md

---

## 시스템 전체 (3-tier, 로컬 우선)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Browser ─ Next.js 16 SPA (App Router, TypeScript, Tailwind v4)         │
│   ├─ app/page.tsx (Welcome)                                              │
│   ├─ app/onboarding (5 카드)                                              │
│   ├─ app/personas (라이브러리 + Builder)                                  │
│   ├─ app/scenario (메인 회피 입력 + 카드 출력)                            │
│   ├─ app/regret/[sessionId] (사후 회고)                                  │
│   ├─ app/settings (페르소나 · forbidden_topics · Safety trend)           │
│   └─ components/ (PersonaCard · ScenarioCard · OnboardingCard · ...)    │
│           │                                                              │
│           │ fetch(NEXT_PUBLIC_API_BASE) — JSON over HTTP                 │
│           ↓                                                              │
│  ─────────────────────────────────────────────────────────────────────  │
│  FastAPI 0.136 (uvicorn :8001) — backend/ ─────                          │
│   ├─ api/users.py                                                        │
│   ├─ api/personas.py        ←─── persona.builder (audit·save)            │
│   ├─ api/onboarding.py      ←─── UserProfile 갱신                         │
│   ├─ api/sessions.py        ←─── pipeline.SessionOrchestrator            │
│   │                              │  ↓                                    │
│   │                              ├─ probe.ProbeEngine (Phase 1/2/3)      │
│   │                              ├─ persona.select_active_prompt         │
│   │                              ├─ Ollama HTTP (exaone3.5:7.8b)          │
│   │                              ├─ Safety: soft_stop·paradox·forbidden  │
│   │                              └─ ScenarioCard DB INSERT               │
│   ├─ api/regret.py          ←─── regret.{scheduler·accuracy}             │
│   ├─ api/safety.py          ←─── regret.slow_harm                        │
│   ├─ api/tone_feedback.py                                                │
│   └─ Depends(get_db) → sqlite3 connection (request-scoped)               │
│           │                                                              │
│           ↓                                                              │
│  ─────────────────────────────────────────────────────────────────────  │
│  SQLite (WAL, foreign_keys) — db/migrations/                             │
│   17 tables = 5 user + 7 LLM ops + 1 Safety + 3 Agent + 1 Persona       │
│   Seed: 5 builtin personas · 12 ProbeQuestion · 5 AgentTool             │
│           │                                                              │
│           │ optional read-only enrichment                                │
│           ↓                                                              │
│  ─────────────────────────────────────────────────────────────────────  │
│  Agent Tools (agent/) ─── ToolInvocation audit ─────                     │
│   ├─ google_calendar (read-only, OAuth local fernet)                     │
│   ├─ local_files (사용자 지정 폴더 mtime 스캔)                            │
│   └─ web_search (Brave/SearXNG, 사용자 명시 활성화)                       │
│           │                                                              │
│           ↓                                                              │
│  ─────────────────────────────────────────────────────────────────────  │
│  Ollama 0.15.6 (:11434) ─ exaone3.5:7.8b (한국어 baseline, Witty 모드)   │
│   Future: qwen3:14b for LLM-as-judge (G009 v2)                           │
└─────────────────────────────────────────────────────────────────────────┘
```

## 핵심 데이터 흐름 — 회피 입력에서 시나리오 카드까지

```
사용자 입력: "내일 발표 슬라이드 0장. 새벽 1시 14분이야."
    ↓
[Frontend] POST /api/sessions {user_id, avoidance_input, timeline_hint}
    ↓
[FastAPI] SessionOrchestrator.start_session → AvoidanceSession INSERT
    ↓
[Frontend] GET /api/sessions/{id}/probe
    ↓
[FastAPI] ProbeEngine.best_question (Phase 2 적응적)
    ├─ Phase 1 (세션 < 4) → null (G005 onboarding이 처리)
    ├─ Phase 2 (4-15 또는 completion < 80%) → 휴리스틱 점수 최고 질문 1개
    └─ Phase 3 (completion ≥ 80%) → null
    ↓
[Frontend] (질문 있으면) 사용자에게 표시 → POST /api/sessions/{id}/probe-answer
[FastAPI] ProbeEngine.record_answer (또는 skip → cooldown 24h)
    ↓
[Frontend] POST /api/sessions/{id}/scenario
    ↓
[FastAPI] generate_scenario:
    1. Safety 키워드 검사 (자해·자살·약통) → 매치되면 soft_stop 즉시 반환
    2. select_active_prompt(user_id) → 활성 페르소나의 system_prompt_override
    3. Agent tool router: 입력 키워드 분석 → calendar/files/search 병렬 호출 (timeout 3s)
    4. Ollama POST /api/chat (exaone3.5:7.8b, persona prompt + tool 결과)
    5. JSON 파싱 → {card_type, sentences:{fact, feeling, micro_action}}
    6. ScenarioCard INSERT + AvoidanceSession.scenario_card_id 업데이트
    7. ToolInvocation 모든 호출 audit 로그
    ↓
[Frontend] ScenarioCard 컴포넌트 렌더링 (페르소나 색·icon·헤더·3단·30s 타이머)
    ↓
사용자 결정: [t]시작 / [c]계속 / [r]리포트 / [d]삭제(Self-Destruct)
    ↓
[Frontend] POST /api/sessions/{id}/decision
[FastAPI] AvoidanceSession.user_decision 갱신 (delete면 cascade)
    ↓
[24h 후 Frontend] POST /api/sessions/{id}/regret + accuracy + return-intent
[FastAPI] regret.record_regret_score + record_card_accuracy + record_return_intent
    ↓
[주별 자동] regret.build_weekly_snapshot → SafetyHarmTimeSeries
    Slow Harm 알람 시 → recovery 카드 비율 자동 상향
```

## 모듈 의존 그래프

```
                    ┌───────────────┐
                    │  FastAPI app  │ (backend/main.py)
                    └──┬────────┬───┘
                       │        │
          ┌────────────┴┐      ┌┴────────────┐
          │  pipeline   │      │   persona   │
          │  (G006)     │      │   (G011)    │
          └─┬─────┬────┬┘      └──┬──────────┘
            │     │    │           │
            ↓     ↓    ↓           ↓
        ┌────┐ ┌────┐ ┌────┐    ┌───┐
        │ db │ │probe│ │ ui │   │db │
        │G003│ │G004│ │TUI │   │G003│
        └─┬──┘ └─┬──┘ └────┘   └─┬─┘
          │     │                 │
          └──┬──┘                 │
             ↓                     ↓
          ┌──────┐            (UPSERT to)
          │SQLite│ ←─ regret ─┐
          │  17  │  (G007)    │
          │tables│ ←─ agent ──┤
          └──────┘  (G010)    │
                              │
                          ToolInvocation
                          (감사 로그)
```

## TUI vs Web 두 UI 트랙

| 트랙 | 입구 | 카드 출력 | 적합 사용자 |
|---|---|---|---|
| **TUI MVP** (G006) | `python3 scripts/cli.py` | ANSI 박스 + Self-Destruct ⊗ + 30s 텍스트 타이머 | 개발자·CLI 선호·서버 환경 |
| **웹 SPA** (G008 + UI 라운드) | `bash scripts/dev.sh` 또는 Vercel/배포 | 디자인 토큰 기반 컴포넌트 + JS 인터랙티비티 (블러·UNDO·타이머 카운트다운) | 일반 사용자·OSSCA 멘토 데모 |

두 트랙 모두 동일한 FastAPI 백엔드를 공유. 백엔드는 카드 생성·DB·Agent tool·Safety를 단일 진실 출처로 관리.

## 안전 게이트 그래프

```
회피 입력
   │
   ├─ Safety A. 위기 키워드 → soft_stop 즉시 반환 (시나리오 생성 X)
   ├─ Safety E. 앱 비꼬기 감지 → paradoxical_validation 반환
   │
   ↓ (위 둘 다 아니면)
시나리오 생성
   │
   ├─ Persona Builder (커스텀 페르소나 입력 시) → audit → 위반 시 거부
   ├─ 절대 금지어 (5 그룹, 모드 무관) → 출력 거부 + 재생성
   ├─ 1인칭 강제 (persona.perspective='1st') → 2인칭 검출 시 재생성
   ├─ 길이 80-150자 → 초과 시 재생성
   └─ "정확하지만 안 쓸 사실" 필터 (forbidden_topics 매치 차단)
   │
   ↓
카드 출력 + 30s 운동성 강제 + Self-Destruct opacity 40%
   │
   ↓
주별 Slow Harm 시계열
   ├─ self_blame_word_count 증가 4주 연속 → 자동 recovery 비율 ↑
   └─ identity_failure 누적 → 페르소나 자동 변경 제안
```

## 패키지 디렉토리 한 줄 요약

| 디렉토리 | 책임 |
|---|---|
| `db/` | SQLite + 마이그레이션 + 5 페르소나 seed |
| `persona/` | 5 default + Builder audit + system_prompt |
| `probe/` | HITL Phase 라우터 + 휴리스틱 + cooldown |
| `pipeline/` | SessionOrchestrator (입력→카드 end-to-end) |
| `ui/` | TUI 카드 ANSI 렌더링 |
| `regret/` | RegretScore + Fingerprint + Slow Harm + accuracy |
| `agent/` | Calendar/Files/Search tool + OAuth 로컬 |
| `backend/` | FastAPI 래퍼 (현재 UI 라운드 신설) |
| `frontend/` | Next.js 16 SPA (현재 UI 라운드 신설) |
| `web/` | v0.1 정적 mock (legacy reference) |
| `scripts/` | CLI MVP + 평가 + 시뮬레이터 + dev 실행기 |
| `tests/` | unittest 170+ 회귀 |
| `.omc/ultragoal/` | v2.3 설계 문서 (17+ 산출) |
