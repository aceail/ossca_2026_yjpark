"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

export default function Welcome() {
  const router = useRouter();
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    const userId = localStorage.getItem("user_id");
    if (userId) {
      router.replace("/scenario");
    } else {
      setChecking(false);
    }
  }, [router]);

  if (checking) {
    return (
      <main className="flex flex-1 items-center justify-center min-h-screen -mx-6 sm:-mx-10 bg-neutral-950">
        <span className="text-neutral-600 text-sm font-sans">잠시만요</span>
      </main>
    );
  }

  return (
    <main className="flex flex-1 flex-col justify-center min-h-screen -mx-6 sm:-mx-10 bg-neutral-950 px-[60px]">
      {/* 메인 카피 — Noto Serif KR, 좌정렬 */}
      <div className="animate-fade-in">
        <p
          className="text-white leading-relaxed"
          style={{
            fontFamily: "var(--font-fact-loaded), 'Noto Serif KR', serif",
            fontSize: "clamp(22px, 2.5vw, 28px)",
            fontWeight: 400,
          }}
        >
          나는 지금 발표 5분 전,
          <br />
          어젯밤 내가 무엇을 하고 있었는지 알고 있다.
        </p>
      </div>

      {/* 서브카피 — 1초 딜레이 fade-in */}
      <div className="mt-6 animate-fade-in-delay">
        <p
          className="text-neutral-500"
          style={{
            fontFamily: "var(--font-feeling-loaded), 'Noto Sans KR', sans-serif",
            fontSize: "14px",
            fontWeight: 400,
          }}
        >
          — 내일의 너
        </p>
      </div>

      {/* CTA 버튼 — 2초 딜레이 */}
      <div className="mt-16 animate-fade-in-cta">
        <button
          onClick={() => router.push("/onboarding")}
          className="text-white border border-neutral-600 px-8 py-3 text-sm tracking-widest hover:border-white transition-colors duration-300 cursor-pointer"
          style={{
            fontFamily: "var(--font-feeling-loaded), 'Noto Sans KR', sans-serif",
            fontWeight: 500,
          }}
        >
          [ 시작하기 ]
        </button>
      </div>
    </main>
  );
}
