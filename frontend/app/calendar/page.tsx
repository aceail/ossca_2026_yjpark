"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useUser } from "../../lib/hooks/useUser";
import { Button } from "../../components/Button";
import { authHeaders } from "../../lib/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8001";

interface CalendarEvent {
  id: string;
  source: string;
  title: string;
  starts_at: string | null;
  ends_at: string | null;
  status: string | null;
  color: string | null;
}

const KO_WEEKDAY = ["일", "월", "화", "수", "목", "금", "토"];

function ymdLocal(d: Date): string {
  // local YYYY-MM-DD
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${dd}`;
}

function eventsByDay(events: CalendarEvent[]): Map<string, CalendarEvent[]> {
  const map = new Map<string, CalendarEvent[]>();
  for (const e of events) {
    if (!e.starts_at) continue;
    const key = e.starts_at.slice(0, 10);
    const list = map.get(key) ?? [];
    list.push(e);
    map.set(key, list);
  }
  return map;
}

export default function CalendarPage() {
  const { userId, loading: userLoading } = useUser();
  const [cursor, setCursor] = useState<Date>(() => new Date());
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  const fetchEvents = useCallback(async (uid: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/calendar/${uid}/events`, {
        headers: { ...authHeaders() },
      });
      if (!res.ok) throw new Error(`목록 로드 실패 (${res.status})`);
      const data = await res.json();
      setEvents(data.events ?? []);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    if (userId) fetchEvents(userId);
  }, [userId, fetchEvents]);

  const byDay = useMemo(() => eventsByDay(events), [events]);

  const monthDays = useMemo(() => {
    // 일요일 시작 grid. 해당 달이 차지하는 실제 주 수(4~6)만큼만 그린다.
    // 28일·일요일 시작 (4 row) ~ 31일·금토 시작 (6 row) 범위.
    const year = cursor.getFullYear();
    const month = cursor.getMonth();
    const first = new Date(year, month, 1);
    const lastDate = new Date(year, month + 1, 0).getDate();
    const startSunday = new Date(first);
    startSunday.setDate(first.getDate() - first.getDay());
    const cellsNeeded = first.getDay() + lastDate;
    const rowsNeeded = Math.ceil(cellsNeeded / 7);
    const totalCells = rowsNeeded * 7;
    return Array.from({ length: totalCells }, (_, i) => {
      const d = new Date(startSunday);
      d.setDate(startSunday.getDate() + i);
      return d;
    });
  }, [cursor]);

  const monthLabel = `${cursor.getFullYear()}년 ${cursor.getMonth() + 1}월`;
  const today = ymdLocal(new Date());

  if (userLoading) {
    return (
      <main className="p-8 min-h-screen" style={{ backgroundColor: "var(--color-bg-base)" }}>
        <p style={{ color: "var(--color-text-secondary)" }}>로딩 중...</p>
      </main>
    );
  }

  return (
    <main
      className="min-h-screen p-6 max-w-3xl mx-auto"
      style={{ backgroundColor: "var(--color-bg-base)", color: "var(--color-text-primary)" }}
    >
      <header className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-[22px] font-semibold" style={{ fontFamily: "var(--font-feeling)" }}>
            캘린더
          </h1>
          <p className="text-[12px]" style={{ color: "var(--color-text-secondary)" }}>
            마감일이 있는 작업이 여기 표시돼요
          </p>
        </div>
        <a
          href="/settings#external-calendar"
          className="text-[12px] underline-offset-2 hover:underline"
          style={{ color: "var(--color-text-secondary)" }}
        >
          외부 캘린더 연동 →
        </a>
      </header>

      {error && (
        <p className="text-[12px] mb-3" style={{ color: "#B00020" }}>
          {error}
        </p>
      )}

      <div className="flex items-center justify-between mb-3">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1))}
          aria-label="이전 달"
        >
          ‹
        </Button>
        <span className="text-[15px] font-medium">{monthLabel}</span>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1))}
          aria-label="다음 달"
        >
          ›
        </Button>
      </div>

      <div
        className="grid grid-cols-7 gap-px rounded-lg overflow-hidden"
        style={{ backgroundColor: "var(--color-border-subtle)" }}
      >
        {KO_WEEKDAY.map((w, i) => (
          <div
            key={w}
            className="text-[11px] py-1.5 text-center font-medium"
            style={{
              backgroundColor: "var(--color-bg-card)",
              color:
                i === 0
                  ? "#B00020"
                  : i === 6
                    ? "var(--color-regret-accent)"
                    : "var(--color-text-secondary)",
            }}
          >
            {w}
          </div>
        ))}
        {monthDays.map((d) => {
          const inMonth = d.getMonth() === cursor.getMonth();
          const key = ymdLocal(d);
          const dayEvents = byDay.get(key) ?? [];
          const isToday = key === today;
          return (
            <div
              key={key}
              className="min-h-[70px] px-1.5 py-1 text-[11px] relative"
              style={{
                backgroundColor: isToday
                  ? "var(--color-recovery-bg)"
                  : "var(--color-bg-card)",
                opacity: inMonth ? 1 : 0.35,
              }}
            >
              <div
                style={{
                  fontWeight: isToday ? 600 : 400,
                  color: isToday ? "var(--color-recovery-accent)" : "var(--color-text-primary)",
                }}
              >
                {d.getDate()}
              </div>
              <div className="flex flex-col gap-0.5 mt-0.5">
                {dayEvents.slice(0, 3).map((e) => (
                  <div
                    key={e.id}
                    className="truncate rounded px-1 py-0.5 text-[10px]"
                    style={{
                      backgroundColor: e.color ?? "var(--color-text-secondary)",
                      color: "#fff",
                      textDecoration: e.status === "done" ? "line-through" : "none",
                      opacity: e.status === "done" ? 0.5 : 1,
                    }}
                    title={e.title}
                  >
                    {e.title}
                  </div>
                ))}
                {dayEvents.length > 3 && (
                  <div className="text-[10px]" style={{ color: "var(--color-text-secondary)" }}>
                    +{dayEvents.length - 3}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex justify-between items-center mt-5">
        <a
          href="/tasks"
          className="text-[12px] underline-offset-2 hover:underline"
          style={{ color: "var(--color-text-secondary)" }}
        >
          ← 작업 목록
        </a>
        <a
          href="/chat"
          className="text-[12px] underline-offset-2 hover:underline"
          style={{ color: "var(--color-text-secondary)" }}
        >
          채팅에서 마감 말하기 →
        </a>
      </div>
    </main>
  );
}
