"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
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

interface TaskFile {
  name: string;
  size: number;
  mtime: string;
}

type EditField = "title" | "deadline" | "folder";

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const EDITABLE_EXTS = new Set([
  "docx", "doc", "odt", "txt", "rtf", "md",
  "xlsx", "xls", "ods", "csv",
  "pptx", "ppt", "odp",
]);

function isEditable(name: string): boolean {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  return EDITABLE_EXTS.has(ext);
}

function daysUntil(deadlineIso: string | null | undefined): string {
  if (!deadlineIso) return "마감 없음";
  const dl = new Date(deadlineIso);
  if (isNaN(dl.getTime())) return "마감 없음";
  const KST_OFFSET = 9 * 60 * 60 * 1000;
  const toKstDay = (t: number): number => {
    const kstMs = t + KST_OFFSET;
    return Math.floor(kstMs / 86_400_000);
  };
  const dlDay = toKstDay(dl.getTime());
  const todayDay = toKstDay(Date.now());
  const diff = dlDay - todayDay;
  if (diff > 1) return `D-${diff}`;
  if (diff === 1) return "내일 마감";
  if (diff === 0) return "오늘 마감";
  return `${Math.abs(diff)}일 지남`;
}

function urgencyColor(deadlineIso: string | null | undefined, status: string): string {
  if (status === "done") return "var(--color-recovery-accent)";
  if (status === "abandoned") return "var(--color-text-secondary)";
  if (!deadlineIso) return "var(--color-text-secondary)";
  const dl = new Date(deadlineIso);
  if (isNaN(dl.getTime())) return "var(--color-text-secondary)";
  const KST_OFFSET = 9 * 60 * 60 * 1000;
  const toKstDay = (t: number) => Math.floor((t + KST_OFFSET) / 86_400_000);
  const diff = toKstDay(dl.getTime()) - toKstDay(Date.now());
  if (diff < 0) return "#B00020";
  if (diff <= 1) return "var(--color-regret-accent)";
  if (diff <= 3) return "var(--color-recovery-accent)";
  return "var(--color-text-secondary)";
}

function toDeadlineInputValue(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function fromDeadlineInputValue(s: string): string | null {
  if (!s) return null;
  return new Date(`${s}T00:00:00+09:00`).toISOString();
}

export default function TasksPage() {
  const { userId, loading: userLoading } = useUser();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 신규 task 생성 폼
  const [showNewForm, setShowNewForm] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newDeadline, setNewDeadline] = useState(""); // YYYY-MM-DD
  const [creating, setCreating] = useState(false);

  // 인라인 edit
  const [editing, setEditing] = useState<{ id: number; field: EditField; draft: string } | null>(
    null,
  );

  // 파일 업로드
  const [uploadingId, setUploadingId] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [pendingUploadFor, setPendingUploadFor] = useState<number | null>(null);

  // 업로드된 파일 목록 (task id → files)
  const [filesByTask, setFilesByTask] = useState<Record<number, TaskFile[]>>({});
  const [expandedTask, setExpandedTask] = useState<Record<number, boolean>>({});
  const [filesLoadingId, setFilesLoadingId] = useState<number | null>(null);

  // 새 파일 생성 폼
  const [newFileForTask, setNewFileForTask] = useState<number | null>(null);
  const [newFileName, setNewFileName] = useState("");
  const [newFileExt, setNewFileExt] = useState<"docx" | "xlsx" | "pptx" | "md" | "txt">(
    "docx",
  );
  const [creatingFile, setCreatingFile] = useState(false);

  const refreshFiles = useCallback(
    async (id: number) => {
      setFilesLoadingId(id);
      try {
        const res = await fetch(`${API_BASE}/api/tasks/${id}/files`, {
          headers: { ...authHeaders() },
        });
        if (!res.ok) throw new Error(`파일 목록 로드 실패 (${res.status})`);
        const data = await res.json();
        setFilesByTask((prev) => ({ ...prev, [id]: data.files ?? [] }));
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setFilesLoadingId(null);
      }
    },
    [],
  );

  const toggleFilesPanel = async (id: number) => {
    const willOpen = !expandedTask[id];
    setExpandedTask((prev) => ({ ...prev, [id]: willOpen }));
    if (willOpen && filesByTask[id] === undefined) {
      await refreshFiles(id);
    }
  };

  const deleteUploadedFile = async (id: number, name: string) => {
    if (!confirm(`"${name}" 파일을 삭제할까요?`)) return;
    try {
      const res = await fetch(
        `${API_BASE}/api/tasks/${id}/files/${encodeURIComponent(name)}`,
        { method: "DELETE", headers: { ...authHeaders() } },
      );
      if (!res.ok && res.status !== 204) {
        throw new Error(`삭제 실패 (${res.status})`);
      }
      await refreshFiles(id);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const openNewFileForm = (id: number) => {
    setNewFileForTask(id);
    setNewFileName("");
    setNewFileExt("docx");
  };

  const cancelNewFileForm = () => {
    setNewFileForTask(null);
    setNewFileName("");
  };

  const submitNewFile = async () => {
    if (newFileForTask === null) return;
    const fname = newFileName.trim() || "새 문서";
    setCreatingFile(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/tasks/${newFileForTask}/files/new`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ filename: fname, ext: newFileExt }),
      });
      if (!res.ok) {
        const msg = await res.text().catch(() => "");
        throw new Error(
          `생성 실패 (${res.status})${msg ? `: ${msg.slice(0, 80)}` : ""}`,
        );
      }
      const body = await res.json();
      const created = body.created_filename as string;
      // 파일 리스트 새로고침 + 편집 페이지 새 탭 열기
      await refreshFiles(newFileForTask);
      setExpandedTask((prev) => ({ ...prev, [newFileForTask]: true }));
      const taskId = newFileForTask;
      cancelNewFileForm();
      // OnlyOffice가 편집 가능한 ext만 자동으로 새 탭 — md/txt는 그냥 리스트로
      if (isEditable(created)) {
        window.open(
          `/tasks/edit?taskId=${taskId}&name=${encodeURIComponent(created)}`,
          "_blank",
          "noopener,noreferrer",
        );
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setCreatingFile(false);
    }
  };

  const downloadUploadedFile = async (id: number, name: string) => {
    try {
      const res = await fetch(
        `${API_BASE}/api/tasks/${id}/files/${encodeURIComponent(name)}/download`,
        { headers: { ...authHeaders() } },
      );
      if (!res.ok) throw new Error(`다운로드 실패 (${res.status})`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      setError((e as Error).message);
    }
  };

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

  const createTask = async () => {
    if (!userId) return;
    const title = newTitle.trim();
    if (!title) {
      setError("제목을 입력해주세요");
      return;
    }
    setCreating(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          user_id: userId,
          title,
          deadline_at: fromDeadlineInputValue(newDeadline),
        }),
      });
      if (!res.ok) throw new Error(`생성 실패 (${res.status})`);
      setNewTitle("");
      setNewDeadline("");
      setShowNewForm(false);
      await fetchTasks(userId);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setCreating(false);
    }
  };

  const patchTask = async (id: number, patch: Record<string, unknown>) => {
    if (!userId) return;
    const res = await fetch(`${API_BASE}/api/tasks/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(patch),
    });
    if (!res.ok) throw new Error(`수정 실패 (${res.status})`);
    await fetchTasks(userId);
  };

  const updateStatus = async (id: number, status: Task["status"]) => {
    try {
      await patchTask(id, { status });
    } catch (e) {
      setError((e as Error).message);
    }
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

  const beginEdit = (id: number, field: EditField, current: string | null | undefined) => {
    const draft =
      field === "deadline" ? toDeadlineInputValue(current) : current ?? "";
    setEditing({ id, field, draft });
  };

  const cancelEdit = () => setEditing(null);

  const submitEdit = async () => {
    if (!editing) return;
    try {
      let patch: Record<string, unknown> = {};
      if (editing.field === "title") {
        const v = editing.draft.trim();
        if (!v) {
          setError("제목은 비울 수 없어요");
          return;
        }
        patch = { title: v };
      } else if (editing.field === "deadline") {
        patch = { deadline_at: fromDeadlineInputValue(editing.draft) };
      } else if (editing.field === "folder") {
        patch = { folder_path: editing.draft.trim() || null };
      }
      await patchTask(editing.id, patch);
      setEditing(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const triggerUpload = (id: number) => {
    setPendingUploadFor(id);
    fileInputRef.current?.click();
  };

  const handleFilesChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const id = pendingUploadFor;
    setPendingUploadFor(null);
    if (!id || !userId) return;
    const files = e.target.files;
    if (!files || files.length === 0) return;
    setUploadingId(id);
    setError(null);
    try {
      const form = new FormData();
      for (const f of Array.from(files)) form.append("files", f);
      const res = await fetch(`${API_BASE}/api/tasks/${id}/upload`, {
        method: "POST",
        headers: { ...authHeaders() }, // do NOT set Content-Type — browser sets boundary
        body: form,
      });
      if (!res.ok) {
        const msg = await res.text().catch(() => "");
        throw new Error(`업로드 실패 (${res.status})${msg ? `: ${msg.slice(0, 80)}` : ""}`);
      }
      await fetchTasks(userId);
      // 업로드 후 자동으로 파일 목록 갱신 + 패널 열기
      setExpandedTask((prev) => ({ ...prev, [id]: true }));
      await refreshFiles(id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setUploadingId(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
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
      {/* 숨김 파일 입력 — triggerUpload가 클릭 */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={handleFilesChange}
      />

      <header className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-[22px] font-semibold" style={{ fontFamily: "var(--font-feeling)" }}>
            작업
          </h1>
          <p className="text-[13px]" style={{ color: "var(--color-text-secondary)" }}>
            새로 만들거나 챗에서 마감을 말하면 자동 등록돼요
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setShowNewForm((v) => !v);
              setError(null);
            }}
          >
            {showNewForm ? "✕ 닫기" : "+ 새 작업"}
          </Button>
          <a href="/chat" className="text-[12px] underline-offset-2 hover:underline">
            채팅으로 →
          </a>
        </div>
      </header>

      {showNewForm && (
        <div
          className="rounded-xl p-4 mb-4 flex flex-col gap-2"
          style={{
            backgroundColor: "var(--color-bg-card)",
            border: "1px solid var(--color-border-subtle)",
          }}
        >
          <input
            type="text"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder="작업 제목 (예: 발표자료 마무리)"
            autoFocus
            className="px-2 py-1.5 text-[14px] rounded"
            style={{
              backgroundColor: "var(--color-bg-base)",
              border: "1px solid var(--color-border-subtle)",
              color: "var(--color-text-primary)",
            }}
          />
          <div className="flex gap-2 items-center">
            <label
              className="text-[12px]"
              style={{ color: "var(--color-text-secondary)" }}
            >
              마감 (선택)
            </label>
            <input
              type="date"
              value={newDeadline}
              onChange={(e) => setNewDeadline(e.target.value)}
              className="px-2 py-1 text-[12px] rounded"
              style={{
                backgroundColor: "var(--color-bg-base)",
                border: "1px solid var(--color-border-subtle)",
                color: "var(--color-text-primary)",
              }}
            />
          </div>
          <div className="flex gap-2 justify-end">
            <button
              type="button"
              onClick={() => {
                setShowNewForm(false);
                setNewTitle("");
                setNewDeadline("");
              }}
              className="text-[12px] px-2"
              style={{ color: "var(--color-text-secondary)" }}
            >
              취소
            </button>
            <Button size="sm" onClick={createTask} disabled={creating}>
              {creating ? "등록 중..." : "등록"}
            </Button>
          </div>
        </div>
      )}

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
          아직 등록된 작업이 없어요. 위 「+ 새 작업」을 누르거나 채팅에서 말해보세요.
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {tasks.map((t) => {
            const dlColor = urgencyColor(t.deadline_at, t.status);
            const isDone = t.status === "done";
            const isEditingTitle =
              editing?.id === t.id && editing.field === "title";
            const isEditingDeadline =
              editing?.id === t.id && editing.field === "deadline";
            const isEditingFolder =
              editing?.id === t.id && editing.field === "folder";
            return (
              <li
                key={t.id}
                className="rounded-xl px-4 py-3"
                style={{
                  backgroundColor: "var(--color-bg-card)",
                  border: "1px solid var(--color-border-subtle)",
                  opacity: isDone ? 0.55 : 1,
                }}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    {/* 제목 */}
                    {isEditingTitle ? (
                      <div className="flex gap-1.5">
                        <input
                          type="text"
                          value={editing.draft}
                          onChange={(e) =>
                            setEditing({ ...editing, draft: e.target.value })
                          }
                          onKeyDown={(e) => {
                            if (e.key === "Enter") submitEdit();
                            if (e.key === "Escape") cancelEdit();
                          }}
                          autoFocus
                          className="flex-1 px-2 py-1 text-[14px] rounded"
                          style={{
                            backgroundColor: "var(--color-bg-base)",
                            border: "1px solid var(--color-border-subtle)",
                            color: "var(--color-text-primary)",
                          }}
                        />
                        <button
                          type="button"
                          onClick={submitEdit}
                          className="text-[11px] px-2 underline-offset-2 hover:underline"
                        >
                          저장
                        </button>
                        <button
                          type="button"
                          onClick={cancelEdit}
                          className="text-[11px] px-1"
                          style={{ color: "var(--color-text-secondary)" }}
                        >
                          취소
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => beginEdit(t.id, "title", t.title)}
                        className="text-[15px] font-medium text-left hover:underline underline-offset-4"
                        style={{
                          textDecoration: isDone ? "line-through" : undefined,
                        }}
                      >
                        {t.title}
                      </button>
                    )}

                    {/* 마감 */}
                    {isEditingDeadline ? (
                      <div className="flex gap-1.5 mt-1">
                        <input
                          type="date"
                          value={editing.draft}
                          onChange={(e) =>
                            setEditing({ ...editing, draft: e.target.value })
                          }
                          onKeyDown={(e) => {
                            if (e.key === "Enter") submitEdit();
                            if (e.key === "Escape") cancelEdit();
                          }}
                          autoFocus
                          className="px-2 py-1 text-[12px] rounded"
                          style={{
                            backgroundColor: "var(--color-bg-base)",
                            border: "1px solid var(--color-border-subtle)",
                            color: "var(--color-text-primary)",
                          }}
                        />
                        <button
                          type="button"
                          onClick={submitEdit}
                          className="text-[11px] px-2 underline-offset-2 hover:underline"
                        >
                          저장
                        </button>
                        <button
                          type="button"
                          onClick={cancelEdit}
                          className="text-[11px] px-1"
                          style={{ color: "var(--color-text-secondary)" }}
                        >
                          취소
                        </button>
                        {t.deadline_at && (
                          <button
                            type="button"
                            onClick={() => {
                              setEditing({ ...editing, draft: "" });
                              submitEdit();
                            }}
                            className="text-[11px] px-1"
                            style={{ color: "var(--color-text-secondary)" }}
                          >
                            지우기
                          </button>
                        )}
                      </div>
                    ) : (
                      <p
                        className="text-[12px] mt-0.5"
                        style={{ color: dlColor, fontWeight: 500 }}
                      >
                        <button
                          type="button"
                          onClick={() => beginEdit(t.id, "deadline", t.deadline_at)}
                          className="underline-offset-2 hover:underline"
                        >
                          {daysUntil(t.deadline_at)}
                        </button>
                        {t.deadline_at && (
                          <span
                            style={{
                              color: "var(--color-text-secondary)",
                              fontWeight: 400,
                            }}
                          >
                            {" · "}
                            {t.deadline_at.slice(0, 10)}
                          </span>
                        )}
                      </p>
                    )}

                    {/* 폴더 */}
                    {isEditingFolder ? (
                      <div className="flex gap-1.5 mt-1.5">
                        <input
                          type="text"
                          value={editing.draft}
                          onChange={(e) =>
                            setEditing({ ...editing, draft: e.target.value })
                          }
                          onKeyDown={(e) => {
                            if (e.key === "Enter") submitEdit();
                            if (e.key === "Escape") cancelEdit();
                          }}
                          placeholder="/Users/yj/Desktop/work 또는 비우기"
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
                          onClick={submitEdit}
                          className="text-[11px] px-2 underline-offset-2 hover:underline"
                        >
                          저장
                        </button>
                        <button
                          type="button"
                          onClick={cancelEdit}
                          className="text-[11px] px-1"
                          style={{ color: "var(--color-text-secondary)" }}
                        >
                          취소
                        </button>
                      </div>
                    ) : (
                      <p
                        className="text-[11px] mt-1.5"
                        style={{ color: "var(--color-text-secondary)" }}
                      >
                        폴더:{" "}
                        <button
                          type="button"
                          onClick={() => beginEdit(t.id, "folder", t.folder_path)}
                          className="underline-offset-2 hover:underline font-mono"
                        >
                          {t.folder_path ?? "등록하기"}
                        </button>
                      </p>
                    )}
                  </div>

                  <div className="flex flex-col gap-1.5 flex-shrink-0">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => openNewFileForm(t.id)}
                      aria-label="새 문서 만들기"
                    >
                      ➕ 새 문서
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => triggerUpload(t.id)}
                      disabled={uploadingId === t.id}
                      aria-label="파일 업로드"
                    >
                      {uploadingId === t.id ? "↑..." : "📎 업로드"}
                    </Button>
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

                {/* 새 문서 생성 인라인 폼 */}
                {newFileForTask === t.id && (
                  <div
                    className="mt-2 pt-2 flex flex-col gap-1.5"
                    style={{ borderTop: "1px dashed var(--color-border-subtle)" }}
                  >
                    <p
                      className="text-[11px]"
                      style={{ color: "var(--color-text-secondary)" }}
                    >
                      새 문서를 만들고 곧장 편집기에 띄울게요
                    </p>
                    <div className="flex gap-1.5 items-center">
                      <input
                        type="text"
                        value={newFileName}
                        onChange={(e) => setNewFileName(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") submitNewFile();
                          if (e.key === "Escape") cancelNewFileForm();
                        }}
                        placeholder="파일명 (예: 발표자료)"
                        autoFocus
                        className="flex-1 px-2 py-1 text-[12px] rounded"
                        style={{
                          backgroundColor: "var(--color-bg-base)",
                          border: "1px solid var(--color-border-subtle)",
                          color: "var(--color-text-primary)",
                        }}
                      />
                      <select
                        value={newFileExt}
                        onChange={(e) =>
                          setNewFileExt(
                            e.target.value as "docx" | "xlsx" | "pptx" | "md" | "txt",
                          )
                        }
                        className="px-2 py-1 text-[12px] rounded"
                        style={{
                          backgroundColor: "var(--color-bg-base)",
                          border: "1px solid var(--color-border-subtle)",
                          color: "var(--color-text-primary)",
                        }}
                      >
                        <option value="docx">docx</option>
                        <option value="xlsx">xlsx</option>
                        <option value="pptx">pptx</option>
                        <option value="md">md</option>
                        <option value="txt">txt</option>
                      </select>
                      <button
                        type="button"
                        onClick={submitNewFile}
                        disabled={creatingFile}
                        className="text-[11px] px-2 underline-offset-2 hover:underline"
                      >
                        {creatingFile ? "..." : "만들기"}
                      </button>
                      <button
                        type="button"
                        onClick={cancelNewFileForm}
                        className="text-[11px] px-1"
                        style={{ color: "var(--color-text-secondary)" }}
                      >
                        취소
                      </button>
                    </div>
                  </div>
                )}

                {/* 업로드된 파일 패널 */}
                <div className="mt-2 pt-2" style={{ borderTop: "1px dashed var(--color-border-subtle)" }}>
                  <button
                    type="button"
                    onClick={() => toggleFilesPanel(t.id)}
                    className="text-[11px] hover:underline underline-offset-2"
                    style={{ color: "var(--color-text-secondary)" }}
                  >
                    📂 업로드 파일{" "}
                    {filesByTask[t.id]
                      ? `${filesByTask[t.id].length}개`
                      : "(확인하기)"}
                    <span className="ml-1">{expandedTask[t.id] ? "▾" : "▸"}</span>
                  </button>
                  {expandedTask[t.id] && (
                    <div className="mt-1.5">
                      {filesLoadingId === t.id && filesByTask[t.id] === undefined ? (
                        <p className="text-[11px]" style={{ color: "var(--color-text-secondary)" }}>
                          불러오는 중...
                        </p>
                      ) : (filesByTask[t.id]?.length ?? 0) === 0 ? (
                        <p className="text-[11px]" style={{ color: "var(--color-text-secondary)" }}>
                          업로드된 파일이 없어요. 「📎 업로드」를 눌러 추가하세요.
                        </p>
                      ) : (
                        <ul className="flex flex-col gap-1">
                          {filesByTask[t.id]!.map((f) => (
                            <li
                              key={f.name}
                              className="flex items-center justify-between gap-2 text-[11px] px-2 py-1 rounded"
                              style={{
                                backgroundColor: "var(--color-bg-base)",
                                border: "1px solid var(--color-border-subtle)",
                              }}
                            >
                              <span className="font-mono truncate flex-1">{f.name}</span>
                              <span
                                className="flex-shrink-0"
                                style={{ color: "var(--color-text-secondary)" }}
                              >
                                {formatSize(f.size)}
                              </span>
                              <div className="flex gap-1 flex-shrink-0">
                                {isEditable(f.name) && (
                                  <a
                                    href={`/tasks/edit?taskId=${t.id}&name=${encodeURIComponent(f.name)}`}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="px-1.5 underline-offset-2 hover:underline"
                                    aria-label={`${f.name} 편집`}
                                    title="브라우저에서 편집 (OnlyOffice)"
                                  >
                                    ✏️
                                  </a>
                                )}
                                <button
                                  type="button"
                                  onClick={() => downloadUploadedFile(t.id, f.name)}
                                  className="px-1.5 underline-offset-2 hover:underline"
                                  aria-label={`${f.name} 다운로드`}
                                  title="다운로드"
                                >
                                  📥
                                </button>
                                <button
                                  type="button"
                                  onClick={() => deleteUploadedFile(t.id, f.name)}
                                  className="px-1.5 underline-offset-2 hover:underline"
                                  aria-label={`${f.name} 삭제`}
                                  title="삭제"
                                  style={{ color: "#B00020" }}
                                >
                                  ✕
                                </button>
                              </div>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}
