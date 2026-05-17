import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  apiRequest,
  AUTH_TOKEN_KEY,
  AUTH_UNAUTHORIZED_EVENT,
  getStoredAuthToken,
} from "./apiClient";

describe("apiRequest authentication", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("attaches the stored bearer token to protected requests", async () => {
    window.localStorage.setItem(AUTH_TOKEN_KEY, "stored-token");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    await apiRequest("/api/employees/");

    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Headers).get("Authorization")).toBe("Bearer stored-token");
  });

  it("clears stale tokens and emits an auth event on unauthorized responses", async () => {
    window.localStorage.setItem(AUTH_TOKEN_KEY, "stale-token");
    const listener = vi.fn();
    window.addEventListener(AUTH_UNAUTHORIZED_EVENT, listener);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: {
              code: "invalid_credentials",
              message: "Could not validate credentials",
            },
          }),
          {
            status: 401,
            headers: { "Content-Type": "application/json" },
          }
        )
      )
    );

    await expect(apiRequest("/api/employees/")).rejects.toMatchObject({
      status: 401,
      code: "invalid_credentials",
      message: "Could not validate credentials",
    });

    expect(getStoredAuthToken()).toBeNull();
    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener(AUTH_UNAUTHORIZED_EVENT, listener);
  });
});
