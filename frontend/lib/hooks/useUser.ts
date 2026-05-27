"use client";

import { useEffect, useState } from "react";
import { clearToken, getToken, setToken } from "../auth";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8001";

interface User {
  user_id: string;
  device_token: string;  // P0-8
}

interface UseUserResult {
  userId: string | null;
  loading: boolean;
  error: string | null;
}

async function createUser(): Promise<User> {
  const response = await fetch(`${API_BASE}/api/users`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),  // CreateUserRequest는 빈 객체 — body 명시 필수
  });

  if (!response.ok) {
    throw new Error(`사용자 생성 실패: ${response.status}`);
  }

  return (await response.json()) as User;
}

export function useUser(): UseUserResult {
  const [userId, setUserId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const stored = localStorage.getItem("user_id");
    const storedToken = getToken();

    // P0-8 마이그레이션: token 없는 옛 user_id는 폐기하고 새로 발급
    if (stored && storedToken) {
      setUserId(stored);
      setLoading(false);
      return;
    }

    if (stored && !storedToken) {
      localStorage.removeItem("user_id");
      clearToken();
    }

    createUser()
      .then(({ user_id, device_token }) => {
        localStorage.setItem("user_id", user_id);
        setToken(device_token);
        setUserId(user_id);
      })
      .catch(() => {
        const fallbackId = `local_${Date.now()}`;
        localStorage.setItem("user_id", fallbackId);
        setUserId(fallbackId);
        setError("백엔드에 연결할 수 없어 임시 ID를 사용합니다.");
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  return { userId, loading, error };
}
