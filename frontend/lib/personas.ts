export interface Persona {
  id: number;
  name: string;
  perspective: "1st" | "2nd" | "3rd";
  tone_mode: "Quiet" | "Sharp" | "Witty" | "Savage";
  voice_style: string;
  greeting: string;
  avatar_color: string;
  avatar_icon: string;
}

export const BUILTIN_PERSONAS: Omit<Persona, "id">[] = [
  {
    name: "내일의 나",
    perspective: "1st",
    tone_mode: "Sharp",
    voice_style: "1인칭 직접 화법, 현재 사실 진술",
    greeting: "내일의 내가 너에게 보낸 메시지야",
    avatar_color: "#3B6B9A",
    avatar_icon: "🌙",
  },
  {
    name: "1년 후의 나",
    perspective: "1st",
    tone_mode: "Quiet",
    voice_style: "1인칭 회고 화법, 조용하고 담담하게",
    greeting: "1년 뒤의 내가 짧게 한 마디",
    avatar_color: "#5A7080",
    avatar_icon: "🌅",
  },
  {
    name: "친한 친구",
    perspective: "2nd",
    tone_mode: "Witty",
    voice_style: "2인칭 구어체, 능청맞은 친구 톤",
    greeting: "야 지금 뭐 해? 한 줄만 같이 쓰자",
    avatar_color: "#C4935A",
    avatar_icon: "🤝",
  },
  {
    name: "엄격한 코치",
    perspective: "2nd",
    tone_mode: "Sharp",
    voice_style: "2인칭 지시형, 간결하고 명확하게",
    greeting: "10분 줄게. 한 줄만 쓰고 와.",
    avatar_color: "#9A6430",
    avatar_icon: "🎯",
  },
  {
    name: "뼈때리는 친구",
    perspective: "2nd",
    tone_mode: "Savage",
    voice_style: "친구 2인칭, 직설적, 사정 봐주지 않음 (정체성 비난 X)",
    greeting: "야 진짜로. 안 하면 어떡할 건데?",
    avatar_color: "#7A2424",
    avatar_icon: "🗯️",
  },
  {
    name: "기록자",
    perspective: "3rd",
    tone_mode: "Quiet",
    voice_style: "3인칭 관찰자 화법, 사실만 서술",
    greeting: "23시 47분, 슬라이드 0장. 기록만 남긴다.",
    avatar_color: "#6B7280",
    avatar_icon: "📓",
  },
];
