# Agent Integrations v1 — G010 산출 요약

**버전**: v1 (G010 산출)
**작성일**: 2026-05-26
**연계**: FINAL_GOAL.md v2.3 §15 Agent Architecture · §11 비목표

---

## 1. 핵심 결정

| 결정 | 내용 |
|---|---|
| **Read-only first** | 모든 tool 기본은 read-only. write 액션 영구 금지 |
| **OAuth 로컬 암호화** | cryptography.fernet (우선) → base64 폴백. 평문 저장 절대 금지 |
| **모든 호출 audit** | ToolInvocation 테이블에 input/output/latency/error 자동 로그 |
| **명시적 동의 단위** | AgentTool.enabled=0 기본, 사용자 동의 후 개별 활성화 |
| **외부 실패 격리** | tool 호출 timeout 3초, 실패해도 시나리오 카드 생성 계속 |

---

## 2. 아키텍처

```
회피 입력
  └─ ToolRouter.route(input_context, user_profile, persona_id)
       ├─ 키워드 분석 (휴리스틱)
       ├─ AgentTool DB 조회 (enabled=1만)
       └─ [GoogleCalendarTool, LocalFilesTool, WebSearchTool]
            └─ 각 tool 병렬 호출 (timeout 3s)
                 ├─ ToolInvocation 자동 로그
                 └─ 결과 → LLM 컨텍스트 주입 → 시나리오 카드 fact/micro_action
```

---

## 3. Tool Router 휴리스틱

키워드 → tool 매핑 (우선순위: 등장 순서):

| 키워드 예 | 선택 Tool |
|---|---|
| 마감 / 시한 / 내일까지 / 일정 | google_calendar.list_events |
| 문서 / PPT / 발표 / 논문 / 파일 | local_files.recent |
| 참고 / 예시 / 검색 / 찾아봐 | web_search.brave |

다중 키워드 시 복수 tool 반환. disabled tool은 제외.

---

## 4. 각 Tool API

### GoogleCalendarTool
```python
tool = GoogleCalendarTool(conn, user_id)
events = tool.list_upcoming_events(days=7)  # → list[dict]
# 필드: id, summary, start, end, description
# 토큰 없으면 []
```

### LocalFilesTool
```python
tool = LocalFilesTool(conn, user_id, watched_dirs=["/path/to/work"])
files = tool.recent_files(category_keyword="PPT", hours=72)  # → list[dict]
# 필드: path, name, size_bytes, modified_at, extension
# 키워드 필터: PPT/발표→.pptx/.key, 논문→.tex/.docx
```

### WebSearchTool
```python
tool = WebSearchTool(conn, user_id)
results = tool.search("query", max_results=3)  # → list[dict]
# 필드: title, url, snippet, rank
# 현재 mock. 실제 API 연동은 향후 라운드.
```

---

## 5. 토큰 암호화

- **우선**: `cryptography.fernet` — 표준 대칭 암호화 (AES-128-CBC + HMAC)
- **폴백**: `base64` — pip 미설치 환경용. 보안 약함. 실 운영 비권장.
- **키 관리**: `TOMORROW_YOU_FERNET_KEY` 환경변수 → `~/.tomorrow_you/fernet.key` 자동 생성

---

## 6. DB 마이그레이션

`db/migrations/004_seed_agent_tools.sql`:
- enabled=1: google_calendar.list_events, local_files.recent, web_search.brave
- enabled=0 (향후): google_calendar.event_detail, local_files.search

---

## 7. 향후 OAuth 흐름 명세 (미구현)

```
1. 사용자가 Calendar 연결 요청
2. 로컬 콜백 서버 127.0.0.1:random_port 시작
3. Google OAuth 2.0 authorize URL 브라우저 오픈
4. 콜백으로 code 수신 → token exchange
5. save_integration(conn, user_id, "google_calendar", access_token, refresh_token, ...)
6. 토큰 Fernet 암호화 → ExternalIntegration BLOB 저장
```

현재 MVP: mock 일정 3개 반환으로 시나리오 카드 생성 검증 가능.

---

## 8. 파일 목록

| 파일 | 역할 |
|---|---|
| `agent/__init__.py` | 모듈 진입점 |
| `agent/router.py` | ToolRouter — 키워드 기반 tool 선택 |
| `agent/integrations.py` | ExternalIntegration CRUD + 토큰 암호화 |
| `agent/tools/__init__.py` | tool 패키지 진입점 |
| `agent/tools/google_calendar.py` | Google Calendar mock 어댑터 |
| `agent/tools/local_files.py` | 로컬 파일 스캔 어댑터 |
| `agent/tools/web_search.py` | 웹 검색 mock 어댑터 |
| `db/migrations/004_seed_agent_tools.sql` | AgentTool 5개 seed |
| `tests/test_agent_tools.py` | 29개 단위 테스트 (29/29 green) |
