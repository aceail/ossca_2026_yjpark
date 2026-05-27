# Autopilot Implementation Plan — v0.5 비서 + 메모리

**상태:** Phase 1 갱신 · 2026-05-27 · 사용자 무인 모드 위임

## Wave 0 — 완료 (참조)

- v0.4 Sprint 11~18: chat 멀티턴 · Task + 자연어 추출 · FolderWatcher · Follow-up · Calendar UI + ICS · PWA + 모바일 탭 · Web Push · 자연어 task 조작 · e2e 시나리오 · chat-first UX · 날짜 cutoff fix · prompt/weeks fix · chrome notification + polling · 캘린더 크기 가변 · ICS panel → settings · ReAct loop + Tool Registry

## v0.5 (이번 autopilot 라운드)

### Sprint 19 — Memory FTS5 + search_memory tool

| Task | 파일 |
|---|---|
| migration 015: FTS5 virtual table for ChatMessage + INSERT/UPDATE/DELETE trigger | `db/migrations/015_chat_message_fts5.sql` |
| `search_memory(query, limit?)` tool 추가 | `pipeline/tools.py` |
| FTS5 sync 검증 + LLM이 search_memory 호출 시나리오 | `tests/test_memory_fts.py` |

### Sprint 20 — UserMemory + 명시 remember/recall

| Task | 파일 |
|---|---|
| migration 016: UserMemory(key, value, salience, source, updated_at) | `db/migrations/016_user_memory.sql` |
| `remember(key, value)` + `recall(query)` tools | `pipeline/tools.py` |
| 매 LLM 호출 시 상위 salient memory를 system prompt에 자동 inject | `pipeline/chat.py` |
| tests | `tests/test_user_memory.py` |

### Sprint 21 — Self-reflection 주기 작업

| Task | 파일 |
|---|---|
| `pipeline/reflection.py` — 매주 1회 LLM이 최근 7일 ChatMessage·Task·FolderSnapshot·RegretScore 요약 → UserMemory 자동 추가 | new |
| backend lifespan에 weekly task | `backend/main.py` |
| tests | `tests/test_reflection.py` |

### Sprint 22 — Daily Briefing (능동성)

| Task | 파일 |
|---|---|
| chat 페이지 진입 시 오늘 첫 1회 어시스턴트가 자동으로 활성 task·마감·진척 brief 메시지 push | `backend/api/chat.py` + frontend |
| 같은 날 재로드는 skip (UserMemory `last_briefing_at` 사용) | |
| tests | |

### Sprint 23 — UX polish + 운영성

| Task | 파일 |
|---|---|
| docker-compose.local.yml + Dockerfile.backend + Dockerfile.frontend | `docker/` |
| `.env.example` 갱신 (NAEIL_AGENT_MODEL 등) | |
| docs/DEPLOY.md 신규 | |
| README v0.5 갱신 | |

## QA 게이트 (각 sprint 종료 시)

- `NAEIL_DISABLE_WATCH=1 NAEIL_DISABLE_FOLLOWUP=1 python -m unittest discover tests` 통과
- `cd frontend && npm run build` 10+ routes 통과
- commit + push (Conventional Commits)

## Phase 5 cleanup
- `.omc/state/autopilot-state.json` 삭제 (생성된 경우만)
