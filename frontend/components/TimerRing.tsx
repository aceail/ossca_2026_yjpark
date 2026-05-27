"use client";

import React, { useEffect, useRef, useState } from "react";

interface TimerRingProps {
  seconds: number;
  color?: string;
  size?: number;
  strokeWidth?: number;
  onTick?: (remaining: number) => void;
  onComplete?: () => void;
  autostart?: boolean;
}

export function TimerRing({
  seconds,
  color = "var(--color-timer-regret)",
  size = 28,
  strokeWidth = 3,
  onTick,
  onComplete,
  autostart = false,
}: TimerRingProps) {
  const [remaining, setRemaining] = useState(seconds);
  const [running, setRunning] = useState(autostart);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = (seconds - remaining) / seconds;
  const dashOffset = circumference * (1 - progress);
  const nearEnd = remaining <= 5 && remaining > 0 && running;

  useEffect(() => {
    if (!running) return;

    intervalRef.current = setInterval(() => {
      setRemaining((prev) => {
        const next = prev - 1;
        onTick?.(next);
        if (next <= 0) {
          setRunning(false);
          onComplete?.();
          return 0;
        }
        return next;
      });
    }, 1000);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [running, onTick, onComplete]);

  const start = () => {
    setRemaining(seconds);
    setRunning(true);
  };

  const stop = () => {
    setRunning(false);
    setRemaining(seconds);
    if (intervalRef.current) clearInterval(intervalRef.current);
  };

  return (
    <span
      className="inline-flex items-center justify-center relative"
      style={{ width: size, height: size }}
      aria-live="polite"
      aria-label={running ? `타이머 ${remaining}초 남음` : "타이머"}
      role="timer"
    >
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className={nearEnd ? "animate-[timer-pulse_1s_ease-in-out_infinite]" : ""}
        style={{ transform: "rotate(-90deg)" }}
      >
        {/* 배경 트랙 */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--color-border-subtle)"
          strokeWidth={strokeWidth}
        />
        {/* 진행 링 */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          style={{ transition: running ? "stroke-dashoffset 1s linear" : "none" }}
        />
      </svg>
      {/* 클릭 토글 — 외부에서 ref로도 제어 가능 */}
      <button
        onClick={running ? stop : start}
        className="absolute inset-0 rounded-full cursor-pointer"
        aria-label={running ? "타이머 중단" : "타이머 시작"}
        style={{ opacity: 0 }}
        tabIndex={-1}
      />
    </span>
  );
}
