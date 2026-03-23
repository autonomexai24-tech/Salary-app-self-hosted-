import { useState, useMemo } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Separator } from "@/components/ui/separator";
import { Search, UserPlus, Zap, Phone, User, Save } from "lucide-react";
import { MOCK_EMPLOYEES, type Employee } from "@/lib/mock-employees";
import { COMPANY_FIXED_SHIFT } from "@/lib/payroll-config";
import CompanySettings from "@/components/CompanySettings";

const INITIAL_DESIGNATIONS = [
  "Operator",
  "Senior Binder",
  "Graphic Designer",
  "Lead Operator",
  "Office Coordinator",
  "Helper",
  "Junior Designer",
];

const INITIAL_DEPARTMENTS = ["Printing", "Binding", "Design", "Cutting", "Admin"];

export default function PeopleHub() {
  const [designations, setDesignations] = useState(INITIAL_DESIGNATIONS);
  const [departments, setDepartments] = useState(INITIAL_DEPARTMENTS);

  // Employee Directory state
  const [employees, setEmployees] = useState<Employee[]>(MOCK_EMPLOYEES);
  const [search, setSearch] = useState("");
  const [sheetOpen, setSheetOpen] = useState(false);

  // Registration form state
  const [regName, setRegName] = useState("");
  const [regPhone, setRegPhone] = useState("");
  const [regDept, setRegDept] = useState("");
  const [regDesig, setRegDesig] = useState("");
  const [regMonthly, setRegMonthly] = useState("");
  const [regWorkingDays, setRegWorkingDays] = useState("26");

  const filteredEmployees = useMemo(() => {
    if (!search.trim()) return employees;
    const q = search.toLowerCase();
    return employees.filter(
      (e) =>
        e.name.toLowerCase().includes(q) ||
        e.department.toLowerCase().includes(q) ||
        e.designation.toLowerCase().includes(q)
    );
  }, [employees, search]);

  // Auto-calc rates
  const monthlyVal = Number(regMonthly) || 0;
  const workingDaysVal = Number(regWorkingDays) || 26;
  const hoursVal = COMPANY_FIXED_SHIFT.totalHours;
  const perDay = monthlyVal > 0 ? Math.round(monthlyVal / workingDaysVal) : 0;
  const perHour = perDay > 0 ? Math.round(perDay / hoursVal) : 0;
  const perMinute = perHour > 0 ? Math.round((perHour / 60) * 100) / 100 : 0;

  const resetForm = () => {
    setRegName("");
    setRegPhone("");
    setRegDept("");
    setRegDesig("");
    setRegMonthly("");
    setRegWorkingDays("26");
  };

  const saveEmployee = () => {
    if (!regName.trim() || !regDept || !regDesig || monthlyVal <= 0) return;
    const initials = regName
      .trim()
      .split(" ")
      .map((w) => w[0])
      .join("")
      .toUpperCase()
      .slice(0, 2);
    const newEmp: Employee = {
      id: `e${Date.now()}`,
      name: regName.trim(),
      department: regDept,
      designation: regDesig,
      dailyRate: perDay,
      monthlyBasic: monthlyVal,
      avatar: initials,
    };
    setEmployees((prev) => [...prev, newEmp]);
    resetForm();
    setSheetOpen(false);
  };

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">People Hub</h1>
        <p className="text-sm text-muted-foreground mt-1">Manage employees, designations, and company settings.</p>
      </div>

      <Tabs defaultValue="directory">
        <TabsList className="grid w-full max-w-md grid-cols-2">
          <TabsTrigger value="directory">Employee Directory</TabsTrigger>
          <TabsTrigger value="settings">Company Settings</TabsTrigger>
        </TabsList>

        {/* ===================== COMPANY SETTINGS TAB ===================== */}
        <TabsContent value="settings" className="mt-6">
          <CompanySettings
            designations={designations}
            setDesignations={setDesignations}
            departments={departments}
            setDepartments={setDepartments}
          />
        </TabsContent>

        {/* ===================== EMPLOYEE DIRECTORY TAB ===================== */}
        <TabsContent value="directory" className="mt-6 space-y-4">
          {/* Action Bar */}
          <div className="flex items-center gap-3">
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                placeholder="Search employees..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-8 h-9 text-sm"
              />
            </div>
            <Button
              onClick={() => { resetForm(); setSheetOpen(true); }}
              className="bg-emerald-600 hover:bg-emerald-700 text-white shrink-0"
              size="sm"
            >
              <UserPlus className="h-3.5 w-3.5 mr-1.5" />
              Register New Employee
            </Button>
          </div>

          {/* Employee Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {filteredEmployees.map((emp) => (
              <Card key={emp.id} className="hover:shadow-md transition-shadow">
                <CardContent className="p-4 flex items-start gap-3">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary text-sm font-semibold">
                    {emp.avatar}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-foreground truncate">{emp.name}</p>
                    <p className="text-xs text-muted-foreground">{emp.designation}</p>
                    <div className="flex items-center gap-2 mt-2">
                      <Badge variant="secondary" className="text-[11px] font-normal">{emp.department}</Badge>
                      <span className="text-[11px] text-muted-foreground">₹{emp.monthlyBasic.toLocaleString("en-IN")}/mo</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          {filteredEmployees.length === 0 && (
            <div className="text-center py-12 text-muted-foreground text-sm">No employees found.</div>
          )}
        </TabsContent>
      </Tabs>

      {/* ===================== REGISTER EMPLOYEE SHEET ===================== */}
      <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
        <SheetContent className="sm:max-w-lg overflow-y-auto">
          <SheetHeader>
            <SheetTitle className="text-lg">Register New Employee</SheetTitle>
            <SheetDescription>Add a new team member. Auto-calculated rates will power the Daily Log.</SheetDescription>
          </SheetHeader>

          <div className="mt-6 space-y-6">
            {/* Section 1: Personal */}
            <div className="space-y-4">
              <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Personal Information</p>
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <Label className="text-xs">Full Name</Label>
                  <div className="relative">
                    <User className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
                    <Input placeholder="e.g. Rahul Mehta" value={regName} onChange={(e) => setRegName(e.target.value)} className="pl-8 h-9 text-sm" />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Phone Number</Label>
                  <div className="relative">
                    <Phone className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
                    <Input placeholder="e.g. 98765 43210" value={regPhone} onChange={(e) => setRegPhone(e.target.value)} className="pl-8 h-9 text-sm" />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs">Department</Label>
                    <Select value={regDept} onValueChange={setRegDept}>
                      <SelectTrigger className="h-9 text-sm"><SelectValue placeholder="Select" /></SelectTrigger>
                      <SelectContent>
                        {departments.map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Designation</Label>
                    <Select value={regDesig} onValueChange={setRegDesig}>
                      <SelectTrigger className="h-9 text-sm"><SelectValue placeholder="Select" /></SelectTrigger>
                      <SelectContent>
                        {designations.map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </div>
            </div>

            <Separator />

            {/* Section 2: Salary Config */}
            <div className="space-y-4">
              <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Salary Configuration</p>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label className="text-xs">Monthly Basic Salary</Label>
                  <div className="relative">
                    <span className="absolute left-2.5 top-2 text-sm text-muted-foreground font-medium">₹</span>
                    <Input type="number" placeholder="25000" value={regMonthly} onChange={(e) => setRegMonthly(e.target.value)} className="pl-7 h-9 text-sm" min={0} />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Working Days / Month</Label>
                  <Input type="number" value={regWorkingDays} onChange={(e) => setRegWorkingDays(e.target.value)} className="h-9 text-sm" min={1} max={31} />
                </div>
              </div>
            </div>

            {/* Auto-Calculation Box */}
            <div className="rounded-xl border-2 border-emerald-200 bg-emerald-50 p-4 space-y-3">
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-600 text-white">
                  <Zap className="h-3.5 w-3.5" />
                </div>
                <p className="text-sm font-semibold text-emerald-900">Automated Rate Breakdown</p>
              </div>
              <div className="grid grid-cols-3 gap-3">
                <RateBox label="Per Day" value={`₹${perDay.toLocaleString("en-IN")}`} />
                <RateBox label="Per Hour" value={`₹${perHour.toLocaleString("en-IN")}`} />
                <RateBox label="Per Minute" value={`₹${perMinute.toFixed(2)}`} />
              </div>
              <p className="text-[11px] text-emerald-700 leading-relaxed">
                These rates will automatically power the Daily Log penalties and overtime calculations.
              </p>
            </div>

            <Button onClick={saveEmployee} className="w-full" disabled={!regName.trim() || !regDept || !regDesig || monthlyVal <= 0}>
              <Save className="h-3.5 w-3.5 mr-1.5" />
              Save Employee Profile
            </Button>
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}

function RateBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-white/80 border border-emerald-200 p-2.5 text-center">
      <p className="text-[11px] text-emerald-700">{label}</p>
      <p className="text-base font-bold text-emerald-900 tabular-nums">{value}</p>
    </div>
  );
}
