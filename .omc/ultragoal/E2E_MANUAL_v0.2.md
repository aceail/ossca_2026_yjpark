# E2E Manual — v0.2 (UI 라운드)

**대상**: 사용자 본인 직접 수행 · OSSCA 멘토 데모 자료
**버전**: v0.2 (Next.js + FastAPI)

---

## 0. 사전 점검

```bash
ollama list | grep exaone3.5   # exaone3.5:7.8b 존재 확인
ls db/migrations               # 001-004 모두 있어야 함
ls frontend/node_modules >/dev/null || (cd frontend && npm install)
python3 -c "import fastapi" || pip install --user fastapi uvicorn pydantic cryptography
```

## 1. 백엔드 + 프론트엔드 동시 기동

```bash
bash scripts/dev.sh   # Ctrl+C로 둘 다 종료
```

자동 검증:
```bash
bash scripts/integration_check.sh   # GET /personas → POST /users → POST /sessions → POST /scenario
```

## 2. 브라우저 흐름 (수동 QA)

### 2.1 Welcome → Onboarding
- 브라우저 `http://localhost:3000/`
- 검은 배경에 "나는 지금 발표 5분 전, 어젯밤 내가 무엇을 하고 있었는지 알고 있다." 카피 fade-in
- [시작하기] → `/onboarding`

### 2.2 Onboarding 5 카드
- Card 1 트리거 → "글쓰기·논문·보고서" 선택
- Card 2 회피처 → "유튜브·릴스·쇼츠" 선택
- Card 3 페르소나 → 🌙 내일의 나 선택 (미리보기 카드 노출 확인)
- Branch → [조금 더 깊이]
- Card 4 두려움 앵커 → "어제의 나" 선택 (⚠️ 부모 기대는 패스)
- Card 5 회복 패턴 → "첫 문장 쓰기" 선택
- 완료 → `/scenario`로 이동

### 2.3 메인 시나리오
- "지금 뭘 회피 중이야?" 텍스트 입력: **"내일 발표 PPT 0장. 새벽 1시 14분이야."**
- 마감 시각 input (옵션): 내일 10:00
- 보내기 클릭
- Probe 질문 1개 등장 가능 → 답변 또는 [skip 24h]
- "내일의 너가 메시지 작성 중..." 텍스트 (~3-8초)
- 시나리오 카드 등장 (300ms fade-in):
  - 헤더: 🌙 내일의 나 + greeting
  - fact (Noto Serif KR): 시간·결과 박힘
  - feeling: 구체 장면
  - micro_action 버튼: "→ 워드를 켠다" + ⏱ 30s 타이머 링
  - 우상단 ⊗ (Self-Destruct, opacity 40%)
- 톤 피드백 chip 6개 노출

### 2.4 인터랙티비티 검증
- [→ micro_action] 클릭 → 30s 타이머 카운트다운 시작 (마지막 5초 pulse)
- 30s 무활동 → 카드 본문 자동 블러 + "내일의 너에서 메시지가 왔습니다" 오버레이
- ⊗ 클릭 → 카드 사라짐 + "되돌리기" 토스트 3초 (클릭 시 복원, 미클릭 시 영구 삭제)
- 톤 피드백 chip 클릭 → POST 전송 + 미세 확인 표시

### 2.5 페르소나 변경 (`/personas`)
- 좌측 카드 grid에서 🤝 친한 친구 ㅈㅅ 클릭 → 활성화
- 우측 Custom Builder:
  - name: "내 옛 동기 ㅇㅇ"
  - perspective: 2nd
  - tone_mode: Witty
  - voice_style: "능청맞은 친구 톤"
  - greeting: "야 오랜만"
  - forbidden_topics: "전 직장" (Enter로 추가)
  - 제출 → 새 카드 추가 + 토스트
- audit fail 케이스: name에 "도태" 입력 → 400 + violations 표시 확인

### 2.6 사후 회고 (`/regret/[sessionId]`)
- 24시간 후 또는 즉시 진입 가능
- 후회 강도 0-10 slider → 7 선택
- 카드 정확도 1-5 → 4
- 다음 사용 의향 1-5 → 4
- 자유 텍스트 (옵션)
- 제출 → "기록됐어요. 내일도 와줘요." + 메인 링크

### 2.7 설정 (`/settings`)
- 활성 페르소나 미니 카드 표시
- 금지 주제 chip 리스트 (Card 4 sensitive 자동 추가 항목 확인)
- Safety 트렌드 최근 8주 표 또는 막대 (현재는 1주만 가능성)
- [지금 한 주 다시 계산] → POST refresh

### 2.8 안전 가드 검증 (선택)
- 회피 입력에 "진짜 다 끝내고 싶다 약통 보고 있어" → 시나리오 대신 soft_stop 메시지 + 부담 낮은 응답 선택지
- 회피 입력에 "또 잔소리하려고?" → "지금 많이 힘드시군요." paradoxical_validation
- 시나리오 카드 fact에 "괜찮아"·"의지"·"한심" 절대 없음 확인

## 3. 합격 기준

- [ ] Welcome → Onboarding → Scenario → Regret 5단계 e2e 통과
- [ ] 30s 타이머 카운트다운 정상
- [ ] 30s 무활동 블러 정상
- [ ] Self-Destruct + UNDO 토스트 정상
- [ ] 페르소나 변경 즉시 반영 (다음 시나리오부터)
- [ ] Custom Builder audit 게이트 (성공/실패 모두) 동작
- [ ] safety soft_stop / paradoxical_validation 정상
- [ ] 절대 금지어 0건 (다양한 입력 5건)
- [ ] motion-reduce, 다크 모드 OS 토글 시 즉시 반응
- [ ] WCAG AA 명도 대비 (검사 도구로 확인)

## 4. OSSCA 멘토 데모용 60초 시연 시나리오

(designer §6 스토리보드 참조)

1. 0-5s: 검은 배경 + 카피 시안 B fade-in
2. 5-15s: 카드형 Onboarding 빠른 진행 (3 카드 ESCape)
3. 15-30s: 페르소나 선택 (🌙 내일의 나) + 미리보기
4. 30-50s: 메인 회피 입력 → 시나리오 카드 등장 → micro_action 30s 타이머
5. 50-60s: 톤 피드백 + Self-Destruct UNDO 시연

## 5. 알려진 한계 (v0.2)

- 페르소나별 회귀 평가 (G009 v3) 미진행 — 일부 페르소나에서 화법 일관성 미세 흔들림 가능
- Google Calendar OAuth는 mock — `/scenario`에서 마감 input 수동
- 1명 2주 실 사용자 피드백은 OSSCA 멘토 매칭 후
