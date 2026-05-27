"use client";

import { useEffect } from "react";

// PWA service worker 등록 — 클라이언트에서만, install 후 캐시·push 알림 활성화.
// dev 모드에서도 HTTPS·localhost면 동작 (브라우저 정책).
export function ServiceWorkerRegister() {
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!("serviceWorker" in navigator)) return;
    // 등록 실패해도 앱 작동에 영향 없음 — graceful
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }, []);
  return null;
}
