import React from "react";

interface ProgressProps {
  current: number;
  total: number;
  className?: string;
}

export function Progress({ current, total, className = "" }: ProgressProps) {
  return (
    <div
      className={["flex items-center gap-1.5", className].join(" ")}
      role="progressbar"
      aria-valuenow={current}
      aria-valuemin={1}
      aria-valuemax={total}
      aria-label={`${total}단계 중 ${current}단계`}
    >
      {Array.from({ length: total }, (_, i) => (
        <span
          key={i}
          className="block rounded-full transition-all duration-200"
          style={{
            width: i + 1 === current ? "20px" : "8px",
            height: "8px",
            backgroundColor:
              i + 1 <= current
                ? "var(--color-regret-accent)"
                : "var(--color-border-subtle)",
          }}
          aria-hidden="true"
        />
      ))}
    </div>
  );
}
