"use client";

import React, { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Logo } from "../../../components/Logo";
import { Button } from "../../../components/Button";
import { useUser } from "../../../lib/hooks/useUser";
import { apiPost } from "../../../lib/api";

// ── 타입 ─────────────────────────────────────────────────────────────────────

interface RegretFormState {
  intensity: number;
  accuracy: number;
  returnIntent: number;
  freeText: string;
}

// ── 슬라이더 컴포넌트 ─────────────────────────────────────────────────────────

function MinimalSlider({
  label,
  value,
  min,
  max,
  onChange,
  description,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (v: number) => void;
  description?: string;
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <label
          className="text-[13px]"
          style={{
            fontFamily: "var(--font-feeling)",
            color: "var(--color-text-primary)",
          }}
        >
          {label}
        </label>
        <span
          className="text-[18px] font-semibold tabular-nums"
          style={{ color: "var(--color-text-primary)", minWidth: "2ch", textAlign: "right" }}
          aria-live="polite"
        >
          {value}
        </span>
      </div>
      {description && (
        <p
          className="text-[11px]"
          style={{
            fontFamily: "var(--font-feeling)",
            color: "var(--color-text-secondary)",
            opacity: 0.7,
          }}
        >
          {description}
        </p>
      )}
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-[var(--color-regret-accent)]"
        aria-label={label}
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={value}
      />
      <div
        className="flex justify-between text-[10px]"
        style={{ color: "var(--color-text-secondary)", opacity: 0.5 }}
        aria-hidden="true"
      >
        <span>{min}</span>
        <span>{max}</span>
      </div>
    </div>
  );
}

// ── 메인 컴포넌트 ─────────────────────────────────────────────────────────────

export default function RegretPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = typeof params.sessionId === "string" ? params.sessionId : "";
  const { userId, loading: userLoading } = useUser();

  const [form, setForm] = useState<RegretFormState>({
    intensity: 5,
    accuracy: 3,
    returnIntent: 3,
    freeText: "",
  });

  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [cardId, setCardId] = useState<string | null>(null);

  // card_id를 localStorage에서 가져오기 (scenario 페이지에서 저장)
  useEffect(() => {
    if (!sessionId) return;
    const stored = localStorage.getItem(`card_id_${sessionId}`);
    if (stored) setCardId(stored);
  }, [sessionId]);

  if (!sessionId) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <p
          style={{
            fontFamily: "var(--font-feeling)",
            color: "var(--color-text-secondary)",
          }}
        >
          세션 정보가 없어요.{" "}
          <Link href="/scenario" className="underline">
            돌아가기
          </Link>
        </p>
      </main>
    );
  }

  const handleSubmit = async () => {
    if (!sessionId) return;
    setSubmitting(true);
    setErrorMsg(null);

    try {
      // 1) 후회 강도
      await apiPost(`/api/sessions/${sessionId}/regret`, {
        intensity: form.intensity,
        free_text: form.freeText.trim() || undefined,
      });

      // 2) 카드 정확도 + return intent (card_id 있을 때만)
      if (cardId) {
        await Promise.allSettled([
          apiPost(`/api/scenario-cards/${cardId}/accuracy`, {
            accuracy: form.accuracy,
          }),
          apiPost(`/api/scenario-cards/${cardId}/return-intent`, {
            intent: form.returnIntent,
          }),
        ]);
      }

      setSubmitted(true);
    } catch {
      setErrorMsg("기록 중 오류가 발생했어요. 잠시 후 다시 시도해줘요.");
    } finally {
      setSubmitting(false);
    }
  };

  if (userLoading) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <p style={{ fontFamily: "var(--font-feeling)", color: "var(--color-text-secondary)" }}>
          준비 중...
        </p>
      </main>
    );
  }

  return (
    <main
      className="min-h-screen flex flex-col"
      style={{ backgroundColor: "var(--color-bg-page)" }}
    >
      {/* 헤더 */}
      <header
        className="flex items-center justify-between px-6 py-4"
        style={{ borderBottom: "1px solid var(--color-border-subtle)" }}
      >
        <Logo className="text-[15px]" />
        <Link
          href="/scenario"
          className="text-[11px]"
          style={{
            fontFamily: "var(--font-feeling)",
            color: "var(--color-text-secondary)",
            opacity: 0.6,
          }}
        >
          ← 돌아가기
        </Link>
      </header>

      {/* 본문 */}
      <section className="flex-1 flex flex-col items-center px-4 py-10 gap-8">
        {!submitted ? (
          <div className="w-full max-w-sm flex flex-col gap-8">
            {/* 안내 */}
            <div className="flex flex-col gap-1">
              <p
                className="text-[16px]"
                style={{
                  fontFamily: "var(--font-fact)",
                  color: "var(--color-text-primary)",
                }}
              >
                그때 어땠나요?
              </p>
              <p
                className="text-[12px]"
                style={{
                  fontFamily: "var(--font-feeling)",
                  color: "var(--color-text-secondary)",
                  opacity: 0.7,
                }}
              >
                솔직하게 기록해줘요.
              </p>
            </div>

            {/* 에러 */}
            {errorMsg && (
              <p
                className="text-[13px]"
                style={{
                  fontFamily: "var(--font-feeling)",
                  color: "var(--color-text-secondary)",
                  opacity: 0.8,
                }}
              >
                {errorMsg}
              </p>
            )}

            {/* 슬라이더들 */}
            <div className="flex flex-col gap-6">
              <MinimalSlider
                label="후회 강도"
                value={form.intensity}
                min={0}
                max={10}
                onChange={(v) => setForm((f) => ({ ...f, intensity: v }))}
                description="그때 얼마나 후회했나요? (0 = 전혀, 10 = 매우)"
              />

              <hr style={{ borderColor: "var(--color-border-subtle)", opacity: 0.5 }} />

              <MinimalSlider
                label="카드 정확도"
                value={form.accuracy}
                min={1}
                max={5}
                onChange={(v) => setForm((f) => ({ ...f, accuracy: v }))}
                description="그 카드가 내 상황에 맞았나요? (1 = 전혀, 5 = 딱 맞음)"
              />

              <hr style={{ borderColor: "var(--color-border-subtle)", opacity: 0.5 }} />

              <MinimalSlider
                label="다음에도 앱을 열 의향"
                value={form.returnIntent}
                min={1}
                max={5}
                onChange={(v) => setForm((f) => ({ ...f, returnIntent: v }))}
                description="다음에도 비슷한 상황에서 앱을 열 것 같나요? (1 = 아니, 5 = 응)"
              />
            </div>

            {/* 자유 텍스트 */}
            <div className="flex flex-col gap-2">
              <label
                className="text-[13px]"
                style={{
                  fontFamily: "var(--font-feeling)",
                  color: "var(--color-text-primary)",
                }}
              >
                더 하고 싶은 말 (선택)
              </label>
              <textarea
                value={form.freeText}
                onChange={(e) => {
                  if (e.target.value.length <= 200) {
                    setForm((f) => ({ ...f, freeText: e.target.value }));
                  }
                }}
                placeholder="200자 이내로 자유롭게..."
                rows={3}
                className="w-full resize-none rounded-lg px-4 py-3 text-[13px] outline-none"
                style={{
                  backgroundColor: "var(--color-bg-card)",
                  border: "1px solid var(--color-border-subtle)",
                  color: "var(--color-text-primary)",
                  fontFamily: "var(--font-feeling)",
                  lineHeight: "1.6",
                }}
                aria-label="자유 텍스트 입력"
              />
              <p
                className="text-[10px] text-right"
                style={{ color: "var(--color-text-secondary)", opacity: 0.5 }}
              >
                {form.freeText.length} / 200
              </p>
            </div>

            {/* 제출 버튼 */}
            <Button
              variant="primary"
              size="md"
              onClick={handleSubmit}
              disabled={submitting}
              style={{ opacity: submitting ? 0.5 : 1 }}
            >
              {submitting ? "기록 중..." : "기록하기"}
            </Button>
          </div>
        ) : (
          /* 제출 완료 */
          <div className="w-full max-w-sm flex flex-col items-center gap-6 py-16">
            <p
              className="text-[16px] text-center"
              style={{
                fontFamily: "var(--font-fact)",
                color: "var(--color-text-primary)",
                lineHeight: "1.8",
              }}
            >
              기록됐어요.
            </p>
            <p
              className="text-[13px] text-center"
              style={{
                fontFamily: "var(--font-feeling)",
                color: "var(--color-text-secondary)",
                opacity: 0.8,
              }}
            >
              내일도 와줘요.
            </p>
            <Link
              href="/scenario"
              className="text-[13px] underline mt-4"
              style={{
                fontFamily: "var(--font-feeling)",
                color: "var(--color-text-secondary)",
              }}
            >
              메인으로
            </Link>
          </div>
        )}
      </section>
    </main>
  );
}
