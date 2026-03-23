

## Payroll OS — Stage 1A: Daily Attendance Roster

### What We're Building

A complete Daily Log page with a Slate/Indigo enterprise theme, sidebar navigation, expandable employee cards, and live payroll math — all UI-only with mock data.

### File Plan

#### 1. Theme Update — `src/index.css`
Restyle CSS variables to a **Slate/Indigo** palette:
- `--primary`: Indigo-600 (`234 89% 74%` range)
- `--background`: Slate-50, `--foreground`: Slate-900
- Sidebar: Dark slate (`215 28% 17%`) with light text

#### 2. Global State — `src/lib/payroll-config.ts`
Export constants:
- `COMPANY_FIXED_SHIFT` (start: "09:00", end: "18:00", totalHours: 8)
- `GRACE_PERIOD_MINUTES`: 10
- `OT_MULTIPLIER`: 1.0

#### 3. Mock Data — `src/lib/mock-employees.ts`
Array of ~8 employees with: id, name, department, designation, dailyRate, monthlyBasic. Pre-seed a few with attendance entries (timeIn/timeOut/advance).

#### 4. Utility Functions — `src/lib/payroll-utils.ts`
Pure functions:
- `calculateShiftDetails(timeIn, timeOut, config)` → hours worked, OT hours, isLate, penaltyAmount
- `calculateNetEarned(dailyRate, otHours, penalty, advance)` → net for day

#### 5. Sidebar Component — `src/components/AppSidebar.tsx`
4 nav items: Daily Log (`/`), People Hub (`/people`), Payroll Engine (`/payroll`), Receipt Vault (`/receipts`). Uses Shadcn Sidebar with `collapsible="icon"`, Lucide icons (CalendarDays, Users, Calculator, FileText). Dark slate background.

#### 6. App Layout — `src/components/AppLayout.tsx`
`SidebarProvider` + `AppSidebar` + header with `SidebarTrigger` + `<Outlet/>` pattern. All pages wrapped in this layout.

#### 7. Daily Log Page — `src/pages/DailyLog.tsx` (replaces Index)
**A. Top Stats Bar** — 3 stat cards in a row:
- Total Present (emerald icon), Total Late Penalties (rose), Advances Issued (amber)
- Values auto-sum from employee state

**B. Expandable Employee Cards** — map over employees:
- **Collapsed**: Avatar circle, Name, Dept badge, Status badge (Pending=gray, Present=emerald, Late=rose)
- **Expanded** (click to toggle): Two-column grid:
  - Left: Time In / Time Out inputs (time pickers), "Standard 9–6" quick-fill button
  - Right: Advance amount input with ₹ prefix, warning if > monthlyBasic
- **Card Footer**: Live summary line: "Shift: Xh (Yh OT) | Penalty: ₹Z | Advance: ₹A | Net: ₹N"
- All math runs instantly on input change using `payroll-utils`

**Visual cues**: Emerald-500 for OT/Present badges, Rose-500 for Late/Penalty, Amber for Advance warning.

#### 8. Route Updates — `src/App.tsx`
- Wrap routes in `AppLayout`
- `/` → DailyLog
- Placeholder routes for `/people`, `/payroll`, `/receipts`

### Key UX Details
- "Standard 9-6" button fills both time fields instantly and triggers recalc
- Late tag appears immediately when Time In > 09:10
- Advance warning is a yellow alert inline, not a modal
- Cards use Shadcn Card + Collapsible for expand/collapse animation
- High whitespace, rounded-xl corners, subtle shadows — enterprise SaaS feel

