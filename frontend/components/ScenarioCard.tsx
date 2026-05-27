"use client";

import React, { useState } from "react";
import type { Persona } from "../lib/personas";
import type { ScenarioCard as ScenarioCardData, ToneFeedbackKind } from "../lib/api";
import { TimerRing } from "./TimerRing";
import { Button } from "./Button";

interface ScenarioCardProps {
  card: ScenarioCardData;
  persona: Persona;
  onDestroy?: () => void;
  onTimerStart?: () => void;
  onToneFeedback?: (kind: ToneFeedbackKind) => void;
}

const cardTypeStyles: Record<
  ScenarioCardData["card_type"],
  { bg: string; border: string; accent: string; dot: string; timerColor: string }
> = {
  regret: {
    bg: "var(--color-regret-bg)",
    border: "var(--color-regret-border)",
    accent: "var(--color-regret-accent)",
    dot: "var(--color-regret-dot)",
    timerColor: "var(--color-timer-regret)",
  },
  recovery: {
    bg: "var(--color-recovery-bg)",
    border: "var(--color-recovery-border)",
    accent: "var(--color-recovery-accent)",
    dot: "var(--color-recovery-dot)",
    timerColor: "var(--color-timer-recovery)",
  },
  soft_stop: {
    bg: "var(--color-softstop-bg)",
    border: "var(--color-softstop-border)",
    accent: "var(--color-softstop-accent)",
    dot: "var(--color-softstop-dot)",
    timerColor: "var(--color-timer-regret)",
  },
  paradoxical_validation: {
    bg: "var(--color-paradox-bg)",
    border: "var(--color-paradox-border)",
    accent: "var(--color-paradox-accent)",
    dot: "var(--color-paradox-dot)",
    timerColor: "var(--color-timer-recovery)",
  },
};

const TONE_FEEDBACK_OPTIONS: Array<{ kind: ToneFeedbackKind; label: string }> = [
  { kind: "too_harsh", label: "너무 세다" },
  { kind: "too_parental", label: "부모 같다" },
  { kind: "too_generic", label: "너무 일반론이다" },
  { kind: "too_therapeutic", label: "너무 치료사 같다" },
  { kind: "not_relevant", label: "나랑 안 맞다" },
  { kind: "just_right", label: "딱 좋다" },
];

const SOFT_STOP_OPTIONS = [
  { label: "작은 행동 하나만" },
  { label: "감정만 기록" },
  { label: "도움 자원 보기" },
  { label: "오늘 앱 끄기" },
];

export function ScenarioCard({
  card,
  persona,
  onDestroy,
  onTimerStart,
  onToneFeedback,
}: ScenarioCardProps) {
  const [timerActive, setTimerActive] = useState(false);
  const [timerDone, setTimerDone] = useState(false);
  const [selectedFeedback, setSelectedFeedback] = useState<ToneFeedbackKind | null>(null);

  const styles = cardTypeStyles[card.card_type];
  const isSoftStop = card.card_type === "soft_stop";
  const isParadox = card.card_type === "paradoxical_validation";

  const handleTimerStart = () => {
    setTimerActive(true);
    onTimerStart?.();
  };

  const handleTimerComplete = () => {
    setTimerActive(false);
    setTimerDone(true);
  };

  const handleFeedback = (kind: ToneFeedbackKind) => {
    setSelectedFeedback(kind);
    onToneFeedback?.(kind);
  };

  return (
    <article
      className="card-enter overflow-hidden rounded-[var(--card-radius)] flex"
      style={{
        maxWidth: "var(--card-max-width)",
        width: "100%",
        backgroundColor: styles.bg,
        border: `1px solid ${styles.border}`,
        boxShadow:
          "0 2px 8px rgba(0,0,0,0.06), 0 0 0 1px var(--color-border-subtle)",
      }}
      role="dialog"
      aria-modal="true"
      aria-label="내일의 너 시나리오 카드"
    >
      {/* 좌측 색 띠 (6px) */}
      <div
        className="flex-shrink-0 w-1.5"
        style={{ backgroundColor: styles.border }}
        aria-hidden="true"
      />

      {/* 카드 본문 */}
      <div
        className="flex-1 flex flex-col gap-[var(--card-gap)] p-[var(--card-padding)] min-w-0"
      >
        {/* 헤더 */}
        {!isParadox && (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span
                aria-hidden="true"
                className="text-[8px]"
                style={{ color: styles.dot }}
              >
                ●
              </span>
              <span
                className="text-[11px]"
                style={{
                  fontFamily: "var(--font-feeling)",
                  color: "var(--color-text-secondary)",
                  letterSpacing: "0.04em",
                }}
              >
                {persona.avatar_icon} {persona.name}
              </span>
            </div>
            <Button
              variant="destruct"
              size="sm"
              onClick={onDestroy}
              aria-label="이 카드 즉시 삭제"
              className="text-[16px] px-1 py-0 leading-none"
            >
              ⊗
            </Button>
          </div>
        )}

        {isParadox && (
          <div className="flex justify-end">
            <Button
              variant="destruct"
              size="sm"
              onClick={onDestroy}
              aria-label="이 카드 즉시 삭제"
              className="text-[16px] px-1 py-0 leading-none"
            >
              ⊗
            </Button>
          </div>
        )}

        {/* 구분선 */}
        {!isParadox && (
          <hr style={{ borderColor: styles.border, opacity: 0.4 }} />
        )}

        {/* P0-24: Moral Licensing 너지 — 24h 사용 빈도 ≥ 임계 시 부드러운 자기참조 */}
        {card.moral_licensing_nudge && (
          <div
            role="status"
            aria-live="polite"
            className="rounded-md px-3 py-2"
            style={{
              backgroundColor: "var(--color-action-bg)",
              border: `1px dashed ${styles.border}`,
              fontFamily: "var(--font-feeling)",
              fontSize: "12px",
              lineHeight: "1.55",
              color: "var(--color-text-secondary)",
            }}
          >
            {card.moral_licensing_nudge}
          </div>
        )}

        {/* soft_stop: 단일 메시지 + 선택지 */}
        {isSoftStop && (
          <>
            <p
              style={{
                fontFamily: "var(--font-feeling)",
                fontSize: "var(--text-body-size)",
                lineHeight: "var(--text-body-line)",
                color: "var(--color-text-primary)",
              }}
            >
              {card.safety_message ?? card.fact}
            </p>
            <hr style={{ borderColor: styles.border, opacity: 0.4 }} />
            <div
              role="radiogroup"
              aria-label="지금 선택"
              className="grid grid-cols-2 gap-2"
            >
              {SOFT_STOP_OPTIONS.map(({ label }) => (
                <Button
                  key={label}
                  variant="ghost"
                  size="sm"
                  className="text-left"
                >
                  {label}
                </Button>
              ))}
            </div>
          </>
        )}

        {/* paradox: 중앙 단일 텍스트 */}
        {isParadox && (
          <>
            <p
              className="text-center py-6"
              style={{
                fontFamily: "var(--font-fact)",
                fontSize: "20px",
                lineHeight: "1.6",
                color: "var(--color-text-primary)",
              }}
            >
              {card.safety_message ?? card.fact}
            </p>
            <hr style={{ borderColor: styles.border, opacity: 0.4 }} />
            <div className="flex justify-center">
              <Button variant="ghost" size="md">
                5분 후에 다시
              </Button>
            </div>
          </>
        )}

        {/* regret / recovery: 3레이어 */}
        {!isSoftStop && !isParadox && (
          <>
            {/* 사실 레이어 */}
            <p
              style={{
                fontFamily: "var(--font-fact)",
                fontSize: "var(--text-fact-size)",
                lineHeight: "var(--text-fact-line)",
                color: "var(--color-text-primary)",
                fontWeight: 400,
              }}
            >
              {card.fact}
            </p>

            {/* 감정 레이어 */}
            <p
              style={{
                fontFamily: "var(--font-feeling)",
                fontSize: "var(--text-body-size)",
                lineHeight: "var(--text-body-line)",
                color: "var(--color-text-secondary)",
                fontWeight: 400,
              }}
            >
              {card.feeling}
            </p>

            {/* 운동성 버튼 + 타이머 */}
            <button
              type="button"
              onClick={timerDone ? undefined : timerActive ? undefined : handleTimerStart}
              disabled={timerDone}
              aria-label={`${card.micro_action} — 30초 타이머 시작`}
              className="flex items-center gap-3 w-full px-4 py-3 rounded-lg transition-colors text-left"
              style={{
                backgroundColor: "var(--color-action-bg)",
                color: "var(--color-action-text)",
                fontFamily: "var(--font-feeling)",
                fontSize: "var(--text-body-size)",
                cursor: timerDone ? "default" : "pointer",
              }}
            >
              <span aria-hidden="true" className="flex-shrink-0 text-[12px]">
                ▶
              </span>
              <span className="flex-1">
                {timerDone ? "시작했군요." : card.micro_action}
              </span>
              {(timerActive || timerDone) && (
                <TimerRing
                  seconds={30}
                  color={styles.timerColor}
                  autostart={timerActive}
                  onComplete={handleTimerComplete}
                />
              )}
            </button>

            {/* 톤 피드백 */}
            <div
              role="group"
              aria-label="카드 톤 피드백"
              className="flex flex-wrap gap-2 overflow-x-auto"
            >
              {TONE_FEEDBACK_OPTIONS.map(({ kind, label }) => (
                <Button
                  key={kind}
                  variant="feedback-chip"
                  size="sm"
                  onClick={() => handleFeedback(kind)}
                  aria-pressed={selectedFeedback === kind}
                  style={
                    selectedFeedback === kind
                      ? { opacity: 1, textDecoration: "underline" }
                      : {}
                  }
                >
                  {selectedFeedback === kind && (
                    <span aria-hidden="true" className="mr-1">
                      ✓
                    </span>
                  )}
                  {label}
                </Button>
              ))}
            </div>
          </>
        )}
      </div>
    </article>
  );
}
