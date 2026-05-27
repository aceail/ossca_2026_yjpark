"use client";

import React, { useEffect, useState, useCallback } from "react";
import { useUser } from "../../lib/hooks/useUser";
import { PersonaCard } from "../../components/PersonaCard";
import { Button } from "../../components/Button";
import { authHeaders } from "../../lib/auth";
import type { Persona } from "../../lib/personas";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8001";

const PERSPECTIVE_OPTIONS: { value: Persona["perspective"]; label: string }[] = [
  { value: "1st", label: "1인칭 (나는...)" },
  { value: "2nd", label: "2인칭 (너는...)" },
  { value: "3rd", label: "3인칭 (그는...)" },
];

const TONE_OPTIONS: { value: Persona["tone_mode"]; label: string }[] = [
  { value: "Quiet", label: "Quiet — 조용하고 담담" },
  { value: "Sharp", label: "Sharp — 날카롭고 직접적" },
  { value: "Witty", label: "Witty — 위트 있는 친구" },
  { value: "Savage", label: "Savage — 거침없는 직설" },
];

const AVATAR_PRESETS = ["#3B6B9A", "#5A7080", "#C4935A", "#9A6430", "#6B7280", "#7C6A9A"];

// P0-21: Savage opt-in 가드 — 직설적 톤은 임상 위험 큼
const SAVAGE_WARNING =
  "이 페르소나는 직설적이고 강한 톤이에요. 최근 자해 사고나 깊은 우울감이 있다면 권하지 않아요.";
const SAVAGE_CONFIRM = `${SAVAGE_WARNING}\n\n그래도 사용하시겠어요?`;

const INTENT_PROMPT_CONFIRM =
  "의도를 한 줄도 적지 않았어요. 의도를 기록해두면 나중에 이 페르소나가 또 다른 미루기 대상이 되었는지 점검할 수 있어요. 그래도 만들까요?";

interface AuditViolation {
  field: string;
  group: string;
  word: string;
}

interface Toast {
  id: number;
  message: string;
}

interface CustomFormState {
  name: string;
  perspective: Persona["perspective"];
  tone_mode: Persona["tone_mode"];
  voice_style: string;
  greeting: string;
  forbidden_topics: string[];
  avatar_color: string;
  avatar_icon: string;
  intent_reason: string;  // P0-21: 의도 기록 (client-side only)
}

const EMPTY_FORM: CustomFormState = {
  name: "",
  perspective: "1st",
  tone_mode: "Quiet",
  voice_style: "",
  greeting: "",
  forbidden_topics: [],
  avatar_color: AVATAR_PRESETS[0],
  avatar_icon: "✨",
  intent_reason: "",
};

export default function PersonasPage() {
  const { userId, loading: userLoading } = useUser();

  const [personas, setPersonas] = useState<Persona[]>([]);
  const [activePersonaId, setActivePersonaId] = useState<number | null>(null);
  const [selectedPersona, setSelectedPersona] = useState<Persona | null>(null);
  const [loadingPersonas, setLoadingPersonas] = useState(false);

  const [form, setForm] = useState<CustomFormState>({ ...EMPTY_FORM });
  const [topicInput, setTopicInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [violations, setViolations] = useState<AuditViolation[]>([]);

  const [toasts, setToasts] = useState<Toast[]>([]);

  const showToast = useCallback((message: string) => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 3000);
  }, []);

  const fetchPersonas = useCallback(async (uid: string) => {
    setLoadingPersonas(true);
    try {
      const res = await fetch(`${API_BASE}/api/personas?user_id=${uid}`, {
        headers: { ...authHeaders() },
      });
      if (!res.ok) throw new Error("페르소나 목록 로드 실패");
      const data = await res.json();
      setPersonas(data);
    } catch {
      // silent — 백엔드 미가용 시 빈 목록
    } finally {
      setLoadingPersonas(false);
    }
  }, []);

  const fetchProfile = useCallback(async (uid: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/users/${uid}/profile`, {
        headers: { ...authHeaders() },
      });
      if (!res.ok) return;
      const data = await res.json();
      if (data.active_persona_id) setActivePersonaId(data.active_persona_id);
    } catch {
      // silent
    }
  }, []);

  useEffect(() => {
    if (userId) {
      fetchPersonas(userId);
      fetchProfile(userId);
    }
  }, [userId, fetchPersonas, fetchProfile]);

  const handleActivate = async (persona: Persona) => {
    if (!userId) return;
    // P0-21: Savage opt-in 가드
    if (persona.tone_mode === "Savage" && !window.confirm(SAVAGE_CONFIRM)) {
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/api/users/${userId}/active-persona`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ persona_id: persona.id }),
      });
      if (!res.ok) throw new Error("활성화 실패");
      setActivePersonaId(persona.id);
      showToast("✓ 페르소나 변경됨");
    } catch {
      showToast("활성화 중 오류가 발생했어요.");
    }
  };

  const handleTopicKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      const val = topicInput.trim();
      if (val && !form.forbidden_topics.includes(val)) {
        setForm((prev) => ({ ...prev, forbidden_topics: [...prev.forbidden_topics, val] }));
      }
      setTopicInput("");
    }
  };

  const removeTopic = (topic: string) => {
    setForm((prev) => ({
      ...prev,
      forbidden_topics: prev.forbidden_topics.filter((t) => t !== topic),
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!userId) return;
    // P0-21: Savage opt-in 가드 (Custom Builder)
    if (form.tone_mode === "Savage" && !window.confirm(SAVAGE_CONFIRM)) {
      return;
    }
    // P0-21: 의도 미기록 시 부드러운 확인
    if (form.intent_reason.trim().length === 0 && !window.confirm(INTENT_PROMPT_CONFIRM)) {
      return;
    }
    setSubmitting(true);
    setViolations([]);
    // intent_reason은 client-side 가드용 — 백엔드 페이로드에서 제외
    const { intent_reason: _intent, ...payload } = form;
    void _intent;
    try {
      const res = await fetch(`${API_BASE}/api/personas/custom`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ user_id: userId, ...payload }),
      });
      if (res.ok) {
        const newPersona = await res.json();
        setPersonas((prev) => [...prev, newPersona]);
        setForm({ ...EMPTY_FORM });
        setTopicInput("");
        showToast("✓ 새 페르소나가 추가됐어요");
      } else {
        const errData = await res.json().catch(() => ({}));
        if (errData.violations) {
          setViolations(errData.violations);
        } else {
          showToast("저장 실패: " + (errData.detail ?? "알 수 없는 오류"));
        }
      }
    } catch {
      showToast("네트워크 오류가 발생했어요.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleSelfDestruct = () => {
    if (!confirm("정말 모든 데이터를 삭제할까요? 되돌릴 수 없어요.")) return;
    localStorage.clear();
    window.location.href = "/";
  };

  if (userLoading) {
    return (
      <main className="p-8 min-h-screen" style={{ backgroundColor: "var(--color-bg-base)" }}>
        <p style={{ color: "var(--color-text-secondary)" }}>로딩 중...</p>
      </main>
    );
  }

  return (
    <main
      className="min-h-screen p-6"
      style={{ backgroundColor: "var(--color-bg-base)", color: "var(--color-text-primary)" }}
    >
      {/* 상단 헤더 */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1
            className="text-[22px] font-semibold mb-1"
            style={{ fontFamily: "var(--font-feeling)" }}
          >
            페르소나 라이브러리
          </h1>
          <p className="text-[13px]" style={{ color: "var(--color-text-secondary)" }}>
            어떤 목소리로 내일을 마주할지 선택해요
          </p>
        </div>
        <Button variant="destruct" size="sm" onClick={handleSelfDestruct} title="모든 데이터 삭제">
          ⊗
        </Button>
      </div>

      <div className="flex flex-col lg:flex-row gap-6">
        {/* 좌측: 페르소나 카드 그리드 */}
        <section className="flex-1 min-w-0">
          {loadingPersonas && (
            <p className="text-[13px]" style={{ color: "var(--color-text-secondary)" }}>
              페르소나 목록 불러오는 중...
            </p>
          )}

          <div className="flex flex-col gap-3">
            {personas.map((p) => (
              <div key={p.id}>
                <PersonaCard
                  persona={p}
                  selected={selectedPersona?.id === p.id}
                  onSelect={(persona) =>
                    setSelectedPersona((prev) => (prev?.id === persona.id ? null : persona))
                  }
                />
                {selectedPersona?.id === p.id && (
                  <div
                    className="mt-2 px-4 py-3 rounded-lg text-[13px]"
                    style={{
                      backgroundColor: "var(--color-bg-card)",
                      border: "1px solid var(--color-border-subtle)",
                    }}
                  >
                    <p className="mb-1" style={{ color: "var(--color-text-secondary)" }}>
                      <span className="font-medium" style={{ color: "var(--color-text-primary)" }}>
                        화법:
                      </span>{" "}
                      {p.perspective === "1st"
                        ? "1인칭"
                        : p.perspective === "2nd"
                          ? "2인칭"
                          : "3인칭"}
                      &nbsp;·&nbsp;
                      {p.tone_mode}
                    </p>
                    {p.voice_style && (
                      <p className="mb-2" style={{ color: "var(--color-text-secondary)" }}>
                        <span
                          className="font-medium"
                          style={{ color: "var(--color-text-primary)" }}
                        >
                          스타일:
                        </span>{" "}
                        {p.voice_style}
                      </p>
                    )}
                    <Button
                      variant={activePersonaId === p.id ? "ghost" : "primary"}
                      size="sm"
                      onClick={() => handleActivate(p)}
                      disabled={activePersonaId === p.id}
                    >
                      {activePersonaId === p.id ? "✓ 현재 활성 페르소나" : "활성화 페르소나로 설정"}
                    </Button>
                  </div>
                )}
              </div>
            ))}

            {!loadingPersonas && personas.length === 0 && (
              <p
                className="text-[13px] py-8 text-center"
                style={{ color: "var(--color-text-secondary)" }}
              >
                페르소나가 없어요. 오른쪽 빌더로 만들어보세요.
              </p>
            )}
          </div>
        </section>

        {/* 우측: Custom Persona Builder */}
        <section
          className="w-full lg:w-[360px] flex-shrink-0 rounded-xl p-5"
          style={{
            backgroundColor: "var(--color-bg-card)",
            border: "1px solid var(--color-border-subtle)",
          }}
        >
          <h2
            className="text-[15px] font-semibold mb-4"
            style={{ fontFamily: "var(--font-feeling)" }}
          >
            ✨ 나만의 페르소나 만들기
          </h2>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            {/* 이름 */}
            <div>
              <label className="block text-[12px] mb-1" style={{ color: "var(--color-text-secondary)" }}>
                이름
              </label>
              <input
                type="text"
                value={form.name}
                onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
                placeholder="예: 내 옛 동기 ㅇㅇ"
                required
                className="w-full px-3 py-2 text-[13px] rounded-lg outline-none"
                style={{
                  backgroundColor: "var(--color-bg-base)",
                  border: "1px solid var(--color-border-subtle)",
                  color: "var(--color-text-primary)",
                }}
              />
            </div>

            {/* Perspective */}
            <div>
              <label className="block text-[12px] mb-1" style={{ color: "var(--color-text-secondary)" }}>
                화법 (Perspective)
              </label>
              <select
                value={form.perspective}
                onChange={(e) =>
                  setForm((prev) => ({
                    ...prev,
                    perspective: e.target.value as Persona["perspective"],
                  }))
                }
                className="w-full px-3 py-2 text-[13px] rounded-lg outline-none"
                style={{
                  backgroundColor: "var(--color-bg-base)",
                  border: "1px solid var(--color-border-subtle)",
                  color: "var(--color-text-primary)",
                }}
              >
                {PERSPECTIVE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Tone Mode */}
            <div>
              <label className="block text-[12px] mb-1" style={{ color: "var(--color-text-secondary)" }}>
                톤 (Tone Mode)
              </label>
              <select
                value={form.tone_mode}
                onChange={(e) =>
                  setForm((prev) => ({
                    ...prev,
                    tone_mode: e.target.value as Persona["tone_mode"],
                  }))
                }
                className="w-full px-3 py-2 text-[13px] rounded-lg outline-none"
                style={{
                  backgroundColor: "var(--color-bg-base)",
                  border: "1px solid var(--color-border-subtle)",
                  color: "var(--color-text-primary)",
                }}
              >
                {TONE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
              {form.tone_mode === "Savage" && (
                <p
                  className="text-[11px] mt-1.5"
                  style={{ color: "var(--color-text-secondary)" }}
                  role="note"
                >
                  ⚠ {SAVAGE_WARNING}
                </p>
              )}
            </div>

            {/* Voice Style */}
            <div>
              <label className="block text-[12px] mb-1" style={{ color: "var(--color-text-secondary)" }}>
                말투 묘사 (선택)
              </label>
              <input
                type="text"
                value={form.voice_style}
                onChange={(e) => setForm((prev) => ({ ...prev, voice_style: e.target.value }))}
                placeholder="예: 능청맞은 친구 톤"
                className="w-full px-3 py-2 text-[13px] rounded-lg outline-none"
                style={{
                  backgroundColor: "var(--color-bg-base)",
                  border: "1px solid var(--color-border-subtle)",
                  color: "var(--color-text-primary)",
                }}
              />
            </div>

            {/* Greeting */}
            <div>
              <label className="block text-[12px] mb-1" style={{ color: "var(--color-text-secondary)" }}>
                첫 인사 (80자 이내)
              </label>
              <input
                type="text"
                value={form.greeting}
                onChange={(e) =>
                  setForm((prev) => ({ ...prev, greeting: e.target.value.slice(0, 80) }))
                }
                placeholder="예: 야 너 지금 뭐 해ㅋ"
                className="w-full px-3 py-2 text-[13px] rounded-lg outline-none"
                style={{
                  backgroundColor: "var(--color-bg-base)",
                  border: "1px solid var(--color-border-subtle)",
                  color: "var(--color-text-primary)",
                }}
              />
              <p className="text-[11px] mt-0.5" style={{ color: "var(--color-text-secondary)" }}>
                {form.greeting.length}/80
              </p>
            </div>

            {/* P0-21: 의도 기록 — 페르소나 자체가 또 다른 미루기 대상이 되는 걸 미리 점검 */}
            <div>
              <label
                className="block text-[12px] mb-1"
                style={{ color: "var(--color-text-secondary)" }}
                htmlFor="intent-reason"
              >
                왜 이 페르소나를 만드세요? <span className="opacity-60">(나만 봐요)</span>
              </label>
              <textarea
                id="intent-reason"
                value={form.intent_reason}
                onChange={(e) =>
                  setForm((prev) => ({ ...prev, intent_reason: e.target.value.slice(0, 200) }))
                }
                placeholder="예: 마감 직전에 나를 깨워줄 누군가가 필요해서"
                rows={2}
                className="w-full px-3 py-2 text-[13px] rounded-lg outline-none resize-none"
                style={{
                  backgroundColor: "var(--color-bg-base)",
                  border: "1px solid var(--color-border-subtle)",
                  color: "var(--color-text-primary)",
                }}
              />
              <p
                className="text-[11px] mt-0.5"
                style={{ color: "var(--color-text-secondary)" }}
              >
                {form.intent_reason.length}/200 · 의도를 적어두면 나중에 점검할 수 있어요
              </p>
            </div>

            {/* Forbidden Topics */}
            <div>
              <label className="block text-[12px] mb-1" style={{ color: "var(--color-text-secondary)" }}>
                금지 주제 (Enter로 추가)
              </label>
              <input
                type="text"
                value={topicInput}
                onChange={(e) => setTopicInput(e.target.value)}
                onKeyDown={handleTopicKeyDown}
                placeholder="예: 연애, 가족"
                className="w-full px-3 py-2 text-[13px] rounded-lg outline-none"
                style={{
                  backgroundColor: "var(--color-bg-base)",
                  border: "1px solid var(--color-border-subtle)",
                  color: "var(--color-text-primary)",
                }}
              />
              {form.forbidden_topics.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {form.forbidden_topics.map((topic) => (
                    <span
                      key={topic}
                      className="flex items-center gap-1 px-2 py-0.5 text-[11px] rounded-full"
                      style={{
                        backgroundColor: "var(--color-bg-base)",
                        border: "1px solid var(--color-border-subtle)",
                        color: "var(--color-text-secondary)",
                      }}
                    >
                      {topic}
                      <button
                        type="button"
                        onClick={() => removeTopic(topic)}
                        className="opacity-50 hover:opacity-100 transition-opacity"
                        aria-label={`${topic} 제거`}
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* Avatar Color */}
            <div>
              <label className="block text-[12px] mb-1" style={{ color: "var(--color-text-secondary)" }}>
                색상
              </label>
              <div className="flex gap-2 flex-wrap">
                {AVATAR_PRESETS.map((color) => (
                  <button
                    key={color}
                    type="button"
                    onClick={() => setForm((prev) => ({ ...prev, avatar_color: color }))}
                    className="w-7 h-7 rounded-full border-2 transition-all"
                    style={{
                      backgroundColor: color,
                      borderColor:
                        form.avatar_color === color ? "var(--color-text-primary)" : "transparent",
                    }}
                    aria-label={`색상 ${color} 선택`}
                  />
                ))}
                <input
                  type="color"
                  value={form.avatar_color}
                  onChange={(e) => setForm((prev) => ({ ...prev, avatar_color: e.target.value }))}
                  className="w-7 h-7 rounded-full cursor-pointer border-0 p-0"
                  title="직접 색상 선택"
                />
              </div>
            </div>

            {/* Avatar Icon */}
            <div>
              <label className="block text-[12px] mb-1" style={{ color: "var(--color-text-secondary)" }}>
                아이콘 (이모지)
              </label>
              <input
                type="text"
                value={form.avatar_icon}
                onChange={(e) => setForm((prev) => ({ ...prev, avatar_icon: e.target.value }))}
                placeholder="✨"
                className="w-full px-3 py-2 text-[13px] rounded-lg outline-none"
                style={{
                  backgroundColor: "var(--color-bg-base)",
                  border: "1px solid var(--color-border-subtle)",
                  color: "var(--color-text-primary)",
                }}
              />
            </div>

            {/* Violations */}
            {violations.length > 0 && (
              <div
                className="px-3 py-2 rounded-lg text-[12px]"
                style={{
                  backgroundColor: "var(--color-bg-base)",
                  border: "1px solid var(--color-border-subtle)",
                  color: "var(--color-text-secondary)",
                }}
              >
                <p className="font-medium mb-1" style={{ color: "var(--color-text-primary)" }}>
                  저장할 수 없는 표현이 있어요
                </p>
                <ul className="list-none space-y-0.5">
                  {violations.map((v, i) => (
                    <li key={i}>
                      · <span className="font-medium">{v.field}</span>: &ldquo;{v.word}&rdquo; ({v.group})
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <Button type="submit" variant="primary" size="md" disabled={submitting}>
              {submitting ? "저장 중..." : "페르소나 만들기"}
            </Button>
          </form>
        </section>
      </div>

      {/* 토스트 */}
      <div className="fixed top-4 right-4 flex flex-col gap-2 z-50">
        {toasts.map((t) => (
          <div
            key={t.id}
            className="px-4 py-2 rounded-lg text-[13px] shadow-lg"
            style={{
              backgroundColor: "var(--color-bg-card)",
              border: "1px solid var(--color-border-subtle)",
              color: "var(--color-text-primary)",
            }}
          >
            {t.message}
          </div>
        ))}
      </div>
    </main>
  );
}
