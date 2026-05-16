import { describe, expect, it } from "vitest";

import { emptyAttendanceEntry, mapAttendanceEntryToUi, type BackendAttendanceEntry } from "./api";

const baseBackendEntry: BackendAttendanceEntry = {
  id: "attendance-1",
  employee_id: "employee-1",
  date: "2026-05-16",
  time_in: "09:11:00",
  time_out: "17:11:00",
  status: "late",
  hours_logged: "8.00",
  regular_hours: "8.00",
  overtime_hours: "0.00",
  late_minutes: 1,
  penalty_amount: "1.67",
  advance_amount: "0.00",
  gross_earned: "800.00",
  net_earned: "798.33",
  notes: null,
  created_at: "2026-05-16T03:41:00Z",
  updated_at: "2026-05-16T03:41:00Z",
};

describe("attendance API mapping", () => {
  it("maps backend-controlled attendance calculations into DailyLog state", () => {
    expect(mapAttendanceEntryToUi(baseBackendEntry)).toMatchObject({
      employeeId: "employee-1",
      timeIn: "09:11",
      timeOut: "17:11",
      status: "late",
      hoursLogged: 8,
      overtimeHours: 0,
      lateMinutes: 1,
      advance: 0,
    });
  });

  it("creates empty attendance rows without local calculations", () => {
    expect(emptyAttendanceEntry("employee-2")).toEqual({
      employeeId: "employee-2",
      timeIn: "",
      timeOut: "",
      advance: 0,
      status: "pending",
      hoursLogged: 0,
      overtimeHours: 0,
      lateMinutes: 0,
    });
  });
});
