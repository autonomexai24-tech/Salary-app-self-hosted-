import { useState, useMemo, useCallback } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { CalendarDays, ChevronDown, Clock, Users, UserCheck, UserX, BarChart3, Save, Download, X } from "lucide-react";
import { toast } from "sonner";
import { MOCK_EMPLOYEES, SEED_ATTENDANCE, type AttendanceEntry } from "@/lib/mock-employees";
import { calculateShiftDetails, getStatusFromEntry } from "@/lib/payroll-utils";
import { COMPANY_FIXED_SHIFT } from "@/lib/payroll-config";
import { cn } from "@/lib/utils";
type FilterStatus = "all" | "present" | "late" | "pending";

export default function DailyLog() {
  const [attendance, setAttendance] = useState<Record<string, AttendanceEntry>>(() => {
    const map: Record<string, AttendanceEntry> = {};
    MOCK_EMPLOYEES.forEach((emp) => {
      const seed = SEED_ATTENDANCE.find((s) => s.employeeId === emp.id);
      map[emp.id] = seed ?? { employeeId: emp.id, timeIn: "", timeOut: "", advance: 0 };
    });
    return map;
  });

  const [openCards, setOpenCards] = useState<Record<string, boolean>>({});
  const [filter, setFilter] = useState<FilterStatus>("all");
  const [reportOpen, setReportOpen] = useState(false);
  const [reportMonth, setReportMonth] = useState("march-2026");

  const updateAttendance = (empId: string, field: keyof AttendanceEntry, value: string | number) => {
    setAttendance((prev) => ({
      ...prev,
      [empId]: { ...prev[empId], [field]: value },
    }));
  };

  const quickFill = (empId: string) => {
    setAttendance((prev) => ({
      ...prev,
      [empId]: { ...prev[empId], timeIn: COMPANY_FIXED_SHIFT.start, timeOut: COMPANY_FIXED_SHIFT.end },
    }));
  };

  // TODO [BACKEND]: Replace with fetch("/api/attendance", { method: "POST", body: JSON.stringify(payload) })
  const saveAttendance = useCallback((empId: string) => {
    const entry = attendance[empId];
    if (!entry.timeIn || !entry.timeOut) return;

    // Format as ISO strings for backend readiness
    const today = new Date().toISOString().split("T")[0];
    const _isoPayload = {
      employeeId: empId,
      date: today,
      timeIn: `${today}T${entry.timeIn}:00`,
      timeOut: `${today}T${entry.timeOut}:00`,
    };

    // Close the card and show success toast
    setOpenCards((prev) => ({ ...prev, [empId]: false }));
    const emp = MOCK_EMPLOYEES.find((e) => e.id === empId);
    toast.success("Attendance Logged Successfully", {
      description: `${emp?.name ?? "Employee"} — ${entry.timeIn} to ${entry.timeOut}`,
    });
  }, [attendance]);

  const employeeStatuses = useMemo(() => {
    const map: Record<string, "present" | "late" | "pending"> = {};
    MOCK_EMPLOYEES.forEach((emp) => {
      const entry = attendance[emp.id];
      map[emp.id] = entry ? getStatusFromEntry(entry.timeIn, entry.timeOut) : "pending";
    });
    return map;
  }, [attendance]);

  const counts = useMemo(() => {
    let present = 0, late = 0, pending = 0;
    Object.values(employeeStatuses).forEach((s) => {
      if (s === "present") present++;
      else if (s === "late") late++;
      else pending++;
    });
    return { present, late, pending, all: MOCK_EMPLOYEES.length };
  }, [employeeStatuses]);

  const filteredEmployees = useMemo(() => {
    if (filter === "all") return MOCK_EMPLOYEES;
    return MOCK_EMPLOYEES.filter((emp) => employeeStatuses[emp.id] === filter);
  }, [filter, employeeStatuses]);

  const today = new Date().toLocaleDateString("en-IN", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  const formatShiftDuration = (hours: number) => {
    const h = Math.floor(hours);
    const m = Math.round((hours - h) * 60);
    return `${h}h ${m}m`;
  };

  return (
    <div className="p-6 space-y-5 max-w-5xl mx-auto">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">Daily Attendance Log</h1>
          <p className="text-sm text-muted-foreground mt-1 flex items-center gap-1.5">
            <CalendarDays className="h-3.5 w-3.5" />
            {today}
          </p>
        </div>
        <Button variant="outline" className="h-9 text-sm gap-2" onClick={() => setReportOpen(true)}>
          <BarChart3 className="h-3.5 w-3.5" />
          View Monthly Attendance Report
        </Button>
      </div>

      {/* Stats Bar — 4 cards, pure attendance */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard label="Total Workforce" value={String(counts.all)} icon={<Users className="h-3.5 w-3.5" />} color="slate" />
        <StatCard label="Present Today" value={String(counts.present + counts.late)} icon={<UserCheck className="h-3.5 w-3.5" />} color="emerald" />
        <StatCard label="Late Arrivals" value={String(counts.late)} icon={<Clock className="h-3.5 w-3.5" />} color="amber" />
        <StatCard label="Absent / Leave" value={String(counts.pending)} icon={<UserX className="h-3.5 w-3.5" />} color="rose" />
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-2">
        <FilterPill active={filter === "all"} onClick={() => setFilter("all")} count={counts.all} label="All Employees" />
        <FilterPill active={filter === "present"} onClick={() => setFilter("present")} count={counts.present} label="Present" variant="emerald" />
        <FilterPill active={filter === "late"} onClick={() => setFilter("late")} count={counts.late} label="Late" variant="amber" />
        <FilterPill active={filter === "pending"} onClick={() => setFilter("pending")} count={counts.pending} label="Absent / Pending" variant="rose" />
      </div>

      {/* Employee Cards */}
      <div className="space-y-2">
        {filteredEmployees.map((emp) => {
          const entry = attendance[emp.id];
          const status = employeeStatuses[emp.id];
          const shift = calculateShiftDetails(entry.timeIn, entry.timeOut);
          const isOpen = openCards[emp.id] ?? false;

          return (
            <Collapsible
              key={emp.id}
              open={isOpen}
              onOpenChange={(open) => setOpenCards((prev) => ({ ...prev, [emp.id]: open }))}
            >
              <Card className="overflow-hidden transition-shadow hover:shadow-md">
                <CollapsibleTrigger asChild>
                  <button className="w-full text-left px-4 py-3 flex items-center gap-3 cursor-pointer">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-semibold">
                      {emp.avatar}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-foreground truncate">{emp.name}</p>
                      <p className="text-[11px] text-muted-foreground">{emp.designation}</p>
                    </div>
                    <Badge variant="secondary" className="hidden sm:inline-flex text-[11px] font-normal">
                      {emp.department}
                    </Badge>
                    <StatusBadge status={status} />
                    <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition-transform duration-200", isOpen && "rotate-180")} />
                  </button>
                </CollapsibleTrigger>

                <CollapsibleContent>
                  <div className="border-t px-4 py-3 space-y-3">
                    {/* Time inputs + quick fill */}
                    <div className="flex items-end gap-3">
                      <div className="flex-1 space-y-1">
                        <label className="text-[11px] text-muted-foreground font-medium">Time In</label>
                        <div className="relative">
                          <Clock className="absolute left-2.5 top-2 h-3.5 w-3.5 text-muted-foreground" />
                          <Input
                            type="time"
                            value={entry.timeIn}
                            onChange={(e) => updateAttendance(emp.id, "timeIn", e.target.value)}
                            className="pl-8 text-sm h-8"
                          />
                        </div>
                      </div>
                      <div className="flex-1 space-y-1">
                        <label className="text-[11px] text-muted-foreground font-medium">Time Out</label>
                        <div className="relative">
                          <Clock className="absolute left-2.5 top-2 h-3.5 w-3.5 text-muted-foreground" />
                          <Input
                            type="time"
                            value={entry.timeOut}
                            onChange={(e) => updateAttendance(emp.id, "timeOut", e.target.value)}
                            className="pl-8 text-sm h-8"
                          />
                        </div>
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-8 text-[11px] px-3 shrink-0"
                        onClick={(e) => { e.stopPropagation(); quickFill(emp.id); }}
                      >
                        <Clock className="h-3 w-3 mr-1" />
                        9–6
                      </Button>
                    </div>

                    {/* Bottom bar: time summary + actions */}
                    <div className="flex items-center justify-between pt-1">
                      <div className="text-xs text-muted-foreground">
                        {entry.timeIn && entry.timeOut ? (
                          <span>
                            Total Shift Hours: <span className="font-medium text-foreground">{formatShiftDuration(shift.hoursWorked)}</span>
                            {shift.otHours > 0 && <span className="text-emerald-600 font-medium"> (+{formatShiftDuration(shift.otHours)} OT)</span>}
                          </span>
                        ) : (
                          <span className="italic">Enter times to see shift duration</span>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 text-xs px-3"
                          onClick={() => setOpenCards((prev) => ({ ...prev, [emp.id]: false }))}
                        >
                          Cancel
                        </Button>
                        <Button
                          size="sm"
                          className="h-7 text-xs px-4"
                          disabled={!entry.timeIn || !entry.timeOut}
                          onClick={() => saveAttendance(emp.id)}
                        >
                          <Save className="h-3 w-3 mr-1" />
                          Save Attendance
                        </Button>
                      </div>
                    </div>
                  </div>
                </CollapsibleContent>
              </Card>
            </Collapsible>
          );
        })}

        {filteredEmployees.length === 0 && (
          <div className="text-center py-10 text-sm text-muted-foreground">No employees match this filter.</div>
        )}
      </div>

      {/* Monthly Attendance Report Dialog */}
      <Dialog open={reportOpen} onOpenChange={setReportOpen}>
        <DialogContent className="max-w-3xl max-h-[85vh] flex flex-col p-0">
          <DialogHeader className="px-6 pt-6 pb-4 border-b space-y-1">
            <div className="flex items-center justify-between">
              <DialogTitle className="text-lg">Monthly Attendance Summary</DialogTitle>
              <Select value={reportMonth} onValueChange={setReportMonth}>
                <SelectTrigger className="w-[160px] h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="january-2026">January 2026</SelectItem>
                  <SelectItem value="february-2026">February 2026</SelectItem>
                  <SelectItem value="march-2026">March 2026</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <DialogDescription>Overview of employee presence, absences, and late arrivals.</DialogDescription>
          </DialogHeader>

          <div className="flex-1 overflow-y-auto px-6 py-4">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/40">
                  <TableHead className="min-w-[180px]">Employee</TableHead>
                  <TableHead className="text-center">Working Days</TableHead>
                  <TableHead className="text-center">Present</TableHead>
                  <TableHead className="text-center">Absent</TableHead>
                  <TableHead className="text-center">Late</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {MONTHLY_REPORT_DATA.map((row) => (
                  <TableRow key={row.name}>
                    <TableCell>
                      <div>
                        <p className="text-sm font-medium text-foreground">{row.name}</p>
                        <p className="text-[11px] text-muted-foreground">{row.department}</p>
                      </div>
                    </TableCell>
                    <TableCell className="text-center text-sm tabular-nums">{row.workingDays}</TableCell>
                    <TableCell className="text-center">
                      <Badge className={cn("tabular-nums text-xs font-medium border-0", row.present >= row.workingDays ? "bg-emerald-100 text-emerald-800 hover:bg-emerald-100" : "bg-emerald-50 text-emerald-700 hover:bg-emerald-50")}>
                        {row.present}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-center">
                      <Badge className={cn("tabular-nums text-xs font-medium border-0", row.absent > 0 ? "bg-rose-100 text-rose-800 hover:bg-rose-100" : "bg-muted text-muted-foreground hover:bg-muted")}>
                        {row.absent}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-center">
                      <Badge className={cn("tabular-nums text-xs font-medium border-0", row.late > 0 ? "bg-amber-100 text-amber-800 hover:bg-amber-100" : "bg-muted text-muted-foreground hover:bg-muted")}>
                        {row.late}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          <DialogFooter className="px-6 py-4 border-t flex items-center justify-between sm:justify-between">
            <Button variant="ghost" size="sm" className="text-xs gap-1.5">
              <Download className="h-3.5 w-3.5" />
              Export as CSV
            </Button>
            <Button size="sm" className="text-xs px-4" onClick={() => setReportOpen(false)}>
              Close Report
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

const MONTHLY_REPORT_DATA = [
  { name: "Rajesh Kumar", department: "Printing", workingDays: 26, present: 24, absent: 0, late: 2 },
  { name: "Priya Sharma", department: "Binding", workingDays: 26, present: 26, absent: 0, late: 0 },
  { name: "Amit Patel", department: "Design", workingDays: 26, present: 21, absent: 4, late: 1 },
  { name: "Sunita Devi", department: "Cutting", workingDays: 26, present: 24, absent: 2, late: 0 },
  { name: "Vikram Singh", department: "Printing", workingDays: 26, present: 26, absent: 0, late: 0 },
  { name: "Meera Joshi", department: "Admin", workingDays: 26, present: 22, absent: 3, late: 1 },
  { name: "Arjun Reddy", department: "Binding", workingDays: 26, present: 25, absent: 0, late: 1 },
  { name: "Kavita Nair", department: "Design", workingDays: 26, present: 23, absent: 2, late: 1 },
];

// ---------- Sub-components ----------

function StatCard({ label, value, icon, color }: { label: string; value: string; icon: React.ReactNode; color: "emerald" | "rose" | "amber" | "slate" }) {
  const styles = {
    emerald: "bg-emerald-50 text-emerald-600 border-emerald-100",
    rose: "bg-rose-50 text-rose-600 border-rose-100",
    amber: "bg-amber-50 text-amber-600 border-amber-100",
    slate: "bg-muted text-muted-foreground border-border",
  };
  return (
    <Card className="border">
      <CardContent className="p-3 flex items-center gap-2.5">
        <div className={cn("flex h-8 w-8 items-center justify-center rounded-lg border", styles[color])}>
          {icon}
        </div>
        <div>
          <p className="text-[11px] text-muted-foreground">{label}</p>
          <p className="text-base font-semibold tracking-tight text-foreground tabular-nums">{value}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function FilterPill({ active, onClick, count, label, variant }: {
  active: boolean; onClick: () => void; count: number; label: string; variant?: "emerald" | "amber" | "rose";
}) {
  const textColor = !variant ? "" : variant === "emerald" ? "text-emerald-700" : variant === "amber" ? "text-amber-700" : "text-rose-700";
  return (
    <button
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-colors",
        active
          ? "bg-primary text-primary-foreground shadow-sm"
          : cn("bg-muted/60 text-muted-foreground hover:bg-muted", !active && variant && textColor)
      )}
    >
      {label}
      <span className={cn(
        "tabular-nums rounded-full px-1.5 py-0.5 text-[10px] font-semibold",
        active ? "bg-primary-foreground/20 text-primary-foreground" : "bg-background text-foreground"
      )}>
        {count}
      </span>
    </button>
  );
}

function StatusBadge({ status }: { status: "present" | "late" | "pending" }) {
  if (status === "present") {
    return <Badge className="bg-emerald-100 text-emerald-800 hover:bg-emerald-100 border-0 text-[11px] font-medium">Present</Badge>;
  }
  if (status === "late") {
    return <Badge className="bg-amber-100 text-amber-800 hover:bg-amber-100 border-0 text-[11px] font-medium">Late</Badge>;
  }
  return <Badge className="bg-rose-100 text-rose-800 hover:bg-rose-100 border-0 text-[11px] font-medium">Absent</Badge>;
}
