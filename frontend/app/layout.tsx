import type { Metadata, Viewport } from "next";
import { Noto_Serif_KR, Noto_Sans_KR } from "next/font/google";
import "./globals.css";
import { BottomTabs } from "../components/BottomTabs";
import { ServiceWorkerRegister } from "../components/ServiceWorkerRegister";

const serif = Noto_Serif_KR({
  subsets: ["latin"],
  variable: "--font-fact-loaded",
  weight: ["400", "600"],
  display: "swap",
});

const sans = Noto_Sans_KR({
  subsets: ["latin"],
  variable: "--font-feeling-loaded",
  weight: ["400", "500", "700"],
  display: "swap",
});

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
      className={`${serif.variable} ${sans.variable} h-full antialiased`}
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
