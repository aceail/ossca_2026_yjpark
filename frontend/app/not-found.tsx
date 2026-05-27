import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex flex-1 flex-col items-start justify-center min-h-screen py-20">
      <p
        className="text-foreground"
        style={{
          fontFamily: "var(--font-feeling-loaded), 'Noto Sans KR', sans-serif",
          fontSize: "16px",
        }}
      >
        이 페이지는 잠시 사라졌어요.{" "}
        <Link
          href="/"
          className="underline underline-offset-4 hover:opacity-60 transition-opacity"
        >
          홈으로
        </Link>
      </p>
    </main>
  );
}
