"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useUser } from "../../lib/hooks/useUser";
import { Button } from "../../components/Button";
import { authHeaders } from "../../lib/auth";

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
  title?: string | null;
  message_count: number;
  updated_at: string;
}

interface TaskSummary {
  id: number;
  title: string;
  deadline_at: string | null;
  folder_path: string | null;
  status: string;
}

// Sprint 15: assistant 메시지 안 action 라인을 rich card로 추출
// backend가 '✅', '📁', '✓', '📅', '✏', '⚠' prefix로 라인 만듦.
const CARD_PREFIXES = ["✅", "📁", "✓", "📅", "✏", "⚠"];

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

function daysUntilLabel(iso: string | null): string {
  if (!iso) return "";
  const d = Math.ceil((new Date(iso).getTime() - Date.now()) / 86_400_000);
  if (d > 1) return `D-${d}`;
  if (d === 1) return "내일";
  if (d === 0) return "오늘";
  return `${Math.abs(d)}일 지남`;
}

export default function ChatPage() {
  const { userId, loading: userLoading } = useUser();

  const [sessionId, setSessionId] = useState<number | null>(null);
  const [sessions, setSessions] = useState<ChatSessionListItem[]>([]);
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

  useEffect(() => {
    if (userId) {
      ensureSession(userId).then(() => {
        triggerBriefing(userId);
        if (sessionId) {
          fetchMessages(sessionId).then(setMessages);
        }
      });
      refreshTaskSummary(userId);
    }
  }, [userId, ensureSession, refreshTaskSummary, triggerBriefing, sessionId, fetchMessages]);

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
    setMessages(await fetchMessages(sid));
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
        <h1 className="text-[18px] font-semibold" style={{ fontFamily: "var(--font-feeling)" }}>
          내일의 너와 대화
        </h1>
        <Button variant="ghost" size="sm" onClick={handleNewSession} disabled={sending}>
          + 새 대화
        </Button>
      </header>

      <div className="flex-1 flex">
        {/* 사이드: 세션 목록 */}
        <aside
          className="w-[220px] flex-shrink-0 overflow-y-auto py-3 hidden md:block"
          style={{ borderRight: "1px solid var(--color-border-subtle)" }}
        >
          {sessions.length === 0 ? (
            <p className="px-4 text-[12px]" style={{ color: "var(--color-text-secondary)" }}>
              아직 대화가 없어요
            </p>
          ) : (
            <ul className="flex flex-col gap-1 px-2">
              {sessions.map((s) => (
                <li key={s.id}>
                  <button
                    type="button"
                    onClick={() => switchSession(s.id)}
                    className="w-full text-left px-3 py-2 rounded-lg text-[13px] transition-colors"
                    style={{
                      backgroundColor:
                        s.id === sessionId ? "var(--color-bg-card)" : "transparent",
                      border:
                        s.id === sessionId
                          ? "1px solid var(--color-border-subtle)"
                          : "1px solid transparent",
                    }}
                  >
                    <div className="flex items-center gap-1.5">
                      <span aria-hidden>{s.avatar_icon ?? "💬"}</span>
                      <span className="truncate">
                        {s.persona_name ?? "내일의 나"}
                      </span>
                    </div>
                    <div className="text-[11px] mt-0.5" style={{ color: "var(--color-text-secondary)" }}>
                      메시지 {s.message_count}개
                    </div>
                  </button>
                </li>
              ))}
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
                        {/* Action 카드 (assistant만) */}
                        {parsed?.cards.map((c, i) => (
                          <div
                            key={i}
                            className="flex items-center gap-2 rounded-xl px-3 py-2"
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
                          >
                            <span aria-hidden className="text-[16px] flex-shrink-0">
                              {c.icon}
                            </span>
                            <span
                              className="text-[13px]"
                              style={{
                                fontFamily: "var(--font-feeling)",
                                color: "var(--color-text-primary)",
                              }}
                            >
                              {c.text}
                            </span>
                          </div>
                        ))}
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
