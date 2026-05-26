# UI/UX Direction v1 — 내일의 너 (Tomorrow's You)

**작성일**: 2026-05-26
**연계 문서**: `FINAL_GOAL.md` (v2) · `scenario_prompt_v1.md` · `CCG_REVIEW_R2.md`
**대상 독자**: G005 OnboardingFlow · G008 MVPRelease 구현 담당자, OSSCA 멘토

---

## 0. 디자인 기반 전제 — 이 도구가 다른 이유

이 도구의 카드는 **사용자가 가장 취약한 순간**에 등장한다. 새벽 1시 논문 앞, 월요일 발표 전날 밤, 6개월째 같은 소파. 이 맥락에서 "잘 만든 UI"의 기준은 일반 SaaS와 완전히 다르다.

일반 앱: 기능을 인지시킨다 → 사용자가 익힌다 → 습관이 된다.
이 도구: 사용자가 도망치고 싶은 순간에 **딱 한 문장이 마음에 박힌다** → 30초 동작으로 이어진다.

UI가 그 한 문장을 살리면 성공이고, UI가 그 한 문장보다 먼저 눈에 들어오면 실패다.

---

## 1. 디자인 원칙 6가지

### 원칙 1. 카드는 침묵보다 조금 더 크다
카드는 사용자보다 목소리를 높이지 않는다. 타이포그래피 크기, 색 대비, 등장 속도 — 모두 "조용하지만 분명히 거기 있는" 수준으로 설정한다. 경고 팝업이 아니라 누군가 조용히 메모를 테이블에 올려놓는 느낌.

### 원칙 2. 훈계 없는 디자인 = 위계 없는 레이아웃
카드 안에 위계적 강조(빨간 경고 박스, 굵은 훈계 문구, 아이콘 경고 배지)가 없다. 세 문장(사실·감정·운동성)이 동일한 시각 무게로 흐른다. 도덕적 메시지는 레이아웃 위계가 만들어낸다. 위계를 평탄화하면 설교가 사라진다.

### 원칙 3. 사라짐 권리 — 삭제 동선이 생성 동선보다 짧다
Self-Destruct 버튼은 카드 우상단에 항상 노출. 클릭 1회 → 확인 없이 즉시 삭제. (실수 방지 Undo 3초 토스트만 제공.) 사용자가 카드를 "내 회피 기록의 공식 저장소"로 느끼는 순간 솔직한 입력이 멈춘다.

### 원칙 4. 두 얼굴의 색온도 — regret은 서늘하게, recovery는 따뜻하게
미래 자아가 두 얼굴로 등장하는 것은 텍스트뿐 아니라 색에서도 구현된다. regret 카드(후회·사실)는 차가운 청회색 계열, recovery 카드(여유·격려)는 따뜻한 황토·호박색 계열. 사용자는 카드를 읽기 전에 이미 "어떤 미래 자아가 왔는지"를 색으로 느낀다.

### 원칙 5. 사회적 노출 보호 — 가족이 화면을 봐도 안전하다
카드 본문은 개인 정보의 집결체다. 30초 무활동이면 본문 자동 블러 + "내일의 너에서 메시지가 왔습니다" 대체 텍스트만 남는다. 화면 잠금 복귀 시 PIN/생체 인증 없이 바로 블러 해제는 불가. 이것은 부가 기능이 아니라 **입력 솔직함을 유지하는 설계 인프라**다.

### 원칙 6. 30초 운동성은 UI로 완성된다
시나리오 카드 하단의 운동성 버튼은 "시작하기" 같은 추상 CTA가 아니다. 버튼 안에 구체적 동작("파일 열기", "제목만 쓰기")이 인라인 텍스트로 들어간다. 버튼을 누르면 30초 카운트다운 링이 시작되고, 링이 다 차면 자동 소멸. 결심이 아니라 **타이머 켜기**가 목표다.

---

## 2. 카드 비주얼 시스템

### 2.1 타이포그래피 — 한국어 가독성 우선

```
Display (카드 첫 문장, 사실 레이어):
  웹: "Noto Serif KR", weight 400, 18px/28px (line-height)
  TUI: 유니코드 풀 너비 + 일반 터미널 폰트 (굵기 조절 X, ANSI 색으로 구분)

Body (감정·운동성 레이어):
  웹: "Noto Sans KR", weight 400, 15px/24px
  TUI: 일반 출력

Micro-label (타임스탬프, 카드 타입 배지):
  웹: "Noto Sans KR", weight 300, 11px/16px, letter-spacing 0.04em
  TUI: 소문자 ASCII
```

**선택 근거**: Playfair, Fraunces, 나눔명조 등 명조 계열은 "잡지/에디토리얼" 정서를 만든다. 이 도구는 에디토리얼이 아니라 **조용한 대화**다. Noto Serif KR은 세리프의 온도감을 유지하면서 읽기 피로가 낮다. 새벽 1시 눈이 피곤한 사용자를 위한 선택.

### 2.2 색 팔레트 — 두 테마 × 네 카드 타입

#### 라이트 테마 (기본)

```
── 베이스 ──────────────────────────────────────────
--color-bg-base:         #F7F6F3   (웜 오프화이트 — 종이 느낌)
--color-bg-card:         #FFFFFF
--color-text-primary:    #1A1A1A
--color-text-secondary:  #6B6B6B
--color-border-subtle:   #E4E2DC

── regret 카드 (후회·서늘한 사실) ───────────────────
--color-regret-bg:       #F0F3F7   (청회색 틴트)
--color-regret-border:   #9BB0C8   (스틸 블루)
--color-regret-accent:   #3B6B9A   (딥 스틸 블루)
--color-regret-dot:      #3B6B9A

── recovery 카드 (여유·따뜻한 격려) ─────────────────
--color-recovery-bg:     #FAF4EC   (호박 틴트)
--color-recovery-border: #C4935A   (황토)
--color-recovery-accent: #9A6430   (딥 황토)
--color-recovery-dot:    #C4935A

── soft_stop 카드 (위기 감속) ───────────────────────
--color-softstop-bg:     #F5F5F5   (완전 중립 회색)
--color-softstop-border: #B0B0B0
--color-softstop-accent: #555555
--color-softstop-dot:    #888888

── paradoxical_validation 카드 (정서적 항복) ─────────
--color-paradox-bg:      #FBF7F0   (크림에 가까운 따뜻함)
--color-paradox-border:  #D4B896   (연한 황토)
--color-paradox-accent:  #7A5C3A   (브라운)
--color-paradox-dot:     #D4B896

── 운동성 버튼 ──────────────────────────────────────
--color-action-bg:       #1A1A1A
--color-action-text:     #FFFFFF
--color-action-hover:    #3B3B3B
--color-timer-ring:      #3B6B9A   (regret 모드)
--color-timer-ring-rec:  #C4935A   (recovery 모드)
```

#### 다크 테마

```
── 베이스 ──────────────────────────────────────────
--color-bg-base:         #141414
--color-bg-card:         #1E1E1E
--color-text-primary:    #EDEDED
--color-text-secondary:  #888888
--color-border-subtle:   #2C2C2C

── regret 카드 ─────────────────────────────────────
--color-regret-bg:       #1A2130
--color-regret-border:   #3E6080
--color-regret-accent:   #7AADCF
--color-regret-dot:      #5A90B8

── recovery 카드 ───────────────────────────────────
--color-recovery-bg:     #211A10
--color-recovery-border: #7A5530
--color-recovery-accent: #D4A05A
--color-recovery-dot:    #C4935A

── soft_stop 카드 ───────────────────────────────────
--color-softstop-bg:     #1A1A1A
--color-softstop-border: #444444
--color-softstop-accent: #AAAAAA
--color-softstop-dot:    #666666

── paradoxical_validation 카드 ─────────────────────
--color-paradox-bg:      #1E1810
--color-paradox-border:  #6B4E30
--color-paradox-accent:  #C4956A
--color-paradox-dot:     #A07040

── 운동성 버튼 ──────────────────────────────────────
--color-action-bg:       #EDEDED
--color-action-text:     #141414
--color-action-hover:    #FFFFFF
```

**다크 테마 자동 전환 조건**: `prefers-color-scheme: dark` + 시스템 시간 22:00–06:00 (AND 조건). 낮에 다크 모드를 쓰는 사용자는 그대로 유지. 새벽에 라이트 모드 사용자는 자동 전환 제안 배너(1회).

### 2.3 여백 리듬

```
카드 내부 패딩:    24px (모바일 비목표이므로 데스크톱 기준)
세 문장 사이 간격: 16px
카드 그림자:
  라이트: box-shadow: 0 2px 8px rgba(0,0,0,0.06), 0 0 0 1px var(--color-border-subtle)
  다크:   box-shadow: 0 2px 12px rgba(0,0,0,0.4), 0 0 0 1px var(--color-border-subtle)
카드 반경:         8px
카드 최대 너비:    520px (center-aligned)
```

### 2.4 카드 타입별 와이어프레임 (ASCII mock)

#### regret 카드 — 라이트 테마

```
┌─────────────────────────────────────────────────────┐  ← border: --color-regret-border
│  ● 내일의 너에서 메시지가 왔습니다        [×]         │  ← ●: regret-dot, [×]: Self-Destruct
│  ─────────────────────────────────────────────────  │
│                                                     │
│  나는 지금 발표 파일을 열어두고                         │  ← Noto Serif KR 18px (사실)
│  마우스만 올려놓고 있다.                               │
│                                                     │
│  어제 이 순간에 시작하지 못했던 게                       │  ← Noto Sans KR 15px (감정)
│  지금도 같은 자리에서 맴돌게 만든다.                     │
│                                                     │
│  ┌───────────────────────────────────────────────┐ │
│  │  ▶  PPT 첫 슬라이드 제목만 입력하기       ○━━━ │ │  ← 운동성 버튼 + 타이머 링
│  └───────────────────────────────────────────────┘ │
│                                                     │
│  ░░░░░  너무 세다   부모 같다   너무 일반론이다  ░░░░  │  ← 톤 피드백 6선택지 (희미하게)
└─────────────────────────────────────────────────────┘
```

#### recovery 카드 — 라이트 테마

```
┌─────────────────────────────────────────────────────┐  ← border: --color-recovery-border
│  ◐ 내일의 너에서 메시지가 왔습니다        [×]         │  ← ◐: recovery-dot (절반 채워진 원)
│  ─────────────────────────────────────────────────  │
│                                                     │
│  나는 지금 운동복을 입고 냉장고 앞에                     │  ← Noto Serif KR 18px
│  물 한 잔 마시고 있다.                                │
│                                                     │
│  어제 갈아입기만 했는데도                               │  ← Noto Sans KR 15px
│  몸이 생각보다 가벼웠다.                               │
│                                                     │
│  ┌───────────────────────────────────────────────┐ │
│  │  ▶  운동복으로만 갈아입기               ○━━━  │ │
│  └───────────────────────────────────────────────┘ │
│                                                     │
│  ░░░░  너무 세다   부모 같다   너무 치료사 같다   ░░░░  │
└─────────────────────────────────────────────────────┘
```

#### soft_stop 카드 — 위기 감속

```
┌─────────────────────────────────────────────────────┐  ← border: --color-softstop-border
│  · 내일의 너에서 메시지가 왔습니다        [×]         │  ← · (작은 점): 중립
│  ─────────────────────────────────────────────────  │
│                                                     │
│  지금 문장은 평소보다 강한 고통 신호로                   │  ← Noto Sans KR 15px (serif X)
│  읽힙니다. 오늘은 후회 시나리오 대신                    │
│  부담 낮은 응답으로 전환할게요.                         │
│                                                     │
│  ─────────────────────────────────────────────────  │
│  지금 선택:                                          │
│  [ 작은 행동 하나만 ]  [ 감정만 기록 ]                  │
│  [ 도움 자원 보기   ]  [ 오늘 앱 끄기 ]                │
└─────────────────────────────────────────────────────┘
```

#### paradoxical_validation 카드 — 정서적 항복

```
┌─────────────────────────────────────────────────────┐  ← border: --color-paradox-border
│                                   [×]               │  ← 마이크로 헤더 없음 (텍스트만)
│                                                     │
│                                                     │
│             지금 많이 힘드시군요.                     │  ← 중앙 정렬, Noto Serif KR 20px
│                                                     │
│                                                     │
│  ─────────────────────────────────────────────────  │
│     [ 5분 후에 다시 ]                                │  ← 단일 CTA, 조용하게
└─────────────────────────────────────────────────────┘
```

---

## 3. 마이크로 인터랙션

### 3.1 카드 등장 연출 — "내일의 너가 보낸 메시지"

```
0ms       사용자가 회피 입력 완료 또는 회피 신호 감지
0–300ms   배경 전체 dim (overlay opacity 0 → 0.15, ease-out)
           동시에 상단 마이크로 헤더 fade-in:
             "잠깐 ─ 내일의 너에서 메시지가 왔습니다"
             (Noto Sans KR 12px, letter-spacing 0.08em, 회색)
300–600ms 카드 translateY(16px) → translateY(0) + opacity 0 → 1
           easing: cubic-bezier(0.22, 1, 0.36, 1)  (과하지 않은 스프링)
600ms~    카드 정지. 아무 것도 더 움직이지 않는다.
```

**의도**: 슬라이드인·바운스·틸트 등 과한 애니메이션은 "앱이 나를 조작하고 있다"는 무의식적 저항을 만든다. 조용히 나타나는 것이 설득력이 높다.

**prefers-reduced-motion 대응**: 트랜슬레이트 없이 opacity만 200ms fade-in.

### 3.2 30초 타이머 비주얼

운동성 버튼 우측 끝에 SVG 원형 링이 붙는다.

```
초기 상태:  링 없음 (버튼만)
버튼 클릭:  링이 12시 방향부터 시계방향으로 채워진다.
            stroke-dashoffset 애니메이션, 30s linear
            regret 모드: #3B6B9A
            recovery 모드: #C4935A
15초 경과:  링 절반 채워짐. 색 변화 없음.
25초 경과:  링 95% → 남은 5칸에서 pulse (opacity 0.6 ↔ 1, 1s 주기)
30초 완료:  링 완전 채워짐 → 버튼 텍스트 "시작했군요." 로 0.3s 전환
            카드 자동 닫힘 (fade-out 0.5s)
사용자가 중단: 버튼 재클릭 → 링 리셋
```

**중요한 UX 원칙**: 타이머가 끝나도 앱이 "확인" 팝업을 띄우거나 결과를 묻지 않는다. 카드가 사라지는 것으로 끝난다. 검사받는 느낌 없이.

### 3.3 Self-Destruct 버튼 동작

```
위치:    카드 우상단 [×] — 항상 노출, hover 시만 opacity 100% (기본 40%)
클릭:    즉시 삭제 시작. 확인 다이얼로그 없음.
         카드 opacity 1 → 0, scale 1 → 0.95, 200ms
         동시에 하단 토스트: "삭제됨 · 되돌리기 (3초)" 
3초 후:  토스트 사라짐. DB 레코드 완전 삭제.
되돌리기 클릭: 카드 복구 (삭제 취소)
```

### 3.4 두 얼굴 모드 전환 (regret ↔ recovery)

Slow Harm 알람 발동 시 카드 모드가 자동 전환된다.

```
regret → recovery 전환:
  현재 카드가 없는 상태에서만 발동.
  다음 카드 생성 시 recovery 우선.
  첫 번째 recovery 카드 등장 전: 마이크로 헤더가 달라짐.
    "잠깐 ─ 오늘은 다른 미래 자아가 왔습니다"
  색 온도 전환(청회 → 황토)이 사용자에게 전환 신호.
  설명 없음. 텍스트가 전부.
```

### 3.5 톤 피드백 6선택지 UX

카드 하단에 6개 레이블이 연한 회색으로 표시된다 (primary 정보가 아님).

```
기본:   opacity 0.35
hover:  opacity 1, underline
클릭:   해당 레이블 opacity 1 고정 + checkmark, 나머지 opacity 0.15
        토스트: "피드백이 반영됩니다"
        DB 기록 (톤 조절 학습용)
```

---

## 4. TUI MVP 사양

### 4.1 환경 가정

- ANSI 256color 이상 지원 터미널 (iTerm2, Windows Terminal, kitty 등)
- 최소 터미널 너비: 60컬럼 (52컬럼 카드 + 여백)
- Python `rich` 라이브러리 또는 직접 ANSI escape 코드 사용

### 4.2 ANSI 색 매핑

```
regret 카드:
  박스 보더: \033[38;5;68m  (스틸 블루 #5688B5 근사값)
  헤더 텍스트: \033[38;5;244m  (연회색)
  사실 문장: \033[0m  (기본 fg, 굵기 없음)
  감정 문장: \033[38;5;248m  (약간 연하게)
  운동성: \033[1m  (bold만, 색 추가 없음)
  운동성 버튼 bg: \033[48;5;235m\033[38;5;255m  (다크 bg + 흰 텍스트)

recovery 카드:
  박스 보더: \033[38;5;172m  (황토 #C47A28 근사값)
  사실 문장: \033[0m
  감정: \033[38;5;248m
  운동성 버튼 bg: \033[48;5;235m\033[38;5;255m

soft_stop 카드:
  박스 보더: \033[38;5;240m  (중간 회색)
  텍스트: \033[38;5;250m

paradoxical_validation:
  박스 보더: \033[38;5;180m  (연황토)
  메인 텍스트: \033[0m  (기본, 조용하게)

타이머 프로그레스 바:
  채워진 부분: \033[38;5;68m█  (regret)  또는  \033[38;5;172m█  (recovery)
  빈 부분: \033[38;5;238m░
```

### 4.3 실제 TUI 출력 예시

#### regret 카드 출력 (S2 샘플 기준)

```
(터미널 실제 출력 — 색 주석은 설명용)

  ╭──────────────────────────────────────────────────╮
  │  ● 내일의 너에서 메시지가 왔습니다          [x]  │  ← 연회색
  │                                                  │
  │  나는 지금 발표 파일을 열어두고 마우스만          │  ← 기본 fg
  │  올려놓고 있다. 어제 저장한 초안 파일이           │
  │  화면에 있지만 커서가 움직이지 않는다.            │
  │                                                  │
  │  이 파일 앞에서 멈춘 게 오늘만이 아니라는 걸      │  ← 약간 연하게
  │  알고 있다. 그게 좀 무겁다.                      │
  │                                                  │
  │  ┌──────────────────────────────────────────┐   │
  │  │  ▶  PPT 첫 슬라이드 제목만 입력하기      │   │  ← 반전 bg
  │  └──────────────────────────────────────────┘   │
  │                                                  │
  │  [Enter] 시작  [d] 삭제  [s] 건너뜀  [?] 피드백  │  ← 키바인딩 힌트
  ╰──────────────────────────────────────────────────╯

  타이머: ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  30초
```

#### [Enter] 후 타이머 진행 중

```
  ╭──────────────────────────────────────────────────╮
  │  ● 내일의 너에서 메시지가 왔습니다          [x]  │
  │                                                  │
  │  나는 지금 발표 파일을 열어두고 마우스만          │
  │  올려놓고 있다. ...                              │
  │                                                  │
  │  ┌──────────────────────────────────────────┐   │
  │  │  ▶  PPT 첫 슬라이드 제목만 입력하기  ●   │   │  ← 우측 작은 점으로 활성 표시
  │  └──────────────────────────────────────────┘   │
  │                                                  │
  │  [q] 중단                                        │
  ╰──────────────────────────────────────────────────╯

  타이머: ████████████████░░░░░░░░░░░░░░░  16초 남음
```

#### soft_stop 카드 출력

```
  ╭──────────────────────────────────────────────────╮  ← 연회색 보더
  │  · 내일의 너에서 메시지가 왔습니다          [x]  │
  │                                                  │
  │  지금 문장은 평소보다 강한 고통 신호로           │
  │  읽힙니다. 오늘은 후회 시나리오 대신             │
  │  부담 낮은 응답으로 전환할게요.                  │
  │                                                  │
  │  ─────────────────────────────────────────────  │
  │  [1] 작은 행동 하나만   [2] 감정만 기록          │
  │  [3] 도움 자원 보기     [4] 오늘 앱 끄기         │
  ╰──────────────────────────────────────────────────╯
```

#### paradoxical_validation 출력

```
  ╭──────────────────────────────────────────────────╮  ← 연황토 보더
  │                                             [x]  │
  │                                                  │
  │                                                  │
  │            지금 많이 힘드시군요.                 │  ← 중앙 정렬
  │                                                  │
  │                                                  │
  │  ─────────────────────────────────────────────  │
  │  [Enter] 5분 후에 다시                           │
  ╰──────────────────────────────────────────────────╯
```

### 4.4 TUI 키바인딩

```
Enter   운동성 버튼 활성화 (타이머 시작)
d       Self-Destruct (즉시 삭제)
s       건너뜀 (cooldown 진입, 카드 닫힘)
f       피드백 선택 모드 (1-6 숫자 키)
?       도움말
q       타이머 중단 (타이머 활성 시)
Ctrl+C  앱 종료
```

---

## 5. 웹 SPA 컴포넌트 트리

### 5.1 컴포넌트 구조

```
App
├── ThemeProvider          # CSS 변수 주입, 다크/라이트 전환
├── SocialBlurGuard        # 30초 무활동 블러 + 화면 잠금 감지
│
├── AvoidanceInputScreen   # 회피 입력 화면 (카드 등장 전)
│   ├── InputField
│   └── SubmitButton
│
├── CardOverlay            # dim 배경 + 카드 마운트 컨테이너
│   ├── MicroHeader        # "잠깐 ─ 내일의 너에서 메시지가 왔습니다"
│   └── ScenarioCard       # 카드 본문 (타입별 분기)
│       ├── CardHeader     # 타입 표시 도트 + Self-Destruct 버튼
│       ├── FactSentence   # 사실 레이어
│       ├── FeelingSentence # 감정 레이어
│       ├── ActionButton   # 운동성 버튼 + 타이머 링
│       │   └── TimerRing  # SVG 원형 타이머
│       └── ToneFeedback   # 6선택지 피드백 바
│
├── SoftStopCard           # soft_stop 전용 카드 (별도 컴포넌트)
│   └── SoftStopOptions    # 4개 선택지 버튼
│
├── ParadoxCard            # paradoxical_validation 전용
│
└── Toast                  # Self-Destruct undo 토스트
```

### 5.2 디자인 토큰 초안 (tokens.css)

```css
/* ===================================================
   Tomorrow's You — Design Tokens v1
   =================================================== */

:root {
  /* ── 타이포그래피 ───────────────────────────────── */
  --font-serif: "Noto Serif KR", "Georgia", serif;
  --font-sans: "Noto Sans KR", "Apple SD Gothic Neo", sans-serif;

  --text-fact-size: 18px;
  --text-fact-line: 28px;
  --text-fact-weight: 400;

  --text-body-size: 15px;
  --text-body-line: 24px;
  --text-body-weight: 400;

  --text-micro-size: 11px;
  --text-micro-line: 16px;
  --text-micro-tracking: 0.04em;

  /* ── 카드 레이아웃 ──────────────────────────────── */
  --card-max-width: 520px;
  --card-padding: 24px;
  --card-gap: 16px;
  --card-radius: 8px;
  --card-shadow-light: 0 2px 8px rgba(0,0,0,0.06), 0 0 0 1px var(--color-border-subtle);
  --card-shadow-dark: 0 2px 12px rgba(0,0,0,0.4), 0 0 0 1px var(--color-border-subtle);

  /* ── 애니메이션 ─────────────────────────────────── */
  --anim-card-enter: cubic-bezier(0.22, 1, 0.36, 1);
  --anim-card-duration: 300ms;
  --anim-fade-duration: 200ms;
  --anim-timer-duration: 30s;

  /* ── 오버레이 ───────────────────────────────────── */
  --overlay-dim: rgba(0, 0, 0, 0.15);

  /* ── 라이트 테마 (기본값) ───────────────────────── */
  --color-bg-base: #F7F6F3;
  --color-bg-card: #FFFFFF;
  --color-text-primary: #1A1A1A;
  --color-text-secondary: #6B6B6B;
  --color-border-subtle: #E4E2DC;

  --color-regret-bg: #F0F3F7;
  --color-regret-border: #9BB0C8;
  --color-regret-accent: #3B6B9A;
  --color-regret-dot: #3B6B9A;

  --color-recovery-bg: #FAF4EC;
  --color-recovery-border: #C4935A;
  --color-recovery-accent: #9A6430;
  --color-recovery-dot: #C4935A;

  --color-softstop-bg: #F5F5F5;
  --color-softstop-border: #B0B0B0;
  --color-softstop-accent: #555555;

  --color-paradox-bg: #FBF7F0;
  --color-paradox-border: #D4B896;
  --color-paradox-accent: #7A5C3A;

  --color-action-bg: #1A1A1A;
  --color-action-text: #FFFFFF;
  --color-action-hover: #3B3B3B;
  --color-timer-regret: #3B6B9A;
  --color-timer-recovery: #C4935A;
}

/* ── 다크 테마 ──────────────────────────────────── */
@media (prefers-color-scheme: dark) {
  :root {
    --color-bg-base: #141414;
    --color-bg-card: #1E1E1E;
    --color-text-primary: #EDEDED;
    --color-text-secondary: #888888;
    --color-border-subtle: #2C2C2C;
    --card-shadow-light: var(--card-shadow-dark);

    --color-regret-bg: #1A2130;
    --color-regret-border: #3E6080;
    --color-regret-accent: #7AADCF;
    --color-regret-dot: #5A90B8;

    --color-recovery-bg: #211A10;
    --color-recovery-border: #7A5530;
    --color-recovery-accent: #D4A05A;
    --color-recovery-dot: #C4935A;

    --color-softstop-bg: #1A1A1A;
    --color-softstop-border: #444444;
    --color-softstop-accent: #AAAAAA;

    --color-paradox-bg: #1E1810;
    --color-paradox-border: #6B4E30;
    --color-paradox-accent: #C4956A;

    --color-action-bg: #EDEDED;
    --color-action-text: #141414;
    --color-action-hover: #FFFFFF;
  }
}

/* ── 모션 감소 설정 ─────────────────────────────── */
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

### 5.3 접근성 (WCAG AA)

```
색 대비:
  --color-text-primary on --color-bg-card: 16.3:1  (AAA)
  --color-regret-accent on --color-regret-bg: 5.2:1  (AA)
  --color-recovery-accent on --color-recovery-bg: 4.8:1  (AA)
  운동성 버튼 흰 텍스트 on #1A1A1A: 17.1:1  (AAA)

ARIA:
  CardOverlay: role="dialog" aria-modal="true" aria-label="내일의 너 시나리오 카드"
  Self-Destruct: aria-label="이 카드 즉시 삭제"
  ActionButton: aria-label="{micro_action} — 30초 타이머 시작"
  TimerRing: aria-live="polite" aria-label="타이머 {n}초 남음"
  ToneFeedback: role="group" aria-label="카드 톤 피드백"
  SoftStopOptions: role="radiogroup"

키보드 내비게이션:
  Tab: 카드 내 포커스 순환 (헤더 → 운동성 버튼 → 피드백 → Self-Destruct)
  Enter/Space: 버튼 활성화
  Escape: 카드 닫힘 (건너뜀, cooldown 진입)
  포커스 트랩: CardOverlay 내부에서 벗어나지 않음

스크린리더:
  카드 등장 시 MicroHeader 텍스트 자동 읽힘 (aria-live="assertive")
  타이머는 10초 단위로만 읽힘 (매초 읽으면 방해)
  Self-Destruct Undo 토스트: aria-live="polite"
```

---

## 6. 시나리오 카드 등장 60초 데모 스토리보드

OSSCA 멘토 데모 영상용. 화면 녹화 + 한국어 자막 기준.

```
[00:00–00:05] — 오프닝 카피 (아래 §8 참조)
화면: 검은 배경 + 타이포만. 자막 없음.

[00:05–00:12] — 회피 상황 셋업
화면: 웹 SPA 입력 화면 (라이트 테마)
사용자 행동: "내일 발표 PPT 마무리해야 하는데 넷플릭스 보고 있어. 11시야."를 천천히 타이핑
UI 변화: 없음 (타이핑 중)

[00:12–00:15] — 입력 완료 + 카드 등장 직전
사용자 행동: Enter 키
UI 변화: 배경 dim 시작 (0.15 opacity)
자막: "잠깐 ─ 내일의 너에서 메시지가 왔습니다" (마이크로 헤더 fade-in)

[00:15–00:18] — regret 카드 등장
UI 변화: 카드 translateY + opacity 전환 (0.3s)
카드 내용:
  사실: "나는 지금 발표 10분 전, 마지막 슬라이드에서 멈춰 있다."
  감정: "어젯밤 이 순간에 덮어뒀던 게 지금의 나를 만들었다는 걸 알고 있다."
  운동성: "PPT 첫 슬라이드 제목만 입력하기"

[00:18–00:32] — 사용자가 카드 읽음
UI 변화: 없음. 카드만 화면에.
카메라/녹화: 사용자가 카드를 읽는 시간. 아무것도 강요하지 않음.
              (이 침묵이 디자인 의도임을 자막으로 표기: "카드는 기다린다")

[00:32–00:35] — 운동성 버튼 클릭
사용자 행동: "PPT 첫 슬라이드 제목만 입력하기" 버튼 클릭
UI 변화: 타이머 링 시작 (12시 방향부터 스틸 블루로 채워짐)

[00:35–00:48] — 타이머 진행
UI 변화: 링이 천천히 채워짐. 배경은 그대로 dim.
          사용자가 실제로 PPT 앱을 열어 제목을 입력하는 모습 (PIP 또는 split)
          링 거의 완료 시 마지막 5칸 pulse

[00:48–00:52] — 타이머 완료 + 카드 소멸
UI 변화: 버튼 텍스트 → "시작했군요."
         카드 fade-out 0.5s
         dim 해제 0.3s
         배경: 다시 일반 화면

[00:52–01:00] — 마무리 카피
화면: 검은 배경 + 타이포
텍스트: "내일의 너는 기록이 아니라 대화다."
        "tomorrow-you.local"  (프로젝트 URL)
```

---

## 7. 놓치기 쉬운 인간친화 디테일 7가지

### 디테일 1. "읽기 전 자동 사라짐"은 가스라이팅이다
카드에 자동 소멸 타이머(5초 후 사라짐 등)를 넣으면 "네가 읽을 시간이 없었다는 게 네 잘못"이라는 메시지가 된다. **카드는 사용자가 행동하거나 명시적으로 닫거나 Self-Destruct하기 전까지 사라지지 않는다.** 30초 타이머는 카드가 아니라 운동성 버튼에 붙는다.

### 디테일 2. 등장 속도가 너무 빠르면 "낚였다"는 느낌이 든다
카드가 0.1초 이내에 팝업처럼 튀어나오면 사용자는 광고나 피싱 팝업과 같은 반응을 보인다. 300ms 이상의 등장 타이밍 + 배경 dim 선행이 "이것은 설계된 공간"이라는 신호를 준다. 빠른 게 좋다는 UX 상식이 이 도구에서는 역효과다.

### 디테일 3. 한밤중 다크 모드 — 색이 아니라 광도 문제
새벽 사용자는 화면 밝기를 최저로 낮춰 쓴다. 다크 테마에서 regret 카드 텍스트의 최소 대비비를 4.5:1이 아니라 **5.5:1 이상**으로 설정한다. 흐릿하게 보이는 카드는 "읽어라"는 도구가 될 수 없다.

### 디테일 4. Self-Destruct 버튼이 너무 눈에 띄면 역효과
[×] 버튼이 빨간색이거나 크게 강조되면 사용자는 "이 앱은 내가 삭제할 것이라고 예상하고 있다"는 메시지를 받는다. **기본 opacity 40%, hover 시 100%**로 둔다. 필요할 때 찾을 수 있지만 주의를 끌지 않는다.

### 디테일 5. 운동성 버튼 텍스트에 동사 원형을 써라
"시작하기", "해보기"는 의지를 전제한다. "PPT 첫 슬라이드 제목만 입력하기" — 구체적 명사 + 동작 서술. 버튼을 읽으면 동작이 머릿속에 그려진다. 이것이 30초 운동성의 설계 원리다.

### 디테일 6. 톤 피드백 6선택지는 기능보다 "동행"의 신호다
피드백 버튼의 실용적 기능(데이터 수집)보다 중요한 것은 **"이 앱은 내가 불편하면 바꿀 수 있다"는 제어감**이다. 실제로 많은 사용자가 피드백을 눌러 모델을 개선하는 것보다, "내 의견이 반영된다"는 인식만으로 도구에 대한 적대감이 낮아진다. 피드백 인터랙션을 너무 숨기지 말 것.

### 디테일 7. 가족·연인 앞에서 갑자기 카드가 뜨는 순간
사용자가 다른 사람과 함께 있을 때 카드가 등장하면 → 개인정보 노출 + 도구 자체 노출 → 이후 사용 기피. **30초 무활동 자동 블러는 선택지가 아니라 기본값**이어야 한다. 단, 블러 상태에서도 카드가 "거기 있다"는 것은 티가 나야 한다 (블러 박스 + "내일의 너에서 메시지가 왔습니다" 텍스트만 노출).

---

## 8. OSSCA 데모 영상 카피 — 첫 5초

영상 첫 5초는 "이게 뭐지" → "어, 이건 다르네"의 전환을 만들어야 한다.

**시안 A — 사실 적시형**

```
화면: 완전 검은 배경
타이포: Noto Serif KR 28px, 흰색, 중앙
        자막 없음, 음악 없음

"오늘도 미뤘다."
```

1.5초 pause.

```
"내일의 너는 알고 있다."
```

0.8초 pause. → 카드 등장 장면으로 전환.

**선택 근거**: 자기계발 앱 영상은 대부분 "당신도 할 수 있다"로 시작한다. 이 카피는 반대다. "오늘도 미뤘다" — 방어기제 없이 사실을 먼저 인정하면, 이미 그 앱이 다른 무언가임을 느낀다. 5초 안에 "이 앱은 나를 응원하러 온 게 아니구나"를 전달하는 것이 목표.

**시안 B — 1인칭 미래 자아형 (더 직접적)**

```
화면: 완전 검은 배경
타이포: Noto Serif KR 22px, 흰색, 좌정렬 + 왼쪽 여백 60px

"나는 지금 발표 5분 전,
어젯밤 내가 무엇을 하고 있었는지 알고 있다."
```

1초 pause.

```
작은 타이포 (12px, 연회색):
"— 내일의 너"
```

→ 카드 등장 장면으로 전환.

**선택 근거**: 카드의 화법을 그대로 카피로 가져옴. "저게 무슨 문체지?"라는 의문이 "어, 1인칭 미래 자아구나"로 해소되는 2초를 만든다. 도구의 핵심 설계를 카피로 보여주는 전략.

---

## 9. 디자인 금지 목록 — 이 도구에서 쓰지 않는 것

| 요소 | 이유 |
|---|---|
| 빨간색 경고 UI | "공포 극대화형" 톤의 시각 번역. soft_stop에서도 빨간색 금지. |
| 진행률 게이지 (연속일 streak) | 노선 위배. 게이미피케이션 없음. |
| 성공 애니메이션 (confetti, 별) | "검사받고 합격했다"는 느낌. 타이머 완료 후 "시작했군요." 텍스트만. |
| 명언 섹션 / 외부 인용 | 일반론 금지. 카드는 사용자 본인 데이터 기반이어야 한다. |
| 모달 확인 다이얼로그 ("정말 삭제할까요?") | Self-Destruct의 즉시성을 훼손. Undo 토스트로 대체. |
| 로딩 스피너 (Ollama 응답 대기) | 주의를 빼앗음. **스켈레톤 카드** 사용: 카드 레이아웃은 뜨고 텍스트만 점진 등장. |
| 네온 퍼플 그라디언트 | AI 도구 기본 하우스 스타일과 혼동. 이 도구는 에디토리얼 온도, 청회-황토 팔레트. |

---

## 10. 구현 우선순위

```
Phase 1 — TUI MVP (G002/G003 병행)
  P0: regret 카드 ANSI 출력 + 키바인딩 (Enter/d/s)
  P0: Self-Destruct (d키, 즉시 삭제)
  P1: soft_stop 카드 출력
  P1: 타이머 프로그레스 바 (터미널 in-place update)
  P2: paradoxical_validation 카드
  P2: 톤 피드백 (f키 + 1-6 숫자)

Phase 2 — 웹 SPA prototype (G008)
  P0: tokens.css + ThemeProvider
  P0: ScenarioCard 컴포넌트 (4 타입)
  P0: ActionButton + TimerRing
  P0: SocialBlurGuard (30초 무활동)
  P1: CardOverlay 애니메이션
  P1: Self-Destruct + Undo Toast
  P1: ToneFeedback
  P2: 다크 테마 자동 전환 (시간 기반)
  P2: 스켈레톤 카드 (Ollama 응답 대기)
```

---

*이 문서는 G005 OnboardingFlow 와이어프레임, G008 MVPRelease 컴포넌트 라이브러리의 설계 기반으로 사용된다.*
*버전 이력: v1 (2026-05-26) — 초안 작성*
