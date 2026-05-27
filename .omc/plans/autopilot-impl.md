# Autopilot Implementation Plan — Local-first Mobile Reality-Check Agent

**상태:** Phase 1 (Planning) complete · 2026-05-27

## Wave 0 — 이미 완료 (참조)

- Sprint 11 (chat 멀티턴) — `ChatSession`/`ChatMessage` + `/api/chat/*` + `/chat` 페이지
- P0-8 (device token), P0-15 (consent), P0-16 (idempotency), Slow Harm gate

## Wave 1 — Task 모델 + 자연어 추출 (Sprint 12)

### W1.1 — 마이그레이션 013
- `db/migrations/013_task_and_folder_snapshot.sql` — `Task` + `FolderSnapshot`

### W1.2 — Backend Task API
- `backend/schemas.py` — `TaskCreateRequest`, `TaskResponse`, `TaskListResponse`, `FolderSnapshotItem`
- `backend/api/tasks.py` — `POST /api/tasks`, `GET /api/tasks?user_id=`, `PATCH /api/tasks/{id}`, `DELETE /api/tasks/{id}`. token 가드.
- `backend/main.py` — 라우터 등록

### W1.3 — 자연어 → action 추출
- `pipeline/chat.py` 수정:
  - system_prompt에 `[형식] {"speak":"...","actions":[...]}` 안내 추가
  - 응답 파싱 분기: JSON이면 actions 실행, 아니면 평문
  - `_execute_actions(conn, user_id, actions)` — `create_task` / `update_task` 등 dispatch
  - speak 텍스트에 액션 결과 자동 prefix ("✅ 5/31 발표자료 캘린더에 박았어")

### W1.4 — Frontend Tasks 페이지
- `frontend/app/tasks/page.tsx` — task 목록 + 카드 (제목·마감·D-N·폴더·진척도)
- chat 페이지에 "캘린더 카드" 인라인 렌더링 (assistant 응답이 action 포함 시)

### W1.5 — Tests
- `tests/test_tasks_api.py` — CRUD + token 가드
- `tests/test_chat_actions.py` — 자연어 → action 추출 mock

## Wave 2 — FolderWatcher (Sprint 13)

### W2.1 — Provider 추상화 골격
- `core/providers/__init__.py`, `core/providers/folder.py`
- `FolderProvider` Protocol + `LocalFolderProvider` (os.scandir)
- `core/providers/factory.py` — `get_folder_provider()` (NAEIL_MODE 분기 준비)

### W2.2 — Watcher 백그라운드 작업
- `pipeline/folder_watch.py` — `scan_all_tasks(conn)` + `record_snapshot(task)`
- `backend/main.py` lifespan에 APScheduler 또는 asyncio.create_task로 30분 주기 호출
  - 환경변수 `NAEIL_WATCH_INTERVAL_MIN=30` 으로 override 가능
  - test 모드(`NAEIL_DISABLE_WATCH=1`)면 skip

### W2.3 — Snapshot Diff API
- `GET /api/tasks/{id}/snapshots?limit=10` — 최근 N개
- `GET /api/tasks/{id}/progress` — file_count/bytes 변화 요약

### W2.4 — Frontend snapshot 시각화
- 카드에 sparkline 또는 텍스트 "어제 3 → 오늘 7 (+4)"

### W2.5 — Tests
- `tests/test_folder_watch.py` — tmp dir 만들고 파일 추가 → snapshot 검증

## Wave 3 — Follow-up Scheduler + Tone Matrix (Sprint 14)

### W3.1 — Scheduler
- `pipeline/followup.py` — `compute_next_followup(task)` (D-3·D-1·D-0 매트릭스 + Slow Harm 가중치)
- `dispatch_due_followups(conn)` 매시간 호출 → chat assistant message INSERT

### W3.2 — Tone Matrix
- `pipeline/followup_tone.py` — 마감 거리 × 폴더 진척 × Slow Harm 신호 → 톤 선택 함수
- Witty (D-3 진척O) / Sharp (D-1 진척X) / Savage (D-0 진척X, Slow Harm normal일 때만) / Quiet (Slow Harm elevated 이상)

### W3.3 — Frontend SSE 또는 polling
- chat 페이지가 5초 polling으로 새 assistant 메시지 fetch (간단)
- 더 좋게: `/api/chat/sessions/{id}/stream` SSE — sprint 15로 분리

### W3.4 — Tests
- followup tone matrix 모든 셀 검증
- scheduler가 due task만 골라내는지

## Wave 4 — PWA + 모바일 UI (Sprint 15)

### W4.1 — Next.js manifest + icons
- `frontend/app/manifest.ts` — name, short_name, theme, icons[]
- `frontend/public/icon-192.png`, `icon-512.png` — 검은 배경 + ⌛ 흰 글리프 (단순 생성)

### W4.2 — Service Worker
- `frontend/public/sw.js` — offline 캐시 (read-only stale-while-revalidate) + push event handler
- `frontend/app/layout.tsx`에 register 코드

### W4.3 — 하단 탭 바 컴포넌트
- `frontend/components/BottomTabs.tsx` — Chat / Tasks / Calendar / Settings 4 탭
- 모바일 viewport에서만 노출 (`md:hidden`)

### W4.4 — 터치 친화 보강
- 모든 인터랙티브 요소 `min-height: 44px`
- 입력창 sticky bottom (모바일)
- chat 메시지 swipe (옵션, v2)

### W4.5 — Backend 0.0.0.0 bind 옵션
- `scripts/dev.sh` 또는 README에 `uvicorn --host 0.0.0.0` 안내
- CORS allow_origins에 `192.168.*` 와이파이 IP 패턴 추가 (개발용)

## Wave 5 — Web Push (Sprint 16)

### W5.1 — VAPID 키 생성
- `scripts/gen_vapid.py` — `pywebpush.helpers.generate_vapid_keypair` 또는 ECDSA stdlib
- 환경변수 `NAEIL_VAPID_PUBLIC_KEY`/`PRIVATE_KEY` set 안내

### W5.2 — DB + API
- `db/migrations/014_push_subscription.sql`
- `POST /api/push/subscriptions` (저장), `DELETE /api/push/subscriptions/{id}` (해지)
- token 가드

### W5.3 — Frontend 구독 흐름
- settings 페이지에 "마감 알림 받기" 토글
- `pushManager.subscribe()` → backend POST
- VAPID public key는 frontend env로 노출 (`NEXT_PUBLIC_VAPID_PUBLIC_KEY`)

### W5.4 — Push 발송
- `pipeline/push.py` — `send_push(subscription, payload)` (`pywebpush`)
- follow-up scheduler가 due 시 chat INSERT + push 발송

### W5.5 — Tests + 수동 검증
- `tests/test_push_subscription_api.py`
- `scripts/test_push.py` — 임의 user의 모든 subscription에 테스트 알림 발송

## Wave 6 — OSS 패키징 + 문서 (Sprint 16 끝물)

### W6.1 — docker-compose
- `docker/local.compose.yml` — `naeil-backend`, `naeil-frontend`, `ollama`
- `docker/Dockerfile.backend`, `docker/Dockerfile.frontend`

### W6.2 — README 두 모드 안내
- Local install (한 명령), Cloud install (stub), Mobile 접근 4종 (LAN/Tailscale/CF Tunnel/frp)
- VAPID 키 생성·등록, Push 권한 안내

### W6.3 — CRITIQUE_v0.2 sprint 12~16 항목 update

## Dependency Matrix

```
W1 (Task)
 └─ W2 (Folder, folder_path 필드 사용)
      └─ W3 (Followup, snapshot 데이터 사용)
            └─ W5 (Push, follow-up dispatch에서 발송)
W4 (PWA) — 독립, W2~W5 어디서나 병행 가능
W6 (OSS docs) — 항상 마지막
```

## Phase 3 QA 게이트 (각 Wave 종료 시)

- `python -m unittest discover tests` 모두 통과
- `cd frontend && npm run build` 8+ 페이지 통과 (새 /tasks 추가)
- `git status` 깨끗 (`.pyc` 외)
- commit + push (Conventional Commits, 본 sprint 명시)

## Phase 4 Validation (Wave 6 후 단일 라운드)

- architect: 컴포넌트 경계 + provider 추상화 적절성
- security-reviewer: push subscription·token 누출 점검
- code-reviewer: provider 추상화·tone matrix 가독성

## Phase 5 Cleanup

- `.omc/state/autopilot-state.json` 등 임시 파일 정리
- 최종 commit `chore(autopilot): close v0.4 mobile-followup pipeline`
