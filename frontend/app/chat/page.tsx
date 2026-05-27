"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
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

export default function ChatPage() {
  const { userId, loading: userLoading } = useUser();

  const [sessionId, setSessionId] = useState<number | null>(null);
  const [sessions, setSessions] = useState<ChatSessionListItem[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const listEndRef = useRef<HTMLDivElement | null>(null);

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

  useEffect(() => {
    if (userId) ensureSession(userId);
  }, [userId, ensureSession]);

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
        <section className="flex-1 flex flex-col min-w-0">
          <div className="flex-1 overflow-y-auto px-6 py-6">
            {messages.length === 0 ? (
              <p className="text-[13px] text-center mt-12" style={{ color: "var(--color-text-secondary)" }}>
                첫 메시지를 보내보세요. 활성 페르소나가 답해요.
              </p>
            ) : (
              <ul className="flex flex-col gap-3 max-w-[640px] mx-auto">
                {messages.map((m) => {
                  const isUser = m.role === "user";
                  return (
                    <li
                      key={m.id}
                      className={`flex ${isUser ? "justify-end" : "justify-start"}`}
                    >
                      <div
                        className="rounded-2xl px-4 py-2.5 max-w-[80%] whitespace-pre-wrap"
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
                        {m.content}
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
                placeholder={sending ? "응답 생성 중..." : "한 줄 적어도 충분해요"}
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
      </div>
    </main>
  );
}
