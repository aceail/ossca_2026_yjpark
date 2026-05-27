"use client";

import React from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";

// 모바일에서만 노출 (md:hidden). 4개 탭: Chat / Tasks / Calendar / Settings.
// PWA standalone 모드에서도 잠금 화면 알림 클릭 시 자연스럽게 이동 가능.

interface TabDef {
  href: string;
  label: string;
  icon: string;
}

const TABS: TabDef[] = [
  { href: "/chat", label: "채팅", icon: "💬" },
  { href: "/tasks", label: "작업", icon: "✓" },
  { href: "/calendar", label: "캘린더", icon: "📅" },
  { href: "/settings", label: "설정", icon: "⚙" },
];

export function BottomTabs() {
  const path = usePathname();
  // 온보딩·메인 진입 페이지에서는 탭 숨김
  if (path === "/" || path?.startsWith("/onboarding")) return null;

  return (
    <nav
      aria-label="주요 탭"
      className="md:hidden fixed bottom-0 left-0 right-0 z-30 flex justify-around"
      style={{
        backgroundColor: "var(--color-bg-card)",
        borderTop: "1px solid var(--color-border-subtle)",
        paddingBottom: "env(safe-area-inset-bottom)",
      }}
    >
      {TABS.map((t) => {
        const active = path === t.href || (path?.startsWith(t.href) ?? false);
        return (
          <Link
            key={t.href}
            href={t.href}
            aria-current={active ? "page" : undefined}
            className="flex flex-col items-center justify-center py-2 px-3 flex-1"
            style={{
              color: active
                ? "var(--color-text-primary)"
                : "var(--color-text-secondary)",
              minHeight: "44px",
            }}
          >
            <span className="text-[18px] leading-none" aria-hidden>
              {t.icon}
            </span>
            <span className="text-[10px] mt-0.5">{t.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
