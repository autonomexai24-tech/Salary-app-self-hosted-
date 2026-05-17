import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AUTH_TOKEN_KEY } from "@/lib/apiClient";
import { AuthProvider, useAuth } from "./AuthContext";

const AUTH_USER_KEY = "payroll_auth_user";

function AuthProbe() {
  const { user, isLoading } = useAuth();
  return (
    <div>
      <span data-testid="loading">{String(isLoading)}</span>
      <span data-testid="user">{user?.id ?? "none"}</span>
    </div>
  );
}

describe("AuthProvider session boot", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("clears legacy offline sessions instead of treating them as authenticated", async () => {
    window.localStorage.setItem(AUTH_TOKEN_KEY, "stale-token");
    window.localStorage.setItem(
      AUTH_USER_KEY,
      JSON.stringify({ id: "offline-admin", name: "Admin", role: "admin" })
    );

    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>
    );

    await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"));
    expect(screen.getByTestId("user")).toHaveTextContent("none");
    expect(window.localStorage.getItem(AUTH_TOKEN_KEY)).toBeNull();
    expect(window.localStorage.getItem(AUTH_USER_KEY)).toBeNull();
  });

  it("validates a stored token before exposing an authenticated user", async () => {
    window.localStorage.setItem(AUTH_TOKEN_KEY, "valid-token");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            id: "user-1",
            email: "admin@example.com",
            full_name: "Admin User",
            role: "admin",
            is_active: true,
            created_at: "2026-05-17T00:00:00Z",
            updated_at: "2026-05-17T00:00:00Z",
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }
        )
      )
    );

    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>
    );

    expect(screen.getByTestId("loading")).toHaveTextContent("true");
    expect(screen.getByTestId("user")).toHaveTextContent("none");

    await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"));
    expect(screen.getByTestId("user")).toHaveTextContent("user-1");
  });
});
