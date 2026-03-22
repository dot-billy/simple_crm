"use client";

import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from "react";
import { apiFetch } from "./api";

interface User {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
}

interface AuthContextType {
  user: User | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  loading: boolean;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const logout = useCallback(async () => {
    try {
      await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/auth/logout`,
        { method: "POST", credentials: "include" }
      );
    } catch {
      // ignore
    }
    setUser(null);
  }, []);

  useEffect(() => {
    apiFetch<User>("/api/auth/me")
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  const login = async (email: string, password: string) => {
    const params = new URLSearchParams();
    params.append("username", email);
    params.append("password", password);

    const data = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/auth/login`,
      {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: params,
      }
    );
    if (!data.ok) {
      const body = await data.json().catch(() => ({}));
      throw new Error(body.detail || "Login failed");
    }
    const result = await data.json();
    setUser(result.user);
  };

  return (
    <AuthContext.Provider value={{ user, login, logout, loading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be inside AuthProvider");
  return ctx;
}
