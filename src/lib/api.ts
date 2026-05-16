import {
  API_BASE_URL,
  ApiError,
  clearStoredAuthToken,
  fileRequest,
  getStoredAuthToken,
  jsonRequest,
  setStoredAuthToken,
} from "@/lib/apiClient";

export {
  API_BASE_URL,
  ApiError,
  clearStoredAuthToken,
  getStoredAuthToken,
  setStoredAuthToken,
};

export interface Employee {
  id: string;
  name: string;
  department: string;
  designation: string;
  dailyRate: number;
  monthlyBasic: number;
  avatar: string;
}

export interface AttendanceEntry {
  employeeId: string;
  timeIn: string;
  timeOut: string;
  advance: number;
}

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

export interface BackendDailyAttendanceSummary {
  date?: string;
  total_employees?: number;
  total_workforce?: number;
  total_entries?: number;
  present_count?: number;
  present?: number;
  late_count?: number;
  late?: number;
  absent_count?: number;
  absent?: number;
  pending_count?: number;
  pending?: number;
}

export interface BackendMonthlyAttendanceRow {
  employee_id?: string;
  employee_name?: string;
  name?: string;
  department?: string;
  working_days?: number;
  present?: number;
  present_count?: number;
  absent?: number;
  absent_count?: number;
  late?: number;
  late_count?: number;
}

export interface BackendMonthlyAttendanceSummary {
  month_year?: string;
  items?: BackendMonthlyAttendanceRow[];
  rows?: BackendMonthlyAttendanceRow[];
  employees?: BackendMonthlyAttendanceRow[];
}

export interface BackendMonthlyPayrollSummary {
  month_year?: string;
  locked_payroll_count?: number;
  total_gross?: string | number;
  total_advances?: string | number;
  total_penalties?: string | number;
  total_net?: string | number;
  total_base?: string | number;
  total_overtime?: string | number;
  total_deductions?: string | number;
}

interface TokenResponse {
  access_token: string;
  token_type: string;
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
  const token = await jsonRequest<TokenResponse>("/api/auth/login", {
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
  const user = await jsonRequest<BackendUser>("/api/users/me", {
    authToken: authToken ?? getStoredAuthToken(),
  });
  return mapBackendUser(user);
}

export async function listUsers(): Promise<BackendUser[]> {
  const params = new URLSearchParams({ limit: "100", offset: "0" });
  const data = await jsonRequest<BackendUserList>(`/api/users/?${params.toString()}`);
  return data.items;
}

export async function createUser(payload: {
  fullName: string;
  email: string;
  password: string;
  role: BackendRole;
}): Promise<BackendUser> {
  return jsonRequest<BackendUser>("/api/users/", {
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
  const data = await jsonRequest<BackendEmployeeList>(`/api/employees/?${params.toString()}`);
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
  return jsonRequest<BackendEmployee>("/api/employees/", {
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
  const data = await jsonRequest<BackendAttendanceList>(`/api/attendance/?${params.toString()}`);
  return data.items;
}

export async function saveAttendanceEntry(entry: AttendanceEntry, date: string): Promise<BackendAttendanceEntry> {
  return jsonRequest<BackendAttendanceEntry>("/api/attendance/log", {
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
  return jsonRequest<BackendCompanySettings>("/api/settings/");
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
  return jsonRequest<BackendCompanySettings>("/api/settings/", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function uploadCompanyLogo(file: File): Promise<BackendCompanySettings> {
  const formData = new FormData();
  formData.append("file", file);
  return jsonRequest<BackendCompanySettings>("/api/settings/logo", {
    method: "POST",
    body: formData,
  });
}

export function resolveApiAssetUrl(path?: string | null): string | null {
  if (!path) return null;
  if (/^https?:\/\//i.test(path)) return path;
  const assetBaseUrl = API_BASE_URL.endsWith("/api") ? API_BASE_URL.slice(0, -4) : API_BASE_URL;
  return `${assetBaseUrl}${path.startsWith("/") ? path : `/${path}`}`;
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
  const monthYear = monthYearFromDate(month);
  return jsonRequest<BackendPayrollPreview>(`/api/payroll/preview/${encodeURIComponent(monthYear)}`, {
    method: "POST",
  });
}

export async function readPayrollLedger(monthYear: string): Promise<BackendPayrollLedger> {
  return jsonRequest<BackendPayrollLedger>(`/api/payroll/ledger/${encodeURIComponent(monthYear)}`);
}

export async function lockPayrollLedger(monthYear: string): Promise<BackendPayrollLedger> {
  return jsonRequest<BackendPayrollLedger>(`/api/payroll/lock/${encodeURIComponent(monthYear)}`, {
    method: "POST",
  });
}

export async function downloadPayslipPdf(monthYear: string, employeeId: string): Promise<{ blob: Blob; filename: string }> {
  return fileRequest(
    `/api/receipts/generate/${encodeURIComponent(employeeId)}/${encodeURIComponent(monthYear)}`,
    `payslip-${monthYear}-${employeeId}.pdf`
  );
}

export async function downloadPayslipsZip(monthYear: string): Promise<{ blob: Blob; filename: string }> {
  return fileRequest(`/api/receipts/generate-all/${encodeURIComponent(monthYear)}`, `payslips-${monthYear}.zip`);
}

export async function readDailyAttendanceSummary(date: string): Promise<BackendDailyAttendanceSummary> {
  const params = new URLSearchParams({ date });
  return jsonRequest<BackendDailyAttendanceSummary>(`/api/dashboard/daily-attendance?${params.toString()}`);
}

export async function readMonthlyAttendanceSummary(monthYear: string): Promise<BackendMonthlyAttendanceSummary> {
  const params = new URLSearchParams({ month: monthYear, month_year: monthYear });
  return jsonRequest<BackendMonthlyAttendanceSummary>(`/api/dashboard/monthly-attendance?${params.toString()}`);
}

export async function readMonthlyPayrollSummary(monthYear: string): Promise<BackendMonthlyPayrollSummary> {
  const params = new URLSearchParams({ month: monthYear, month_year: monthYear });
  return jsonRequest<BackendMonthlyPayrollSummary>(`/api/dashboard/monthly-payroll?${params.toString()}`);
}

export function apiErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong while contacting the backend.";
}
