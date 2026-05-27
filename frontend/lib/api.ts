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

export interface ScenarioCard {
  id: string;
  session_id: string;
  card_type: CardType;
  fact: string;
  feeling: string;
  micro_action: string;
  persona_id: number;
  created_at: string;
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
