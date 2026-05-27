"use client";

import React, { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Logo } from "../../components/Logo";
import { Button } from "../../components/Button";
import { ScenarioCard } from "../../components/ScenarioCard";
import { SocialBlurGuard } from "../../components/SocialBlurGuard";
import { UndoToast } from "../../components/UndoToast";
import { useUser } from "../../lib/hooks/useUser";
import { apiGet, apiPost } from "../../lib/api";
import type { ToneFeedbackKind } from "../../lib/api";
import type { Persona } from "../../lib/personas";

// ── 타입 ─────────────────────────────────────────────────────────────────────

interface ProbeQuestionResponse {
  question?: { id: string; text: string };
  persona?: { name: string; icon: string };
}

interface ScenarioResponse {
  card_id: string;
  card_type: "regret" | "recovery" | "soft_stop" | "paradoxical_validation";
  sentences: { fact: string; feeling: string; micro_action: string };
  safety_message?: string;
  persona: {
    id: number;
    name: string;
    perspective: "1st" | "2nd" | "3rd";
    tone_mode: "Quiet" | "Sharp" | "Witty" | "Savage";
    avatar_color: string;
    avatar_icon: string;
    greeting: string;
  };
}

type Phase =
  | "input"
  | "probe"
  | "generating"
  | "card"
  | "post_decision";

// ── 컴포넌트 ──────────────────────────────────────────────────────────────────

export default function ScenarioPage() {
  const router = useRouter();
  const { userId, loading: userLoading } = useUser();

  // 입력 상태
  const [avoidanceText, setAvoidanceText] = useState("");
  const [timelineHint, setTimelineHint] = useState("");

  // 플로우 상태
  const [phase, setPhase] = useState<Phase>("input");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [cardId, setCardId] = useState<string | null>(null);

  // probe 질문
  const [probeQuestion, setProbeQuestion] = useState<{ id: string; text: string } | null>(null);
  const [probeAnswer, setProbeAnswer] = useState("");

  // 카드 데이터
  const [cardData, setCardData] = useState<{
    id: string;
    session_id: string;
    card_type: "regret" | "recovery" | "soft_stop" | "paradoxical_validation";
    fact: string;
    feeling: string;
    micro_action: string;
    persona_id: number;
    created_at: string;
  } | null>(null);
  const [personaData, setPersonaData] = useState<Persona | null>(null);

  // UI 상태
  const [destroyed, setDestroyed] = useState(false);
  const [showUndoToast, setShowUndoToast] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const cardRef = useRef<string | null>(null);

  // ── 핸들러 ────────────────────────────────────────────────────────────────

  const handleSubmitAvoidance = async () => {
    if (!avoidanceText.trim()) return;
    if (!userId) {
      router.push("/");
      return;
    }

    setSubmitting(true);
    setErrorMsg(null);

    try {
      const body: Record<string, unknown> = {
        user_id: userId,
        avoidance_input: avoidanceText.trim(),
      };
      if (timelineHint) body.timeline_hint = timelineHint;

      const sessionRes = await apiPost<{ session_id: string }>("/api/sessions", body);
      const sid = sessionRes.session_id;
      setSessionId(sid);

      const probeRes = await apiGet<ProbeQuestionResponse>(`/api/sessions/${sid}/probe`);
      if (probeRes.question) {
        setProbeQuestion(probeRes.question);
        setPhase("probe");
      } else {
        await generateScenario(sid);
      }
    } catch {
      setErrorMsg("연결에 문제가 생겼어요. 잠시 후 다시 시도해줘요.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleProbeSubmit = async (skip: boolean) => {
    if (!sessionId || !probeQuestion) return;

    setSubmitting(true);
    setErrorMsg(null);

    try {
      const body = skip
        ? { question_id: probeQuestion.id, skip: true }
        : { question_id: probeQuestion.id, answer_text: probeAnswer.trim() };

      await apiPost(`/api/sessions/${sessionId}/probe-answer`, body);
      await generateScenario(sessionId);
    } catch {
      setErrorMsg("답변 전송에 실패했어요. 다시 시도해줘요.");
    } finally {
      setSubmitting(false);
    }
  };

  const generateScenario = async (sid: string) => {
    setPhase("generating");
    setErrorMsg(null);

    try {
      const res = await apiPost<ScenarioResponse>(`/api/sessions/${sid}/scenario`, {});

      const card = {
        id: res.card_id,
        session_id: sid,
        card_type: res.card_type,
        fact: res.sentences.fact,
        feeling: res.sentences.feeling,
        micro_action: res.sentences.micro_action,
        persona_id: res.persona.id,
        created_at: new Date().toISOString(),
      };

      const persona: Persona = {
        id: res.persona.id,
        name: res.persona.name,
        perspective: res.persona.perspective,
        tone_mode: res.persona.tone_mode,
        voice_style: "",
        greeting: res.persona.greeting,
        avatar_color: res.persona.avatar_color,
        avatar_icon: res.persona.avatar_icon,
      };

      setCardData(card);
      setPersonaData(persona);
      setCardId(res.card_id);
      cardRef.current = res.card_id;

      // card_id를 localStorage에 저장 (회고 페이지용)
      localStorage.setItem(`card_id_${sid}`, res.card_id);

      setPhase("card");
    } catch {
      setErrorMsg("메시지를 가져오는 데 실패했어요. 잠시 후 다시 시도해줘요.");
      setPhase("input");
    }
  };

  const handleDestroy = async () => {
    if (!sessionId) return;
    try {
      await fetch(
        `${process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8001"}/api/sessions/${sessionId}`,
        { method: "DELETE" }
      );
    } catch {
      // 실패해도 UI에서는 제거
    }
    setDestroyed(true);
    setShowUndoToast(true);
  };

  const handleToneFeedback = async (kind: ToneFeedbackKind) => {
    if (!cardId) return;
    try {
      await apiPost(`/api/scenario-cards/${cardId}/tone-feedback`, { kind });
    } catch {
      // 무시
    }
  };

  const handleDecision = async (decision: "transition" | "continue" | "report" | "delete") => {
    if (!sessionId) return;
    try {
      await apiPost(`/api/sessions/${sessionId}/decision`, { decision });
    } catch {
      // 무시
    }
    setPhase("post_decision");
  };

  const handleTimerStart = async () => {
    if (!sessionId) return;
    try {
      await apiPost(`/api/sessions/${sessionId}/decision`, { decision: "transition" });
    } catch {
      // 무시
    }
  };

  // ── 렌더링 ────────────────────────────────────────────────────────────────

  if (userLoading) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <p style={{ fontFamily: "var(--font-feeling)", color: "var(--color-text-secondary)" }}>
          준비 중...
        </p>
      </main>
    );
  }

  return (
    <main
      className="min-h-screen flex flex-col"
      style={{ backgroundColor: "var(--color-bg-page)" }}
    >
      {/* 헤더 */}
      <header
        className="flex items-center justify-between px-6 py-4"
        style={{ borderBottom: "1px solid var(--color-border-subtle)" }}
      >
        <Logo className="text-[15px]" />
        <div className="flex items-center gap-3">
          <Link
            href="/settings"
            aria-label="설정"
            style={{ color: "var(--color-text-secondary)", fontSize: "18px", opacity: 0.6 }}
          >
            ⚙
          </Link>
        </div>
      </header>

      {/* 본문 */}
      <SocialBlurGuard>
        <section className="flex-1 flex flex-col items-center px-4 py-8 gap-8">
          {/* 에러 메시지 */}
          {errorMsg && (
            <p
              className="text-[13px] text-center max-w-sm"
              style={{
                fontFamily: "var(--font-feeling)",
                color: "var(--color-text-secondary)",
                opacity: 0.8,
              }}
            >
              {errorMsg}
            </p>
          )}

          {/* 입력 폼 */}
          {phase === "input" && (
            <div className="w-full max-w-sm flex flex-col gap-4">
              <p
                className="text-[13px]"
                style={{
                  fontFamily: "var(--font-feeling)",
                  color: "var(--color-text-secondary)",
                  letterSpacing: "0.03em",
                }}
              >
                지금 뭘 회피 중이야?
              </p>
              <textarea
                value={avoidanceText}
                onChange={(e) => setAvoidanceText(e.target.value)}
                placeholder="지금 하기 싫거나 미루고 있는 것..."
                rows={4}
                className="w-full resize-none rounded-lg px-4 py-3 text-[14px] outline-none"
                style={{
                  backgroundColor: "var(--color-bg-card)",
                  border: "1px solid var(--color-border-subtle)",
                  color: "var(--color-text-primary)",
                  fontFamily: "var(--font-feeling)",
                  lineHeight: "1.6",
                }}
                aria-label="회피 중인 것 입력"
              />
              <div className="flex flex-col gap-1">
                <label
                  className="text-[11px]"
                  style={{
                    fontFamily: "var(--font-feeling)",
                    color: "var(--color-text-secondary)",
                    opacity: 0.7,
                  }}
                >
                  마감 시각 (선택)
                </label>
                <input
                  type="datetime-local"
                  value={timelineHint}
                  onChange={(e) => setTimelineHint(e.target.value)}
                  className="rounded-lg px-3 py-2 text-[13px] outline-none"
                  style={{
                    backgroundColor: "var(--color-bg-card)",
                    border: "1px solid var(--color-border-subtle)",
                    color: "var(--color-text-primary)",
                    fontFamily: "var(--font-feeling)",
                  }}
                />
              </div>
              <Button
                variant="primary"
                size="md"
                onClick={handleSubmitAvoidance}
                disabled={!avoidanceText.trim() || submitting}
                style={{ opacity: !avoidanceText.trim() || submitting ? 0.5 : 1 }}
              >
                {submitting ? "전송 중..." : "보내기"}
              </Button>
            </div>
          )}

          {/* probe 질문 */}
          {phase === "probe" && probeQuestion && (
            <div className="w-full max-w-sm flex flex-col gap-4">
              <p
                className="text-[14px]"
                style={{
                  fontFamily: "var(--font-feeling)",
                  color: "var(--color-text-primary)",
                  lineHeight: "1.6",
                }}
              >
                {probeQuestion.text}
              </p>
              <textarea
                value={probeAnswer}
                onChange={(e) => setProbeAnswer(e.target.value)}
                placeholder="짧게 답해도 괜찮아요..."
                rows={3}
                className="w-full resize-none rounded-lg px-4 py-3 text-[14px] outline-none"
                style={{
                  backgroundColor: "var(--color-bg-card)",
                  border: "1px solid var(--color-border-subtle)",
                  color: "var(--color-text-primary)",
                  fontFamily: "var(--font-feeling)",
                  lineHeight: "1.6",
                }}
              />
              <div className="flex gap-2">
                <Button
                  variant="primary"
                  size="md"
                  onClick={() => handleProbeSubmit(false)}
                  disabled={!probeAnswer.trim() || submitting}
                  style={{ flex: 1, opacity: !probeAnswer.trim() || submitting ? 0.5 : 1 }}
                >
                  {submitting ? "전송 중..." : "답하기"}
                </Button>
                <Button
                  variant="ghost"
                  size="md"
                  onClick={() => handleProbeSubmit(true)}
                  disabled={submitting}
                >
                  24h 후로 미루기
                </Button>
              </div>
            </div>
          )}

          {/* 생성 중 */}
          {phase === "generating" && (
            <div className="w-full max-w-sm flex flex-col items-center gap-4 py-12">
              <p
                className="text-[14px] text-center"
                style={{
                  fontFamily: "var(--font-feeling)",
                  color: "var(--color-text-secondary)",
                  lineHeight: "1.8",
                  letterSpacing: "0.02em",
                }}
              >
                내일의 너가 메시지 작성 중...
              </p>
            </div>
          )}

          {/* 카드 */}
          {phase === "card" && cardData && personaData && !destroyed && (
            <div className="w-full max-w-sm flex flex-col gap-4">
              <ScenarioCard
                card={cardData}
                persona={personaData}
                onDestroy={handleDestroy}
                onTimerStart={handleTimerStart}
                onToneFeedback={handleToneFeedback}
              />

              {/* 결정 버튼 */}
              <div
                className="flex gap-2 justify-center flex-wrap"
                role="group"
                aria-label="다음 결정"
              >
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleDecision("transition")}
                  aria-label="시작하기"
                >
                  [t] 시작
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleDecision("continue")}
                  aria-label="계속 미루기"
                >
                  [c] 계속
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleDecision("report")}
                  aria-label="리포트 보기"
                >
                  [r] 리포트
                </Button>
              </div>
            </div>
          )}

          {/* 카드 파괴 후 빈 상태 */}
          {phase === "card" && destroyed && (
            <div className="w-full max-w-sm flex flex-col items-center gap-4 py-12">
              <p
                className="text-[13px] text-center"
                style={{
                  fontFamily: "var(--font-feeling)",
                  color: "var(--color-text-secondary)",
                  opacity: 0.7,
                }}
              >
                메시지가 삭제됐어요.
              </p>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setPhase("input");
                  setAvoidanceText("");
                  setTimelineHint("");
                  setSessionId(null);
                  setCardData(null);
                  setPersonaData(null);
                  setDestroyed(false);
                  setProbeQuestion(null);
                  setProbeAnswer("");
                }}
              >
                다시 시작
              </Button>
            </div>
          )}

          {/* 결정 후 후속 메시지 */}
          {phase === "post_decision" && sessionId && (
            <div className="w-full max-w-sm flex flex-col items-center gap-4 py-12">
              <p
                className="text-[14px] text-center"
                style={{
                  fontFamily: "var(--font-feeling)",
                  color: "var(--color-text-primary)",
                  lineHeight: "1.8",
                }}
              >
                지금 어땠나요?
              </p>
              <p
                className="text-[13px] text-center"
                style={{
                  fontFamily: "var(--font-feeling)",
                  color: "var(--color-text-secondary)",
                  opacity: 0.8,
                }}
              >
                24시간 후에 다시 알려드릴까요?
              </p>
              <div className="flex gap-3 flex-wrap justify-center">
                <Link
                  href={`/regret/${sessionId}`}
                  className="text-[13px] underline"
                  style={{
                    fontFamily: "var(--font-feeling)",
                    color: "var(--color-text-secondary)",
                  }}
                >
                  지금 바로 회고
                </Link>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setPhase("input");
                    setAvoidanceText("");
                    setTimelineHint("");
                    setSessionId(null);
                    setCardData(null);
                    setPersonaData(null);
                    setProbeQuestion(null);
                    setProbeAnswer("");
                  }}
                >
                  처음으로
                </Button>
              </div>
            </div>
          )}
        </section>
      </SocialBlurGuard>

      {/* UndoToast */}
      {showUndoToast && (
        <UndoToast
          message="메시지가 삭제됐어요."
          durationMs={3000}
          onDismiss={() => setShowUndoToast(false)}
        />
      )}
    </main>
  );
}
