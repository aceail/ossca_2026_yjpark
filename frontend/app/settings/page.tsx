"use client";

import React, { useEffect, useState, useCallback } from "react";
import { useUser } from "../../lib/hooks/useUser";
import { Button } from "../../components/Button";
import { authHeaders } from "../../lib/auth";
import type { Persona } from "../../lib/personas";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8001";

interface SafetyWeek {
  week_start: string;
  self_blame_word_count: number;
  identity_failure_count: number;
  failure_imagery_ratio: number;
  pre_card_tension: number;
}

interface UserProfile {
  id: string;
  active_persona_id: number;
  onboarding_completed: boolean;
  created_at: string;
  forbidden_topics?: string[];
}

// P0-15: 외부 도구 동의
interface ConsentItem {
  tool_id: number;
  tool_name: string;
  tool_type: string;
  granted_at: string | null;
  revoked_at: string | null;
  active: boolean;
}

const TOOL_LABELS: Record<string, { label: string; hint: string }> = {
  "google_calendar.list_events": {
    label: "Google Calendar — 다가올 일정 조회",
    hint: "마감·일정 키워드 감지 시 다가올 7일 일정을 참고합니다.",
  },
  "local_files.recent": {
    label: "로컬 파일 — 최근 수정 목록",
    hint: "문서·발표·논문 키워드 감지 시 최근 파일 목록을 참고합니다.",
  },
  "web_search.brave": {
    label: "웹 검색 — Brave / SearXNG",
    hint: "참고·예시·검색 키워드 감지 시 웹 검색 결과를 참고합니다.",
  },
};

interface Toast {
  id: number;
  message: string;
}

function MiniBar({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div
      className="relative h-2 rounded-full overflow-hidden"
      style={{ backgroundColor: "var(--color-border-subtle)", width: "60px" }}
    >
      <div
        className="absolute left-0 top-0 h-full rounded-full"
        style={{
          width: `${pct}%`,
          backgroundColor: "var(--color-text-secondary)",
          opacity: 0.6,
        }}
      />
    </div>
  );
}

function detectSelfBlameRising(weeks: SafetyWeek[]): boolean {
  if (weeks.length < 4) return false;
  const last4 = weeks.slice(-4).map((w) => w.self_blame_word_count);
  for (let i = 1; i < last4.length; i++) {
    if (last4[i] <= last4[i - 1]) return false;
  }
  return true;
}

export default function SettingsPage() {
  const { userId, loading: userLoading } = useUser();

  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [activePersona, setActivePersona] = useState<Persona | null>(null);
  const [safetyTrend, setSafetyTrend] = useState<SafetyWeek[]>([]);
  const [loadingTrend, setLoadingTrend] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const [forbiddenTopics, setForbiddenTopics] = useState<string[]>([]);
  const [topicInput, setTopicInput] = useState("");
  const [savingTopics, setSavingTopics] = useState(false);

  const [consents, setConsents] = useState<ConsentItem[]>([]);
  const [togglingTool, setTogglingTool] = useState<number | null>(null);

  const [toasts, setToasts] = useState<Toast[]>([]);

  const showToast = useCallback((message: string) => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 3000);
  }, []);

  const fetchProfile = useCallback(async (uid: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/users/${uid}/profile`, {
        headers: { ...authHeaders() },
      });
      if (!res.ok) return;
      const data: UserProfile = await res.json();
      setProfile(data);
      setForbiddenTopics(data.forbidden_topics ?? []);

      if (data.active_persona_id) {
        const pRes = await fetch(`${API_BASE}/api/personas?user_id=${uid}`, {
          headers: { ...authHeaders() },
        });
        if (pRes.ok) {
          const personas: Persona[] = await pRes.json();
          const found = personas.find((p) => p.id === data.active_persona_id) ?? null;
          setActivePersona(found);
        }
      }
    } catch {
      // silent
    }
  }, []);

  const fetchSafetyTrend = useCallback(async (uid: string) => {
    setLoadingTrend(true);
    try {
      const res = await fetch(`${API_BASE}/api/users/${uid}/safety-trend`, {
        headers: { ...authHeaders() },
      });
      if (!res.ok) return;
      const data: SafetyWeek[] = await res.json();
      setSafetyTrend(data);
    } catch {
      // silent
    } finally {
      setLoadingTrend(false);
    }
  }, []);

  const fetchConsents = useCallback(async (uid: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/users/${uid}/agent-consents`, {
        headers: { ...authHeaders() },
      });
      if (!res.ok) return;
      const data = await res.json();
      setConsents(data.consents ?? []);
    } catch {
      // silent
    }
  }, []);

  useEffect(() => {
    if (userId) {
      fetchProfile(userId);
      fetchSafetyTrend(userId);
      fetchConsents(userId);
    }
  }, [userId, fetchProfile, fetchSafetyTrend, fetchConsents]);

  const toggleConsent = async (item: ConsentItem) => {
    if (!userId) return;
    setTogglingTool(item.tool_id);
    try {
      const method = item.active ? "DELETE" : "POST";
      const res = await fetch(
        `${API_BASE}/api/users/${userId}/agent-consents/${item.tool_id}`,
        { method, headers: { ...authHeaders() } },
      );
      if (!res.ok) throw new Error("toggle failed");
      await fetchConsents(userId);
      showToast(item.active ? "동의를 철회했어요" : "✓ 동의했어요");
    } catch {
      showToast("변경 중 오류가 발생했어요");
    } finally {
      setTogglingTool(null);
    }
  };

  const handleRefreshSnapshot = async () => {
    if (!userId) return;
    setRefreshing(true);
    try {
      await fetch(`${API_BASE}/api/users/${userId}/safety-snapshot/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
      });
      await fetchSafetyTrend(userId);
      showToast("이번 주 데이터를 다시 계산했어요");
    } catch {
      showToast("새로고침 중 오류가 발생했어요");
    } finally {
      setRefreshing(false);
    }
  };

  const handleTopicKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      const val = topicInput.trim();
      if (val && !forbiddenTopics.includes(val)) {
        setForbiddenTopics((prev) => [...prev, val]);
      }
      setTopicInput("");
    }
  };

  const removeTopic = (topic: string) => {
    setForbiddenTopics((prev) => prev.filter((t) => t !== topic));
  };

  const saveTopics = async () => {
    if (!userId) return;
    setSavingTopics(true);
    try {
      // forbidden_topics 갱신 — onboarding endpoint 재활용
      const res = await fetch(`${API_BASE}/api/onboarding`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ user_id: userId, forbidden_topics: forbiddenTopics }),
      });
      if (!res.ok) throw new Error("저장 실패");
      showToast("✓ 금지 주제가 저장됐어요");
    } catch {
      showToast("저장 중 오류가 발생했어요");
    } finally {
      setSavingTopics(false);
    }
  };

  const handleDownload = () => {
    if (!userId) return;
    // stub: 실제 엔드포인트 미구현 — 로컬 데이터만 내보냄
    const exportData = {
      user_id: userId,
      profile,
      forbidden_topics: forbiddenTopics,
      exported_at: new Date().toISOString(),
    };
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `naeil-data-${userId}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleSelfDestruct = async () => {
    if (!confirm("정말 모든 데이터를 영구 삭제할까요? 되돌릴 수 없어요.")) return;
    if (!userId) return;
    try {
      // stub: DELETE endpoint 미구현 시 로컬 초기화
      await fetch(`${API_BASE}/api/users/${userId}`, { method: "DELETE" }).catch(() => {});
    } finally {
      localStorage.clear();
      window.location.href = "/";
    }
  };

  const isSelfBlameRising = detectSelfBlameRising(safetyTrend);

  const maxSelfBlame = Math.max(...safetyTrend.map((w) => w.self_blame_word_count), 1);
  const maxIdentityFail = Math.max(...safetyTrend.map((w) => w.identity_failure_count), 1);

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
      {/* 헤더 */}
      <div className="flex items-center justify-between mb-8">
        <h1
          className="text-[22px] font-semibold"
          style={{ fontFamily: "var(--font-feeling)" }}
        >
          설정
        </h1>
        <Button
          variant="destruct"
          size="sm"
          onClick={handleSelfDestruct}
          title="모든 데이터 영구 삭제"
        >
          ⊗
        </Button>
      </div>

      <div className="flex flex-col gap-8">
        {/* 섹션 1: 활성 페르소나 */}
        <section>
          <h2 className="text-[14px] font-semibold mb-3" style={{ fontFamily: "var(--font-feeling)" }}>
            활성 페르소나
          </h2>
          <div
            className="flex items-center justify-between px-4 py-3 rounded-xl"
            style={{
              backgroundColor: "var(--color-bg-card)",
              border: "1px solid var(--color-border-subtle)",
            }}
          >
            {activePersona ? (
              <div className="flex items-center gap-3 min-w-0">
                <div
                  className="w-1 h-10 rounded-full flex-shrink-0"
                  style={{ backgroundColor: activePersona.avatar_color }}
                />
                <div className="min-w-0">
                  <p className="text-[13px] font-medium">
                    {activePersona.avatar_icon} {activePersona.name}
                  </p>
                  <p className="text-[11px] truncate" style={{ color: "var(--color-text-secondary)" }}>
                    {activePersona.perspective === "1st"
                      ? "1인칭"
                      : activePersona.perspective === "2nd"
                        ? "2인칭"
                        : "3인칭"}{" "}
                    · {activePersona.tone_mode}
                  </p>
                </div>
              </div>
            ) : (
              <p className="text-[13px]" style={{ color: "var(--color-text-secondary)" }}>
                설정된 페르소나가 없어요
              </p>
            )}
            <a
              href="/personas"
              className="text-[12px] flex-shrink-0 ml-4 underline-offset-2 hover:underline"
              style={{ color: "var(--color-text-secondary)" }}
            >
              변경하러 가기 →
            </a>
          </div>
        </section>

        {/* 섹션 2: 금지 주제 */}
        <section>
          <h2 className="text-[14px] font-semibold mb-1" style={{ fontFamily: "var(--font-feeling)" }}>
            금지 주제
          </h2>
          <p className="text-[12px] mb-3" style={{ color: "var(--color-text-secondary)" }}>
            이 주제들은 카드에 등장하지 않아요. Enter로 추가, ×로 제거.
          </p>
          <input
            type="text"
            value={topicInput}
            onChange={(e) => setTopicInput(e.target.value)}
            onKeyDown={handleTopicKeyDown}
            placeholder="예: 연애, 가족, 돈"
            className="w-full px-3 py-2 text-[13px] rounded-lg outline-none mb-3"
            style={{
              backgroundColor: "var(--color-bg-card)",
              border: "1px solid var(--color-border-subtle)",
              color: "var(--color-text-primary)",
            }}
          />
          {forbiddenTopics.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-3">
              {forbiddenTopics.map((topic) => (
                <span
                  key={topic}
                  className="flex items-center gap-1 px-2 py-0.5 text-[11px] rounded-full"
                  style={{
                    backgroundColor: "var(--color-bg-card)",
                    border: "1px solid var(--color-border-subtle)",
                    color: "var(--color-text-secondary)",
                  }}
                >
                  {topic}
                  <button
                    type="button"
                    onClick={() => removeTopic(topic)}
                    className="opacity-50 hover:opacity-100 transition-opacity"
                    aria-label={`${topic} 제거`}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}
          <Button variant="ghost" size="sm" onClick={saveTopics} disabled={savingTopics}>
            {savingTopics ? "저장 중..." : "저장"}
          </Button>
        </section>

        {/* 섹션 2.5: 외부 도구 동의 (P0-15) */}
        <section>
          <h2 className="text-[14px] font-semibold mb-1" style={{ fontFamily: "var(--font-feeling)" }}>
            외부 도구 연결 동의
          </h2>
          <p className="text-[12px] mb-3" style={{ color: "var(--color-text-secondary)" }}>
            동의한 도구만 시나리오 생성 시 참고됩니다. 기본은 모두 미동의.
          </p>
          {consents.length === 0 ? (
            <p className="text-[12px]" style={{ color: "var(--color-text-secondary)" }}>
              불러오는 중...
            </p>
          ) : (
            <div className="flex flex-col gap-2">
              {consents.map((item) => {
                const meta = TOOL_LABELS[item.tool_name] ?? {
                  label: item.tool_name,
                  hint: "",
                };
                return (
                  <div
                    key={item.tool_id}
                    className="flex items-start justify-between gap-3 px-4 py-3 rounded-xl"
                    style={{
                      backgroundColor: "var(--color-bg-card)",
                      border: "1px solid var(--color-border-subtle)",
                    }}
                  >
                    <div className="min-w-0">
                      <p className="text-[13px] font-medium">{meta.label}</p>
                      {meta.hint && (
                        <p className="text-[11px] mt-0.5" style={{ color: "var(--color-text-secondary)" }}>
                          {meta.hint}
                        </p>
                      )}
                    </div>
                    <Button
                      variant={item.active ? "ghost" : "primary"}
                      size="sm"
                      onClick={() => toggleConsent(item)}
                      disabled={togglingTool === item.tool_id}
                      aria-pressed={item.active}
                    >
                      {togglingTool === item.tool_id
                        ? "..."
                        : item.active
                          ? "✓ 동의함"
                          : "동의하기"}
                    </Button>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* 섹션 3: Safety 트렌드 */}
        <section>
          <div className="flex items-center justify-between mb-1">
            <h2 className="text-[14px] font-semibold" style={{ fontFamily: "var(--font-feeling)" }}>
              Safety 트렌드 (최근 8주)
            </h2>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleRefreshSnapshot}
              disabled={refreshing || !userId}
            >
              {refreshing ? "계산 중..." : "지금 한 주 다시 계산"}
            </Button>
          </div>
          <p className="text-[12px] mb-4" style={{ color: "var(--color-text-secondary)" }}>
            자기 비난·실패 이미지·긴장도 패턴을 주별로 봐요
          </p>

          {isSelfBlameRising && (
            <div
              className="px-4 py-3 rounded-xl mb-4 text-[13px]"
              style={{
                backgroundColor: "var(--color-bg-card)",
                border: "1px solid var(--color-border-subtle)",
                color: "var(--color-text-secondary)",
              }}
            >
              최근 패턴이 좀 무거워 보여요. recovery 카드를 더 자주 보여드릴까요?
            </div>
          )}

          {loadingTrend ? (
            <p className="text-[13px]" style={{ color: "var(--color-text-secondary)" }}>
              불러오는 중...
            </p>
          ) : safetyTrend.length === 0 ? (
            <p className="text-[13px]" style={{ color: "var(--color-text-secondary)" }}>
              아직 데이터가 없어요. 카드를 더 사용하면 나타나요.
            </p>
          ) : (
            <div
              className="overflow-x-auto rounded-xl"
              style={{
                border: "1px solid var(--color-border-subtle)",
              }}
            >
              <table className="w-full text-[12px] border-collapse">
                <thead>
                  <tr style={{ backgroundColor: "var(--color-bg-card)" }}>
                    <th
                      className="px-3 py-2 text-left font-medium"
                      style={{ color: "var(--color-text-secondary)", borderBottom: "1px solid var(--color-border-subtle)" }}
                    >
                      주
                    </th>
                    <th
                      className="px-3 py-2 text-left font-medium"
                      style={{ color: "var(--color-text-secondary)", borderBottom: "1px solid var(--color-border-subtle)" }}
                    >
                      자기비난
                    </th>
                    <th
                      className="px-3 py-2 text-left font-medium"
                      style={{ color: "var(--color-text-secondary)", borderBottom: "1px solid var(--color-border-subtle)" }}
                    >
                      정체성실패
                    </th>
                    <th
                      className="px-3 py-2 text-left font-medium"
                      style={{ color: "var(--color-text-secondary)", borderBottom: "1px solid var(--color-border-subtle)" }}
                    >
                      실패이미지
                    </th>
                    <th
                      className="px-3 py-2 text-left font-medium"
                      style={{ color: "var(--color-text-secondary)", borderBottom: "1px solid var(--color-border-subtle)" }}
                    >
                      긴장도
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {safetyTrend.map((week, idx) => (
                    <tr
                      key={week.week_start}
                      style={{
                        backgroundColor:
                          idx % 2 === 0 ? "var(--color-bg-base)" : "var(--color-bg-card)",
                      }}
                    >
                      <td
                        className="px-3 py-2"
                        style={{ color: "var(--color-text-secondary)" }}
                      >
                        {week.week_start.slice(5, 10).replace("-", "/")}
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-2">
                          <span style={{ color: "var(--color-text-primary)" }}>
                            {week.self_blame_word_count}
                          </span>
                          <MiniBar value={week.self_blame_word_count} max={maxSelfBlame} />
                        </div>
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-2">
                          <span style={{ color: "var(--color-text-primary)" }}>
                            {week.identity_failure_count}
                          </span>
                          <MiniBar value={week.identity_failure_count} max={maxIdentityFail} />
                        </div>
                      </td>
                      <td
                        className="px-3 py-2"
                        style={{ color: "var(--color-text-primary)" }}
                      >
                        {(week.failure_imagery_ratio * 100).toFixed(0)}%
                      </td>
                      <td
                        className="px-3 py-2"
                        style={{ color: "var(--color-text-primary)" }}
                      >
                        {week.pre_card_tension.toFixed(1)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* 섹션 4: 데이터 */}
        <section>
          <h2 className="text-[14px] font-semibold mb-3" style={{ fontFamily: "var(--font-feeling)" }}>
            내 데이터
          </h2>
          <div className="flex flex-col gap-3">
            <div
              className="flex items-center justify-between px-4 py-3 rounded-xl"
              style={{
                backgroundColor: "var(--color-bg-card)",
                border: "1px solid var(--color-border-subtle)",
              }}
            >
              <div>
                <p className="text-[13px] font-medium">내 모든 데이터 다운로드</p>
                <p className="text-[11px]" style={{ color: "var(--color-text-secondary)" }}>
                  JSON 파일로 내보내요 (로컬 데이터 기준)
                </p>
              </div>
              <Button variant="ghost" size="sm" onClick={handleDownload}>
                다운로드
              </Button>
            </div>

            <div
              className="flex items-center justify-between px-4 py-3 rounded-xl"
              style={{
                backgroundColor: "var(--color-bg-card)",
                border: "1px solid var(--color-border-subtle)",
              }}
            >
              <div>
                <p className="text-[13px] font-medium">모든 데이터 영구 삭제</p>
                <p className="text-[11px]" style={{ color: "var(--color-text-secondary)" }}>
                  계정 전체 삭제 · 되돌릴 수 없음 (우상단 ⊗와 동일)
                </p>
              </div>
              <Button variant="destruct" size="sm" onClick={handleSelfDestruct}>
                삭제
              </Button>
            </div>
          </div>
        </section>
      </div>

      {/* 토스트 */}
      <div className="fixed top-4 right-4 flex flex-col gap-2 z-50">
        {toasts.map((t) => (
          <div
            key={t.id}
            className="px-4 py-2 rounded-lg text-[13px] shadow-lg"
            style={{
              backgroundColor: "var(--color-bg-card)",
              border: "1px solid var(--color-border-subtle)",
              color: "var(--color-text-primary)",
            }}
          >
            {t.message}
          </div>
        ))}
      </div>
    </main>
  );
}
