"use client";

import React from "react";
import { Progress } from "./Progress";
import { Button } from "./Button";

interface OnboardingOption {
  value: string;
  label: string;
  warning?: boolean;
}

interface OnboardingCardProps {
  stepIndex: 1 | 2 | 3 | 4 | 5;
  total?: 5;
  question: string;
  options: OnboardingOption[];
  onSelect: (value: string) => void;
  allowSkip?: boolean;
  onSkip?: () => void;
}

export function OnboardingCard({
  stepIndex,
  total = 5,
  question,
  options,
  onSelect,
  allowSkip = false,
  onSkip,
}: OnboardingCardProps) {
  return (
    <div
      className="card-enter flex flex-col gap-[var(--card-gap)] p-[var(--card-padding)] rounded-[var(--card-radius)]"
      style={{
        maxWidth: "var(--card-max-width)",
        width: "100%",
        backgroundColor: "var(--color-bg-card)",
        border: "1px solid var(--color-border-subtle)",
        boxShadow: "0 2px 8px rgba(0,0,0,0.06), 0 0 0 1px var(--color-border-subtle)",
      }}
      role="form"
      aria-label={`온보딩 ${stepIndex}/${total}단계`}
    >
      {/* 진행 표시 */}
      <Progress current={stepIndex} total={total} />

      {/* 질문 */}
      <p
        style={{
          fontFamily: "var(--font-fact)",
          fontSize: "var(--text-fact-size)",
          lineHeight: "var(--text-fact-line)",
          color: "var(--color-text-primary)",
          fontWeight: 400,
        }}
      >
        {question}
      </p>

      {/* 선택지 */}
      <div className="flex flex-col gap-2" role="list">
        {options.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => onSelect(opt.value)}
            role="listitem"
            className="flex items-center gap-2 w-full px-4 py-3 rounded-lg text-left transition-colors"
            style={{
              fontFamily: "var(--font-feeling)",
              fontSize: "var(--text-body-size)",
              lineHeight: "var(--text-body-line)",
              backgroundColor: "var(--color-bg-base)",
              border: "1px solid var(--color-border-subtle)",
              color: "var(--color-text-primary)",
              cursor: "pointer",
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLButtonElement).style.borderColor =
                "var(--color-text-secondary)";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.borderColor =
                "var(--color-border-subtle)";
            }}
          >
            {opt.warning && (
              <span
                aria-label="주의"
                title="이 선택지에 대해 확인이 필요합니다"
                className="flex-shrink-0 text-[12px]"
                style={{ color: "var(--color-softstop-accent)" }}
              >
                ⚠
              </span>
            )}
            <span>{opt.label}</span>
          </button>
        ))}
      </div>

      {/* 건너뛰기 */}
      {allowSkip && (
        <div className="flex justify-end">
          <Button variant="ghost" size="sm" onClick={onSkip}>
            건너뛰기
          </Button>
        </div>
      )}
    </div>
  );
}
