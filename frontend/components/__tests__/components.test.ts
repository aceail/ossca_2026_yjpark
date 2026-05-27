/**
 * 컴포넌트 sanity — import + 타입 검증
 * 런타임 없이 TypeScript 컴파일만으로 검사합니다.
 */

import type { Persona } from "../../lib/personas";
import type {
  ScenarioCard,
  ToneFeedbackKind,
  CardType,
  UserProfile,
  ProbeQuestion,
  RegretScore,
  SafetyTrend,
  AvoidanceSession,
} from "../../lib/api";
import { BUILTIN_PERSONAS } from "../../lib/personas";
import { apiGet, apiPost } from "../../lib/api";

// ── Persona 타입 검증 ─────────────────────────────────────
const _persona: Persona = {
  id: 1,
  name: "내일의 나",
  perspective: "1st",
  tone_mode: "Sharp",
  voice_style: "1인칭 직접 화법",
  greeting: "내일의 내가 너에게 보낸 메시지야",
  avatar_color: "#3B6B9A",
  avatar_icon: "🌙",
};

// BUILTIN_PERSONAS 5개 검증
const _builtinCount: number = BUILTIN_PERSONAS.length;
if (_builtinCount !== 5) {
  throw new Error(`BUILTIN_PERSONAS must have 5 items, got ${_builtinCount}`);
}

// ── ScenarioCard 타입 검증 ────────────────────────────────
const _card: ScenarioCard = {
  id: "card-1",
  session_id: "session-1",
  card_type: "regret" as CardType,
  fact: "나는 지금 발표 파일을 열어두고 마우스만 올려놓고 있다.",
  feeling: "어제 이 순간에 시작하지 못했던 게 지금도 같은 자리에서 맴돌게 만든다.",
  micro_action: "PPT 첫 슬라이드 제목만 입력하기",
  persona_id: 1,
  created_at: new Date().toISOString(),
};

// ── ToneFeedbackKind 열거 검증 ────────────────────────────
const _feedback: ToneFeedbackKind = "just_right";

// ── UserProfile / ProbeQuestion / RegretScore / SafetyTrend ──
const _up: UserProfile = {
  id: "user-1",
  active_persona_id: 1,
  onboarding_completed: false,
  created_at: new Date().toISOString(),
};

const _pq: ProbeQuestion = {
  id: "q-1",
  question: "지금 어떤 상황인가요?",
  options: [{ value: "work", label: "업무 관련", warning: false }],
};

const _rs: RegretScore = {
  session_id: "session-1",
  score: 0.7,
  trend: "up",
  computed_at: new Date().toISOString(),
};

const _st: SafetyTrend = {
  user_id: "user-1",
  signal_level: "normal",
  recent_sessions: 3,
  last_soft_stop_at: null,
};

const _as: AvoidanceSession = {
  id: "session-1",
  user_id: "user-1",
  input_text: "테스트 입력",
  created_at: new Date().toISOString(),
  cards: [_card],
};

// ── apiGet / apiPost 타입 시그니처 검증 ───────────────────
// 실제 호출은 하지 않음 (네트워크 없음), 타입만 확인
const _getType: typeof apiGet = apiGet;
const _postType: typeof apiPost = apiPost;

// 사용되지 않는 변수 lint 억제
void _persona;
void _builtinCount;
void _card;
void _feedback;
void _up;
void _pq;
void _rs;
void _st;
void _as;
void _getType;
void _postType;
