// TODO [BACKEND]: Holiday calendar → fetch("/api/settings/holidays") GET/POST/DELETE
import { useEffect, useState, useMemo } from "react";
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
  readCompanySettings,
  resolveApiAssetUrl,
  updateCompanySettings,
  uploadCompanyLogo,
} from "@/lib/api";
import { toast } from "sonner";

interface Holiday {
  id: string;
  date: Date;
  name: string;
}

const INITIAL_HOLIDAYS: Holiday[] = [
  { id: "h1", date: new Date(2026, 7, 15), name: "Independence Day" },
  { id: "h2", date: new Date(2026, 10, 12), name: "Diwali" },
  { id: "h3", date: new Date(2026, 0, 26), name: "Republic Day" },
];

interface CompanySettingsProps {
  designations: string[];
  setDesignations: React.Dispatch<React.SetStateAction<string[]>>;
  departments: string[];
  setDepartments: React.Dispatch<React.SetStateAction<string[]>>;
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

  // Holiday Calendar
  const [holidays, setHolidays] = useState<Holiday[]>(INITIAL_HOLIDAYS);
  const [holidayDate, setHolidayDate] = useState<Date>();
  const [holidayName, setHolidayName] = useState("");
  const [datePickerOpen, setDatePickerOpen] = useState(false);

  // Branding
  const [companyName, setCompanyName] = useState("PrintWorks Pvt. Ltd.");
  const [companyAddress, setCompanyAddress] = useState("42 Industrial Area, Sector 7\nNew Delhi — 110020");
  const [logoPreview, setLogoPreview] = useState<string | null>(null);
  const [isSavingTimings, setIsSavingTimings] = useState(false);
  const [isSavingBranding, setIsSavingBranding] = useState(false);

  // Designation & Department inputs
  const [newDesignation, setNewDesignation] = useState("");
  const [newDepartment, setNewDepartment] = useState("");

  useEffect(() => {
    let cancelled = false;

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

    return () => {
      cancelled = true;
    };
  }, []);

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

  const addDesignation = () => {
    const val = newDesignation.trim();
    if (val && !designations.includes(val)) {
      setDesignations((prev) => [...prev, val]);
      setNewDesignation("");
    }
  };

  const addDepartment = () => {
    const val = newDepartment.trim();
    if (val && !departments.includes(val)) {
      setDepartments((prev) => [...prev, val]);
      setNewDepartment("");
    }
  };

  const addHoliday = () => {
    if (!holidayDate || !holidayName.trim()) return;
    setHolidays((prev) => [
      ...prev,
      { id: `h${Date.now()}`, date: holidayDate, name: holidayName.trim() },
    ]);
    setHolidayDate(undefined);
    setHolidayName("");
  };

  const saveMasterTimings = async () => {
    setIsSavingTimings(true);
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
            <Button className="w-full mt-2" size="sm" onClick={() => toast.info("Leave policy storage is not available on the backend yet.")}>
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
                    onClick={() => setHolidays((prev) => prev.filter((x) => x.id !== h.id))}
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
                    onClick={() => setDesignations((prev) => prev.filter((x) => x !== d))}
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
                    onClick={() => setDepartments((prev) => prev.filter((x) => x !== d))}
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
