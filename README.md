# 내일의 너 (Tomorrow's You)

> 미루기 직전, 미래 자아가 1인칭 시점으로 reality-check해 행동을 멈추게 하는 **로컬-우선 윤리적 행동 변화 PWA**.
> 채팅에서 마감을 말하면 자동 캘린더 등록 → 폴더 감시 → 마감 거리·진척도·자기비난 신호에 따라 톤 자동 follow-up → 잠금 화면 알림.
> OSSCA 2026 멘티 산출물 · Ollama 로컬 LLM · 모든 데이터 사용자 디스크.

```
오늘도 미뤘다.
내일의 너는 알고 있다.
```

---

## 무엇이 다른가

- **자기 보고 + 객관 신호 동시 reality-check** — "거의 다 했어"라고 말해도 폴더 mtime이 어제 그대로면 부드럽게 의심.
- **다중 페르소나 (Character.AI 패러다임)** — 6 default (Quiet·Sharp·Witty·Savage 4 톤 + 1인칭/2인칭/3인칭 perspective) + Custom Builder. 의도 확인·Savage opt-in 가드.
- **Slow Harm 안전 시계열** — 자기 비난 누적 측정 → follow-up 톤 자동 완화·차단.
- **로컬 우선** — Ollama LLM + SQLite + 폴더 직접 접근. 클라우드 백엔드 없음.
- **PWA + 잠금 화면 알림** — 폰 홈 화면 앱처럼. VAPID Web Push 옵션.
- **외부 캘린더 양방향** — ICS feed로 Google Calendar / Apple Calendar 구독 가능.
- **윤리 디자인** — 11+ 안전 메커니즘 (Slow Harm·Moral Licensing·Savage opt-in·Self-Destruct·token 인증·동의 게이트·idempotency).

## Quickstart (Local 모드)

### 1. 의존성

```bash
# Ollama (LLM)
ollama serve &
ollama pull exaone3.5:7.8b

# Backend
pip install --user fastapi uvicorn pydantic cryptography
# (옵션) 잠금 화면 Push 알림
pip install --user pywebpush

# Frontend (1회)
cd frontend && npm install && cd ..
```

### 2. 실행

```bash
# 한 번에:
bash scripts/dev.sh

# 또는 따로:
python -m uvicorn backend.main:app --port 8001          # backend
cd frontend && npm run dev                              # frontend :3000
```

브라우저: **http://localhost:3000**

### 3. (옵션) 잠금 화면 알림 활성화

```bash
# VAPID 키 1회 생성
python scripts/gen_vapid.py
# 출력된 환경변수 세 줄을 backend가 보는 셸에 export 또는 .env에 추가
# NEXT_PUBLIC_VAPID_PUBLIC_KEY 한 줄은 frontend/.env.local에 추가
```

backend 재시작 후 `/settings → 마감 알림 → 켜기` 토글.

## 사용 흐름

1. **PWA 설치** — 폰 Chrome/Safari에서 사이트 접속 → "홈 화면에 추가" → 아이콘.
2. **페르소나 선택** — `/personas` 에서 6 default 중 1 (Savage 톤은 opt-in 확인).
3. **자연어로 마감 등록** — `/chat` 에서 "5월 31일까지 발표자료 만들어야해" → 자동 `Task` 등록 + 캘린더 카드 + `/tasks`/`/calendar` 페이지에서 확인.
4. **폴더 등록** — `/tasks` 카드의 "폴더: 등록하기" → 절대 경로 입력 → backend가 30분 주기로 file_count/mtime 스냅샷.
5. **외부 캘린더 구독** — `/calendar → 외부 캘린더에서 구독` → URL 복사 → Google/Apple에서 URL로 구독.
6. **자동 follow-up** — 마감 D-3부터 chat에 push:
   - 진척 있고 D-3 → 위트 (`오 시작했네 👀`)
   - 진척 없고 D-1 → 직설 (`어제부터 폴더 그대로야`)
   - 진척 없고 D-0 → 단호 (`'거의 다 했어' 같은 말은 안 통해`)
   - Slow Harm `elevated` 누적 시 → Quiet 톤 강제
7. **잠금 화면 알림** (Push 활성화 시) — 같은 메시지가 폰 잠금 화면에 표시 → 탭 시 `/chat` 진입.

## 모바일에서 접근하기

같은 폰 + 같은 머신은 LAN으로 즉시. 외부망은 옵션:

| 옵션 | OSS 정도 | 한 줄 |
|---|---|---|
| **LAN** | 100% | `uvicorn --host 0.0.0.0`로 backend bind → 폰에서 `http://PC_IP:8001` |
| **Tailscale** | 클라이언트 OSS, 컨트롤 SaaS | PC + 폰에 깔면 mesh VPN. 100명 무료. |
| **headscale** + Tailscale 클라이언트 | 100% OSS | 컨트롤 플레인 셀프호스트. |
| **Cloudflare Tunnel** | 클라이언트 OSS, CF 의존 | 도메인 필요. 무료. |
| **frp** | 100% OSS | VPS 1대 필요. 100% 자기 인프라. |

자세한 설정은 [`docs/MOBILE_ACCESS.md`](docs/MOBILE_ACCESS.md).

## 두 모드: Local vs Cloud

이 저장소는 **Local 모드**를 기본으로 동작. Cloud 모드는 provider 추상화(`core/providers/`)에 자리만 마련되어 있으며 desktop agent(`agent_desktop/`)와 Google OAuth는 후속 sprint.

`NAEIL_MODE=local` (기본) · `NAEIL_MODE=cloud` 환경변수 한 줄로 분기. 같은 코드, provider 인스턴스만 다름.

## 디렉토리 구조

```
.
├── db/                          # 14 마이그레이션 + SQLite helper
├── core/providers/              # FolderProvider 추상화 (local·cloud)
├── persona/                     # 6 default + Custom Builder audit
├── probe/                       # HITL Phase routing
├── pipeline/                    # SessionOrchestrator + chat + folder_watch + followup
├── regret/                      # RegretScore + Slow Harm + ratio scheduler
├── agent/                       # ToolRouter + consent + integrations
├── eval/                        # LLM-as-judge framework (judge/repair/runner)
├── ui/                          # TUI 카드 렌더링
├── scripts/                     # CLI, VAPID 생성, dev.sh 등
├── backend/                     # FastAPI app + 13 라우터
│   ├── api/
│   │   ├── users / personas / sessions / regret / safety / tone_feedback
│   │   ├── onboarding / consent / chat / tasks
│   │   ├── calendar (ICS feed 포함) / push_api
│   ├── deps.py                  # require_token + resolve_user_from_token
│   ├── idempotency.py           # POST 중복 방지
│   └── push.py                  # VAPID Web Push helper
├── frontend/                    # Next.js 16 + React 19 + Tailwind v4
│   ├── app/
│   │   ├── manifest.ts          # PWA manifest
│   │   ├── chat/ tasks/ calendar/ settings/ personas/ onboarding/ scenario/
│   ├── components/
│   │   ├── BottomTabs.tsx       # 모바일 4-탭
│   │   └── ServiceWorkerRegister.tsx
│   ├── public/sw.js             # Push handler + offline 캐시
│   └── lib/{auth, api, hooks}/
├── tests/                       # unittest 340+
└── .omc/                        # 설계 문서 + autopilot 산출물
    ├── autopilot/spec.md
    ├── plans/autopilot-impl.md
    └── ultragoal/
        ├── FINAL_GOAL.md
        └── CRITIQUE_v0.2.md
```

## 안전·보안 (요약)

| 메커니즘 | 위치 |
|---|---|
| device token Bearer 인증 (P0-8) | `backend/deps.py` |
| Slow Harm 신호 게이트 (P0-9) | `pipeline/orchestrator.py` |
| 두 얼굴 비율 스케줄러 (P0-11) | `regret/ratio.py` |
| PromptVersion 추적 (P0-12) | `db/schema.py` |
| Fernet PBKDF2 passphrase (P0-14) | `agent/integrations.py` |
| Agent tool 동의 게이트 (P0-15) | `agent/consent.py` |
| Idempotency keys (P0-16) | `backend/idempotency.py` |
| Typography 위계 (P0-19) | `frontend/app/globals.css` |
| Savage opt-in + Custom Builder 의도 (P0-21) | `frontend/app/personas/page.tsx` |
| Moral Licensing 너지 (P0-24) | `pipeline/orchestrator.py` |
| Follow-up tone matrix | `pipeline/followup_tone.py` |

자세한 보안 정책은 [`SECURITY.md`](SECURITY.md).

## 테스트

```bash
NAEIL_DISABLE_WATCH=1 NAEIL_DISABLE_FOLLOWUP=1 python -m unittest discover tests
```

340+ unittest (data model · persona · probe · pipeline · chat · tasks · calendar/ICS · push subscription · folder watch · followup tone · token auth · consent · idempotency · slow harm · ratio · PromptVersion · Fernet key derivation · evaluation framework).

## 비목표

- 클라우드 백엔드 / 회원가입 서버 (Local 모드 기본)
- 자동 외부 액션 (read-only first, P0-15 동의 게이트 필수)
- 게이미피케이션 (streak·뱃지·confetti)
- 수치심 기반 동기

## 라이선스

MIT + **Ethical Use Restriction**. 사용자 취약성을 설득 무기로 변환하는 파생 금지. 자세한 조건은 [`LICENSE`](LICENSE).

## 만든 사람

OSSCA 2026 멘티 — Yeonjae Park (claude@jlkgroup.com)
