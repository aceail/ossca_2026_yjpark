import type { Metadata, Viewport } from "next";
import "./globals.css";
import { BottomTabs } from "../components/BottomTabs";
import { ServiceWorkerRegister } from "../components/ServiceWorkerRegister";

// Sprint 36: next/font/google의 Noto_Serif/Sans_KR + subsets:["latin"] 조합은
// 한글 글리프를 안 받아오면서도 폰트 파일을 다운로드해 FCP를 늦췄다. 한국어
// 시스템 폰트(Apple SD Gothic Neo / Malgun Gothic / Noto CJK)가 우수하니
// 웹 폰트 다운로드 제거하고 globals.css의 fallback chain에 맡긴다.

export const metadata: Metadata = {
  title: "내일의 너 — Tomorrow's You",
  description:
    "미래의 내가 지금의 나에게 보내는 메시지. 회피하는 순간, 한 문장이 마음에 박힌다.",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "내일의 너",
  },
  icons: {
    icon: [{ url: "/icon.svg", type: "image/svg+xml" }],
    apple: [{ url: "/icon.svg" }],
  },
};

export const viewport: Viewport = {
  themeColor: "#1A1A1A",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="ko"
      className="h-full antialiased"
    >
      <body className="min-h-full flex flex-col bg-background text-foreground">
        <ServiceWorkerRegister />
        <div className="flex flex-col flex-1 w-full max-w-screen-lg mx-auto px-6 sm:px-10 pb-16">
          {children}
        </div>
        <BottomTabs />
      </body>
    </html>
  );
}
