import type { AttendanceEntry, Employee } from "@/lib/mock-employees";

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
const defaultBaseUrl = import.meta.env.PROD ? "" : "http://localhost:8000";

export const API_BASE_URL = (configuredBaseUrl ?? defaultBaseUrl).replace(/\/+$/, "");

const AUTH_TOKEN_KEY = "payroll_auth_token";
const DEFAULT_TIMEOUT_MS = 12_000;

export type BackendRole = "admin" | "staff";
export type AppRoleFromApi = "admin" | "operator";

export interface ApiAuthUser {
  id: string;
  name: string;
  role: AppRoleFromApi;
}

export interface BackendUser {
  id: string;
  email: string;
  full_name: string;
  role: BackendRole;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  last_login_at?: string | null;
}

export interface BackendEmployee {
  id: string;
  employee_code: string;
  full_name: string;
  department: string;
  designation: string;
  monthly_basic: string | number;
  daily_rate: string | number;
  hourly_rate: string | number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface BackendEmployeeList {
  items: BackendEmployee[];
  limit: number;
  offset: number;
  total: number;
}

export interface BackendUserList {
  items: BackendUser[];
  limit: number;
  offset: number;
  total: number;
}

export interface BackendAttendanceEntry {
  id: string;
  employee_id: string;
  date: string;
  time_in?: string | null;
  time_out?: string | null;
  status: "pending" | "present" | "absent" | "late";
  regular_hours: string | number;
  overtime_hours: string | number;
  late_minutes: number;
  penalty_amount: string | number;
  advance_amount: string | number;
  gross_earned: string | number;
  net_earned: string | number;
  notes?: string | null;
  created_at: string;
  updated_at: string;
  employee?: BackendEmployee | null;
}

export interface BackendAttendanceList {
  date: string;
  items: BackendAttendanceEntry[];
  total: number;
}

export interface BackendCompanySettings {
  id: number;
  company_name: string;
  address?: string | null;
  phone?: string | null;
  email?: string | null;
  tax_id?: string | null;
  shift_start_time: string;
  shift_end_time: string;
  standard_work_hours: string | number;
  grace_period_minutes: number;
  overtime_multiplier: string | number;
  logo_url?: string | null;
  logo_content_type?: string | null;
  logo_updated_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface BackendPayrollLine {
  employee_id: string;
  employee_code: string;
  employee_name: string;
  department: string;
  designation: string;
  days_present: number;
  regular_hours: string | number;
  overtime_hours: string | number;
  gross_pay: string | number;
  total_advances: string | number;
  total_penalties: string | number;
  net_pay: string | number;
  id?: string;
  created_at?: string;
}

export interface BackendPayrollPreview {
  period_start: string;
  period_end: string;
  line_items: BackendPayrollLine[];
  total_gross: string | number;
  total_advances: string | number;
  total_penalties: string | number;
  total_net: string | number;
}

export interface BackendPayrollLedger {
  month_year: string;
  period_start: string;
  period_end: string;
  items: BackendPayrollLine[];
  total_gross: string | number;
  total_advances: string | number;
  total_penalties: string | number;
  total_net: string | number;
  saved_at?: string | null;
}

type RequestOptions = RequestInit & {
  authToken?: string | null;
  timeoutMs?: number;
};

interface TokenResponse {
  access_token: string;
  token_type: string;
}

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

function numberFromApi(value: string | number | null | undefined): number {
  const parsed = typeof value === "number" ? value : Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function initialsFromName(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);
}

function toTimeInputValue(value?: string | null): string {
  if (!value) return "";
  return value.slice(0, 5);
}

function buildUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE_URL}${normalizedPath}`;
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

async function request(path: string, options: RequestOptions = {}): Promise<Response> {
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

async function jsonRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await request(path, options);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function fileRequest(path: string, fallbackFilename: string): Promise<{ blob: Blob; filename: string }> {
  const response = await request(path);
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const filenameMatch = disposition.match(/filename="?([^"]+)"?/i);
  return {
    blob: await response.blob(),
    filename: filenameMatch?.[1] ?? fallbackFilename,
  };
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function mapBackendUser(user: BackendUser): ApiAuthUser {
  return {
    id: user.id,
    name: user.full_name,
    role: user.role === "admin" ? "admin" : "operator",
  };
}

export async function loginWithPassword(email: string, password: string): Promise<ApiAuthUser> {
  const token = await jsonRequest<TokenResponse>("/auth/login", {
    method: "POST",
    authToken: null,
    body: JSON.stringify({ email, password }),
  });
  setStoredAuthToken(token.access_token);

  try {
    return await getCurrentUser(token.access_token);
  } catch (error) {
    clearStoredAuthToken();
    throw error;
  }
}

export async function getCurrentUser(authToken?: string): Promise<ApiAuthUser> {
  const user = await jsonRequest<BackendUser>("/users/me", {
    authToken: authToken ?? getStoredAuthToken(),
  });
  return mapBackendUser(user);
}

export async function listUsers(): Promise<BackendUser[]> {
  const params = new URLSearchParams({ limit: "100", offset: "0" });
  const data = await jsonRequest<BackendUserList>(`/users?${params.toString()}`);
  return data.items;
}

export async function createUser(payload: {
  fullName: string;
  email: string;
  password: string;
  role: BackendRole;
}): Promise<BackendUser> {
  return jsonRequest<BackendUser>("/users", {
    method: "POST",
    body: JSON.stringify({
      full_name: payload.fullName,
      email: payload.email,
      password: payload.password,
      role: payload.role,
      is_active: true,
    }),
  });
}

export function mapEmployeeToUi(employee: BackendEmployee): Employee {
  return {
    id: employee.id,
    name: employee.full_name,
    department: employee.department,
    designation: employee.designation,
    dailyRate: numberFromApi(employee.daily_rate),
    monthlyBasic: numberFromApi(employee.monthly_basic),
    avatar: initialsFromName(employee.full_name),
  };
}

export async function listEmployees(search?: string): Promise<BackendEmployee[]> {
  const params = new URLSearchParams({ limit: "100", offset: "0" });
  if (search?.trim()) params.set("search", search.trim());
  const data = await jsonRequest<BackendEmployeeList>(`/employees?${params.toString()}`);
  return data.items;
}

export async function createEmployee(payload: {
  fullName: string;
  department: string;
  designation: string;
  monthlyBasic: number;
  employeeCode?: string;
}): Promise<BackendEmployee> {
  const employeeCode = payload.employeeCode ?? `${initialsFromName(payload.fullName) || "EMP"}${Date.now()}`;
  return jsonRequest<BackendEmployee>("/employees", {
    method: "POST",
    body: JSON.stringify({
      employee_code: employeeCode,
      full_name: payload.fullName,
      department: payload.department,
      designation: payload.designation,
      monthly_basic: payload.monthlyBasic,
      is_active: true,
    }),
  });
}

export function emptyAttendanceEntry(employeeId: string): AttendanceEntry {
  return { employeeId, timeIn: "", timeOut: "", advance: 0 };
}

export function mapAttendanceEntryToUi(entry: BackendAttendanceEntry): AttendanceEntry {
  return {
    employeeId: entry.employee_id,
    timeIn: toTimeInputValue(entry.time_in),
    timeOut: toTimeInputValue(entry.time_out),
    advance: numberFromApi(entry.advance_amount),
  };
}

export async function listAttendanceEntries(date: string): Promise<BackendAttendanceEntry[]> {
  const params = new URLSearchParams({ date });
  const data = await jsonRequest<BackendAttendanceList>(`/attendance?${params.toString()}`);
  return data.items;
}

export async function saveAttendanceEntry(entry: AttendanceEntry, date: string): Promise<BackendAttendanceEntry> {
  return jsonRequest<BackendAttendanceEntry>("/attendance", {
    method: "POST",
    body: JSON.stringify({
      employee_id: entry.employeeId,
      date,
      time_in: entry.timeIn || null,
      time_out: entry.timeOut || null,
      advance_amount: entry.advance || 0,
    }),
  });
}

export async function readCompanySettings(): Promise<BackendCompanySettings> {
  return jsonRequest<BackendCompanySettings>("/company-settings", { authToken: null });
}

export async function updateCompanySettings(payload: Partial<{
  company_name: string;
  address: string | null;
  phone: string | null;
  email: string | null;
  tax_id: string | null;
  shift_start_time: string;
  shift_end_time: string;
  standard_work_hours: number;
  grace_period_minutes: number;
  overtime_multiplier: number;
}>): Promise<BackendCompanySettings> {
  return jsonRequest<BackendCompanySettings>("/company-settings", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function uploadCompanyLogo(file: File): Promise<BackendCompanySettings> {
  const formData = new FormData();
  formData.append("file", file);
  return jsonRequest<BackendCompanySettings>("/company-settings/logo", {
    method: "POST",
    body: formData,
  });
}

export function resolveApiAssetUrl(path?: string | null): string | null {
  if (!path) return null;
  if (/^https?:\/\//i.test(path)) return path;
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

export function monthYearFromDate(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  return `${month}-${date.getFullYear()}`;
}

export function dateInputValue(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

export function monthRangeFromDate(date: Date): { periodStart: string; periodEnd: string } {
  const start = new Date(date.getFullYear(), date.getMonth(), 1);
  const end = new Date(date.getFullYear(), date.getMonth() + 1, 0);
  return {
    periodStart: dateInputValue(start),
    periodEnd: dateInputValue(end),
  };
}

export async function readPayrollPreview(month: Date): Promise<BackendPayrollPreview> {
  const { periodStart, periodEnd } = monthRangeFromDate(month);
  const params = new URLSearchParams({
    period_start: periodStart,
    period_end: periodEnd,
  });
  return jsonRequest<BackendPayrollPreview>(`/payroll/preview?${params.toString()}`);
}

export async function readPayrollLedger(monthYear: string): Promise<BackendPayrollLedger> {
  return jsonRequest<BackendPayrollLedger>(`/payroll/ledger/${monthYear}`);
}

export async function savePayrollLedger(monthYear: string): Promise<BackendPayrollLedger> {
  return jsonRequest<BackendPayrollLedger>("/payroll/ledger", {
    method: "POST",
    body: JSON.stringify({ month_year: monthYear }),
  });
}

export async function downloadPayslipPdf(monthYear: string, employeeId: string): Promise<{ blob: Blob; filename: string }> {
  return fileRequest(
    `/payroll/ledger/${monthYear}/payslips/${employeeId}/pdf`,
    `payslip-${monthYear}-${employeeId}.pdf`
  );
}

export async function downloadPayslipsZip(monthYear: string): Promise<{ blob: Blob; filename: string }> {
  return fileRequest(`/payroll/ledger/${monthYear}/payslips.zip`, `payslips-${monthYear}.zip`);
}

export function apiErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong while contacting the backend.";
}
