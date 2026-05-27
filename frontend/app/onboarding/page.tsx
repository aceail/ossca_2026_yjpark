"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { OnboardingCard } from "../../components/OnboardingCard";
import { PersonaCard } from "../../components/PersonaCard";
import { Button } from "../../components/Button";
import { Progress } from "../../components/Progress";
import { apiGet, apiPost } from "../../lib/api";
import type { ScenarioCard } from "../../lib/api";
import { useUser } from "../../lib/hooks/useUser";
import { BUILTIN_PERSONAS } from "../../lib/personas";
import type { Persona } from "../../lib/personas";

// ── 타입 ────────────────────────────────────────────────────

interface OnboardingSelections {
  trigger_category?: string;
  avoidance_destination?: string;
  persona_id?: number;
  fear_anchor?: string;
  recovery_pattern?: string;
}

type Step = 1 | 2 | 3 | "branch" | 4 | 5;

const TONE_OPTIONS = ["Quiet", "Sharp", "Witty", "Savage"] as const;
const PERSPECTIVE_OPTIONS = ["1st", "2nd", "3rd"] as const;

interface CustomPersonaForm {
  name: string;
  perspective: Persona["perspective"];
  tone_mode: Persona["tone_mode"];
  voice_style: string;
  greeting: string;
  forbidden_topics: string[];
  forbiddenInput: string;
}

// ── 상수 ────────────────────────────────────────────────────

const TRIGGER_OPTIONS = [
  { value: "글쓰기·논문·보고서", label: "글쓰기·논문·보고서" },
  { value: "발표·PPT·프레젠테이션", label: "발표·PPT·프레젠테이션" },
  { value: "이메일·연락·답장", label: "이메일·연락·답장" },
  { value: "공부·시험 준비", label: "공부·시험 준비" },
  { value: "운동·습관 만들기", label: "운동·습관 만들기" },
  { value: "정리·청소·집안일", label: "정리·청소·집안일" },
  { value: "의사결정·결단", label: "의사결정·결단" },
  { value: "행정·서류·세금", label: "행정·서류·세금" },
  { value: "관계·사과·고백", label: "관계·사과·고백" },
  { value: "기타", label: "기타" },
];

const AVOIDANCE_OPTIONS = [
  { value: "유튜브·릴스·쇼츠", label: "유튜브·릴스·쇼츠" },
  { value: "잠·침대·휴식", label: "잠·침대·휴식" },
  { value: "SNS·인스타·X", label: "SNS·인스타·X" },
  { value: "음식·간식·배달", label: "음식·간식·배달" },
  { value: "게임", label: "게임" },
  { value: "넷플릭스·OTT", label: "넷플릭스·OTT" },
  { value: "인터넷 서핑·뉴스", label: "인터넷 서핑·뉴스" },
  { value: "기타", label: "기타" },
];

const FEAR_OPTIONS = [
  { value: "나를 한심하게 보는 옛 동기", label: "나를 한심하게 보는 옛 동기" },
  { value: "내가 따라잡지 못한 친구", label: "내가 따라잡지 못한 친구" },
  { value: "어쩐지 잘 살고 있는 그 사람", label: "어쩐지 잘 살고 있는 그 사람" },
  { value: "부모의 기대와 다른 모습", label: "부모의 기대와 다른 모습", warning: true },
  { value: "어제의 나", label: "어제의 나" },
  { value: "내가 약속한 미래의 나", label: "내가 약속한 미래의 나" },
  { value: "기타·없음", label: "기타·없음" },
];

const RECOVERY_QUICK_OPTIONS = [
  { value: "첫 문장 쓰기", label: "첫 문장 쓰기" },
  { value: "운동복 갈아입기", label: "운동복 갈아입기" },
  { value: "한 페이지만 읽기", label: "한 페이지만 읽기" },
  { value: "메시지 한 줄 보내기", label: "메시지 한 줄 보내기" },
];

const EMPTY_CUSTOM_FORM: CustomPersonaForm = {
  name: "",
  perspective: "1st",
  tone_mode: "Quiet",
  voice_style: "",
  greeting: "",
  forbidden_topics: [],
  forbiddenInput: "",
};

// ── 유틸 ────────────────────────────────────────────────────

function stepToNumber(step: Step): number {
  if (step === "branch") return 3;
  return step as number;
}

// ── 메인 컴포넌트 ────────────────────────────────────────────

export default function OnboardingPage() {
  const router = useRouter();
  const { userId, loading: userLoading } = useUser();

  const [currentStep, setCurrentStep] = useState<Step>(1);
  const [selections, setSelections] = useState<OnboardingSelections>({});
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [previews, setPreviews] = useState<Record<number, ScenarioCard>>({});
  const [selectedPersonaId, setSelectedPersonaId] = useState<number | null>(null);
  const [personasLoading, setPersonasLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [visible, setVisible] = useState(false);

  // Custom persona builder
  const [showCustomBuilder, setShowCustomBuilder] = useState(false);
  const [customForm, setCustomForm] = useState<CustomPersonaForm>(EMPTY_CUSTOM_FORM);
  const [customViolations, setCustomViolations] = useState<string[]>([]);
  const [customSubmitting, setCustomSubmitting] = useState(false);

  // Card 5 free text
  const [recoveryFreeText, setRecoveryFreeText] = useState("");

  // Sensitive notice for fear anchor
  const [fearSensitiveNotice, setFearSensitiveNotice] = useState(false);

  // fade-in on mount
  useEffect(() => {
    const t = setTimeout(() => setVisible(true), 50);
    return () => clearTimeout(t);
  }, []);

  // Fetch personas and previews in parallel on mount
  useEffect(() => {
    let cancelled = false;

    async function fetchData() {
      setPersonasLoading(true);
      try {
        const [fetchedPersonas, fetchedPreviews] = await Promise.all([
          apiGet<Persona[]>("/api/personas"),
          apiGet<Record<number, ScenarioCard>>("/api/personas/previews"),
        ]);
        if (!cancelled) {
          setPersonas(fetchedPersonas);
          setPreviews(fetchedPreviews);
        }
      } catch (err) {
        console.error("페르소나 로드 실패, 기본값 사용:", err);
        if (!cancelled) {
          // BUILTIN_PERSONAS fallback — id를 인덱스로 임시 할당
          const fallback: Persona[] = BUILTIN_PERSONAS.map((p, i) => ({ ...p, id: i + 1 }));
          setPersonas(fallback);
        }
      } finally {
        if (!cancelled) setPersonasLoading(false);
      }
    }

    fetchData();
    return () => { cancelled = true; };
  }, []);

  // ── 핸들러 ────────────────────────────────────────────────

  function handleSelfDestruct() {
    if (typeof window !== "undefined") {
      localStorage.removeItem("user_id");
    }
    router.push("/");
  }

  function handleSelect(key: keyof OnboardingSelections, value: string | number) {
    setSelections((prev) => ({ ...prev, [key]: value }));
  }

  function handleTriggerSelect(value: string) {
    handleSelect("trigger_category", value);
    setCurrentStep(2);
  }

  function handleAvoidanceSelect(value: string) {
    handleSelect("avoidance_destination", value);
    setCurrentStep(3);
  }

  function handlePersonaSelect(persona: Persona) {
    setSelectedPersonaId(persona.id);
    handleSelect("persona_id", persona.id);
  }

  function handlePersonaConfirm() {
    if (selectedPersonaId === null) return;
    setCurrentStep("branch");
  }

  function handleBranchQuick() {
    submitOnboarding(false);
  }

  function handleBranchDeep() {
    setCurrentStep(4);
  }

  function handleFearSelect(value: string) {
    if (value === "부모의 기대와 다른 모습") {
      setFearSensitiveNotice(true);
    }
    handleSelect("fear_anchor", value);
    setCurrentStep(5);
  }

  function handleFearSkip() {
    setCurrentStep(5);
  }

  function handleRecoverySelect(value: string) {
    handleSelect("recovery_pattern", value);
    submitOnboarding(true);
  }

  function handleRecoveryFreeTextSubmit() {
    const trimmed = recoveryFreeText.trim().slice(0, 80);
    if (!trimmed) {
      submitOnboarding(true);
      return;
    }
    handleSelect("recovery_pattern", trimmed);
    submitOnboarding(true, trimmed);
  }

  function handleRecoverySkip() {
    submitOnboarding(true);
  }

  async function submitOnboarding(withBonus: boolean, recoveryOverride?: string) {
    if (!userId || selections.persona_id == null) return;
    setSubmitting(true);
    setError(null);

    const body: Record<string, unknown> = {
      user_id: userId,
      trigger_category: selections.trigger_category,
      avoidance_destination: selections.avoidance_destination,
      persona_id: selections.persona_id,
    };

    if (withBonus) {
      if (selections.fear_anchor) body.fear_anchor = selections.fear_anchor;
      const rp = recoveryOverride ?? selections.recovery_pattern;
      if (rp) body.recovery_pattern = rp;
    }

    try {
      await apiPost("/api/onboarding", body);
      router.push("/scenario");
    } catch (err) {
      console.error("온보딩 저장 실패:", err);
      setError("저장 중 문제가 생겼어요. 다시 시도해 주세요.");
      setSubmitting(false);
    }
  }

  // ── Custom Persona ────────────────────────────────────────

  function handleCustomFormChange<K extends keyof CustomPersonaForm>(
    key: K,
    value: CustomPersonaForm[K]
  ) {
    setCustomForm((prev) => ({ ...prev, [key]: value }));
  }

  function handleAddForbiddenTopic() {
    const topic = customForm.forbiddenInput.trim();
    if (!topic) return;
    setCustomForm((prev) => ({
      ...prev,
      forbidden_topics: [...prev.forbidden_topics, topic],
      forbiddenInput: "",
    }));
  }

  function handleRemoveForbiddenTopic(topic: string) {
    setCustomForm((prev) => ({
      ...prev,
      forbidden_topics: prev.forbidden_topics.filter((t) => t !== topic),
    }));
  }

  async function handleCustomPersonaSubmit() {
    if (!customForm.name.trim() || !customForm.greeting.trim()) return;
    setCustomSubmitting(true);
    setCustomViolations([]);

    try {
      const result = await apiPost<Persona & { violations?: string[] }>("/api/personas/custom", {
        name: customForm.name.trim(),
        perspective: customForm.perspective,
        tone_mode: customForm.tone_mode,
        voice_style: customForm.voice_style.trim(),
        greeting: customForm.greeting.trim(),
        forbidden_topics: customForm.forbidden_topics,
      });

      if (result.violations && result.violations.length > 0) {
        setCustomViolations(result.violations);
      } else {
        const newPersona: Persona = {
          id: result.id,
          name: result.name,
          perspective: result.perspective,
          tone_mode: result.tone_mode,
          voice_style: result.voice_style,
          greeting: result.greeting,
          avatar_color: result.avatar_color ?? "#6B7280",
          avatar_icon: result.avatar_icon ?? "✨",
        };
        setPersonas((prev) => [...prev, newPersona]);
        setSelectedPersonaId(newPersona.id);
        handleSelect("persona_id", newPersona.id);
        setShowCustomBuilder(false);
        setCustomForm(EMPTY_CUSTOM_FORM);
      }
    } catch (err) {
      console.error("커스텀 페르소나 생성 실패:", err);
      setCustomViolations(["페르소나 생성 중 오류가 발생했어요. 다시 시도해 주세요."]);
    } finally {
      setCustomSubmitting(false);
    }
  }

  // ── 렌더 ─────────────────────────────────────────────────

  const progressStep = currentStep === "branch" ? 3 : (currentStep as number);

  const pageStyle: React.CSSProperties = {
    opacity: visible ? 1 : 0,
    transition: "opacity 300ms ease",
    minHeight: "100vh",
    backgroundColor: "var(--color-bg-base)",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    padding: "24px 16px 48px",
    position: "relative",
  };

  if (userLoading) {
    return (
      <main style={pageStyle}>
        <p style={{ color: "var(--color-text-secondary)", marginTop: "40vh", fontSize: "14px" }}>
          잠시만요...
        </p>
      </main>
    );
  }

  return (
    <main style={pageStyle}>
      {/* Self-Destruct 버튼 */}
      <button
        type="button"
        onClick={handleSelfDestruct}
        title="모든 흔적 삭제"
        aria-label="모든 흔적 삭제"
        style={{
          position: "fixed",
          top: "16px",
          right: "16px",
          background: "none",
          border: "none",
          cursor: "pointer",
          opacity: 0.4,
          fontSize: "18px",
          color: "var(--color-text-secondary)",
          lineHeight: 1,
          padding: "4px",
          zIndex: 50,
          transition: "opacity 200ms",
        }}
        onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.opacity = "1"; }}
        onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.opacity = "0.4"; }}
      >
        ⊗
      </button>

      {/* Progress */}
      <div style={{ width: "100%", maxWidth: "480px", marginBottom: "32px" }}>
        <Progress current={progressStep} total={5} />
      </div>

      {/* 에러 메시지 */}
      {error && (
        <div
          style={{
            width: "100%",
            maxWidth: "480px",
            marginBottom: "16px",
            padding: "12px 16px",
            borderRadius: "8px",
            backgroundColor: "var(--color-bg-card)",
            border: "1px solid var(--color-border-subtle)",
            color: "var(--color-text-secondary)",
            fontSize: "13px",
          }}
        >
          {error}
        </div>
      )}

      {/* ── Step 1: 트리거 카테고리 ── */}
      {currentStep === 1 && (
        <OnboardingCard
          stepIndex={1}
          question="지금 당신을 도망치게 만드는 건 무엇인가요?"
          options={TRIGGER_OPTIONS}
          onSelect={handleTriggerSelect}
        />
      )}

      {/* ── Step 2: 회피처 ── */}
      {currentStep === 2 && (
        <OnboardingCard
          stepIndex={2}
          question="도망치면 주로 어디로 가나요?"
          options={AVOIDANCE_OPTIONS}
          onSelect={handleAvoidanceSelect}
        />
      )}

      {/* ── Step 3: 페르소나 선택 ── */}
      {currentStep === 3 && (
        <div
          style={{
            width: "100%",
            maxWidth: "480px",
            display: "flex",
            flexDirection: "column",
            gap: "12px",
          }}
        >
          <p
            style={{
              fontFamily: "var(--font-fact)",
              fontSize: "var(--text-fact-size)",
              color: "var(--color-text-primary)",
              marginBottom: "4px",
            }}
          >
            누가 당신에게 말을 걸어줄까요?
          </p>
          <p
            style={{
              fontSize: "12px",
              color: "var(--color-text-secondary)",
              marginBottom: "8px",
            }}
          >
            {personasLoading
              ? "페르소나 불러오는 중..."
              : "카드를 탭하면 샘플 시나리오를 미리 볼 수 있어요."}
          </p>

          {personas.map((persona) => (
            <PersonaCard
              key={persona.id}
              persona={persona}
              selected={selectedPersonaId === persona.id}
              onSelect={handlePersonaSelect}
              preview={previews[persona.id]}
            />
          ))}

          {/* Custom Builder 진입 버튼 */}
          <button
            type="button"
            onClick={() => setShowCustomBuilder((v) => !v)}
            style={{
              width: "100%",
              padding: "12px 16px",
              borderRadius: "var(--card-radius)",
              backgroundColor: "var(--color-bg-card)",
              border: "1px dashed var(--color-border-subtle)",
              color: "var(--color-text-secondary)",
              cursor: "pointer",
              fontSize: "13px",
              fontFamily: "var(--font-feeling)",
              textAlign: "left",
              display: "flex",
              alignItems: "center",
              gap: "8px",
            }}
          >
            <span>✨</span>
            <span>내가 직접 만들래요</span>
          </button>

          {/* Custom Persona Builder */}
          {showCustomBuilder && (
            <div
              style={{
                padding: "20px",
                borderRadius: "var(--card-radius)",
                backgroundColor: "var(--color-bg-card)",
                border: "1px solid var(--color-border-subtle)",
                display: "flex",
                flexDirection: "column",
                gap: "12px",
              }}
            >
              <p style={{ fontSize: "13px", color: "var(--color-text-secondary)", fontFamily: "var(--font-feeling)" }}>
                나만의 페르소나를 만들어요
              </p>

              {/* violations */}
              {customViolations.length > 0 && (
                <div
                  style={{
                    padding: "10px 12px",
                    borderRadius: "6px",
                    backgroundColor: "var(--color-bg-base)",
                    border: "1px solid var(--color-border-subtle)",
                    fontSize: "12px",
                    color: "var(--color-text-secondary)",
                  }}
                >
                  {customViolations.map((v, i) => (
                    <p key={i}>⚠ {v}</p>
                  ))}
                </div>
              )}

              <label style={labelStyle}>
                이름
                <input
                  type="text"
                  value={customForm.name}
                  onChange={(e) => handleCustomFormChange("name", e.target.value)}
                  placeholder="예: 미래의 CEO 나"
                  style={inputStyle}
                  maxLength={30}
                />
              </label>

              <label style={labelStyle}>
                시점
                <select
                  value={customForm.perspective}
                  onChange={(e) =>
                    handleCustomFormChange("perspective", e.target.value as Persona["perspective"])
                  }
                  style={inputStyle}
                >
                  {PERSPECTIVE_OPTIONS.map((p) => (
                    <option key={p} value={p}>{p === "1st" ? "1인칭 (나로서)" : p === "2nd" ? "2인칭 (너에게)" : "3인칭 (그/그녀를)"}</option>
                  ))}
                </select>
              </label>

              <label style={labelStyle}>
                톤
                <select
                  value={customForm.tone_mode}
                  onChange={(e) =>
                    handleCustomFormChange("tone_mode", e.target.value as Persona["tone_mode"])
                  }
                  style={inputStyle}
                >
                  {TONE_OPTIONS.map((t) => (
                    <option key={t} value={t}>{t === "Quiet" ? "Quiet — 조용하고 담담하게" : t === "Sharp" ? "Sharp — 날카롭고 명확하게" : t === "Witty" ? "Witty — 위트있게" : "Savage — 직설적으로"}</option>
                  ))}
                </select>
              </label>

              <label style={labelStyle}>
                말투 스타일
                <input
                  type="text"
                  value={customForm.voice_style}
                  onChange={(e) => handleCustomFormChange("voice_style", e.target.value)}
                  placeholder="예: 짧고 건조한 1인칭 독백"
                  style={inputStyle}
                  maxLength={60}
                />
              </label>

              <label style={labelStyle}>
                첫 인사말
                <input
                  type="text"
                  value={customForm.greeting}
                  onChange={(e) => handleCustomFormChange("greeting", e.target.value)}
                  placeholder="예: 야, 그거 지금 안 하면 내일 후회해."
                  style={inputStyle}
                  maxLength={80}
                />
              </label>

              <div>
                <p style={{ fontSize: "11px", color: "var(--color-text-secondary)", marginBottom: "6px" }}>
                  시나리오에서 다루지 않을 주제 (선택)
                </p>
                <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginBottom: "6px" }}>
                  {customForm.forbidden_topics.map((topic) => (
                    <span
                      key={topic}
                      style={{
                        padding: "3px 8px",
                        borderRadius: "99px",
                        backgroundColor: "var(--color-bg-base)",
                        border: "1px solid var(--color-border-subtle)",
                        fontSize: "11px",
                        color: "var(--color-text-secondary)",
                        display: "flex",
                        alignItems: "center",
                        gap: "4px",
                      }}
                    >
                      {topic}
                      <button
                        type="button"
                        onClick={() => handleRemoveForbiddenTopic(topic)}
                        style={{ background: "none", border: "none", cursor: "pointer", padding: 0, lineHeight: 1, fontSize: "11px" }}
                        aria-label={`${topic} 삭제`}
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
                <div style={{ display: "flex", gap: "6px" }}>
                  <input
                    type="text"
                    value={customForm.forbiddenInput}
                    onChange={(e) => handleCustomFormChange("forbiddenInput", e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleAddForbiddenTopic(); } }}
                    placeholder="주제 입력 후 Enter"
                    style={{ ...inputStyle, flex: 1 }}
                    maxLength={30}
                  />
                  <Button variant="ghost" size="sm" onClick={handleAddForbiddenTopic}>추가</Button>
                </div>
              </div>

              <div style={{ display: "flex", gap: "8px", justifyContent: "flex-end" }}>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => { setShowCustomBuilder(false); setCustomViolations([]); setCustomForm(EMPTY_CUSTOM_FORM); }}
                >
                  취소
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleCustomPersonaSubmit}
                  disabled={customSubmitting || !customForm.name.trim() || !customForm.greeting.trim()}
                >
                  {customSubmitting ? "만드는 중..." : "만들기"}
                </Button>
              </div>
            </div>
          )}

          {/* Sensitive notice */}
          {fearSensitiveNotice && (
            <div
              style={{
                padding: "10px 14px",
                borderRadius: "8px",
                backgroundColor: "var(--color-bg-card)",
                border: "1px solid var(--color-border-subtle)",
                fontSize: "12px",
                color: "var(--color-text-secondary)",
              }}
            >
              이 주제는 시나리오에 사용하지 않을게요.
            </div>
          )}

          {/* 확인 버튼 */}
          {selectedPersonaId !== null && (
            <Button
              variant="primary"
              size="md"
              onClick={handlePersonaConfirm}
              style={{ width: "100%", marginTop: "8px" }}
            >
              이 페르소나로 시작할게요
            </Button>
          )}
        </div>
      )}

      {/* ── Branch ── */}
      {currentStep === "branch" && (
        <div
          style={{
            width: "100%",
            maxWidth: "480px",
            padding: "var(--card-padding)",
            borderRadius: "var(--card-radius)",
            backgroundColor: "var(--color-bg-card)",
            border: "1px solid var(--color-border-subtle)",
            boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
            display: "flex",
            flexDirection: "column",
            gap: "24px",
          }}
        >
          <p
            style={{
              fontFamily: "var(--font-fact)",
              fontSize: "var(--text-fact-size)",
              color: "var(--color-text-primary)",
            }}
          >
            3 카드 완료 — 어떻게 갈까요?
          </p>
          <p style={{ fontSize: "13px", color: "var(--color-text-secondary)", marginTop: "-12px" }}>
            지금 바로 첫 시나리오를 볼 수도 있어요.
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            <button
              type="button"
              onClick={handleBranchQuick}
              disabled={submitting}
              style={{
                padding: "16px 20px",
                borderRadius: "var(--card-radius)",
                backgroundColor: "var(--color-action-bg)",
                color: "var(--color-action-text)",
                border: "none",
                cursor: submitting ? "not-allowed" : "pointer",
                fontSize: "14px",
                fontFamily: "var(--font-feeling)",
                textAlign: "left",
                display: "flex",
                flexDirection: "column",
                gap: "4px",
              }}
            >
              <span style={{ fontWeight: 500 }}>여기까지로 충분해</span>
              <span style={{ fontSize: "12px", opacity: 0.75 }}>첫 시나리오 바로 보기 · 60초 완료</span>
            </button>

            <button
              type="button"
              onClick={handleBranchDeep}
              style={{
                padding: "16px 20px",
                borderRadius: "var(--card-radius)",
                backgroundColor: "var(--color-bg-base)",
                color: "var(--color-text-primary)",
                border: "1px solid var(--color-border-subtle)",
                cursor: "pointer",
                fontSize: "14px",
                fontFamily: "var(--font-feeling)",
                textAlign: "left",
                display: "flex",
                flexDirection: "column",
                gap: "4px",
              }}
            >
              <span style={{ fontWeight: 500 }}>조금 더 깊이</span>
              <span style={{ fontSize: "12px", color: "var(--color-text-secondary)" }}>카드 2장 더 · 60초 추가 · 더 깊은 개인화</span>
            </button>
          </div>
        </div>
      )}

      {/* ── Step 4: 두려움 앵커 ── */}
      {currentStep === 4 && (
        <div style={{ width: "100%", maxWidth: "480px", display: "flex", flexDirection: "column", gap: "16px" }}>
          {fearSensitiveNotice && (
            <div
              style={{
                padding: "10px 14px",
                borderRadius: "8px",
                backgroundColor: "var(--color-bg-card)",
                border: "1px solid var(--color-border-subtle)",
                fontSize: "12px",
                color: "var(--color-text-secondary)",
              }}
            >
              이 주제는 시나리오에 사용하지 않을게요.
            </div>
          )}
          <OnboardingCard
            stepIndex={4}
            question="당신이 제자리에 머물 때 가장 좋아할 사람은 누구인가요?"
            options={FEAR_OPTIONS}
            onSelect={handleFearSelect}
            allowSkip
            onSkip={handleFearSkip}
          />
        </div>
      )}

      {/* ── Step 5: 회복 패턴 ── */}
      {currentStep === 5 && (
        <div
          style={{
            width: "100%",
            maxWidth: "480px",
            padding: "var(--card-padding)",
            borderRadius: "var(--card-radius)",
            backgroundColor: "var(--color-bg-card)",
            border: "1px solid var(--color-border-subtle)",
            boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
            display: "flex",
            flexDirection: "column",
            gap: "16px",
          }}
        >
          <Progress current={5} total={5} />

          <p
            style={{
              fontFamily: "var(--font-fact)",
              fontSize: "var(--text-fact-size)",
              color: "var(--color-text-primary)",
            }}
          >
            과거에 늪에서 당신을 꺼내준 단 하나의 행동은?
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            {RECOVERY_QUICK_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => handleRecoverySelect(opt.value)}
                style={{
                  padding: "12px 16px",
                  borderRadius: "8px",
                  backgroundColor: "var(--color-bg-base)",
                  border: "1px solid var(--color-border-subtle)",
                  color: "var(--color-text-primary)",
                  cursor: "pointer",
                  fontSize: "13px",
                  fontFamily: "var(--font-feeling)",
                  textAlign: "left",
                }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--color-text-secondary)"; }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--color-border-subtle)"; }}
              >
                {opt.label}
              </button>
            ))}
          </div>

          {/* 자유 입력 */}
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <input
              type="text"
              value={recoveryFreeText}
              onChange={(e) => setRecoveryFreeText(e.target.value.slice(0, 80))}
              placeholder="직접 입력 (80자 한도)"
              style={{
                ...inputStyle,
                width: "100%",
                boxSizing: "border-box",
              }}
              maxLength={80}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleRecoveryFreeTextSubmit(); } }}
            />
            {recoveryFreeText.trim() && (
              <Button variant="primary" size="sm" onClick={handleRecoveryFreeTextSubmit} style={{ alignSelf: "flex-end" }}>
                이걸로 할게요
              </Button>
            )}
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <Button variant="ghost" size="sm" onClick={handleRecoverySkip}>
              건너뛰기
            </Button>
          </div>
        </div>
      )}

      {/* submitting overlay */}
      {submitting && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            backgroundColor: "rgba(0,0,0,0.15)",
            zIndex: 100,
          }}
        >
          <p style={{ color: "var(--color-text-primary)", fontSize: "14px", fontFamily: "var(--font-feeling)" }}>
            첫 시나리오 준비 중...
          </p>
        </div>
      )}
    </main>
  );
}

// ── 인라인 스타일 상수 ───────────────────────────────────────

const labelStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "4px",
  fontSize: "11px",
  color: "var(--color-text-secondary)",
  fontFamily: "var(--font-feeling)",
};

const inputStyle: React.CSSProperties = {
  padding: "8px 12px",
  borderRadius: "6px",
  border: "1px solid var(--color-border-subtle)",
  backgroundColor: "var(--color-bg-base)",
  color: "var(--color-text-primary)",
  fontSize: "13px",
  fontFamily: "var(--font-feeling)",
  outline: "none",
};
