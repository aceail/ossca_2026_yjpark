import type { Metadata } from "next";
import { Noto_Serif_KR, Noto_Sans_KR } from "next/font/google";
import "./globals.css";

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
        <div className="flex flex-col flex-1 w-full max-w-screen-lg mx-auto px-6 sm:px-10">
          {children}
        </div>
      </body>
    </html>
  );
}
