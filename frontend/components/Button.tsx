"use client";

import React from "react";

type ButtonVariant = "primary" | "ghost" | "destruct" | "action" | "feedback-chip";
type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  children: React.ReactNode;
}

const variantStyles: Record<ButtonVariant, string> = {
  primary:
    "bg-[var(--color-action-bg)] text-[var(--color-action-text)] hover:bg-[var(--color-action-hover)] border border-transparent",
  ghost:
    "bg-transparent text-[var(--color-text-secondary)] border border-[var(--color-border-subtle)] hover:border-[var(--color-text-secondary)]",
  destruct:
    "bg-transparent text-[var(--color-text-secondary)] border border-transparent opacity-40 hover:opacity-100 transition-opacity",
  action:
    "bg-[var(--color-action-bg)] text-[var(--color-action-text)] hover:bg-[var(--color-action-hover)] w-full flex items-center gap-3",
  "feedback-chip":
    "bg-transparent text-[var(--color-text-secondary)] border border-transparent opacity-35 hover:opacity-100 hover:underline transition-opacity text-[11px]",
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: "px-3 py-1.5 text-[11px] rounded-md",
  md: "px-4 py-2 text-[13px] rounded-lg",
  lg: "px-5 py-3 text-[15px] rounded-lg",
};

export function Button({
  variant = "primary",
  size = "md",
  className = "",
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      className={[
        "font-[var(--font-feeling)] transition-colors cursor-pointer select-none",
        variantStyles[variant],
        sizeStyles[size],
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      {...props}
    >
      {children}
    </button>
  );
}
