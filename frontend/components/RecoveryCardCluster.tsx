"use client";

import React from "react";
import { authHeaders } from "../lib/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8001";

export interface RecoveryCardData {
  fact?: string;
  feeling?: string;
  micro?: string;
  deepLink?: string;
}

interface Props {
  data: RecoveryCardData;
  onDismiss?: () => void;
}

function extractTaskId(link: string | undefined): string | null {
  if (!link) return null;
  const m = link.match(/focus=(\d+)/);
  return m ? m[1] : null;
}

export function RecoveryCardCluster({ data, onDismiss }: Props) {
  const deepLink = data.deepLink || "/tasks";
  const taskId = extractTaskId(deepLink);

  const goDeep = () => {
    if (typeof window !== "undefined") window.location.href = deepLink;
  };

  const markDone = async () => {
    if (!taskId) return;
    try {
      await fetch(`${API_BASE}/api/tasks/${taskId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ status: "done" }),
      });
      onDismiss?.();
    } catch {
      // silent
    }
  };

  return (
    <div
      className="flex rounded-2xl overflow-hidden"
      style={{
        border: "1px solid var(--color-recovery-border)",
      }}
    >
      {/* 좌측 세로 띠 */}
      <div
        className="w-1.5 flex-shrink-0"
        style={{ backgroundColor: "var(--color-recovery-border)" }}
        aria-hidden
      />
      <div className="flex-1 flex flex-col">
        {/* 🪞 fact */}
        {data.fact && (
          <button
            type="button"
            onClick={goDeep}
            className="card-mount text-left px-4 py-3 flex items-center justify-between gap-3 group transition-transform duration-100 active:scale-[0.99]"
            style={{
              backgroundColor: "var(--color-bg-card)",
              animationDelay: "0ms",
              borderBottom: "1px solid var(--color-border-subtle)",
            }}
            aria-label="작업 상세 보기"
          >
            <span className="text-[14px]" style={{ color: "var(--color-text-primary)", fontFamily: "var(--font-feeling)" }}>
              <span aria-hidden className="mr-2">🪞</span>{data.fact}
            </span>
            <span
              aria-hidden
              className="text-[12px] opacity-40 group-hover:opacity-80 group-hover:translate-x-0.5 transition-all duration-150 flex-shrink-0"
              style={{ color: "var(--color-recovery-accent)" }}
            >
              →
            </span>
          </button>
        )}
        {/* 🫧 feeling */}
        {data.feeling && (
          <button
            type="button"
            onClick={goDeep}
            className="card-mount text-left px-4 py-3 flex items-center justify-between gap-3 group transition-transform duration-100 active:scale-[0.99]"
            style={{
              backgroundColor: "var(--color-recovery-bg)",
              animationDelay: "60ms",
              borderBottom: "1px solid var(--color-border-subtle)",
            }}
            aria-label="작업 상세 보기"
          >
            <span className="text-[13px]" style={{ color: "var(--color-text-secondary)", fontFamily: "var(--font-feeling)" }}>
              <span aria-hidden className="mr-2">🫧</span>{data.feeling}
            </span>
            <span
              aria-hidden
              className="text-[12px] opacity-40 group-hover:opacity-80 group-hover:translate-x-0.5 transition-all duration-150 flex-shrink-0"
              style={{ color: "var(--color-recovery-accent)" }}
            >
              →
            </span>
          </button>
        )}
        {/* 👣 micro */}
        {data.micro && (
          <div
            className="card-mount px-4 py-3 flex flex-col gap-2"
            style={{
              backgroundColor: "var(--color-action-bg)",
              animationDelay: "120ms",
            }}
          >
            <p className="text-[14px] font-medium" style={{ color: "var(--color-action-text)", fontFamily: "var(--font-feeling)" }}>
              <span aria-hidden className="mr-2">👣</span>{data.micro}
            </p>
            <button
              type="button"
              onClick={goDeep}
              className="w-full h-11 rounded-lg text-[14px] font-medium transition-transform duration-100 active:scale-[0.97]"
              style={{
                backgroundColor: "rgba(255,255,255,0.15)",
                color: "var(--color-action-text)",
              }}
            >
              ▶ 시작
            </button>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={markDone}
                disabled={!taskId}
                className="flex-1 h-10 rounded-lg text-[13px] transition-transform duration-100 active:scale-[0.97]"
                style={{
                  backgroundColor: "rgba(255,255,255,0.08)",
                  color: "rgba(255,255,255,0.7)",
                  border: "1px solid rgba(255,255,255,0.15)",
                }}
              >
                ✓ 완료
              </button>
              <button
                type="button"
                onClick={() => onDismiss?.()}
                className="flex-1 h-10 rounded-lg text-[13px] transition-transform duration-100 active:scale-[0.97]"
                style={{
                  backgroundColor: "rgba(255,255,255,0.08)",
                  color: "rgba(255,255,255,0.7)",
                  border: "1px solid rgba(255,255,255,0.15)",
                }}
              >
                ⏰ 30분후
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
