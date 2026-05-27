"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useUser } from "../../lib/hooks/useUser";
import { Button } from "../../components/Button";
import { authHeaders } from "../../lib/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8001";

interface Task {
  id: number;
  user_id: string;
  persona_id?: number | null;
  title: string;
  deadline_at?: string | null;
  folder_path?: string | null;
  status: "open" | "done" | "abandoned";
  last_followup_at?: string | null;
  created_at: string;
  updated_at: string;
}

function daysUntil(deadlineIso: string | null | undefined): string {
  if (!deadlineIso) return "마감 없음";
  const d = new Date(deadlineIso).getTime();
  const now = Date.now();
  const diff = Math.ceil((d - now) / (24 * 60 * 60 * 1000));
  if (diff > 1) return `D-${diff}`;
  if (diff === 1) return "내일 마감";
  if (diff === 0) return "오늘 마감";
  return `${Math.abs(diff)}일 지남`;
}

function urgencyColor(deadlineIso: string | null | undefined, status: string): string {
  if (status === "done") return "var(--color-recovery-accent)";
  if (status === "abandoned") return "var(--color-text-secondary)";
  if (!deadlineIso) return "var(--color-text-secondary)";
  const diff = Math.ceil(
    (new Date(deadlineIso).getTime() - Date.now()) / (24 * 60 * 60 * 1000),
  );
  if (diff < 0) return "#B00020";
  if (diff <= 1) return "var(--color-regret-accent)";
  if (diff <= 3) return "var(--color-recovery-accent)";
  return "var(--color-text-secondary)";
}

export default function TasksPage() {
  const { userId, loading: userLoading } = useUser();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchTasks = useCallback(async (uid: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/tasks?user_id=${uid}`, {
        headers: { ...authHeaders() },
      });
      if (!res.ok) throw new Error(`목록 로드 실패 (${res.status})`);
      const data = await res.json();
      setTasks(data.tasks as Task[]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (userId) fetchTasks(userId);
  }, [userId, fetchTasks]);

  const updateStatus = async (id: number, status: Task["status"]) => {
    if (!userId) return;
    await fetch(`${API_BASE}/api/tasks/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ status }),
    });
    await fetchTasks(userId);
  };

  const remove = async (id: number) => {
    if (!userId) return;
    if (!confirm("이 작업을 영구 삭제할까요?")) return;
    await fetch(`${API_BASE}/api/tasks/${id}`, {
      method: "DELETE",
      headers: { ...authHeaders() },
    });
    await fetchTasks(userId);
  };

  const [folderEditId, setFolderEditId] = useState<number | null>(null);
  const [folderDraft, setFolderDraft] = useState<string>("");

  const beginEditFolder = (id: number, current: string | null | undefined) => {
    setFolderEditId(id);
    setFolderDraft(current ?? "");
  };

  const cancelEditFolder = () => {
    setFolderEditId(null);
    setFolderDraft("");
  };

  const submitFolder = async (id: number) => {
    if (!userId) return;
    await fetch(`${API_BASE}/api/tasks/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ folder_path: folderDraft.trim() || null }),
    });
    cancelEditFolder();
    await fetchTasks(userId);
  };

  if (userLoading) {
    return (
      <main className="p-8 min-h-screen" style={{ backgroundColor: "var(--color-bg-base)" }}>
        <p style={{ color: "var(--color-text-secondary)" }}>로딩 중...</p>
      </main>
    );
  }

  return (
    <main
      className="min-h-screen p-6 max-w-2xl mx-auto"
      style={{ backgroundColor: "var(--color-bg-base)", color: "var(--color-text-primary)" }}
    >
      <header className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-[22px] font-semibold" style={{ fontFamily: "var(--font-feeling)" }}>
            작업
          </h1>
          <p className="text-[13px]" style={{ color: "var(--color-text-secondary)" }}>
            챗에서 마감 있는 작업을 말하면 자동으로 등록돼요
          </p>
        </div>
        <a href="/chat" className="text-[12px] underline-offset-2 hover:underline">
          채팅으로 →
        </a>
      </header>

      {error && (
        <p className="text-[12px] mb-3" style={{ color: "#B00020" }}>
          {error}
        </p>
      )}

      {loading && tasks.length === 0 ? (
        <p className="text-[13px]" style={{ color: "var(--color-text-secondary)" }}>
          불러오는 중...
        </p>
      ) : tasks.length === 0 ? (
        <p className="text-[13px] py-12 text-center" style={{ color: "var(--color-text-secondary)" }}>
          아직 등록된 작업이 없어요. 채팅에서 마감을 말해보세요.
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {tasks.map((t) => {
            const dlColor = urgencyColor(t.deadline_at, t.status);
            const isDone = t.status === "done";
            return (
              <li
                key={t.id}
                className="rounded-xl px-4 py-3"
                style={{
                  backgroundColor: "var(--color-bg-card)",
                  border: "1px solid var(--color-border-subtle)",
                  opacity: isDone ? 0.5 : 1,
                }}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <p
                      className="text-[15px] font-medium"
                      style={{
                        textDecoration: isDone ? "line-through" : "none",
                      }}
                    >
                      {t.title}
                    </p>
                    <p
                      className="text-[12px] mt-0.5"
                      style={{ color: dlColor, fontWeight: 500 }}
                    >
                      {daysUntil(t.deadline_at)}
                      {t.deadline_at && (
                        <span style={{ color: "var(--color-text-secondary)", fontWeight: 400 }}>
                          {" · "}
                          {t.deadline_at.slice(0, 10)}
                        </span>
                      )}
                    </p>
                    {folderEditId === t.id ? (
                      <div className="flex gap-1.5 mt-1.5">
                        <input
                          type="text"
                          value={folderDraft}
                          onChange={(e) => setFolderDraft(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") submitFolder(t.id);
                            if (e.key === "Escape") cancelEditFolder();
                          }}
                          placeholder="/Users/yj/Desktop/work"
                          autoFocus
                          className="flex-1 px-2 py-1 text-[11px] rounded font-mono"
                          style={{
                            backgroundColor: "var(--color-bg-base)",
                            border: "1px solid var(--color-border-subtle)",
                            color: "var(--color-text-primary)",
                          }}
                        />
                        <button
                          type="button"
                          onClick={() => submitFolder(t.id)}
                          className="text-[11px] px-2 underline-offset-2 hover:underline"
                        >
                          저장
                        </button>
                        <button
                          type="button"
                          onClick={cancelEditFolder}
                          className="text-[11px] px-1"
                          style={{ color: "var(--color-text-secondary)" }}
                        >
                          취소
                        </button>
                      </div>
                    ) : (
                      <p className="text-[11px] mt-1.5" style={{ color: "var(--color-text-secondary)" }}>
                        폴더:{" "}
                        <button
                          type="button"
                          onClick={() => beginEditFolder(t.id, t.folder_path)}
                          className="underline-offset-2 hover:underline"
                        >
                          {t.folder_path ?? "등록하기"}
                        </button>
                      </p>
                    )}
                  </div>
                  <div className="flex flex-col gap-1.5 flex-shrink-0">
                    {!isDone && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => updateStatus(t.id, "done")}
                      >
                        ✓ 완료
                      </Button>
                    )}
                    {isDone && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => updateStatus(t.id, "open")}
                      >
                        ↺ 재개
                      </Button>
                    )}
                    <Button
                      variant="destruct"
                      size="sm"
                      onClick={() => remove(t.id)}
                      aria-label="삭제"
                    >
                      ⊗
                    </Button>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}
