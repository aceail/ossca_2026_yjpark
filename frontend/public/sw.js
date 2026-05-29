// Wave 5: 서비스 워커 — offline 캐시 (stale-while-revalidate) + Wave 6 push handler stub.
// 외부 라이브러리 없이 stdlib만 (OSS 정렬).

const CACHE_NAME = "naeil-v23";  // Sprint 40 — interactive cards + time
const APP_SHELL = ["/", "/chat", "/tasks", "/calendar", "/settings", "/personas", "/icon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL).catch(() => {})),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))),
    ),
  );
  self.clients.claim();
});

// Sprint 36: HTML 페이지는 network-first (SSR/RSC + Next.js 빌드별 chunk hash
// 변경 때문에 stale HTML이 사용자에게 가면 chunk 404 → 페이지가 깨짐).
// 정적 자산은 cache-first (Next.js가 chunk filename에 hash 박아서 안전).
self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.pathname.startsWith("/api/")) return;  // API는 캐시 안 함

  const isDoc = req.mode === "navigate" || req.destination === "document";
  if (isDoc) {
    event.respondWith(
      fetch(req).catch(async () => {
        const cache = await caches.open(CACHE_NAME);
        return (await cache.match(req)) || (await cache.match("/")) || Response.error();
      }),
    );
    return;
  }

  event.respondWith(
    caches.open(CACHE_NAME).then(async (cache) => {
      const cached = await cache.match(req);
      if (cached) return cached;
      try {
        const fresh = await fetch(req);
        if (fresh.ok && fresh.type === "basic") cache.put(req, fresh.clone());
        return fresh;
      } catch {
        return cached || Response.error();
      }
    }),
  );
});

// Wave 6: Web Push handler (VAPID). 지금은 stub — 알림 권한 받은 사용자만 발송.
self.addEventListener("push", (event) => {
  let payload = { title: "내일의 너", body: "마감 알림이 있어요" };
  try {
    if (event.data) payload = { ...payload, ...event.data.json() };
  } catch {
    if (event.data) payload.body = event.data.text();
  }
  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      icon: "/icon.svg",
      badge: "/icon.svg",
      actions: payload.actions || [],
      data: payload.data || (payload.url ? { url: payload.url } : undefined),
    }),
  );
});

// Sprint 39: notification click handler. action button 처리 + click 보고.
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const data = (event.notification.data || {});
  const nid = data.notification_id || null;
  const action = event.action || "";

  if (action.startsWith("done:")) {
    const taskId = action.slice(5);
    event.waitUntil(
      fetch(`/api/tasks/${taskId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "done" }),
      })
        .catch(() => {})
        .then(() => reportClick(nid, "done"))
    );
    return;
  }
  if (action.startsWith("snooze:")) {
    event.waitUntil(
      fetch(`/api/push/${nid}/snooze`, { method: "POST" })
        .catch(() => {})
        .then(() => reportClick(nid, "snooze"))
    );
    return;
  }
  event.waitUntil(
    Promise.all([
      reportClick(nid, "open"),
      self.clients.openWindow(data.url || "/"),
    ])
  );
});

function reportClick(nid, action) {
  if (!nid) return Promise.resolve();
  return fetch(`/api/push/${nid}/clicked`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action }),
  }).catch(() => {});
}
