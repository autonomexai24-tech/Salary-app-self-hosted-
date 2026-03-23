import { COMPANY_FIXED_SHIFT, GRACE_PERIOD_MINUTES, OT_MULTIPLIER, PENALTY_PER_MINUTE } from "./payroll-config";

function timeToMinutes(time: string): number {
  const [h, m] = time.split(":").map(Number);
  return h * 60 + m;
}

export interface ShiftDetails {
  hoursWorked: number;
  otHours: number;
  isLate: boolean;
  lateMinutes: number;
  penaltyAmount: number;
}

export function calculateShiftDetails(timeIn: string, timeOut: string): ShiftDetails {
  if (!timeIn || !timeOut) {
    return { hoursWorked: 0, otHours: 0, isLate: false, lateMinutes: 0, penaltyAmount: 0 };
  }

  const inMin = timeToMinutes(timeIn);
  const outMin = timeToMinutes(timeOut);
  const shiftStartMin = timeToMinutes(COMPANY_FIXED_SHIFT.start);
  const shiftEndMin = timeToMinutes(COMPANY_FIXED_SHIFT.end);

  const totalMinutesWorked = Math.max(0, outMin - inMin);
  const hoursWorked = Math.round((totalMinutesWorked / 60) * 10) / 10;

  // Late calculation
  const lateMinutes = Math.max(0, inMin - shiftStartMin - GRACE_PERIOD_MINUTES);
  const isLate = inMin > shiftStartMin + GRACE_PERIOD_MINUTES;
  const penaltyAmount = lateMinutes * PENALTY_PER_MINUTE;

  // OT calculation (time worked beyond shift end)
  const otMinutes = Math.max(0, outMin - shiftEndMin);
  const otHours = Math.round((otMinutes / 60) * 10) / 10;

  return { hoursWorked, otHours, isLate, lateMinutes, penaltyAmount };
}

export function calculateNetEarned(
  dailyRate: number,
  otHours: number,
  penaltyAmount: number,
  advance: number
): number {
  const hourlyRate = dailyRate / COMPANY_FIXED_SHIFT.totalHours;
  const otPay = otHours * hourlyRate * OT_MULTIPLIER;
  return Math.round(dailyRate + otPay - penaltyAmount - advance);
}

export function getStatusFromEntry(timeIn: string, timeOut: string): "present" | "late" | "pending" {
  if (!timeIn) return "pending";
  const shiftStartMin = timeToMinutes(COMPANY_FIXED_SHIFT.start);
  const inMin = timeToMinutes(timeIn);
  if (inMin > shiftStartMin + GRACE_PERIOD_MINUTES) return "late";
  return "present";
}
