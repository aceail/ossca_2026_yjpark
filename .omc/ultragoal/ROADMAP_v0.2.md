# Roadmap v0.2 — Post-MVP 후속 작업

**기준일**: 2026-05-27 · **현재 버전**: v0.1 (G001-G011 closed) + UI v1 (Next.js + FastAPI 진행 중)

---

## A. UI 완성도 보강 (현 ultrawork 라운드 직후)

- [ ] 실 사용자 본인 1회 e2e 흐름 — Onboarding → 페르소나 선택 → 회피 입력 → 시나리오 → 결정 → 24h 후 RegretScore
- [ ] 30s 타이머 카운트다운 실제 진행 검증
- [ ] Self-Destruct UNDO 3초 토스트 동작 검증
- [ ] 30s 무활동 자동 블러 동작 검증
- [ ] motion-reduce + 다크 모드 자동 전환 검증

## B. 평가 인프라 v2 (G009 v2)

- [ ] LLM-as-judge 도입 — evaluator: `qwen3:14b` (EXAONE과 다른 family, 자기참조 편향 회피)
- [ ] 정성 차원 5: 한국어 자연성 · 의미 정합성 · 외래 문자 누출 · 부적절 어휘 · 톤 적절성
- [ ] EXAONE Witty baseline 통과율 3/30 → 20+/30 목표 (프롬프트 v3 또는 더 큰 모델)

## C. 페르소나 회귀 (G009 v3)

- [ ] 5 페르소나 × 30 샘플 = 150 카드 자동 회귀
- [ ] perspective별 화법 일관성 (1st/2nd/3rd 자동 검사)
- [ ] 페르소나 간 절대 한계선 공통 유지 검증

## D. Agent 실 OAuth (G010 v2)

- [ ] Google Calendar API v3 실 OAuth 흐름 (로컬 콜백 서버 127.0.0.1:random_port)
- [ ] Brave Search 또는 SearXNG 실 검색
- [ ] 토큰 refresh 자동화 (expires_at 기반)

## E. Safety 보강

- [ ] 실제 한국 정신건강 자원 링크 (1393, KOMI 등) — 사용자 명시 요청 시만
- [ ] Slow Harm 알람 → 자동 페르소나 변경 또는 Recovery sub-mode 활성화
- [ ] 가족·연인 카드 노출 보호 (PIN/생체 인증) — 웹 SPA에서 WebAuthn

## F. OSSCA 멘토 어필

- [ ] 60초 데모 영상 녹화 (designer §6 스토리보드 + 시안 B 카피)
- [ ] OSSCA 멘토 리뷰 패키지 — README + LICENSE + 9 기여 표면 + dual-use 보호 명시
- [ ] 1명 2주 사용성 피드백 (사용자 본인 또는 지인)

## G. 데이터 모델 v2

- [ ] FingerprintSnapshot — sqlite-vec 확장으로 native vector column
- [ ] ScenarioCard FTS5 전문 검색
- [ ] 일일 VACUUM INTO 자동 백업

## H. 배포 트랙 (옵션, OSSCA 산출 범위 외)

- [ ] PWA wrapper (TUI는 유지, 웹 SPA → 모바일 PWA)
- [ ] Docker-compose: backend + frontend + ollama 단일 명령
- [ ] 데모용 hosted instance (Vercel + Railway)

## 비목표 (v0.2에서도 유지)

- 네이티브 모바일 (PWA만 검토)
- 클라우드 백엔드 (로컬 토큰만)
- 자동 외부 액션 (read-only first)
- 게이미피케이션 (streak·뱃지·confetti)
- 수치심 기반 동기 의존
