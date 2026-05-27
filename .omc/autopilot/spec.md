# Autopilot Spec — "내일의 너" Local-first Mobile Reality-Check Agent

**상태:** Phase 0 (Expansion) complete · 2026-05-27

## 1. 컨셉 한 줄

> 미래의 내가 현재의 나에게 마감·진척·자기보고를 객관 신호(폴더 mtime, 파일 수)와 함께 reality-check 해주는 로컬-우선 PWA. 모바일에서 잠금 화면 알림으로 follow-up. OpenClaw 패턴 차용, 자체 안전 게이트 위에 얹음.

## 2. 사용자 흐름

```
1. 사용자 채팅: "나 5/31까지 발표자료 다 만들어야해"
2. LLM이 자연어 파싱 → {action: create_task, title: 발표자료, deadline: 2026-05-31}
3. backend가 Task INSERT → chat에 "✅ 5/31 발표자료 캘린더에 박았어. 폴더 알려줄래?"
4. 사용자 응답: "/Users/yj/Docs/2026Q2_발표"
5. backend `Task.folder_path` 업데이트 → FolderWatcher가 30분마다 mtime/file_count 스캔
6. 마감 D-3: chat 자동 push "오 시작했네 👀 / 한 줄만 보여줘"
7. 마감 D-1 + 폴더 멈춤: 폰 잠금 화면 push "내일 마감인데 어제부터 폴더 그대로야"
8. 사용자: "거의 다 했어" + 폴더 mtime 어제 이전 → "야 폴더 어제 멈춰있는데?"
9. 마감 통과 + done 신호 → 회고 카드 + 통계 누적
```

## 3. 비목표 (이번 autopilot 범위 밖)

- Cloud 모드 / 멀티 사용자 (Sprint 17+)
- Google Calendar 실 OAuth (Sprint 17+)
- 외부망 접근 — LAN 가정 (Tailscale/CF Tunnel은 README 안내만)
- 네이티브 모바일 앱 — PWA만
- OpenClaw 직접 통합 — 패턴만 차용 (B 옵션, 사용자 합의)
- Hermes 모델 교체 — EXAONE 유지, function-calling은 JSON action 패턴

## 4. 핵심 컴포넌트

### 4.1 데이터 모델 (DB)

```sql
Task(id, user_id, title, deadline_at, folder_path?, persona_id?,
     status: open|done|abandoned, created_at, last_followup_at)

FolderSnapshot(id, task_id, taken_at, file_count, total_bytes,
               newest_mtime, files_json)

PushSubscription(id, user_id, endpoint, p256dh, auth, created_at)
```

기존 `ChatSession`/`ChatMessage` (Sprint 11)와 결합 — task 등록·follow-up이 chat을 통해 흐름.

### 4.2 Provider 추상화 (core/providers)

| Provider | Local 구현 | Cloud 구현 (Sprint 17+) |
|---|---|---|
| LLMProvider | OllamaProvider | OllamaRemote / Anthropic / OpenAI |
| FolderProvider | LocalFolderProvider (os.scandir) | RemoteAgentFolderProvider |
| CalendarProvider | LocalIcsProvider | GoogleCalendarProvider |
| PushProvider | WebPushVapidProvider | (동일, VAPID 키만 다름) |

`get_providers()` 팩토리가 `NAEIL_MODE` 환경변수로 분기.

### 4.3 자연어 → Task 추출

기존 `pipeline/chat.py`의 system_prompt에 다음 prefix 추가:
```
사용자 메시지에서 작업·마감을 발견하면 다음 형식의 JSON action을 응답에 포함:
{"speak": "...", "actions": [{"type": "create_task", "title": "...", "deadline": "YYYY-MM-DD"}]}
actions 없으면 그냥 평문 응답.
```

backend `post_user_message`가 응답 JSON 파싱 → actions 실행 → 결과를 `speak` 텍스트에 자동 prefix.

### 4.4 FolderWatcher

`pipeline/folder_watch.py`:
- APScheduler (또는 자체 asyncio task) 30분 주기
- 각 `Task.folder_path != NULL` 순회 → `LocalFolderProvider.snapshot()` → INSERT `FolderSnapshot`
- 새 스냅샷과 직전 비교 → 진척 변화 산출

### 4.5 Follow-up Scheduler

`pipeline/followup.py`:
- 매시간 cron: 모든 open task에 대해 다음 follow-up 시각 계산
  - D-3: 매일 1회, 부드러운 톤
  - D-1: 매 6시간, 직접적 톤
  - D-0: 매 2시간, 단호한 톤
  - Slow Harm `elevated`/`high`: 강도 자동 한 단계 완화
- 시각 도래 시: chat 자동 push (assistant 메시지로 INSERT) + push 알림 발송 (VAPID)

### 4.6 PWA 변환

- `frontend/app/manifest.ts` (Next.js 16 file convention)
- `frontend/public/icon-{192,512}.png` (단순 흑백 ⌛ 글리프)
- `frontend/public/sw.js` (service worker — offline 캐시 + push 수신)
- viewport meta + 모바일 하단 탭 바 컴포넌트

### 4.7 Push 알림 (Web Push / VAPID)

- 신규 의존: `pywebpush` (Python OSS) 또는 stdlib + ECDSA 수동 — 단순화 위해 `pywebpush` 사용 가능. 미설치 환경 대비 graceful fallback.
- backend env: `NAEIL_VAPID_PUBLIC_KEY`, `NAEIL_VAPID_PRIVATE_KEY`
- frontend service worker: `pushManager.subscribe()` → backend `POST /api/push/subscriptions`
- follow-up scheduler가 push 발송

## 5. 안전 게이트 (기존 유지)

- Slow Harm `compute_signal_level` → follow-up 톤 자동 완화
- Moral Licensing 너지: 24h 내 5 chat 세션 이상 → 부드러운 자기참조
- Task done 처리 시 Self-Destruct cascade는 옵션 (UI 토글)

## 6. OSS 정렬 산출물

- README 두 모드 install 가이드 (Local 본격, Cloud는 stub)
- `docker/local.compose.yml` (ollama + backend + frontend)
- LICENSE dual-use 조항 유지
- VAPID 키 생성 스크립트 (`scripts/gen_vapid.py`)
- 외부 의존성 (Tailscale, CF Tunnel)은 docs/MOBILE_ACCESS.md에 안내만

## 7. 비기능 요구

- 모든 새 endpoint는 device token 게이트 (P0-8 패턴)
- 모든 새 DB 마이그레이션은 backward compat
- 새 코드 ≥ 80% 커버리지 (단위·통합)
- frontend `npm run build` clean (현 8/8 페이지 + 새 /chat, /tasks)

## 8. 성공 기준 (Done = )

- [ ] chat에서 "나 5/31까지 발표자료" 한 줄 → DB에 `Task` 레코드 생성
- [ ] `/tasks` 페이지에서 task 목록 + 마감 진척도 표시
- [ ] 폴더 등록 → 30분 후 FolderSnapshot 1개 이상 누적
- [ ] PWA install — 모바일 홈 화면 아이콘 + standalone 모드
- [ ] Web Push — backend `scripts/test_push.py` 가 폰 잠금 화면에 알림 발송
- [ ] 모든 회귀 테스트 통과 + frontend build OK
- [ ] README에 두 모드 install 가이드 + 모바일 접근 옵션 4종 안내
