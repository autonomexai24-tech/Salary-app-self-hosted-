import { useState } from "react";
// TODO [BACKEND]: Replace APPROVED_PAYSLIPS with fetch("/api/payslips?month=YYYY-MM")
// TODO [BACKEND]: "Download All (ZIP)" → fetch("/api/payslips/download-all?month=YYYY-MM")
// TODO [BACKEND]: "Broadcast via WhatsApp" → fetch("/api/payslips/broadcast", { method: "POST" })
import { format } from "date-fns";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Calendar } from "@/components/ui/calendar";
import {
  CalendarIcon,
  Download,
  MessageCircle,
  Printer,
  FileDown,
  Send,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ---------- Hourly-based payslip data ----------
interface ApprovedPayslip {
  employeeId: string;
  name: string;
  avatar: string;
  department: string;
  designation: string;
  baseSalary: number;
  standardHours: number;
  hoursLogged: number;
  hourlyRate: number;
  paidLeaves: number;
  leaveBalance: number;
  advancesTaken: number;
  professionalTax: number;
  bonus: number;
}

const APPROVED_PAYSLIPS: ApprovedPayslip[] = [
  { employeeId: "e1", name: "Rajesh Kumar", avatar: "RK", department: "Printing", designation: "Operator", baseSalary: 20800, standardHours: 208, hoursLogged: 218, hourlyRate: 100, paidLeaves: 0, leaveBalance: 10, advancesTaken: 2000, professionalTax: 200, bonus: 0 },
  { employeeId: "e2", name: "Priya Sharma", avatar: "PS", department: "Binding", designation: "Senior Binder", baseSalary: 19500, standardHours: 208, hoursLogged: 208, hourlyRate: 93.75, paidLeaves: 0, leaveBalance: 8, advancesTaken: 0, professionalTax: 200, bonus: 0 },
  { employeeId: "e3", name: "Amit Patel", avatar: "AP", department: "Design", designation: "Graphic Designer", baseSalary: 31200, standardHours: 208, hoursLogged: 224, hourlyRate: 150, paidLeaves: 0, leaveBalance: 12, advancesTaken: 5000, professionalTax: 200, bonus: 0 },
  { employeeId: "e4", name: "Sunita Devi", avatar: "SD", department: "Cutting", designation: "Cutting Operator", baseSalary: 18200, standardHours: 208, hoursLogged: 192, hourlyRate: 87.5, paidLeaves: 1, leaveBalance: 6, advancesTaken: 1500, professionalTax: 200, bonus: 0 },
  { employeeId: "e5", name: "Vikram Singh", avatar: "VS", department: "Printing", designation: "Lead Operator", baseSalary: 26000, standardHours: 208, hoursLogged: 212, hourlyRate: 125, paidLeaves: 0, leaveBalance: 9, advancesTaken: 3000, professionalTax: 200, bonus: 0 },
  { employeeId: "e6", name: "Meera Joshi", avatar: "MJ", department: "Admin", designation: "Office Coordinator", baseSalary: 23400, standardHours: 208, hoursLogged: 184, hourlyRate: 112.5, paidLeaves: 2, leaveBalance: 4, advancesTaken: 0, professionalTax: 200, bonus: 0 },
  { employeeId: "e7", name: "Arjun Reddy", avatar: "AR", department: "Binding", designation: "Helper", baseSalary: 14300, standardHours: 208, hoursLogged: 208, hourlyRate: 68.75, paidLeaves: 0, leaveBalance: 11, advancesTaken: 1000, professionalTax: 0, bonus: 0 },
  { employeeId: "e8", name: "Kavita Nair", avatar: "KN", department: "Design", designation: "Junior Designer", baseSalary: 22100, standardHours: 208, hoursLogged: 202, hourlyRate: 106.25, paidLeaves: 0, leaveBalance: 7, advancesTaken: 0, professionalTax: 200, bonus: 0 },
];

function getCalcs(p: ApprovedPayslip) {
  const otHours = Math.max(0, p.hoursLogged - p.standardHours);
  const shortHours = Math.max(0, p.standardHours - p.hoursLogged - p.paidLeaves * 8);
  const otPay = Math.round(otHours * p.hourlyRate * 100) / 100;
  const shortPenalty = Math.round(shortHours * p.hourlyRate * 100) / 100;
  const grossEarnings = p.baseSalary + otPay + p.bonus;
  const totalDeductions = shortPenalty + p.advancesTaken + p.professionalTax;
  const net = grossEarnings - totalDeductions;
  return { otHours, shortHours, otPay, shortPenalty, grossEarnings, totalDeductions, net };
}

function amountToWords(n: number): string {
  if (n === 0) return "Zero";
  const ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"];
  const tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"];
  function convert(num: number): string {
    if (num < 20) return ones[num];
    if (num < 100) return tens[Math.floor(num / 10)] + (num % 10 ? " " + ones[num % 10] : "");
    if (num < 1000) return ones[Math.floor(num / 100)] + " Hundred" + (num % 100 ? " and " + convert(num % 100) : "");
    if (num < 100000) return convert(Math.floor(num / 1000)) + " Thousand" + (num % 1000 ? " " + convert(num % 1000) : "");
    if (num < 10000000) return convert(Math.floor(num / 100000)) + " Lakh" + (num % 100000 ? " " + convert(num % 100000) : "");
    return convert(Math.floor(num / 10000000)) + " Crore" + (num % 10000000 ? " " + convert(num % 10000000) : "");
  }
  return "Rupees " + convert(Math.abs(Math.round(n))) + " Only";
}

const fmtInr = (n: number) => n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// ---------- Component ----------
export default function ReceiptVault() {
  const [selectedMonth, setSelectedMonth] = useState<Date>(new Date(2026, 2, 1));
  const [calendarOpen, setCalendarOpen] = useState(false);
  const [selectedId, setSelectedId] = useState("e1");

  const selected = APPROVED_PAYSLIPS.find((p) => p.employeeId === selectedId) ?? APPROVED_PAYSLIPS[0];
  const c = getCalcs(selected);

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">Receipt Vault</h1>
          <p className="text-sm text-muted-foreground mt-1">Review, print, and distribute finalized payslips.</p>
        </div>
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
      </div>

      {/* Split view */}
      <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-6 items-start">
        {/* Left: Directory */}
        <div className="space-y-4">
          <Card className="overflow-hidden">
            <div className="px-4 pt-4 pb-2">
              <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Approved Employees</p>
            </div>
            <ScrollArea className="h-[420px]">
              <div className="px-2 pb-2">
                {APPROVED_PAYSLIPS.map((p) => {
                  const pCalc = getCalcs(p);
                  return (
                    <button
                      key={p.employeeId}
                      onClick={() => setSelectedId(p.employeeId)}
                      className={cn(
                        "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-colors",
                        p.employeeId === selectedId
                          ? "bg-primary/10 text-primary"
                          : "hover:bg-muted/60 text-foreground"
                      )}
                    >
                      <div className={cn(
                        "flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold",
                        p.employeeId === selectedId ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
                      )}>
                        {p.avatar}
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium truncate">{p.name}</p>
                        <p className="text-xs text-muted-foreground">{p.department}</p>
                      </div>
                      <span className="text-xs font-semibold tabular-nums text-emerald-600">₹{pCalc.net.toLocaleString("en-IN")}</span>
                    </button>
                  );
                })}
              </div>
            </ScrollArea>
          </Card>

          <Card>
            <CardContent className="p-4 space-y-2">
              <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-3">Mass Actions</p>
              <Button variant="outline" className="w-full h-9 text-sm gap-2 justify-center">
                <Download className="h-3.5 w-3.5" />
                Download All (ZIP)
              </Button>
              <Button className="w-full h-9 text-sm gap-2 justify-center bg-emerald-600 hover:bg-emerald-700 text-white">
                <MessageCircle className="h-3.5 w-3.5" />
                Broadcast via WhatsApp
              </Button>
            </CardContent>
          </Card>
        </div>

        {/* Right: A4 Preview */}
        <div className="relative">
          {/* Floating action bar */}
          <div className="flex items-center gap-1 mb-3 justify-end">
            <Button variant="outline" size="sm" className="h-8 text-xs gap-1.5">
              <Printer className="h-3.5 w-3.5" />
              Print
            </Button>
            <Button variant="outline" size="sm" className="h-8 text-xs gap-1.5">
              <FileDown className="h-3.5 w-3.5" />
              Download PDF
            </Button>
            <Button size="sm" className="h-8 text-xs gap-1.5 bg-indigo-600 hover:bg-indigo-700 text-white">
              <Send className="h-3.5 w-3.5" />
              WhatsApp
            </Button>
          </div>

          {/* Dark canvas */}
          <div className="bg-[hsl(220,14%,20%)] rounded-xl p-6 lg:p-10">
            {/* A4 Paper */}
            <div className="bg-white max-w-[700px] mx-auto shadow-2xl relative overflow-hidden" style={{ fontFamily: "'Segoe UI', system-ui, sans-serif" }}>

              {/* Watermark */}
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none select-none opacity-[0.03]">
                <span className="text-[120px] font-black tracking-widest text-foreground rotate-[-30deg]">PW</span>
              </div>

              {/* Header band */}
              <div className="px-10 pt-8 pb-6 flex items-start justify-between relative">
                <div className="flex items-start gap-4">
                  {/* TODO [BACKEND]: Replace with dynamic logo from company settings */}
                  <div className="h-14 w-14 rounded-lg bg-indigo-50 border border-indigo-200 flex items-center justify-center text-indigo-700 font-black text-xl shrink-0">
                    P
                  </div>
                  <div>
                    <p className="text-[15px] font-bold text-foreground tracking-tight leading-tight">PrintWorks Pvt. Ltd.</p>
                    <p className="text-[10px] text-muted-foreground leading-relaxed mt-1">
                      42 Industrial Area, Sector 7<br />
                      New Delhi — 110020
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-[22px] font-black tracking-[0.2em] text-foreground leading-none">SALARY SLIP</p>
                  <p className="text-[10px] text-muted-foreground mt-2">For the month of {format(selectedMonth, "MMMM yyyy")}</p>
                </div>
              </div>

              {/* Thick divider */}
              <div className="h-[2px] bg-foreground/80 mx-10" />

              {/* Employee Info Grid - Row 1 */}
              <div className="mx-10 mt-0 grid grid-cols-4 border-x border-b border-foreground/20">
                <SlipCell label="Employee Name" value={selected.name} />
                <SlipCell label="Employee ID" value={selected.employeeId.toUpperCase()} />
                <SlipCell label="Designation" value={selected.designation} />
                <SlipCell label="Department" value={selected.department} last />
              </div>

              {/* Employee Info Grid - Row 2 (Hourly data) */}
              <div className="mx-10 grid grid-cols-3 border-x border-b border-foreground/20">
                <SlipCell label="Expected Hours" value={`${selected.standardHours}h`} />
                <SlipCell label="Hours Logged" value={`${selected.hoursLogged}h`} highlight={selected.hoursLogged >= selected.standardHours ? "success" : "destructive"} />
                <SlipCell label="Leave Balance" value={`${selected.leaveBalance}`} last />
              </div>

              {/* Financial Ledger */}
              <div className="mx-10 mt-6 grid grid-cols-2 gap-0">
                {/* Earnings */}
                <div className="border border-foreground/20 border-r-0">
                  <div className="bg-slate-50 px-5 py-2 border-b border-foreground/20">
                    <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-foreground">Earnings</p>
                  </div>
                  <div className="divide-y divide-foreground/10">
                    <SlipLedgerRow label={`Basic Salary (for ${selected.standardHours}h)`} value={fmtInr(selected.baseSalary)} />
                    <SlipLedgerRow label={`Overtime Pay (${c.otHours}h)`} value={fmtInr(c.otPay)} />
                    {selected.bonus > 0 && <SlipLedgerRow label="Bonus / Incentive" value={fmtInr(selected.bonus)} />}
                  </div>
                  <div className="px-5 py-2.5 border-t-2 border-foreground/30 flex items-center justify-between bg-slate-50/50">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-foreground">Gross Earnings</span>
                    <span className="text-xs font-black tabular-nums text-foreground">₹{fmtInr(c.grossEarnings)}</span>
                  </div>
                </div>

                {/* Deductions */}
                <div className="border border-foreground/20">
                  <div className="bg-slate-50 px-5 py-2 border-b border-foreground/20">
                    <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-foreground">Deductions</p>
                  </div>
                  <div className="divide-y divide-foreground/10">
                    <SlipLedgerRow label="Shortfall / Leave Penalties" value={fmtInr(c.shortPenalty)} />
                    <SlipLedgerRow label="Advance Recovery" value={fmtInr(selected.advancesTaken)} />
                    <SlipLedgerRow label="Professional Tax" value={fmtInr(selected.professionalTax)} />
                  </div>
                  <div className="px-5 py-2.5 border-t-2 border-foreground/30 flex items-center justify-between bg-slate-50/50">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-foreground">Total Deductions</span>
                    <span className="text-xs font-black tabular-nums text-destructive">₹{fmtInr(c.totalDeductions)}</span>
                  </div>
                </div>
              </div>

              {/* Net Payable Footer */}
              <div className="mx-10 mt-6 border-t-[3px] border-foreground/90">
                <div className="bg-indigo-950 px-6 py-5 flex items-center justify-between">
                  <div>
                    <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-indigo-200">Net Salary Payable</p>
                  </div>
                  <p className="text-[28px] font-black text-white tabular-nums tracking-tight">₹{fmtInr(c.net)}</p>
                </div>
                <div className="bg-muted/40 px-6 py-2 border border-t-0 border-foreground/20">
                  <p className="text-[10px] italic text-muted-foreground">({amountToWords(c.net)})</p>
                </div>
              </div>

              {/* Signatures */}
              <div className="mx-10 mt-10 mb-6 flex items-end justify-between">
                <div>
                  <div className="w-36 border-t border-dashed border-foreground/40 mb-1.5" />
                  <p className="text-[9px] text-muted-foreground">Employer Signature</p>
                </div>
                <div className="text-right">
                  <div className="w-36 border-t border-dashed border-foreground/40 mb-1.5 ml-auto" />
                  <p className="text-[9px] text-muted-foreground">Employee Signature</p>
                </div>
              </div>

              {/* Footer disclaimer */}
              <div className="bg-muted/30 border-t border-foreground/10 px-10 py-3">
                <p className="text-[8px] text-muted-foreground text-center leading-relaxed">
                  This is a system-generated document and does not require a physical seal if distributed digitally. Generated on {format(new Date(), "dd MMM yyyy")}.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------- Payslip Sub-components ----------
function SlipCell({ label, value, last, highlight }: { label: string; value: string; last?: boolean; highlight?: "success" | "destructive" }) {
  const color = highlight === "success" ? "text-emerald-700 font-bold" : highlight === "destructive" ? "text-destructive font-bold" : "text-foreground font-semibold";
  return (
    <div className={cn("px-4 py-3", !last && "border-r border-foreground/20")}>
      <p className="text-[8px] uppercase tracking-[0.12em] text-muted-foreground mb-0.5">{label}</p>
      <p className={cn("text-[11px] tabular-nums", color)}>{value}</p>
    </div>
  );
}

function SlipLedgerRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="px-5 py-2.5 flex items-center justify-between">
      <span className="text-[10px] text-muted-foreground">{label}</span>
      <span className="text-[11px] font-semibold text-foreground tabular-nums">₹{value}</span>
    </div>
  );
}
