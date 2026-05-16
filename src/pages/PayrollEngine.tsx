import { useEffect, useState, useMemo } from "react";
import { format } from "date-fns";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Calendar } from "@/components/ui/calendar";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  CalendarIcon,
  CheckCircle2,
  IndianRupee,
  TrendingDown,
  TrendingUp,
  Minus,
  Plus,
  Equal,
  FileCheck,
  AlertTriangle,
  Timer,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  apiErrorMessage,
  initialsFromName,
  listEmployees,
  monthYearFromDate,
  readMonthlyPayrollSummary,
  readPayrollLedger,
  readPayrollPreview,
  lockPayrollLedger,
  type BackendMonthlyPayrollSummary,
  type BackendEmployee,
  type BackendPayrollLine,
} from "@/lib/api";
import { toast } from "sonner";

interface PayrollRow {
  employeeId: string;
  name: string;
  avatar: string;
  role: string;
  department: string;
  baseSalary: number;
  standardHours: number;
  hoursLogged: number;
  hourlyRate: number;
  paidLeaves: number;
  advancesTaken: number;
  backendGrossPay?: number;
  backendTotalPenalties?: number;
  backendNetPay?: number;
  backendOvertimeHours?: number;
}

/**
 * Pure function: Net Payable calculation
 * Formula: (Base Salary) + (OT Hours × OT Rate) - (Shortfall Hours × Shortfall Rate) - (Advances) + (Bonuses) - (Fines)
 */
function getCalcs(row: PayrollRow, bonus = 0, fines = 0) {
  const otHours = row.backendOvertimeHours ?? Math.max(0, row.hoursLogged - row.standardHours);
  const shortHours = Math.max(0, row.standardHours - row.hoursLogged - row.paidLeaves * 8);
  const otPay = Math.round(otHours * row.hourlyRate);
  const shortDeduction = row.backendTotalPenalties ?? Math.round(shortHours * row.hourlyRate);
  const grossEarned = row.backendGrossPay ?? row.baseSalary + otPay;
  const totalDeductions = shortDeduction + row.advancesTaken + fines;
  const netPayable = (row.backendNetPay ?? grossEarned - shortDeduction - row.advancesTaken) + bonus - fines;
  return { otHours, shortHours, otPay, shortDeduction, grossEarned, totalDeductions, netPayable };
}

function numberFromApi(value: string | number | null | undefined): number {
  const parsed = typeof value === "number" ? value : Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function mapPayrollLineToRow(line: BackendPayrollLine, employees: BackendEmployee[]): PayrollRow {
  const employee = employees.find((record) => record.id === line.employee_id);
  const regularHours = numberFromApi(line.regular_hours);
  const overtimeHours = numberFromApi(line.overtime_hours);
  const monthlyBasic = numberFromApi(employee?.monthly_basic);
  const hourlyRate = numberFromApi(employee?.hourly_rate) || (monthlyBasic > 0 ? monthlyBasic / 208 : 0);

  return {
    employeeId: line.employee_id,
    name: line.employee_name,
    avatar: initialsFromName(line.employee_name),
    role: line.designation,
    department: line.department,
    baseSalary: monthlyBasic || numberFromApi(line.gross_pay),
    standardHours: 208,
    hoursLogged: Math.round((regularHours + overtimeHours) * 100) / 100,
    hourlyRate,
    paidLeaves: 0,
    advancesTaken: numberFromApi(line.total_advances),
    backendGrossPay: numberFromApi(line.gross_pay),
    backendTotalPenalties: numberFromApi(line.total_penalties),
    backendNetPay: numberFromApi(line.net_pay),
    backendOvertimeHours: overtimeHours,
  };
}

// ---------- Component ----------
export default function PayrollEngine() {
  const [selectedMonth, setSelectedMonth] = useState<Date>(new Date(2026, 2, 1));
  const [calendarOpen, setCalendarOpen] = useState(false);
  const [reviewRow, setReviewRow] = useState<PayrollRow | null>(null);
  const [bonus, setBonus] = useState("");
  const [fines, setFines] = useState("");
  const [employeeRecords, setEmployeeRecords] = useState<BackendEmployee[]>([]);
  const [payrollRows, setPayrollRows] = useState<PayrollRow[]>([]);
  const [monthlyPayrollSummary, setMonthlyPayrollSummary] = useState<BackendMonthlyPayrollSummary | null>(null);
  const [isSavingPayroll, setIsSavingPayroll] = useState(false);
  const selectedMonthYear = useMemo(() => monthYearFromDate(selectedMonth), [selectedMonth]);

  useEffect(() => {
    let cancelled = false;

    async function loadPayroll() {
      try {
        const employees = await listEmployees();
        if (cancelled) return;
        setEmployeeRecords(employees);

        readMonthlyPayrollSummary(selectedMonthYear)
          .then((summary) => {
            if (!cancelled) setMonthlyPayrollSummary(summary);
          })
          .catch(() => {
            if (!cancelled) setMonthlyPayrollSummary(null);
          });

        const preview = await readPayrollPreview(selectedMonth);
        if (cancelled) return;
        if (preview.line_items.length > 0) {
          setPayrollRows(preview.line_items.map((line) => mapPayrollLineToRow(line, employees)));
          return;
        }

        try {
          const ledger = await readPayrollLedger(selectedMonthYear);
          if (cancelled) return;
          setPayrollRows(ledger.items.map((line) => mapPayrollLineToRow(line, employees)));
        } catch {
          if (!cancelled) setPayrollRows([]);
        }
      } catch (error) {
        if (cancelled) return;
        toast.error("Could not load payroll data", {
          description: apiErrorMessage(error),
        });
      }
    }

    loadPayroll();

    return () => {
      cancelled = true;
    };
  }, [selectedMonth, selectedMonthYear]);

  const openReview = (row: PayrollRow) => {
    setReviewRow(row);
    setBonus("");
    setFines("");
  };

  const pulse = useMemo(() => {
    if (monthlyPayrollSummary) {
      const totalDeductions = numberFromApi(monthlyPayrollSummary.total_deductions)
        || numberFromApi(monthlyPayrollSummary.total_advances) + numberFromApi(monthlyPayrollSummary.total_penalties);
      return {
        totalBase: numberFromApi(monthlyPayrollSummary.total_base ?? monthlyPayrollSummary.total_gross),
        totalOT: numberFromApi(monthlyPayrollSummary.total_overtime),
        totalDeductions,
        totalNet: numberFromApi(monthlyPayrollSummary.total_net),
      };
    }

    let totalBase = 0, totalOT = 0, totalDeductions = 0, totalNet = 0;
    for (const r of payrollRows) {
      const c = getCalcs(r);
      totalBase += r.baseSalary;
      totalOT += c.otPay;
      totalDeductions += c.shortDeduction + r.advancesTaken;
      totalNet += c.netPayable;
    }
    return { totalBase, totalOT, totalDeductions, totalNet };
  }, [monthlyPayrollSummary, payrollRows]);

  const approvePayroll = async () => {
    setIsSavingPayroll(true);
    try {
      const ledger = await lockPayrollLedger(selectedMonthYear);
      const [employees, summary] = await Promise.all([
        employeeRecords.length ? Promise.resolve(employeeRecords) : listEmployees(),
        readMonthlyPayrollSummary(selectedMonthYear),
      ]);
      setEmployeeRecords(employees);
      setPayrollRows(ledger.items.map((line) => mapPayrollLineToRow(line, employees)));
      setMonthlyPayrollSummary(summary);
      toast.success("Payroll ledger locked", {
        description: `${format(selectedMonth, "MMMM yyyy")} payslips are ready.`,
      });
    } catch (error) {
      toast.error("Could not approve payroll", {
        description: apiErrorMessage(error),
      });
    } finally {
      setIsSavingPayroll(false);
    }
  };

  const inr = (n: number) => n.toLocaleString("en-IN");

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">Payroll Engine</h1>
          <p className="text-sm text-muted-foreground mt-1">Hourly-driven Master Ledger — auto-calculated from total hours logged.</p>
        </div>
        <div className="flex items-center gap-3">
          <Popover open={calendarOpen} onOpenChange={setCalendarOpen}>
            <PopoverTrigger asChild>
              <Button variant="outline" className="h-9 text-sm gap-2 min-w-[160px] justify-start">
                <CalendarIcon className="h-3.5 w-3.5" />
                {format(selectedMonth, "MMMM yyyy")}
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0" align="end">
              <Calendar
                mode="single"
                selected={selectedMonth}
                onSelect={(d) => { if (d) { setSelectedMonth(d); setCalendarOpen(false); } }}
                className={cn("p-3 pointer-events-auto")}
                initialFocus
              />
            </PopoverContent>
          </Popover>
          <Button className="bg-emerald-600 hover:bg-emerald-700 text-white h-9 text-sm gap-2" onClick={approvePayroll} disabled={isSavingPayroll}>
            <FileCheck className="h-3.5 w-3.5" />
            Approve & Generate Payslips
          </Button>
        </div>
      </div>

      {/* Pulse Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <PulseCard icon={<IndianRupee className="h-4 w-4" />} label="Total Base Payroll" value={`₹${inr(pulse.totalBase)}`} color="primary" />
        <PulseCard icon={<TrendingUp className="h-4 w-4" />} label="Overtime Earnings" value={`+₹${inr(pulse.totalOT)}`} color="success" />
        <PulseCard icon={<TrendingDown className="h-4 w-4" />} label="Total Deductions" value={`-₹${inr(pulse.totalDeductions)}`} color="destructive" />
        <PulseCard icon={<CheckCircle2 className="h-4 w-4" />} label="Final Net Payable" value={`₹${inr(pulse.totalNet)}`} color="success" />
      </div>

      {/* Ledger Table */}
      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40">
                <TableHead className="min-w-[180px]">Employee</TableHead>
                <TableHead className="text-right">Base Salary</TableHead>
                <TableHead className="text-right">Hours Logged</TableHead>
                <TableHead className="text-right">Gross Earned</TableHead>
                <TableHead className="text-right">Total Deductions</TableHead>
                <TableHead className="text-right font-semibold">Net Payable</TableHead>
                <TableHead className="text-center w-[100px]">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {payrollRows.map((row) => {
                const c = getCalcs(row);
                const hoursOver = row.hoursLogged >= row.standardHours;
                return (
                  <TableRow key={row.employeeId} className="group hover:bg-muted/30 transition-colors">
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-semibold">
                          {row.avatar}
                        </div>
                        <div>
                          <p className="text-sm font-medium text-foreground">{row.name}</p>
                          <p className="text-xs text-muted-foreground">{row.role}</p>
                        </div>
                      </div>
                    </TableCell>

                    <TableCell className="text-right text-sm tabular-nums">₹{inr(row.baseSalary)}</TableCell>

                    <TableCell className="text-right">
                      <div className="flex flex-col items-end gap-0.5">
                        <span className={cn("text-sm font-medium tabular-nums", hoursOver ? "text-emerald-600" : "text-destructive")}>
                          {row.hoursLogged}h / {row.standardHours}h
                        </span>
                        {c.otHours > 0 && (
                          <span className="text-xs text-emerald-600 tabular-nums">+{c.otHours}h OT</span>
                        )}
                        {c.shortHours > 0 && (
                          <span className="text-xs text-destructive tabular-nums">-{c.shortHours}h short</span>
                        )}
                      </div>
                    </TableCell>

                    <TableCell className="text-right">
                      <div className="flex flex-col items-end gap-0.5">
                        <span className="text-sm tabular-nums">₹{inr(c.grossEarned)}</span>
                        {c.otPay > 0 && (
                          <span className="text-xs text-emerald-600 tabular-nums">+₹{inr(c.otPay)} OT</span>
                        )}
                      </div>
                    </TableCell>

                    <TableCell className="text-right">
                      {c.totalDeductions > 0 ? (
                        <span className="text-sm text-destructive tabular-nums font-medium">-₹{inr(c.totalDeductions)}</span>
                      ) : (
                        <span className="text-sm text-muted-foreground">₹0</span>
                      )}
                    </TableCell>

                    <TableCell className="text-right">
                      <span className="text-sm font-bold text-emerald-600 tabular-nums">₹{inr(c.netPayable)}</span>
                    </TableCell>

                    <TableCell className="text-center">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-8 text-xs text-primary hover:text-primary hover:bg-primary/10"
                        onClick={() => openReview(row)}
                      >
                        Review
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </Card>

      {/* Review Sheet */}
      <Sheet open={!!reviewRow} onOpenChange={(open) => { if (!open) setReviewRow(null); }}>
        <SheetContent className="sm:max-w-lg overflow-y-auto">
          {reviewRow && <ReviewPanel row={reviewRow} month={selectedMonth} bonus={bonus} fines={fines} setBonus={setBonus} setFines={setFines} />}
        </SheetContent>
      </Sheet>
    </div>
  );
}

// ---------- Review Panel ----------
function ReviewPanel({ row, month, bonus, fines, setBonus, setFines }: {
  row: PayrollRow; month: Date; bonus: string; fines: string; setBonus: (v: string) => void; setFines: (v: string) => void;
}) {
  const bonusVal = Number(bonus) || 0;
  const finesVal = Number(fines) || 0;
  const c = getCalcs(row, bonusVal, finesVal);
  const inr = (n: number) => n.toLocaleString("en-IN");

  return (
    <>
      <SheetHeader>
        <SheetTitle className="text-lg">Review Payroll — {row.name}</SheetTitle>
        <SheetDescription>{format(month, "MMMM yyyy")} · {row.role}, {row.department}</SheetDescription>
      </SheetHeader>

      <div className="mt-6 space-y-5">
        {/* Section A: Time Audit */}
        <div className="rounded-xl bg-muted/60 border p-4 space-y-3">
          <div className="flex items-center gap-2 mb-1">
            <Timer className="h-4 w-4 text-muted-foreground" />
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Time Audit</p>
          </div>
          <AuditLine label="Expected Monthly Hours" value={`${row.standardHours}h`} sub={`26 Days × 8h`} />
          <AuditLine label="Actual Hours Logged" value={`${row.hoursLogged}h`} highlight={row.hoursLogged >= row.standardHours ? "success" : "destructive"} />
          {c.otHours > 0 && <AuditLine label="Auto-Calculated OT" value={`+${c.otHours}h`} highlight="success" />}
          {c.shortHours > 0 && <AuditLine label="Hours Short" value={`-${c.shortHours}h`} highlight="destructive" />}
          <AuditLine label="Paid Leaves Applied" value={`${row.paidLeaves}`} />
        </div>

        {/* Section B: Financial Breakdown */}
        <div className="space-y-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Financial Breakdown</p>

          {/* Earnings */}
          <div className="space-y-2">
            <p className="text-xs font-medium text-emerald-600 uppercase tracking-wide">Earnings</p>
            <BreakdownLine label={`Base Salary (for ${row.standardHours}h)`} value={`₹${inr(row.baseSalary)}`} tooltip={`Monthly base for ${row.standardHours} standard hours at ₹${inr(row.hourlyRate)}/hr`} />
            {c.otPay > 0 && (
              <BreakdownLine label={`Overtime Pay (${c.otHours}h × ₹${inr(row.hourlyRate)}/h)`} value={`+₹${inr(c.otPay)}`} variant="success" tooltip={`${c.otHours}h OT calculated at ₹${inr(row.hourlyRate)}/hr`} />
            )}
            {bonusVal > 0 && (
              <BreakdownLine label="Bonus" value={`+₹${inr(bonusVal)}`} variant="success" tooltip="Manually added bonus" />
            )}
          </div>

          <Separator />

          {/* Deductions */}
          <div className="space-y-2">
            <p className="text-xs font-medium text-destructive uppercase tracking-wide">Deductions</p>
            <BreakdownLine
              label={`Short Hours / Late Penalties (${c.shortHours}h)`}
              value={c.shortDeduction > 0 ? `-₹${inr(c.shortDeduction)}` : "₹0"}
              variant={c.shortDeduction > 0 ? "destructive" : undefined}
              tooltip={c.shortDeduction > 0 ? `${c.shortHours}h short at ₹${inr(row.hourlyRate)}/hr = ₹${inr(c.shortDeduction)} deducted` : "No shortfall this period"}
            />
            <BreakdownLine
              label="Advance Recovery"
              value={row.advancesTaken > 0 ? `-₹${inr(row.advancesTaken)}` : "₹0"}
              variant={row.advancesTaken > 0 ? "warning" : undefined}
              tooltip={row.advancesTaken > 0 ? `Advance of ₹${inr(row.advancesTaken)} issued this month` : "No advances taken"}
            />
            {finesVal > 0 && (
              <BreakdownLine label="Other Fines" value={`-₹${inr(finesVal)}`} variant="destructive" tooltip="Manually added fine" />
            )}
          </div>

          <Separator />

          {/* Net result */}
          <div className="flex items-center justify-between py-2">
            <span className="text-sm font-semibold text-foreground">Net Payable</span>
            <span className="text-xl font-bold text-emerald-600 tabular-nums">₹{inr(c.netPayable)}</span>
          </div>
        </div>

        {/* Section C: Formula & Overrides */}
        <div className="rounded-xl border-2 border-primary/20 bg-primary/5 p-4">
          <p className="text-xs font-medium text-muted-foreground mb-3">Calculation Formula</p>
          <div className="flex items-center gap-1.5 flex-wrap text-sm">
            <Badge variant="secondary" className="tabular-nums text-xs">Base: ₹{inr(row.baseSalary)}</Badge>
            {c.otPay > 0 && (
              <>
                <Plus className="h-3 w-3 text-muted-foreground" />
                <Badge className="bg-emerald-100 text-emerald-800 hover:bg-emerald-100 tabular-nums text-xs">OT: ₹{inr(c.otPay)}</Badge>
              </>
            )}
            {bonusVal > 0 && (
              <>
                <Plus className="h-3 w-3 text-muted-foreground" />
                <Badge className="bg-emerald-100 text-emerald-800 hover:bg-emerald-100 tabular-nums text-xs">Bonus: ₹{inr(bonusVal)}</Badge>
              </>
            )}
            <Minus className="h-3 w-3 text-muted-foreground" />
            <Badge variant="destructive" className="tabular-nums text-xs">Ded: ₹{inr(c.totalDeductions)}</Badge>
            <Equal className="h-3 w-3 text-muted-foreground" />
            <Badge className="bg-emerald-600 text-white hover:bg-emerald-600 tabular-nums text-xs">₹{inr(c.netPayable)}</Badge>
          </div>
        </div>

        <Separator />

        {/* Manual Overrides */}
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-500" />
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Manual Overrides</p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Add Bonus (₹)</Label>
              <div className="relative">
                <span className="absolute left-2.5 top-2 text-sm text-muted-foreground font-medium">₹</span>
                <Input type="number" placeholder="0" value={bonus} onChange={(e) => setBonus(e.target.value)} className="pl-7 h-9 text-sm" min={0} />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Other Fines (₹)</Label>
              <div className="relative">
                <span className="absolute left-2.5 top-2 text-sm text-muted-foreground font-medium">₹</span>
                <Input type="number" placeholder="0" value={fines} onChange={(e) => setFines(e.target.value)} className="pl-7 h-9 text-sm" min={0} />
              </div>
            </div>
          </div>
        </div>

        <Button className="w-full bg-emerald-600 hover:bg-emerald-700 text-white">
          <CheckCircle2 className="h-3.5 w-3.5 mr-1.5" />
          Lock & Approve Salary
        </Button>
      </div>
    </>
  );
}

// ---------- Sub-components ----------
function PulseCard({ icon, label, value, color }: { icon: React.ReactNode; label: string; value: string; color: "primary" | "destructive" | "warning" | "success" }) {
  const styles = {
    primary: "bg-primary/10 text-primary",
    destructive: "bg-destructive/10 text-destructive",
    warning: "bg-amber-100 text-amber-700",
    success: "bg-emerald-100 text-emerald-700",
  };
  const valueStyles = {
    primary: "text-foreground",
    destructive: "text-destructive",
    warning: "text-amber-700",
    success: "text-emerald-700",
  };
  return (
    <Card>
      <CardContent className="p-4 space-y-2">
        <div className="flex items-center gap-2">
          <div className={cn("flex h-7 w-7 items-center justify-center rounded-lg", styles[color])}>{icon}</div>
          <p className="text-xs text-muted-foreground">{label}</p>
        </div>
        <p className={cn("text-xl font-bold tabular-nums", valueStyles[color])}>{value}</p>
      </CardContent>
    </Card>
  );
}

function AuditLine({ label, value, sub, highlight }: { label: string; value: string; sub?: string; highlight?: "success" | "destructive" }) {
  const color = highlight === "success" ? "text-emerald-600 font-medium" : highlight === "destructive" ? "text-destructive font-medium" : "text-foreground";
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-muted-foreground">{label}</span>
      <div className="flex items-center gap-2">
        {sub && <span className="text-xs text-muted-foreground">({sub})</span>}
        <span className={cn("text-sm tabular-nums", color)}>{value}</span>
      </div>
    </div>
  );
}

function BreakdownLine({ label, value, variant, tooltip }: { label: string; value: string; variant?: "destructive" | "warning" | "success"; tooltip?: string }) {
  const valueColor = variant === "destructive" ? "text-destructive" : variant === "warning" ? "text-amber-600" : variant === "success" ? "text-emerald-600" : "text-foreground";
  const content = (
    <div className="flex items-center justify-between">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className={cn("text-sm font-medium tabular-nums", valueColor)}>{value}</span>
    </div>
  );
  if (!tooltip) return content;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div className="cursor-help">{content}</div>
      </TooltipTrigger>
      <TooltipContent side="left" className="text-xs max-w-[240px]">
        {tooltip}
      </TooltipContent>
    </Tooltip>
  );
}
