// P0-8: 디바이스 토큰 보관/조회/헤더 생성
// 사용자 생성 시 backend가 발급한 device_token을 localStorage에 보관하고
// 모든 사용자별 API 호출의 Authorization Bearer 헤더로 첨부한다.

const TOKEN_KEY = "device_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
}

export function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
