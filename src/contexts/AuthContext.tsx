import { createContext, useContext, useState, useCallback, type ReactNode } from "react";

export type AppRole = "admin" | "operator";

interface AuthUser {
  id: string;
  name: string;
  role: AppRole;
}

interface AuthContextValue {
  user: AuthUser | null;
  login: (role: AppRole) => void;
  logout: () => void;
  isAdmin: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const MOCK_USERS: Record<AppRole, AuthUser> = {
  admin: { id: "u1", name: "Admin User", role: "admin" },
  operator: { id: "u2", name: "Front Desk", role: "operator" },
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);

  const login = useCallback((role: AppRole) => {
    setUser(MOCK_USERS[role]);
  }, []);

  const logout = useCallback(() => {
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
