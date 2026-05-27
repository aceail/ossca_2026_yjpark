# Security Policy

## 지원 버전

| 버전 | 지원 |
|---|---|
| v0.2.x (현재 main) | ✅ |
| v0.1.x (TUI MVP) | ✅ (보안 패치만) |
| < v0.1 | ❌ |

## 취약성 보고

**공개 issue로 올리지 말고** 다음으로 이메일:

📧 **claude@jlkgroup.com** (yjpark)

제목: `[SECURITY] <간단 요약>`

본문에 포함:
- 영향 받는 버전 + 환경
- 재현 단계
- 잠재 영향 (개인 데이터 유출·취약성 무기화·dual-use 등)
- 가능하면 패치 제안

**응답 SLA**: 72시간 내 1차 확인, 14일 내 패치 계획.

## 우선순위 카테고리

### CRITICAL (24h 응답)
- 사용자 회피·후회 데이터 외부 유출 경로
- OAuth 토큰 평문 노출
- ToolInvocation audit 우회
- Persona Builder audit 우회 → 절대 금지어 출력
- soft_stop / paradoxical_validation 우회

### HIGH
- SQL injection (sqlite3 parametrize 미적용)
- Self-Destruct가 cascade 실패하는 케이스
- Slow Harm 시계열 변조
- frontend XSS (시나리오 카드 본문 렌더링)

### MEDIUM
- CORS 설정 오류
- API rate limit 부재 (사용자 1명 환경에선 낮음)
- 로깅에 개인 정보 누출

### LOW (보고 환영)
- 의존성 outdated
- 문서 모순

## 책임 있는 공개 (Responsible Disclosure)

1. 우리가 패치 배포할 때까지 비공개
2. 패치 PR + 보안 권고문 동시 공개
3. 보고자 credit (원치 않으면 익명)
4. CVE 신청 (해당하는 경우)

## 윤리 라이선스 위반 신고

기술 취약성과 별개로, **dual-use 라이선스 위반** (사용자 취약성 무기화·게이미피케이션 추가·취약 사용자 대상 강한 톤 적용 등):

- 메인테이너 이메일 + 위반 사례 링크
- 위반 fork·repo는 공개 designation 가능 (LICENSE §)

## 알려진 한계 (v0.2)

- `agent/tools/google_calendar.py`는 mock — 실 OAuth는 v0.3에서 토큰 관리 가이드 추가 예정
- `regret/fingerprint.py` embedding은 hash 기반 — sentence-transformers 도입 시 사용자 데이터가 외부 모델에 전달되지 않도록 로컬 추론만 허용 예정
- Ollama 서버 인증 없음 — 로컬 1인용 가정. 멀티 사용자 환경 배포 금지.

## 외부 의존성 보안

- Ollama (LLM) — 로컬 호스팅, 외부 통신 X (모델 다운로드 제외)
- SQLite — stdlib, WAL 모드
- FastAPI · uvicorn · pydantic — PyPI 안정 버전
- Next.js · React · Tailwind — npm 안정 버전
- cryptography (Fernet) — OAuth 토큰 암호화

업데이트 정책: `pip list --outdated` + `npm outdated` 분기별 점검.
