"use client";

import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error("[app-error]", error);
  }, [error]);

  return (
    <main
      className="min-h-screen p-6 max-w-2xl mx-auto"
      style={{
        backgroundColor: "var(--color-bg-base)",
        color: "var(--color-text-primary)",
      }}
    >
      <h1
        className="text-[20px] font-semibold mb-3"
        style={{ fontFamily: "var(--font-feeling)" }}
      >
        ⚠ 페이지 오류
      </h1>
      <p
        className="text-[12px] mb-4"
        style={{ color: "var(--color-text-secondary)" }}
      >
        무엇이 잘못됐는지 그대로 보여드릴게요. 새로고침해도 안 되면 메시지를 캡처해주세요.
      </p>
      <pre
        className="text-[11px] whitespace-pre-wrap break-words rounded-lg p-3 mb-4"
        style={{
          backgroundColor: "var(--color-bg-card)",
          border: "1px solid var(--color-border-subtle)",
          color: "#B00020",
          fontFamily: "monospace",
        }}
      >
        {error?.name}: {error?.message}
        {error?.digest ? `\n\ndigest: ${error.digest}` : ""}
        {error?.stack ? `\n\n${error.stack.slice(0, 800)}` : ""}
      </pre>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={reset}
          className="px-3 py-1.5 rounded-lg text-[12px]"
          style={{
            backgroundColor: "var(--color-action-bg)",
            color: "var(--color-action-text)",
          }}
        >
          다시 시도
        </button>
        <a
          href="/"
          className="px-3 py-1.5 rounded-lg text-[12px] underline-offset-2 hover:underline"
          style={{ color: "var(--color-text-secondary)" }}
        >
          홈으로
        </a>
      </div>
    </main>
  );
}
