"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useUser } from "../../lib/hooks/useUser";
import { Button } from "../../components/Button";
import { authHeaders } from "../../lib/auth";
import { RecoveryCardCluster } from "../../components/RecoveryCardCluster";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8001";

interface ChatMessage {
  id: number;
  role: "user" | "assistant" | "system";
  content: string;
  created_at?: string;
}

interface ChatSessionListItem {
  id: number;
  persona_id?: number | null;
  persona_name?: string | null;
  avatar_icon?: string | null;
  avatar_color?: string | null;
  title?: string | null;
  message_count: number;
  updated_at: string;
  last_message?: string | null;
}

interface TaskSummary {
  id: number;
  title: string;
  deadline_at: string | null;
  folder_path: string | null;
  status: string;
}

function relativeTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();
  if (sameDay) {
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    return `${hh}:${mm}`;
  }
  const y = new Date(now);
  y.setDate(now.getDate() - 1);
  if (
    d.getFullYear() === y.getFullYear() &&
    d.getMonth() === y.getMonth() &&
    d.getDate() === y.getDate()
  ) {
    return "어제";
  }
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

// Sprint 15: assistant 메시지 안 action 라인을 rich card로 추출
// backend가 '✅', '📁', '✓', '📅', '✏', '⚠' prefix로 라인 만듦.
const CARD_PREFIXES = ["✅", "📁", "✓", "📅", "✏", "⚠", "🪞", "🫧", "👣"];
const RECOVERY_PREFIXES = ["🪞", "🫧", "👣"];

interface ParsedMessage {
  cards: { icon: string; text: string }[];
  body: string;
}

function parseAssistantContent(content: string): ParsedMessage {
  const lines = content.split("\n");
  const cards: { icon: string; text: string }[] = [];
  const bodyLines: string[] = [];
  for (const line of lines) {
    const trimmed = line.trim();
    const prefix = CARD_PREFIXES.find((p) => trimmed.startsWith(p));
    if (prefix) {
      if (RECOVERY_PREFIXES.includes(prefix)) continue; // consumed by RecoveryCardCluster
      cards.push({ icon: prefix, text: trimmed.slice(prefix.length).trim() });
    } else {
      bodyLines.push(line);
    }
  }
  return {
    cards,
    body: bodyLines.join("\n").trim(),
  };
}

interface RecoveryParsed {
  fact?: string;
  feeling?: string;
  micro?: string;
  deepLink?: string;
}

function extractRecoveryCard(content: string): RecoveryParsed | null {
  const lines = content.split("\n");
  let fact: string | undefined, feeling: string | undefined, micro: string | undefined, deepLink: string | undefined;
  for (const line of lines) {
    const t = line.trim();
    if (t.startsWith("🪞")) fact = t.slice(2).trim();
    else if (t.startsWith("🫧")) feeling = t.slice(2).trim();
    else if (t.startsWith("👣")) {
      let m = t.slice(2).trim();
      const dm = m.match(/::\s*deeplink=([^\s]+)/);
      if (dm) {
        deepLink = dm[1];
        m = m.slice(0, dm.index).trim();
      }
      micro = m;
    }
  }
  if (fact || feeling || micro) return { fact, feeling, micro, deepLink };
  return null;
}

function daysUntilLabel(iso: string | null): string {
  if (!iso) return "";
  const d = Math.ceil((new Date(iso).getTime() - Date.now()) / 86_400_000);
  if (d > 1) return `D-${d}`;
  if (d === 1) return "내일";
  if (d === 0) return "오늘";
  return `${Math.abs(d)}일 지남`;
}

function cardDeepLink(icon: string, text: string): string {
  // try to extract a task id from text
  const m = text.match(/#(\d+)|id=(\d+)|task[\s_]?(\d+)/i);
  const tid = m ? (m[1] || m[2] || m[3]) : null;
  const focus = tid ? `?focus=${tid}` : "";
  switch (icon) {
    case "📅": return "/calendar";
    case "⚠": return "/settings";
    case "✅":
    case "✓":
    case "📁":
    case "✏":
    default: return `/tasks${focus}`;
  }
}

export default function ChatPage() {
  const { userId, loading: userLoading } = useUser();

  const [sessionId, setSessionId] = useState<number | null>(null);
  const [sessions, setSessions] = useState<ChatSessionListItem[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(false); // 모바일 기록 드로워
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [taskSummary, setTaskSummary] = useState<TaskSummary[]>([]);
  const listEndRef = useRef<HTMLDivElement | null>(null);
  // Sprint 17: polling으로 새 assistant 메시지 도착 시 chrome notification 발사
  const lastMessageIdRef = useRef<number>(0);
  const notifyPermissionRef = useRef<string>("default");

  const refreshTaskSummary = useCallback(async (uid: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/tasks?user_id=${uid}&status=open`, {
        headers: { ...authHeaders() },
      });
      if (!res.ok) return;
      const data = await res.json();
      setTaskSummary(data.tasks ?? []);
    } catch {
      // silent
    }
  }, []);

  const fetchSessions = useCallback(async (uid: string) => {
    const res = await fetch(`${API_BASE}/api/chat/sessions?user_id=${uid}`, {
      headers: { ...authHeaders() },
    });
    if (!res.ok) return [];
    const data = await res.json();
    return data.sessions as ChatSessionListItem[];
  }, []);

  const fetchMessages = useCallback(async (sid: number) => {
    const res = await fetch(`${API_BASE}/api/chat/sessions/${sid}/messages`, {
      headers: { ...authHeaders() },
    });
    if (!res.ok) return [];
    const data = await res.json();
    return data.messages as ChatMessage[];
  }, []);

  const ensureSession = useCallback(
    async (uid: string) => {
      const list = await fetchSessions(uid);
      setSessions(list);
      if (list.length > 0) {
        const latest = list[0];
        setSessionId(latest.id);
        setMessages(await fetchMessages(latest.id));
        return;
      }
      const res = await fetch(`${API_BASE}/api/chat/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ user_id: uid }),
      });
      if (!res.ok) {
        setError("새 채팅 세션을 만들 수 없어요");
        return;
      }
      const { session_id } = await res.json();
      setSessionId(session_id);
      setMessages([]);
      setSessions(await fetchSessions(uid));
    },
    [fetchSessions, fetchMessages],
  );

  // Sprint 22: 오늘 첫 브리핑 트리거. backend가 cooldown 관리.
  const triggerBriefing = useCallback(async (uid: string) => {
    try {
      await fetch(`${API_BASE}/api/chat/briefing?user_id=${uid}`, {
        method: "POST",
        headers: { ...authHeaders() },
      });
    } catch {
      // silent — 브리핑 실패가 chat 동작 막지 않게
    }
  }, []);

  // Sprint 37 fix: 이전엔 sessionId 의존성 + ensureSession이 항상 list[0]
  // (latest)로 setSessionId하는 게 결합돼서, 사용자가 옛 세션을 클릭해도
  // 즉시 latest로 revert됐음. ensureSession은 초기 1회 (sessionId null)에만
  // 실행하고, 이후 sessionId 변경은 switchSession이 책임진다.
  useEffect(() => {
    if (!userId) return;
    refreshTaskSummary(userId);
    if (sessionId === null) {
      ensureSession(userId).then(() => triggerBriefing(userId));
    }
  }, [userId, sessionId, ensureSession, refreshTaskSummary, triggerBriefing]);

  // Sprint 17: chat 페이지 진입 시 Notification 권한 한 번 요청
  useEffect(() => {
    if (typeof window === "undefined" || !("Notification" in window)) return;
    notifyPermissionRef.current = Notification.permission;
    if (Notification.permission === "default") {
      Notification.requestPermission().then((p) => {
        notifyPermissionRef.current = p;
      });
    }
  }, []);

  // Sprint 17: 15초마다 polling — 새 assistant 메시지가 있으면 messages 갱신 +
  // 페이지가 포커스 없을 때 chrome notification 발사.
  useEffect(() => {
    if (!sessionId) return;
    const interval = window.setInterval(async () => {
      const fresh = await fetchMessages(sessionId);
      if (fresh.length === 0) return;
      const newest = fresh[fresh.length - 1];
      const prevLastId = lastMessageIdRef.current;
      if (newest.id > prevLastId) {
        lastMessageIdRef.current = newest.id;
        setMessages(fresh);
        if (userId) refreshTaskSummary(userId);
        // chrome notification (페이지 visible이 아닐 때만)
        if (
          prevLastId !== 0 &&
          newest.role === "assistant" &&
          typeof document !== "undefined" &&
          document.visibilityState !== "visible" &&
          typeof Notification !== "undefined" &&
          Notification.permission === "granted"
        ) {
          try {
            const n = new Notification("내일의 너", {
              body: parseAssistantContent(newest.content).body
                || newest.content.split("\n").slice(0, 3).join(" "),
              icon: "/icon.svg",
              tag: `chat-${sessionId}`,
            });
            n.onclick = () => {
              window.focus();
              n.close();
            };
          } catch {
            // graceful
          }
        }
      }
    }, 15_000);
    return () => window.clearInterval(interval);
  }, [sessionId, fetchMessages, userId, refreshTaskSummary]);

  // 메시지 초기 로드 시 마지막 id 동기화
  useEffect(() => {
    if (messages.length > 0) {
      lastMessageIdRef.current = messages[messages.length - 1].id;
    }
  }, [messages.length]);

  useEffect(() => {
    listEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || !sessionId || sending) return;
    setSending(true);
    setError(null);
    // optimistic 사용자 메시지
    const optimistic: ChatMessage = {
      id: -Date.now(),
      role: "user",
      content: text,
    };
    setMessages((prev) => [...prev, optimistic]);
    setInput("");

    try {
      const res = await fetch(
        `${API_BASE}/api/chat/sessions/${sessionId}/messages`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", ...authHeaders() },
          body: JSON.stringify({ content: text }),
        },
      );
      if (!res.ok) throw new Error(`전송 실패 (${res.status})`);
      const data = await res.json();
      // 전체 히스토리 재로드 (assistant 응답 + 저장된 user 메시지 동기화)
      const fresh = await fetchMessages(sessionId);
      setMessages(fresh);
      // task 요약 갱신 — action 결과 카드가 떴을 수 있음
      if (userId) refreshTaskSummary(userId);
      void data;
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
    }
  };

  const handleNewSession = async () => {
    if (!userId) return;
    setSending(true);
    try {
      const res = await fetch(`${API_BASE}/api/chat/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ user_id: userId }),
      });
      if (!res.ok) throw new Error("새 세션 생성 실패");
      const { session_id } = await res.json();
      setSessionId(session_id);
      setMessages([]);
      setSessions(await fetchSessions(userId));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
    }
  };

  const switchSession = async (sid: number) => {
    setSessionId(sid);
    setSidebarOpen(false); // 모바일에서 선택하면 드로워 닫기
    setMessages(await fetchMessages(sid));
  };

  // Sprint 26: 대화 영구 삭제. 현재 active면 다른 세션 또는 새 세션으로 전환.
  const deleteSession = async (sid: number) => {
    if (!userId) return;
    if (!confirm("이 대화를 영구 삭제할까요? 메시지·기록 모두 사라져요.")) return;
    try {
      const res = await fetch(`${API_BASE}/api/chat/sessions/${sid}`, {
        method: "DELETE",
        headers: { ...authHeaders() },
      });
      if (!res.ok && res.status !== 204) {
        throw new Error(`삭제 실패 (${res.status})`);
      }
    } catch (e) {
      setError((e as Error).message);
      return;
    }
    const list = await fetchSessions(userId);
    setSessions(list);
    if (sessionId === sid) {
      if (list.length > 0) {
        const next = list[0];
        setSessionId(next.id);
        setMessages(await fetchMessages(next.id));
      } else {
        // 세션 0개 → 새로 자동 생성
        ensureSession(userId);
      }
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
      className="min-h-screen flex flex-col"
      style={{ backgroundColor: "var(--color-bg-base)", color: "var(--color-text-primary)" }}
    >
      <header
        className="flex items-center justify-between px-6 py-4"
        style={{ borderBottom: "1px solid var(--color-border-subtle)" }}
      >
        <div className="min-w-0">
          <h1
            className="text-[17px] font-semibold truncate"
            style={{ fontFamily: "var(--font-feeling)" }}
          >
            {(() => {
              const cur = sessions.find((s) => s.id === sessionId);
              return (cur?.title && cur.title.trim()) || cur?.persona_name || "내일의 너와 대화";
            })()}
          </h1>
          {(() => {
            const cur = sessions.find((s) => s.id === sessionId);
            if (!cur) return null;
            return (
              <p
                className="text-[11px] mt-0.5"
                style={{ color: "var(--color-text-secondary)" }}
              >
                {cur.avatar_icon ?? "💬"} {cur.persona_name ?? "내일의 나"} · 메시지 {cur.message_count}
              </p>
            );
          })()}
        </div>
        <div className="flex items-center gap-1.5">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setSidebarOpen(true)}
            aria-label="대화 기록 열기"
            className="md:hidden"
          >
            📚 기록
          </Button>
          <Button variant="ghost" size="sm" onClick={handleNewSession} disabled={sending}>
            + 새 대화
          </Button>
        </div>
      </header>

      <div className="flex-1 flex relative">
        {/* 모바일 백드롭 — 드로워 열렸을 때 탭하면 닫힘 */}
        {sidebarOpen && (
          <button
            type="button"
            aria-label="대화 기록 닫기"
            onClick={() => setSidebarOpen(false)}
            className="fixed inset-0 z-20 md:hidden"
            style={{ backgroundColor: "rgba(0,0,0,0.35)" }}
          />
        )}
        {/* 사이드: 세션 목록 — 데스크탑은 항상, 모바일은 sidebarOpen일 때 드로워 */}
        <aside
          className={`w-[260px] sm:w-[280px] flex-shrink-0 overflow-y-auto py-3 ${
            sidebarOpen
              ? "fixed inset-y-0 left-0 z-30 shadow-2xl"
              : "hidden"
          } md:block md:static md:z-auto md:shadow-none`}
          style={{
            borderRight: "1px solid var(--color-border-subtle)",
            backgroundColor: "var(--color-bg-base)",
          }}
        >
          {/* 모바일 닫기 버튼 */}
          {sidebarOpen && (
            <div className="flex items-center justify-between px-3 pb-2 md:hidden">
              <span
                className="text-[12px] uppercase tracking-widest"
                style={{ color: "var(--color-text-secondary)" }}
              >
                대화 기록
              </span>
              <button
                type="button"
                onClick={() => setSidebarOpen(false)}
                aria-label="닫기"
                className="text-[14px] px-2"
                style={{ color: "var(--color-text-secondary)" }}
              >
                ✕
              </button>
            </div>
          )}
          {sessions.length === 0 ? (
            <p className="px-4 text-[12px]" style={{ color: "var(--color-text-secondary)" }}>
              아직 대화가 없어요
            </p>
          ) : (
            <ul className="flex flex-col gap-1 px-2">
              {sessions.map((s) => {
                const isActive = s.id === sessionId;
                const title =
                  (s.title && s.title.trim()) ||
                  (s.last_message &&
                    s.last_message.trim().split("\n")[0].slice(0, 30)) ||
                  "(빈 대화)";
                const preview = (s.last_message ?? "").replace(/\n+/g, " ").trim();
                return (
                  <li key={s.id} className="group relative">
                    <button
                      type="button"
                      onClick={() => switchSession(s.id)}
                      className="w-full text-left px-3 py-2 rounded-lg transition-colors flex gap-2"
                      style={{
                        backgroundColor: isActive ? "var(--color-bg-card)" : "transparent",
                        border: `1px solid ${isActive ? "var(--color-border-subtle)" : "transparent"}`,
                      }}
                    >
                      <span
                        aria-hidden
                        className="mt-1 w-1 rounded-full flex-shrink-0"
                        style={{
                          backgroundColor: s.avatar_color ?? "var(--color-text-secondary)",
                          minHeight: "32px",
                        }}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-[13px] font-medium truncate">{title}</span>
                          <span
                            className="text-[10px] flex-shrink-0"
                            style={{ color: "var(--color-text-secondary)" }}
                          >
                            {relativeTime(s.updated_at)}
                          </span>
                        </div>
                        <div
                          className="text-[11px] mt-0.5 truncate"
                          style={{ color: "var(--color-text-secondary)" }}
                        >
                          <span aria-hidden className="mr-1">
                            {s.avatar_icon ?? "💬"}
                          </span>
                          {preview ||
                            `${s.persona_name ?? "내일의 나"} · 메시지 ${s.message_count}`}
                        </div>
                      </div>
                    </button>
                    {/* Sprint 26: 호버 시 삭제 버튼 */}
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteSession(s.id);
                      }}
                      aria-label={`'${title}' 대화 삭제`}
                      className="absolute right-1 top-1 opacity-0 group-hover:opacity-100 transition-opacity rounded px-1.5 py-0.5 text-[12px]"
                      style={{
                        color: "var(--color-text-secondary)",
                        backgroundColor: "var(--color-bg-base)",
                      }}
                      title="이 대화 삭제"
                    >
                      ⊗
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </aside>

        {/* 본문: 메시지 + 입력 */}
        <section className="flex-1 flex flex-col min-w-0 md:border-r"
          style={{ borderColor: "var(--color-border-subtle)" }}>
          <div className="flex-1 overflow-y-auto px-6 py-6">
            {messages.length === 0 ? (
              <p className="text-[13px] text-center mt-12" style={{ color: "var(--color-text-secondary)" }}>
                첫 메시지를 보내보세요. 활성 페르소나가 답해요.
              </p>
            ) : (
              <ul className="flex flex-col gap-3 max-w-[640px] mx-auto">
                {messages.map((m) => {
                  const isUser = m.role === "user";
                  const parsed = isUser
                    ? null
                    : parseAssistantContent(m.content);
                  return (
                    <li
                      key={m.id}
                      className={`flex ${isUser ? "justify-end" : "justify-start"}`}
                    >
                      <div className="max-w-[80%] flex flex-col gap-1.5">
                        {/* Recovery 카드 클러스터 (🪞🫧👣) */}
                        {parsed && (() => {
                          const rec = extractRecoveryCard(m.content);
                          return rec ? <RecoveryCardCluster key="recovery" data={rec} /> : null;
                        })()}
                        {/* Action 카드 (assistant만) */}
                        {parsed?.cards.map((c, i) => {
                          const href = cardDeepLink(c.icon, c.text);
                          return (
                            <button
                              key={i}
                              type="button"
                              onClick={() => { window.location.href = href; }}
                              className="card-mount flex items-center justify-between gap-3 rounded-xl px-3 py-2 group transition-transform duration-100 active:scale-[0.97] text-left w-full"
                              style={{
                                backgroundColor: c.icon === "⚠"
                                  ? "var(--color-softstop-bg)"
                                  : "var(--color-recovery-bg)",
                                border: `1px solid ${
                                  c.icon === "⚠"
                                    ? "var(--color-softstop-border)"
                                    : "var(--color-recovery-border)"
                                }`,
                              }}
                              aria-label={`${c.text} 이동`}
                            >
                              <span className="flex items-center gap-2 min-w-0">
                                <span aria-hidden className="text-[16px] flex-shrink-0">
                                  {c.icon}
                                </span>
                                <span
                                  className="text-[13px] truncate"
                                  style={{
                                    fontFamily: "var(--font-feeling)",
                                    color: "var(--color-text-primary)",
                                  }}
                                >
                                  {c.text}
                                </span>
                              </span>
                              <span
                                aria-hidden
                                className="text-[12px] opacity-40 group-hover:opacity-80 group-hover:translate-x-0.5 transition-all duration-150 flex-shrink-0"
                                style={{ color: "var(--color-recovery-accent)" }}
                              >
                                →
                              </span>
                            </button>
                          );
                        })}
                        {/* 본문 (있을 때만) */}
                        {(isUser || (parsed && parsed.body)) && (
                          <div
                            className="rounded-2xl px-4 py-2.5 whitespace-pre-wrap"
                            style={{
                              backgroundColor: isUser
                                ? "var(--color-action-bg)"
                                : "var(--color-bg-card)",
                              color: isUser
                                ? "var(--color-action-text)"
                                : "var(--color-text-primary)",
                              border: isUser
                                ? "none"
                                : "1px solid var(--color-border-subtle)",
                              fontFamily: "var(--font-feeling)",
                              fontSize: "var(--text-body-size)",
                              lineHeight: "var(--text-body-line)",
                            }}
                          >
                            {isUser ? m.content : parsed?.body}
                          </div>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
            <div ref={listEndRef} />
          </div>

          <div
            className="px-6 py-4"
            style={{ borderTop: "1px solid var(--color-border-subtle)" }}
          >
            {error && (
              <p className="text-[12px] mb-2" style={{ color: "#B00020" }}>
                {error}
              </p>
            )}
            <div className="flex gap-2 max-w-[640px] mx-auto">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                placeholder={sending ? "응답 생성 중..." : "마감·폴더·완료 — 다 채팅으로 말해요"}
                disabled={sending || sessionId === null}
                className="flex-1 px-4 py-2.5 text-[14px] rounded-xl outline-none"
                style={{
                  backgroundColor: "var(--color-bg-card)",
                  border: "1px solid var(--color-border-subtle)",
                  color: "var(--color-text-primary)",
                }}
              />
              <Button
                variant="primary"
                size="md"
                onClick={handleSend}
                disabled={sending || !input.trim() || sessionId === null}
              >
                보내기
              </Button>
            </div>
          </div>
        </section>

        {/* Sprint 15: 우측 사이드 — 오픈 task 요약 (md 이상) */}
        <aside
          className="w-[240px] flex-shrink-0 overflow-y-auto py-4 px-3 hidden md:block"
          style={{ backgroundColor: "var(--color-bg-base)" }}
        >
          <p
            className="text-[11px] uppercase tracking-widest mb-2"
            style={{ color: "var(--color-text-secondary)" }}
          >
            진행 중
          </p>
          {taskSummary.length === 0 ? (
            <p className="text-[12px]" style={{ color: "var(--color-text-secondary)" }}>
              아직 등록된 작업이 없어요. 채팅에 마감을 말해봐요.
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {taskSummary.slice(0, 8).map((t) => {
                const dl = daysUntilLabel(t.deadline_at);
                return (
                  <li
                    key={t.id}
                    className="rounded-lg px-3 py-2 text-[12px]"
                    style={{
                      backgroundColor: "var(--color-bg-card)",
                      border: "1px solid var(--color-border-subtle)",
                    }}
                  >
                    <div className="font-medium" style={{ color: "var(--color-text-primary)" }}>
                      {t.title}
                    </div>
                    <div className="mt-0.5" style={{ color: "var(--color-text-secondary)" }}>
                      {dl}
                      {t.folder_path && <span className="ml-1">· 📁</span>}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
          <div className="mt-4 flex flex-col gap-1.5">
            <a
              href="/tasks"
              className="text-[11px] underline-offset-2 hover:underline"
              style={{ color: "var(--color-text-secondary)" }}
            >
              작업 전체 →
            </a>
            <a
              href="/calendar"
              className="text-[11px] underline-offset-2 hover:underline"
              style={{ color: "var(--color-text-secondary)" }}
            >
              캘린더 보기 →
            </a>
          </div>
        </aside>
      </div>
    </main>
  );
}
