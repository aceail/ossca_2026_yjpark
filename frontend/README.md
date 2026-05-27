# 내일의 너 — Frontend 컴포넌트 라이브러리

## 구조

```
components/   재사용 컴포넌트 (ScenarioCard, PersonaCard, ...)
lib/          타입 정의 + API 클라이언트 (personas.ts, api.ts)
app/          Next.js App Router 페이지 (별도 agent 담당)
```

## Wave 2 페이지 agent를 위한 import 예시

```tsx
// 페르소나 선택 화면
import { PersonaCard } from "@/components";
import { BUILTIN_PERSONAS } from "@/lib/personas";

export default function SelectPersonaPage() {
  return BUILTIN_PERSONAS.map((p, i) => (
    <PersonaCard key={i} persona={{ ...p, id: i + 1 }} onSelect={console.log} />
  ));
}
```

```tsx
// 시나리오 카드 + 블러 가드
import { ScenarioCard, SocialBlurGuard, UndoToast } from "@/components";
import type { ScenarioCard as CardData } from "@/lib/api";

export default function CardPage({ card, persona }) {
  return (
    <SocialBlurGuard>
      <ScenarioCard card={card} persona={persona} onDestroy={() => {}} />
    </SocialBlurGuard>
  );
}
```

## 디자인 토큰

`app/globals.css` `@theme` 블록에 정의. CSS 변수로 직접 참조 가능:

- `var(--color-regret-accent)` — 청회색 강조
- `var(--color-recovery-accent)` — 황토 강조
- `var(--font-fact)` — Noto Serif KR (사실 레이어)
- `var(--font-feeling)` — Noto Sans KR (감정·본문)

## 금지 사항 (§9)

빨간 경고 UI · streak/badge · confetti · 네온 그라디언트 사용 금지.
