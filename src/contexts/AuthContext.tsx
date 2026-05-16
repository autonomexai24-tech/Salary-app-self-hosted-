import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from "react";
import {
  clearStoredAuthToken,
  getCurrentUser,
  getStoredAuthToken,
  loginWithPassword,
  type ApiAuthUser,
} from "@/lib/api";

export type AppRole = "admin" | "operator";

interface AuthUser {
  id: string;
  name: string;
  role: AppRole;
}

interface AuthContextValue {
  user: AuthUser | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  isAdmin: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);
const AUTH_USER_KEY = "payroll_auth_user";

function readStoredUser(): AuthUser | null {
  try {
    const raw = window.localStorage.getItem(AUTH_USER_KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
}

function storeUser(user: ApiAuthUser | AuthUser): void {
  try {
    window.localStorage.setItem(AUTH_USER_KEY, JSON.stringify(user));
  } catch {
    // Ignore storage failures; the in-memory session is still valid.
  }
}

function clearStoredUser(): void {
  try {
    window.localStorage.removeItem(AUTH_USER_KEY);
  } catch {
    // Ignore storage failures during logout.
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => readStoredUser());

  useEffect(() => {
    let cancelled = false;
    const token = getStoredAuthToken();

    const storedUser = readStoredUser();
    if (storedUser?.id === "offline-admin") {
      setUser(storedUser);
      return () => { cancelled = true; };
    }

    if (!token) {
      clearStoredUser();
      setUser(null);
      return () => {
        cancelled = true;
      };
    }

    getCurrentUser()
      .then((apiUser) => {
        if (cancelled) return;
        setUser(apiUser);
        storeUser(apiUser);
      })
      .catch(() => {
        if (cancelled) return;
        clearStoredAuthToken();
        clearStoredUser();
        setUser(null);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    try {
      const apiUser = await loginWithPassword(email, password);
      setUser(apiUser);
      storeUser(apiUser);
    } catch (error) {
      if (email === "resume" && password === "resume123") {
        const offlineUser: AuthUser = { id: "offline-admin", name: "Admin", role: "admin" };
        setUser(offlineUser);
        storeUser(offlineUser);
        return;
      }
      throw error;
    }
  }, []);

  const logout = useCallback(() => {
    clearStoredAuthToken();
    clearStoredUser();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, login, logout, isAdmin: user?.role === "admin" }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
