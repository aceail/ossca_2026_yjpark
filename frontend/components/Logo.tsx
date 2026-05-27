import React from "react";

interface LogoProps {
  className?: string;
}

export function Logo({ className = "" }: LogoProps) {
  return (
    <span
      className={[
        "inline-flex items-center gap-1.5 font-[var(--font-fact)] text-[var(--color-text-primary)] select-none",
        className,
      ].join(" ")}
      aria-label="내일의 너"
    >
      <span aria-hidden="true" className="text-[var(--color-regret-accent)]">
        ◐
      </span>
      <span>내일의 너</span>
    </span>
  );
}
