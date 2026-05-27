# Manual E2E 시연 (본인 사용)

`tests/test_e2e_flow.py`가 자동으로 검증하는 흐름을 본인이 브라우저·터미널로 직접 따라할 때 가이드. 멘토 시연·본인 retention 데이터 수집 시작점.

## 0. 의존성

```bash
ollama serve &
ollama pull exaone3.5:7.8b
pip install --user fastapi uvicorn pydantic cryptography
cd frontend && npm install && cd ..
```

## 1. backend·frontend 띄우기

터미널 두 개:

```bash
# A 터미널: backend
NAEIL_WATCH_INTERVAL_MIN=1 python -m uvicorn backend.main:app --host 0.0.0.0 --port 8001
#                       ^^ 1분 간격 폴더 스캔으로 빠른 검증

# B 터미널: frontend
cd frontend && npm run dev
```

브라우저: <http://localhost:3000>. (시크릿 모드 또는 localStorage 클리어 권장 — token 새로 발급)

## 2. 7단계 시연

| # | 화면 | 입력 |
|---|---|---|
| 1 | `/onboarding` | 5단계 그냥 채우기 (Witty 페르소나 추천) |
| 2 | `/chat` | "5월 31일까지 발표자료 만들어야해" |
| 3 | assistant 응답에 `✅ '발표자료' 마감 2026-05-31 캘린더에 박았어` 확인 |
| 4 | `/tasks` | 카드 1개 등록 확인. 마감일·D-N 표시 |
| 5 | `/chat` 으로 돌아가 | "발표자료 폴더는 /tmp/naeil-demo 야" (먼저 그 폴더 만들기) |
| 6 | 1분 후 | 그 폴더에 파일 추가. `/tasks` 진척 확인 |
| 7 | `/calendar` | 월 그리드에 발표자료 표시. "외부 캘린더 구독" URL 복사해 Google Calendar에 붙이기 |

## 3. 폴더 진척 확인

`/tmp/naeil-demo`에 파일 한 개 만들고 1분+ 기다림. backend 로그에 watch 호출 보임. 그 후 `/tasks` 카드 다시 보면 변동 반영.

`GET /api/tasks/{id}/snapshots` 직접 호출도 OK:

```bash
TOKEN=<localStorage에서 device_token 복사>
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8001/api/tasks/1/snapshots | jq
```

## 4. 자연어 status 변경

`/chat` 에서 한 줄:

- `"발표자료 다 했어"` → status=done, `/tasks` open 목록에서 사라짐
- `"발표자료 다시 시작"` → status=open
- `"발표자료 마감 6월 15일로 바꿔"` → deadline 갱신

## 5. (옵션) 잠금 화면 알림

```bash
python scripts/gen_vapid.py  # 3 줄 환경변수 출력
# backend가 보는 셸에 export, NEXT_PUBLIC_VAPID_PUBLIC_KEY는 frontend/.env.local
pip install --user pywebpush
# backend·frontend 재기동
```

`/settings → 마감 알림 → 켜기`. 폰 잠금 화면에서 알림 받으려면 PWA install 필수 (Chrome → "홈 화면에 추가").

## 6. (옵션) 외부 캘린더 구독

`/calendar → 외부 캘린더에서 구독 → URL 복사`. Google Calendar 좌측 "다른 캘린더 +" → "URL로 구독" → 붙여넣기. 우리 task가 Google에 read-only로 나타남.

Apple Calendar: 파일 → 새로운 캘린더 구독 → URL.

## 7. 회귀 자가 검증

```bash
NAEIL_DISABLE_WATCH=1 NAEIL_DISABLE_FOLLOWUP=1 python -m unittest discover tests
```

356 OK 확인 후 본격 사용 시작 — 본인 2주 데이터가 OSSCA 멘토 어필의 진실성.
