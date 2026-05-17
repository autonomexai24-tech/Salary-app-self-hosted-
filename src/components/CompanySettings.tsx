import { useEffect, useState, useMemo, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Plus, X, Clock, Save, CalendarDays, Palmtree, Building2, ImageIcon } from "lucide-react";
import { format } from "date-fns";
import { cn } from "@/lib/utils";
import { COMPANY_FIXED_SHIFT, GRACE_PERIOD_MINUTES } from "@/lib/payroll-config";
import {
  apiErrorMessage,
  createDepartment,
  createDesignation,
  createHoliday,
  dateInputValue,
  deleteDepartment,
  deleteDesignation,
  deleteHoliday,
  listDepartments,
  listDesignations,
  listHolidays,
  readCompanySettings,
  readLeavePolicy,
  resolveApiAssetUrl,
  updateCompanySettings,
  updateLeavePolicy,
  uploadCompanyLogo,
  type BackendHoliday,
  type BackendSettingsCatalogItem,
} from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

interface Holiday {
  id: string;
  date: Date;
  name: string;
}

interface CompanySettingsProps {
  designations: string[];
  setDesignations: React.Dispatch<React.SetStateAction<string[]>>;
  departments: string[];
  setDepartments: React.Dispatch<React.SetStateAction<string[]>>;
}

function dateFromApiValue(value: string): Date {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function mapHoliday(record: BackendHoliday): Holiday {
  return {
    id: record.id,
    date: dateFromApiValue(record.date),
    name: record.name,
  };
}

function catalogNames(records: BackendSettingsCatalogItem[]): string[] {
  return records.map((record) => record.name);
}

const OFFLINE_STORAGE_KEYS = {
  designations: "payroll_offline_designations",
  departments: "payroll_offline_departments",
  holidays: "payroll_offline_holidays",
  timings: "payroll_offline_timings",
  leavePolicy: "payroll_offline_leave_policy",
} as const;

function readOfflineJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function writeOfflineJson(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch { /* ignore */ }
}

function makeLocalCatalogItem(name: string): BackendSettingsCatalogItem {
  const now = new Date().toISOString();
  return {
    id: `local-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    name,
    is_active: true,
    created_at: now,
    updated_at: now,
  };
}

export default function CompanySettings({
  designations,
  setDesignations,
  departments,
  setDepartments,
}: CompanySettingsProps) {
  // Shift & Timing
  const [shiftStart, setShiftStart] = useState(COMPANY_FIXED_SHIFT.start);
  const [shiftEnd, setShiftEnd] = useState(COMPANY_FIXED_SHIFT.end);
  const [workingHours, setWorkingHours] = useState(String(COMPANY_FIXED_SHIFT.totalHours));
  const [gracePeriod, setGracePeriod] = useState(String(GRACE_PERIOD_MINUTES));

  // Leave Policy
  const [annualLeaves, setAnnualLeaves] = useState("12");
  const [monthlyAccrual, setMonthlyAccrual] = useState("1");
  const [unusedLeaveAction, setUnusedLeaveAction] = useState("carry_forward");
  const [defaultLeaveBalance, setDefaultLeaveBalance] = useState("0");
  const [overtimeMultiplier, setOvertimeMultiplier] = useState("1");
  const [latePenaltyPerMinute, setLatePenaltyPerMinute] = useState("0");

  // Holiday Calendar
  const [holidays, setHolidays] = useState<Holiday[]>([]);
  const [holidayDate, setHolidayDate] = useState<Date>();
  const [holidayName, setHolidayName] = useState("");
  const [datePickerOpen, setDatePickerOpen] = useState(false);

  // Branding
  const [companyName, setCompanyName] = useState("");
  const [companyAddress, setCompanyAddress] = useState("");
  const [logoPreview, setLogoPreview] = useState<string | null>(null);
  const [isSavingTimings, setIsSavingTimings] = useState(false);
  const [isSavingBranding, setIsSavingBranding] = useState(false);

  // Designation & Department inputs
  const [newDesignation, setNewDesignation] = useState("");
  const [newDepartment, setNewDepartment] = useState("");
  const [designationRecords, setDesignationRecords] = useState<BackendSettingsCatalogItem[]>([]);
  const [departmentRecords, setDepartmentRecords] = useState<BackendSettingsCatalogItem[]>([]);

  const { user } = useAuth();
  const isOffline = user?.id === "offline-admin";

  const syncDesignations = (records: BackendSettingsCatalogItem[]) => {
    setDesignationRecords(records);
    setDesignations(catalogNames(records));
  };

  const syncDepartments = (records: BackendSettingsCatalogItem[]) => {
    setDepartmentRecords(records);
    setDepartments(catalogNames(records));
  };

  useEffect(() => {
    let cancelled = false;

    if (isOffline) {
      // Load from localStorage in offline mode
      const offDesg = readOfflineJson<BackendSettingsCatalogItem[]>(OFFLINE_STORAGE_KEYS.designations, []);
      const offDept = readOfflineJson<BackendSettingsCatalogItem[]>(OFFLINE_STORAGE_KEYS.departments, []);
      const offHol = readOfflineJson<Holiday[]>(OFFLINE_STORAGE_KEYS.holidays, []);
      const offTimings = readOfflineJson<{ shiftStart: string; shiftEnd: string; workingHours: string; gracePeriod: string } | null>(OFFLINE_STORAGE_KEYS.timings, null);
      const offLeave = readOfflineJson<{ annualLeaves: string; monthlyAccrual: string; unusedLeaveAction: string } | null>(OFFLINE_STORAGE_KEYS.leavePolicy, null);
      setDesignationRecords(offDesg);
      setDesignations(catalogNames(offDesg));
      setDepartmentRecords(offDept);
      setDepartments(catalogNames(offDept));
      setHolidays(offHol.map((h) => ({ ...h, date: new Date(h.date) })));
      if (offTimings) {
        setShiftStart(offTimings.shiftStart);
        setShiftEnd(offTimings.shiftEnd);
        setWorkingHours(offTimings.workingHours);
        setGracePeriod(offTimings.gracePeriod);
      }
      if (offLeave) {
        setAnnualLeaves(offLeave.annualLeaves);
        setMonthlyAccrual(offLeave.monthlyAccrual);
        setUnusedLeaveAction(offLeave.unusedLeaveAction);
      }
      return () => { cancelled = true; };
    }

    readCompanySettings()
      .then((settings) => {
        if (cancelled) return;
        setShiftStart(settings.shift_start_time.slice(0, 5));
        setShiftEnd(settings.shift_end_time.slice(0, 5));
        setWorkingHours(String(Number(settings.standard_work_hours)));
        setGracePeriod(String(settings.grace_period_minutes));
        setCompanyName(settings.company_name);
        setCompanyAddress(settings.address ?? "");
        setLogoPreview(resolveApiAssetUrl(settings.logo_url));
      })
      .catch((error) => {
        if (cancelled) return;
        toast.error("Could not load company settings", {
          description: apiErrorMessage(error),
        });
      });

    readLeavePolicy()
      .then((policy) => {
        if (cancelled) return;
        setAnnualLeaves(String(Number(policy.annual_paid_leaves)));
        setMonthlyAccrual(String(Number(policy.monthly_leave_accrual)));
        setUnusedLeaveAction(policy.unused_leave_action);
        setDefaultLeaveBalance(String(Number(policy.default_leave_balance)));
        setOvertimeMultiplier(String(Number(policy.overtime_multiplier)));
        setLatePenaltyPerMinute(String(Number(policy.late_penalty_per_minute)));
      })
      .catch((error) => {
        if (cancelled) return;
        toast.error("Could not load leave policy", {
          description: apiErrorMessage(error),
        });
      });

    listHolidays()
      .then((records) => {
        if (cancelled) return;
        setHolidays(records.map(mapHoliday));
      })
      .catch((error) => {
        if (cancelled) return;
        toast.error("Could not load holidays", {
          description: apiErrorMessage(error),
        });
      });

    listDesignations()
      .then((records) => {
        if (cancelled) return;
        setDesignationRecords(records);
        setDesignations(catalogNames(records));
      })
      .catch((error) => {
        if (cancelled) return;
        toast.error("Could not load designations", {
          description: apiErrorMessage(error),
        });
      });

    listDepartments()
      .then((records) => {
        if (cancelled) return;
        setDepartmentRecords(records);
        setDepartments(catalogNames(records));
      })
      .catch((error) => {
        if (cancelled) return;
        toast.error("Could not load departments", {
          description: apiErrorMessage(error),
        });
      });

    return () => {
      cancelled = true;
    };
  }, [setDepartments, setDesignations, isOffline]);

  const formatShiftLabel = (time: string) => {
    if (!time) return "";
    const [h, m] = time.split(":").map(Number);
    const suffix = h >= 12 ? "PM" : "AM";
    const displayH = h > 12 ? h - 12 : h === 0 ? 12 : h;
    return `${String(displayH).padStart(2, "0")}:${String(m).padStart(2, "0")} ${suffix}`;
  };

  const graceEnd = useMemo(() => {
    const [h, m] = shiftStart.split(":").map(Number);
    const totalMin = h * 60 + m + (Number(gracePeriod) || 0);
    const nh = Math.floor(totalMin / 60);
    const nm = totalMin % 60;
    return formatShiftLabel(`${String(nh).padStart(2, "0")}:${String(nm).padStart(2, "0")}`);
  }, [shiftStart, gracePeriod]);

  const addDesignation = async () => {
    const val = newDesignation.trim();
    if (!val || designations.includes(val)) return;

    if (isOffline) {
      const created = makeLocalCatalogItem(val);
      const nextRecords = [...designationRecords, created];
      syncDesignations(nextRecords);
      writeOfflineJson(OFFLINE_STORAGE_KEYS.designations, nextRecords);
      setNewDesignation("");
      toast.success("Designation added (offline)");
      return;
    }

    try {
      const created = await createDesignation(val);
      const nextRecords = [
        ...designationRecords.filter((record) => record.id !== created.id),
        created,
      ];
      syncDesignations(nextRecords);
      setNewDesignation("");
    } catch (error) {
      toast.error("Could not save designation", {
        description: apiErrorMessage(error),
      });
    }
  };

  const addDepartment = async () => {
    const val = newDepartment.trim();
    if (!val || departments.includes(val)) return;

    if (isOffline) {
      const created = makeLocalCatalogItem(val);
      const nextRecords = [...departmentRecords, created];
      syncDepartments(nextRecords);
      writeOfflineJson(OFFLINE_STORAGE_KEYS.departments, nextRecords);
      setNewDepartment("");
      toast.success("Department added (offline)");
      return;
    }

    try {
      const created = await createDepartment(val);
      const nextRecords = [
        ...departmentRecords.filter((record) => record.id !== created.id),
        created,
      ];
      syncDepartments(nextRecords);
      setNewDepartment("");
    } catch (error) {
      toast.error("Could not save department", {
        description: apiErrorMessage(error),
      });
    }
  };

  const addHoliday = async () => {
    if (!holidayDate || !holidayName.trim()) return;

    if (isOffline) {
      const localHoliday: Holiday = {
        id: `local-${Date.now()}`,
        date: holidayDate,
        name: holidayName.trim(),
      };
      const next = [...holidays, localHoliday];
      setHolidays(next);
      writeOfflineJson(OFFLINE_STORAGE_KEYS.holidays, next);
      setHolidayDate(undefined);
      setHolidayName("");
      toast.success("Holiday added (offline)");
      return;
    }

    try {
      const created = await createHoliday({
        date: dateInputValue(holidayDate),
        name: holidayName.trim(),
      });
      setHolidays((prev) => [...prev, mapHoliday(created)]);
      setHolidayDate(undefined);
      setHolidayName("");
    } catch (error) {
      toast.error("Could not save holiday", {
        description: apiErrorMessage(error),
      });
    }
  };

  const saveMasterTimings = async () => {
    setIsSavingTimings(true);
    if (isOffline) {
      writeOfflineJson(OFFLINE_STORAGE_KEYS.timings, { shiftStart, shiftEnd, workingHours, gracePeriod });
      toast.success("Master timings saved (offline)");
      setIsSavingTimings(false);
      return;
    }
    try {
      await updateCompanySettings({
        shift_start_time: shiftStart,
        shift_end_time: shiftEnd,
        standard_work_hours: Number(workingHours) || COMPANY_FIXED_SHIFT.totalHours,
        grace_period_minutes: Number(gracePeriod) || 0,
      });
      toast.success("Master timings saved");
    } catch (error) {
      toast.error("Could not save master timings", {
        description: apiErrorMessage(error),
      });
    } finally {
      setIsSavingTimings(false);
    }
  };

  const saveBranding = async () => {
    setIsSavingBranding(true);
    if (isOffline) {
      toast.success("Company branding saved (offline)");
      setIsSavingBranding(false);
      return;
    }
    try {
      const settings = await updateCompanySettings({
        company_name: companyName.trim(),
        address: companyAddress.trim() || null,
      });
      setCompanyName(settings.company_name);
      setCompanyAddress(settings.address ?? "");
      toast.success("Company branding saved");
    } catch (error) {
      toast.error("Could not save company branding", {
        description: apiErrorMessage(error),
      });
    } finally {
      setIsSavingBranding(false);
    }
  };

  const saveLeaveRules = async () => {
    if (isOffline) {
      writeOfflineJson(OFFLINE_STORAGE_KEYS.leavePolicy, { annualLeaves, monthlyAccrual, unusedLeaveAction });
      toast.success("Leave rules saved (offline)");
      return;
    }
    try {
      const policy = await updateLeavePolicy({
        annual_paid_leaves: Number(annualLeaves) || 0,
        monthly_leave_accrual: Number(monthlyAccrual) || 0,
        unused_leave_action: unusedLeaveAction,
        default_leave_balance: Number(defaultLeaveBalance) || 0,
        overtime_multiplier: Number(overtimeMultiplier) || 0,
        late_penalty_per_minute: Number(latePenaltyPerMinute) || 0,
        shift_start_time: shiftStart,
        shift_end_time: shiftEnd,
        standard_work_hours: Number(workingHours) || COMPANY_FIXED_SHIFT.totalHours,
        grace_period_minutes: Number(gracePeriod) || 0,
      });
      setAnnualLeaves(String(Number(policy.annual_paid_leaves)));
      setMonthlyAccrual(String(Number(policy.monthly_leave_accrual)));
      setUnusedLeaveAction(policy.unused_leave_action);
      setDefaultLeaveBalance(String(Number(policy.default_leave_balance)));
      setOvertimeMultiplier(String(Number(policy.overtime_multiplier)));
      setLatePenaltyPerMinute(String(Number(policy.late_penalty_per_minute)));
      toast.success("Leave rules saved");
    } catch (error) {
      toast.error("Could not save leave rules", {
        description: apiErrorMessage(error),
      });
    }
  };

  const handleLogoFile = async (file: File) => {
    const previousLogo = logoPreview;
    const localPreviewUrl = URL.createObjectURL(file);
    setLogoPreview(localPreviewUrl);
    try {
      const settings = await uploadCompanyLogo(file);
      setLogoPreview(resolveApiAssetUrl(settings.logo_url));
      toast.success("Company logo uploaded");
    } catch (error) {
      setLogoPreview(previousLogo);
      toast.error("Could not upload company logo", {
        description: apiErrorMessage(error),
      });
    } finally {
      URL.revokeObjectURL(localPreviewUrl);
    }
  };

  const sortedHolidays = useMemo(
    () => [...holidays].sort((a, b) => a.date.getTime() - b.date.getTime()),
    [holidays]
  );

  const removeHoliday = async (holiday: Holiday) => {
    const previousHolidays = holidays;
    const next = holidays.filter((item) => item.id !== holiday.id);
    setHolidays(next);
    if (isOffline) {
      writeOfflineJson(OFFLINE_STORAGE_KEYS.holidays, next);
      return;
    }
    try {
      await deleteHoliday(holiday.id);
    } catch (error) {
      setHolidays(previousHolidays);
      toast.error("Could not delete holiday", {
        description: apiErrorMessage(error),
      });
    }
  };

  const removeDesignation = async (name: string) => {
    const record = designationRecords.find((item) => item.name === name);
    if (!record) {
      setDesignations((prev) => prev.filter((item) => item !== name));
      return;
    }

    if (isOffline) {
      const nextRecords = designationRecords.filter((item) => item.id !== record.id);
      syncDesignations(nextRecords);
      writeOfflineJson(OFFLINE_STORAGE_KEYS.designations, nextRecords);
      return;
    }

    try {
      await deleteDesignation(record.id);
      syncDesignations(designationRecords.filter((item) => item.id !== record.id));
    } catch (error) {
      toast.error("Could not delete designation", {
        description: apiErrorMessage(error),
      });
    }
  };

  const removeDepartment = async (name: string) => {
    const record = departmentRecords.find((item) => item.name === name);
    if (!record) {
      setDepartments((prev) => prev.filter((item) => item !== name));
      return;
    }

    if (isOffline) {
      const nextRecords = departmentRecords.filter((item) => item.id !== record.id);
      syncDepartments(nextRecords);
      writeOfflineJson(OFFLINE_STORAGE_KEYS.departments, nextRecords);
      return;
    }

    try {
      await deleteDepartment(record.id);
      syncDepartments(departmentRecords.filter((item) => item.id !== record.id));
    } catch (error) {
      toast.error("Could not delete department", {
        description: apiErrorMessage(error),
      });
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* ========== LEFT COLUMN ========== */}
      <div className="space-y-6">
        {/* Card A: Shift & Timing Rules */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Clock className="h-4 w-4 text-primary" />
              Global Shift & Timing Rules
            </CardTitle>
            <CardDescription>Set the default timings used across all payroll calculations.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-xs">Default Shift Start</Label>
                <Input type="time" value={shiftStart} onChange={(e) => setShiftStart(e.target.value)} className="h-9 text-sm" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Default Shift End</Label>
                <Input type="time" value={shiftEnd} onChange={(e) => setShiftEnd(e.target.value)} className="h-9 text-sm" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-xs">Working Hours / Day</Label>
                <Input type="number" value={workingHours} onChange={(e) => setWorkingHours(e.target.value)} className="h-9 text-sm" min={1} max={24} />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Late Grace Period (min)</Label>
                <Input type="number" value={gracePeriod} onChange={(e) => setGracePeriod(e.target.value)} className="h-9 text-sm" min={0} />
                <p className="text-[11px] text-muted-foreground">No penalty before {graceEnd}</p>
              </div>
            </div>
            <Button className="w-full mt-2" size="sm" onClick={saveMasterTimings} disabled={isSavingTimings}>
              <Save className="h-3.5 w-3.5 mr-1.5" />
              Save Master Timings
            </Button>
          </CardContent>
        </Card>

        {/* Card B: Global Leave Policy */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Palmtree className="h-4 w-4 text-primary" />
              Global Leave Policy
            </CardTitle>
            <CardDescription>Set default paid time off (PTO) rules for all employees.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-xs">Annual Paid Leaves (Total)</Label>
                <Input type="number" value={annualLeaves} onChange={(e) => setAnnualLeaves(e.target.value)} className="h-9 text-sm" min={0} />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Monthly Accrual Limit</Label>
                <Input type="number" value={monthlyAccrual} onChange={(e) => setMonthlyAccrual(e.target.value)} className="h-9 text-sm" min={0} />
                <p className="text-[11px] text-muted-foreground">Leaves earned per month</p>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Unused Leave Action</Label>
              <Select value={unusedLeaveAction} onValueChange={setUnusedLeaveAction}>
                <SelectTrigger className="h-9 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="encash">Encash at year-end</SelectItem>
                  <SelectItem value="carry_forward">Carry forward</SelectItem>
                  <SelectItem value="expire">Expire</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button className="w-full mt-2" size="sm" onClick={saveLeaveRules}>
              <Save className="h-3.5 w-3.5 mr-1.5" />
              Save Leave Rules
            </Button>
          </CardContent>
        </Card>

        {/* Card F: Company Branding */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Building2 className="h-4 w-4 text-primary" />
              Company Branding & Details
            </CardTitle>
            <CardDescription>Details appear on official payslips and reports.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label className="text-xs">Registered Company Name</Label>
              <Input value={companyName} onChange={(e) => setCompanyName(e.target.value)} className="h-9 text-sm" placeholder="e.g., PrintWorks Pvt. Ltd." />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Registered Address</Label>
              <Textarea value={companyAddress} onChange={(e) => setCompanyAddress(e.target.value)} className="text-sm min-h-[72px] resize-none" placeholder="Full registered address..." />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Company Logo</Label>
              <label
                className="flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-muted-foreground/25 bg-muted/30 p-6 cursor-pointer hover:border-primary/40 hover:bg-primary/5 transition-colors"
              >
                {logoPreview ? (
                  <img src={logoPreview} alt="Company logo" className="max-h-16 max-w-[200px] object-contain" />
                ) : (
                  <>
                    <ImageIcon className="h-8 w-8 text-muted-foreground/50" />
                    <p className="text-xs font-medium text-muted-foreground">Click or Drag to Add Company Logo</p>
                    <p className="text-[10px] text-muted-foreground/70">Recommended: 250×100px (PNG / JPG)</p>
                  </>
                )}
                <input
                  type="file"
                  accept="image/png,image/jpeg"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleLogoFile(file);
                  }}
                />
              </label>
            </div>
            <Button className="w-full mt-2" size="sm" onClick={saveBranding} disabled={isSavingBranding}>
              <Save className="h-3.5 w-3.5 mr-1.5" />
              Save Branding
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* ========== RIGHT COLUMN ========== */}
      <div className="space-y-6">
        {/* Card C: Holiday Calendar */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <CalendarDays className="h-4 w-4 text-primary" />
              Company Holiday Calendar
            </CardTitle>
            <CardDescription>Mark festival/public holidays to prevent absent penalties.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex gap-2">
              <Popover open={datePickerOpen} onOpenChange={setDatePickerOpen}>
                <PopoverTrigger asChild>
                  <Button
                    variant="outline"
                    className={cn(
                      "h-9 w-[130px] justify-start text-left text-sm font-normal shrink-0",
                      !holidayDate && "text-muted-foreground"
                    )}
                  >
                    <CalendarDays className="h-3.5 w-3.5 mr-1.5" />
                    {holidayDate ? format(holidayDate, "dd MMM") : "Pick date"}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-auto p-0" align="start">
                  <Calendar
                    mode="single"
                    selected={holidayDate}
                    onSelect={(d) => {
                      setHolidayDate(d);
                      setDatePickerOpen(false);
                    }}
                    className={cn("p-3 pointer-events-auto")}
                  />
                </PopoverContent>
              </Popover>
              <Input
                placeholder="Holiday name..."
                value={holidayName}
                onChange={(e) => setHolidayName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && addHoliday()}
                className="h-9 text-sm"
              />
              <Button size="sm" variant="outline" onClick={addHoliday} className="shrink-0" disabled={!holidayDate || !holidayName.trim()}>
                <Plus className="h-3.5 w-3.5" />
              </Button>
            </div>
            <div className="flex flex-wrap gap-2">
              {sortedHolidays.map((h) => (
                <Badge key={h.id} variant="secondary" className="pl-2 pr-1 py-1 text-xs gap-1.5">
                  <span className="text-muted-foreground">🗓️ {format(h.date, "dd MMM")}</span>
                  <span className="font-medium">–</span>
                  <span>{h.name}</span>
                  <button
                    onClick={() => removeHoliday(h)}
                    className="ml-0.5 rounded-full p-0.5 hover:bg-foreground/10 transition-colors"
                  >
                    <X className="h-2.5 w-2.5" />
                  </button>
                </Badge>
              ))}
              {sortedHolidays.length === 0 && (
                <p className="text-xs text-muted-foreground py-2">No holidays added yet.</p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Card D: Designations */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Designations</CardTitle>
            <CardDescription>Manage roles available for employee registration.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex gap-2">
              <Input
                placeholder="Add new designation..."
                value={newDesignation}
                onChange={(e) => setNewDesignation(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && addDesignation()}
                className="h-9 text-sm"
              />
              <Button size="sm" variant="outline" onClick={addDesignation} className="shrink-0">
                <Plus className="h-3.5 w-3.5" />
              </Button>
            </div>
            <div className="flex flex-wrap gap-2">
              {designations.map((d) => (
                <Badge key={d} variant="secondary" className="pl-2.5 pr-1 py-1 text-xs gap-1">
                  {d}
                  <button
                    onClick={() => removeDesignation(d)}
                    className="ml-0.5 rounded-full p-0.5 hover:bg-foreground/10 transition-colors"
                  >
                    <X className="h-2.5 w-2.5" />
                  </button>
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Card E: Departments */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Departments</CardTitle>
            <CardDescription>Manage departments for grouping employees.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex gap-2">
              <Input
                placeholder="Add new department..."
                value={newDepartment}
                onChange={(e) => setNewDepartment(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && addDepartment()}
                className="h-9 text-sm"
              />
              <Button size="sm" variant="outline" onClick={addDepartment} className="shrink-0">
                <Plus className="h-3.5 w-3.5" />
              </Button>
            </div>
            <div className="flex flex-wrap gap-2">
              {departments.map((d) => (
                <Badge key={d} variant="secondary" className="pl-2.5 pr-1 py-1 text-xs gap-1">
                  {d}
                  <button
                    onClick={() => removeDepartment(d)}
                    className="ml-0.5 rounded-full p-0.5 hover:bg-foreground/10 transition-colors"
                  >
                    <X className="h-2.5 w-2.5" />
                  </button>
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
