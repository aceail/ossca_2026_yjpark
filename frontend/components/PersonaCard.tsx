"use client";

import React from "react";
import type { Persona } from "../lib/personas";
import type { ScenarioCard } from "../lib/api";

interface PersonaCardProps {
  persona: Persona;
  selected?: boolean;
  onSelect?: (p: Persona) => void;
  preview?: ScenarioCard;
}

const perspectiveLabel: Record<Persona["perspective"], string> = {
  "1st": "1인칭",
  "2nd": "2인칭",
  "3rd": "3인칭",
};

const toneModeLabel: Record<Persona["tone_mode"], string> = {
  Quiet: "조용한",
  Sharp: "날카로운",
  Witty: "위트있는",
  Savage: "직설적인",
};

export function PersonaCard({
  persona,
  selected = false,
  onSelect,
  preview,
}: PersonaCardProps) {
  return (
    <button
      type="button"
      onClick={() => onSelect?.(persona)}
      aria-pressed={selected}
      aria-label={`${persona.name} 페르소나 선택`}
      className="w-full text-left flex overflow-hidden rounded-[var(--card-radius)] transition-all duration-150 cursor-pointer"
      style={{
        backgroundColor: "var(--color-bg-card)",
        border: selected
          ? `2px solid ${persona.avatar_color}`
          : "1px solid var(--color-border-subtle)",
        boxShadow: selected
          ? `0 0 0 1px ${persona.avatar_color}22`
          : "0 2px 8px rgba(0,0,0,0.06), 0 0 0 1px var(--color-border-subtle)",
      }}
    >
      {/* 좌측 색 띠 */}
      <div
        className="flex-shrink-0 w-1.5"
        style={{ backgroundColor: persona.avatar_color }}
        aria-hidden="true"
      />

      {/* 본문 */}
      <div className="flex-1 px-4 py-3 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span aria-hidden="true" className="text-lg leading-none">
            {persona.avatar_icon}
          </span>
          <span
            className="font-medium text-[14px]"
            style={{
              fontFamily: "var(--font-feeling)",
              color: "var(--color-text-primary)",
            }}
          >
            {persona.name}
          </span>
          <span
            className="text-[11px] ml-auto flex-shrink-0"
            style={{
              color: "var(--color-text-secondary)",
              letterSpacing: "var(--text-micro-tracking)",
            }}
          >
            {perspectiveLabel[persona.perspective]} · {toneModeLabel[persona.tone_mode]}
          </span>
        </div>

        <p
          className="text-[13px] leading-relaxed truncate"
          style={{
            fontFamily: "var(--font-feeling)",
            color: "var(--color-text-secondary)",
            fontStyle: "italic",
          }}
        >
          &ldquo;{persona.greeting}&rdquo;
        </p>

        {/* 미리보기 카드 */}
        {preview && (
          <div
            className="mt-3 px-3 py-2 rounded text-[12px] leading-relaxed"
            style={{
              backgroundColor: "var(--color-bg-base)",
              border: "1px solid var(--color-border-subtle)",
              color: "var(--color-text-secondary)",
              fontFamily: "var(--font-fact)",
            }}
          >
            {preview.fact}
          </div>
        )}
      </div>
    </button>
  );
}
