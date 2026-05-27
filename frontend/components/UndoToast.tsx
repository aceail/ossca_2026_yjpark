"use client";

import React, { useEffect, useRef } from "react";

interface UndoToastProps {
  message: string;
  onUndo?: () => void;
  durationMs?: number;
  onDismiss?: () => void;
}

export function UndoToast({
  message,
  onUndo,
  durationMs = 3000,
  onDismiss,
}: UndoToastProps) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    timerRef.current = setTimeout(() => {
      onDismiss?.();
    }, durationMs);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [durationMs, onDismiss]);

  return (
    <div
      className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 card-enter"
      role="status"
      aria-live="polite"
    >
      <div
        className="flex items-center gap-4 px-5 py-3 rounded-lg text-[13px]"
        style={{
          backgroundColor: "var(--color-bg-card)",
          border: "1px solid var(--color-border-subtle)",
          boxShadow: "0 2px 12px rgba(0,0,0,0.10)",
          color: "var(--color-text-primary)",
          fontFamily: "var(--font-feeling)",
        }}
      >
        <span>{message}</span>
        {onUndo && (
          <button
            onClick={() => {
              if (timerRef.current) clearTimeout(timerRef.current);
              onUndo();
            }}
            className="underline text-[var(--color-regret-accent)] cursor-pointer hover:opacity-70 transition-opacity"
          >
            되돌리기
          </button>
        )}
      </div>
    </div>
  );
}
