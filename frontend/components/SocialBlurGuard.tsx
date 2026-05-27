"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";

interface SocialBlurGuardProps {
  children: React.ReactNode;
  idleThresholdMs?: number;
}

export function SocialBlurGuard({
  children,
  idleThresholdMs = 30000,
}: SocialBlurGuardProps) {
  const [blurred, setBlurred] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const resetTimer = useCallback(() => {
    if (blurred) return;
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      setBlurred(true);
    }, idleThresholdMs);
  }, [blurred, idleThresholdMs]);

  useEffect(() => {
    const events = ["mousemove", "mousedown", "keydown", "touchstart", "scroll"];
    events.forEach((e) => window.addEventListener(e, resetTimer, { passive: true }));
    resetTimer();
    return () => {
      events.forEach((e) => window.removeEventListener(e, resetTimer));
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [resetTimer]);

  const handleReveal = () => {
    setBlurred(false);
    resetTimer();
  };

  return (
    <div className="relative">
      <div
        style={{
          filter: blurred ? "blur(8px)" : "none",
          transition: "filter 0.3s ease",
          pointerEvents: blurred ? "none" : "auto",
          userSelect: blurred ? "none" : "auto",
        }}
        aria-hidden={blurred}
      >
        {children}
      </div>

      {blurred && (
        <div
          className="absolute inset-0 flex flex-col items-center justify-center gap-3 cursor-pointer"
          onClick={handleReveal}
          role="button"
          tabIndex={0}
          aria-label="화면 잠금 해제"
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") handleReveal();
          }}
        >
          <p
            className="text-[13px] text-center px-4"
            style={{
              fontFamily: "var(--font-feeling)",
              color: "var(--color-text-secondary)",
              letterSpacing: "0.04em",
            }}
          >
            내일의 너에서 메시지가 왔습니다
          </p>
          <p
            className="text-[11px]"
            style={{ color: "var(--color-text-secondary)", opacity: 0.6 }}
          >
            클릭하여 확인
          </p>
        </div>
      )}
    </div>
  );
}
