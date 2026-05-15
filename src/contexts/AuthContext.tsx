import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from "react";
import {
  clearStoredAuthToken,
  getCurrentUser,
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
  loginAsPrototype: (role: AppRole) => void;
  logout: () => void;
  isAdmin: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);
const AUTH_USER_KEY = "payroll_auth_user";

const MOCK_USERS: Record<AppRole, AuthUser> = {
  admin: { id: "u1", name: "Admin User", role: "admin" },
  operator: { id: "u2", name: "Front Desk", role: "operator" },
};

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
    const apiUser = await loginWithPassword(email, password);
    setUser(apiUser);
    storeUser(apiUser);
  }, []);

  const loginAsPrototype = useCallback((role: AppRole) => {
    const prototypeUser = MOCK_USERS[role];
    clearStoredAuthToken();
    setUser(prototypeUser);
    storeUser(prototypeUser);
  }, []);

  const logout = useCallback(() => {
    clearStoredAuthToken();
    clearStoredUser();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, login, loginAsPrototype, logout, isAdmin: user?.role === "admin" }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
