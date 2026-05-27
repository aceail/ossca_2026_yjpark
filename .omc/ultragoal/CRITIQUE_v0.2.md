# CRITIQUE v0.2 — 자기 비판 보고서

**작성일**: 2026-05-27
**기준 commit**: `937467e` (v0.2 ship)
**방법**: CCG (Claude-Codex-Gemini) blind-spot 라운드 — 두 외부 advisor에게 sycophantic praise 금지·진짜 문제만 짚도록 요청
**원본 합성 파일**:
- `.omc/artifacts/ask/codex-tomorrow-s-you-v0-2-ossca-2026-ollama-llm-1-python-11-db-17--2026-05-27T00-33-20-336Z.md`
- `.omc/artifacts/ask/gemini-ux-tomorrow-s-you-v0-2-ossca-2026-ollama-llm-1-ux-noto-serif-2026-05-27T00-31-01-270Z.md`

---

## 0. Meta — 가장 무거운 한 줄

두 advisor 합의:

> **"안전한 미루기 개입 도구"라는 핵심 주장이 (a) 구현이 증명 못하고 (평가 vs 런타임 분리, Slow Harm 미연결, soft_stop 렌더링 깨짐), (b) 도구 사용 자체가 회피 정당화로 변질될 수 있는 메커니즘이 곳곳에 박혀 있다 (Custom Builder 채팅 놀이화, Moral Licensing).**

v0.2를 "출시"라 부른 건 잘못된 표현 — 현재는 **v0.2 prototype + 24 식별된 결함 (P0 11개 + 추가 13)**.

## 1. P0 — 즉시 수정 (양쪽 advisor 일치)

| # | 결함 | 출처 |
|---|---|---|
| P0-1 | "ㅈㅅ" 페르소나 이름 — 한국어 "죄송/자살" 약어 | Gemini |
| P0-2 | "Self-Destruct" 용어 — 자해 메타포, 우상단 상시 노출 | Gemini |
| P0-3 | "내일의 너가" 한국어 맞춤법 오류 ("내일의 네가" 맞음) | Gemini |
| P0-4 | timeline_hint가 백엔드에서 무시됨 — 평가 vs 런타임 불일치 | Codex `backend/api/sessions.py:118` |
| P0-5 | 1인칭 화법 강제 vs 5 default 페르소나 중 3개가 2nd/3rd | Codex `persona/builder.py:130` |
| P0-6 | soft_stop 렌더링 깨짐 — backend `safety_message` ↔ frontend `card.fact` | Codex schema mismatch |
| P0-7 | Fake UNDO — 복원 API 없는데 UI에 노출 | Codex + Gemini |
| P0-8 | API 인증 0 — uvicorn `0.0.0.0` + user_id만 알면 조작 가능 | Codex |
| P0-9 | Slow Harm 정책 vs 코드 분리 — 카드 생성 직전 호출 X | Codex |
| P0-10 | 평가 통과율 3/30의 진짜 의미 — "스타일 실패 X, 개입 메커니즘 실패" | Codex |
| P0-11 | 미래 자아 두 얼굴 비율 미구현 — regret:recovery 스케줄러 0 | Codex |

## 2. Codex 단독 P0 — 시스템·아키텍처

12. 프롬프트의 3중 진실원 (평가/런타임/문서) — `PromptVersion` 테이블 미사용
13. PersonaInfo schema mismatch — backend 누락 vs frontend 사용
14. Fernet key 저장 위치 + base64 fallback — CWE-312 / CWE-522
15. 프롬프트 인젝션 경계 열림 — agent router keyword substring, AgentTool enabled=1
16. SQLite + sync Ollama + request-path WAL — 세션 1000건 또는 동시 탭 3개에서 무너짐

## 3. Gemini 단독 P0 — UX·심리

17. 첫 카피 "어젯밤 내가 무엇을 하고 있었는지" — CCTV식, 사용자 수치심 ↑ 강화
18. 명도 #A05A5A WCAG 미달 (3.3:1, 기준 4.5:1)
19. Typography 위계 전도 — Serif(사실) ↔ Sans(감정) 일반 관습 반대
20. 객관 옵저버 👁️ 아이콘 = 감시 메타포
21. Custom Builder 채팅 놀이화 — 듣고 싶은 말만 해주는 페르소나 만들기
22. micro_copy 종결어미 충돌 — Sharp/Quiet vs "기록됐어요. 내일도 와줘요." 친절체
23. 톤 피드백 옵션 모호 — "부모 같다"의 한국적 중의성 → 학습 신호 오염
24. **Moral Licensing 위험** — 앱 사용 자체가 면죄부 → "정교한 회피 보조제"로 변질

## 4. 처리 계획 (v0.2.1 + v0.3 분리)

### v0.2.1 즉시 fix (현재 라운드)
**Cheap (1-2h)**:
- [x] P0-1 페르소나 이름 → "ㅈㅅ" 제거
- [x] P0-2 Self-Destruct → "흔적 지우기"
- [x] P0-3 "너가" → "네가" (시나리오 프롬프트·카피 검수)
- [x] P0-18 명도 색 교체
- [x] P0-17 첫 카피 톤 완화
- [x] P0-22 micro_copy 통일

**Mid (3-6h)**:
- [x] P0-4 timeline_hint 마이그레이션 005 + 사용
- [x] P0-5 페르소나 평가 perspective별 분기
- [x] P0-6 soft_stop 렌더링 수정
- [x] P0-7 Fake UNDO → 정직 처리 (UNDO 텍스트 제거 또는 실 복원)
- [x] P0-13 PersonaInfo schema 완성

### v0.3 sprint 1 (closed 2026-05-27)
**Safety gates — generate-time enforcement**:
- [x] P0-9 Slow Harm 시계열을 generate 직전 호출 → `compute_signal_level` 등급화 + high→soft_stop, elevated→`ELEVATED_TONE_PREFIX` 주입
- [x] P0-24 Moral Licensing — 24h 사용 세션 ≥ 5건이면 `moral_licensing_nudge` 응답 필드 + 카드 상단 부드러운 자기참조 배너
- [x] SafetyTrend API `signal_level` 필드 추가 (frontend 타입과 동기)

### v0.3 sprint 2 (closed 2026-05-27)
**Two-face balance scheduler**:
- [x] P0-11 `regret/ratio.py` `recommend_card_type` + `build_ratio_hint` → 최근 5 카드 중 한쪽 ≥0.7이면 반대 유형 권장 hint를 `system_prompt`에 주입. soft_stop/paradox는 분모에서 제외.
- [x] 설계 결정: ratio hint와 `elevated` 신호는 함께 적용 (high만 soft_stop 강제로 차단). `failure_imagery_ratio`가 ratio skew와 동치이므로 elevated와 ratio hint를 분리하면 hint가 영영 적용되지 않는다.

### v0.3 sprint 3 (closed 2026-05-27)
**UX safety gates**:
- [x] P0-21 Savage opt-in — `personas/page.tsx`에서 빌트인 Savage 활성화 / Custom Builder Savage 톤 제출 시 confirm dialog ("자해 사고나 깊은 우울감이 있다면 권하지 않아요"). Builder 톤 셀렉터 아래 inline 경고 라인.
- [x] P0-21 Custom Builder 의도 확인 — "왜 이 페르소나를 만드세요?" textarea (200자, client-side only). 비어있을 시 부드러운 confirm — 페르소나 자체가 또 다른 미루기 대상이 되는지 점검 가능.

### v0.3 본격 (다음 라운드)
**Complex**:
- P0-8 API 인증 (간단 디바이스 토큰 + Authorization 헤더)
- P0-10 평가 baseline 재정의 (3중 진실원 통합, repair loop 추가)
- P0-12 PromptVersion → 실 사용
- P0-14 Fernet key OS keychain 또는 PBKDF2
- P0-15 agent tool 활성화 사용자 명시 동의 게이트
- P0-16 작업 큐 + idempotency
- P0-19 Typography 위계 재검토 (Serif/Sans 역할 교환 또는 단일 fontfamily)

## 5. OSSCA 멘토 제출 전 필수 게이트

- [ ] **자기 비판 능력 증명**: 본 CRITIQUE 게시 (실행 중)
- [ ] v0.2.1 cheap+mid fix 완료 후 commit
- [ ] 평가 baseline 재검토 — "G002는 모델 한계 정량화이지 baseline 확정 X" 문서 수정
- [ ] README에 한계 명시 추가 — 평가 통과율 3/30 솔직 게시
- [ ] v0.3 로드맵 P0 처리 일정 제시
- [ ] 1명 실 사용자 2주 피드백 진행 (최소 사용자 본인)

## 6. 답변 못 한 가장 무거운 질문

> **"이거 진짜 누가 써?"**

현재 우리 답: "시뮬레이션 결과는 좋습니다."
Gemini: **"리서치 관점에서 넌센스"**.

해결 경로: 본인 2주 사용 → 후회 점수·정확도·return intent 데이터 → 정직한 retention 그래프 게시. 거짓 좋은 결과 X.
