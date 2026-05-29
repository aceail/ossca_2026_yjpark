"use client";

import React, { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { authHeaders } from "../../../lib/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8001";

interface EditConfigResponse {
  documentServerUrl: string;
  config: Record<string, unknown> & {
    document: { title: string };
  };
  token: string;
}

declare global {
  interface Window {
    DocsAPI?: {
      DocEditor: new (
        placeholderId: string,
        config: Record<string, unknown>,
      ) => unknown;
    };
  }
}

function injectScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[data-oo-src="${src}"]`);
    if (existing) {
      // 이미 로드된 경우, DocsAPI 존재 시 바로 resolve
      if (window.DocsAPI) return resolve();
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener("error", () => reject(new Error("script load failed")), {
        once: true,
      });
      return;
    }
    const s = document.createElement("script");
    s.src = src;
    s.async = true;
    s.dataset.ooSrc = src;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("script load failed"));
    document.head.appendChild(s);
  });
}

function EditPageInner() {
  const params = useSearchParams();
  const taskId = params.get("taskId");
  const filename = params.get("name");
  const placeholderRef = useRef<HTMLDivElement | null>(null);
  const editorRef = useRef<unknown>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("준비 중...");

  useEffect(() => {
    if (!taskId || !filename) {
      setError("taskId 또는 파일명이 누락됐어요");
      return;
    }
    let cancelled = false;

    const run = async () => {
      try {
        setStatus("편집 설정 가져오는 중...");
        const res = await fetch(
          `${API_BASE}/api/tasks/${taskId}/files/${encodeURIComponent(filename)}/edit-config`,
          { headers: { ...authHeaders() } },
        );
        if (!res.ok) {
          const msg = await res.text().catch(() => "");
          throw new Error(`설정 로드 실패 (${res.status})${msg ? `: ${msg.slice(0, 80)}` : ""}`);
        }
        const body: EditConfigResponse = await res.json();
        if (cancelled) return;

        setStatus("OnlyOffice 로딩...");
        await injectScript(`${body.documentServerUrl}/web-apps/apps/api/documents/api.js`);
        if (cancelled) return;
        if (!window.DocsAPI) {
          throw new Error("DocsAPI 미로드 (OnlyOffice 응답 확인)");
        }

        setStatus("");
        const cfg = {
          ...body.config,
          token: body.token,
          width: "100%",
          height: "100%",
          type: "desktop",
        };
        editorRef.current = new window.DocsAPI.DocEditor("oo-placeholder", cfg);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    };

    run();

    return () => {
      cancelled = true;
      // OnlyOffice DocEditor.destroyEditor가 있으면 호출 — 메모리 누수 방지
      const cur = editorRef.current as { destroyEditor?: () => void } | null;
      cur?.destroyEditor?.();
    };
  }, [taskId, filename]);

  // 전체 viewport overlay — root layout의 컨테이너·BottomTabs·globals.css main
  // padding을 모두 escape. OnlyOffice iframe이 정확한 height/width를 받아야
  // 짤리지 않음.
  return (
    <main
      className="fixed inset-0 flex flex-col z-50"
      style={{
        padding: 0,
        margin: 0,
        backgroundColor: "var(--color-bg-base)",
      }}
    >
      <header
        className="flex items-center justify-between px-4 py-2 flex-shrink-0"
        style={{
          borderBottom: "1px solid var(--color-border-subtle)",
          backgroundColor: "var(--color-bg-card)",
          height: "48px",
        }}
      >
        <div className="min-w-0 flex-1">
          <p
            className="text-[13px] font-medium truncate"
            style={{ color: "var(--color-text-primary)" }}
          >
            ✏️ {filename ?? "(파일 없음)"}
          </p>
          {status && (
            <p
              className="text-[11px] truncate"
              style={{ color: "var(--color-text-secondary)" }}
            >
              {status}
            </p>
          )}
        </div>
        <a
          href="/tasks"
          className="text-[12px] underline-offset-2 hover:underline flex-shrink-0 ml-3"
          style={{ color: "var(--color-text-secondary)" }}
        >
          ← 작업으로
        </a>
      </header>
      {error && (
        <div
          className="p-3 text-[12px] flex-shrink-0"
          style={{ color: "#B00020", backgroundColor: "var(--color-bg-base)" }}
        >
          {error}
        </div>
      )}
      <div
        ref={placeholderRef}
        id="oo-placeholder"
        className="flex-1"
        style={{ minHeight: 0, width: "100%" }}
      />
    </main>
  );
}

export default function EditPage() {
  return (
    <Suspense fallback={<div className="p-6 text-[13px]">로딩 중...</div>}>
      <EditPageInner />
    </Suspense>
  );
}
