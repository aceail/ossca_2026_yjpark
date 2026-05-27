import type { MetadataRoute } from "next";

// Wave 5: PWA manifest — 모바일 홈 화면에서 standalone 앱처럼 동작.
// Chrome/Edge/Samsung 브라우저는 SVG 아이콘 지원. iOS Safari는 별도
// apple-touch-icon meta가 layout.tsx에 들어가 있음.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "내일의 너",
    short_name: "내일의 너",
    description: "미래 자아가 현재의 나를 reality-check 하는 로컬 에이전트",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "portrait-primary",
    background_color: "#F7F6F3",
    theme_color: "#1A1A1A",
    icons: [
      {
        src: "/icon.svg",
        sizes: "any",
        type: "image/svg+xml",
        purpose: "any",
      },
      {
        src: "/icon.svg",
        sizes: "any",
        type: "image/svg+xml",
        purpose: "maskable",
      },
    ],
  };
}
