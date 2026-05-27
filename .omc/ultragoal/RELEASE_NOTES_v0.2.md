# Release Notes — v0.2 (UI 라운드 진행 중)

**기준일**: 2026-05-27 · **이전 버전**: v0.1 (G001-G011 closed)

---

## 새로 추가된 산출 (UI 라운드)

### Frontend (`frontend/`)
- Next.js 16 + React 19 + TypeScript 5 + Tailwind v4 (App Router)
- 디자인 토큰 — Tailwind v4 `@theme` 블록으로 v0.1 `web/tokens.css` 이식
- 한국어 폰트 — Noto Serif KR (사실 레이어) + Noto Sans KR (감정·운동성)
- 9 재사용 컴포넌트 (Button · Logo · Progress · UndoToast · TimerRing · SocialBlurGuard · PersonaCard · ScenarioCard · OnboardingCard)
- 라우팅 6경로 + Welcome 페이지 (designer §8 카피 시안 B)
- API client (`lib/api.ts`) + 5 페르소나 fallback (`lib/personas.ts`) + useUser hook

### Backend (`backend/`)
- FastAPI 0.136 + uvicorn 0.48 + pydantic 2.13
- 7 라우터 (users · personas · onboarding · sessions · regret · safety · tone_feedback)
- 기존 Python 모듈(db · persona · probe · pipeline · regret · agent) 그대로 import
- TestClient 통합 테스트

### Infrastructure
- `scripts/dev.sh` — backend + frontend 동시 실행 helper
- `scripts/integration_check.sh` — 5 endpoint curl 검증
- `.env.example` (root + frontend/) — 환경변수 가이드
- `.gitignore` 확장 (Next.js, Python builds, editor/OS)
- `ARCHITECTURE.md` — 시스템 전체 다이어그램 + 데이터 흐름

## 변경된 산출

- `README.md` — Quickstart에 frontend·backend 실행 추가 (다음 라운드)
- `tests/test_data_model.py` — 마이그레이션 수 증가에 대응 (1→4), AgentTool 충돌 회피

## v0.1 → v0.2 호환성

- v0.1 TUI MVP (`python3 scripts/cli.py`) 그대로 작동
- v0.1 SQLite 스키마 그대로 (`db/migrations/001-004`)
- 5 default 페르소나 seed 그대로
- 정적 mock (`web/index.html`) 그대로 (legacy reference로 보존)

## 다음 단계 (v0.2 마무리)

- [ ] Wave 2D: 페이지 실제 구현 (onboarding 5 카드 · scenario 메인 · personas Builder · regret 회고 · settings)
- [ ] Wave 2E: JS interactivity (타이머·UNDO·블러·등장 애니메이션·tone feedback POST)
- [ ] Wave 3: 통합 검증 + commit + push
- [ ] v0.3 후속 (ROADMAP_v0.2.md 참조)

## 알려진 한계 (v0.2 출시 시점)

- Google Calendar / Web Search tool은 mock (실 OAuth는 v0.3)
- LLM-as-judge 평가 (G009 v2)는 v0.3
- 페르소나 회귀 (G009 v3) v0.3
- 실 사용자 2주 피드백은 OSSCA 멘토 매칭 후
