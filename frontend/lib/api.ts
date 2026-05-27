const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8001";

// ── 타입 정의 ────────────────────────────────────────────

export type CardType =
  | "regret"
  | "recovery"
  | "soft_stop"
  | "paradoxical_validation";

export type ToneFeedbackKind =
  | "too_harsh"
  | "too_parental"
  | "too_generic"
  | "too_therapeutic"
  | "not_relevant"
  | "just_right";

export interface PersonaInfo {
  id?: number;
  name: string;
  perspective?: "1st" | "2nd" | "3rd";
  tone_mode?: "Quiet" | "Sharp" | "Witty" | "Savage";
  greeting?: string;
  icon?: string;
  color?: string;
}

export interface ScenarioCard {
  card_id?: number;          // backend canonical
  id?: string;               // legacy alias
  session_id?: string;
  card_type: CardType;
  fact?: string;             // soft_stop/paradox는 null
  feeling?: string;
  micro_action?: string;
  safety_message?: string;   // soft_stop/paradox
  persona?: PersonaInfo;
  persona_id?: number;
  created_at?: string;
  sentences?: {              // backend response 구조 (호환)
    fact?: string | null;
    feeling?: string | null;
    micro_action?: string | null;
  };
}

export interface AvoidanceSession {
  id: string;
  user_id: string;
  input_text: string;
  created_at: string;
  cards: ScenarioCard[];
}

export interface UserProfile {
  id: string;
  active_persona_id: number;
  onboarding_completed: boolean;
  created_at: string;
}

export interface ProbeQuestion {
  id: string;
  question: string;
  options: Array<{
    value: string;
    label: string;
    warning?: boolean;
  }>;
}

export interface RegretScore {
  session_id: string;
  score: number;
  trend: "up" | "down" | "stable";
  computed_at: string;
}

export interface SafetyTrend {
  user_id: string;
  signal_level: "normal" | "elevated" | "high";
  recent_sessions: number;
  last_soft_stop_at: string | null;
}

// ── fetch 래퍼 ───────────────────────────────────────────

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`GET ${path} failed (${res.status}): ${text}`);
  }

  return res.json() as Promise<T>;
}

async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`POST ${path} failed (${res.status}): ${text}`);
  }

  return res.json() as Promise<T>;
}

export { apiGet, apiPost };
