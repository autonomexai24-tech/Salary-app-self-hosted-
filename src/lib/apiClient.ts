const configuredBaseUrl = (
  import.meta.env.VITE_API_URL ??
  import.meta.env.VITE_API_BASE_URL ??
  ""
).trim();

export const API_BASE_URL = configuredBaseUrl.replace(/\/+$/, "");
export const AUTH_TOKEN_KEY = "payroll_auth_token";

const DEFAULT_TIMEOUT_MS = 12_000;

export type ApiRequestOptions = RequestInit & {
  authToken?: string | null;
  timeoutMs?: number;
};

export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status = 0, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

function normalizePath(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  if (API_BASE_URL.endsWith("/api") && normalizedPath.startsWith("/api/")) {
    return normalizedPath.slice(4);
  }
  return normalizedPath;
}

function buildUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  return `${API_BASE_URL}${normalizePath(path)}`;
}

function apiMessageFromDetail(detail: unknown, fallback: string): { message: string; code?: string } {
  if (typeof detail === "string") return { message: detail };
  if (detail && typeof detail === "object") {
    const candidate = detail as { message?: unknown; code?: unknown; detail?: unknown };
    if (typeof candidate.message === "string") {
      return {
        message: candidate.message,
        code: typeof candidate.code === "string" ? candidate.code : undefined,
      };
    }
    if (candidate.detail) return apiMessageFromDetail(candidate.detail, fallback);
  }
  return { message: fallback };
}

async function parseErrorResponse(response: Response): Promise<ApiError> {
  const fallback = `Request failed with status ${response.status}`;
  try {
    const body = await response.json();
    const { message, code } = apiMessageFromDetail(body.detail ?? body, fallback);
    return new ApiError(message, response.status, code);
  } catch {
    return new ApiError(fallback, response.status);
  }
}

export function getStoredAuthToken(): string | null {
  try {
    return window.localStorage.getItem(AUTH_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setStoredAuthToken(token: string): void {
  try {
    window.localStorage.setItem(AUTH_TOKEN_KEY, token);
  } catch {
    // Storage can be unavailable in hardened browser contexts; auth still works in memory.
  }
}

export function clearStoredAuthToken(): void {
  try {
    window.localStorage.removeItem(AUTH_TOKEN_KEY);
  } catch {
    // Ignore storage failures during logout.
  }
}

export async function apiRequest(path: string, options: ApiRequestOptions = {}): Promise<Response> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), options.timeoutMs ?? DEFAULT_TIMEOUT_MS);
  const headers = new Headers(options.headers);
  const token = options.authToken === undefined ? getStoredAuthToken() : options.authToken;
  const body = options.body;

  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (body && !(body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  try {
    const response = await fetch(buildUrl(path), {
      ...options,
      headers,
      signal: controller.signal,
    });

    if (!response.ok) throw await parseErrorResponse(response);
    return response;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("The backend took too long to respond. Please try again.", 0, "request_timeout");
    }
    throw new ApiError(
      "Could not reach the backend. Check that the API is running and that CORS allows this frontend.",
      0,
      "network_error"
    );
  } finally {
    window.clearTimeout(timeout);
  }
}

export async function jsonRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const response = await apiRequest(path, options);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function fileRequest(path: string, fallbackFilename: string): Promise<{ blob: Blob; filename: string }> {
  const response = await apiRequest(path);
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const filenameMatch = disposition.match(/filename="?([^"]+)"?/i);
  return {
    blob: await response.blob(),
    filename: filenameMatch?.[1] ?? fallbackFilename,
  };
}
