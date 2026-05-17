import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BrandingProvider, useBranding } from "./BrandingContext";

const SETTINGS_RESPONSE = {
  id: 1,
  company_name: "Persistent Brand Pvt Ltd",
  address: "123 Payroll Street\nMumbai",
  phone: null,
  email: null,
  tax_id: null,
  timezone: "Asia/Kolkata",
  currency: "INR",
  shift_start_time: "09:00:00",
  shift_end_time: "18:00:00",
  standard_work_hours: "8.00",
  grace_period_minutes: 10,
  overtime_multiplier: "1.00",
  working_days_per_month: "26.00",
  payroll_cycle: "monthly",
  payroll_day: 1,
  annual_paid_leaves: "12.00",
  monthly_leave_accrual: "1.00",
  unused_leave_action: "carry_forward",
  default_leave_balance: "0.00",
  late_penalty_per_minute: "0.00",
  logo_url: "/uploads/logos/company-logo.png",
  logo_content_type: "image/png",
  logo_updated_at: "2026-05-17T08:30:00Z",
  created_at: "2026-05-17T08:00:00Z",
  updated_at: "2026-05-17T08:30:00Z",
};

function BrandingProbe() {
  const { companyName, companyAddressLines, logoUrl } = useBranding();
  return (
    <div>
      <span data-testid="company-name">{companyName}</span>
      <span data-testid="address-lines">{companyAddressLines.join("|")}</span>
      <span data-testid="logo-url">{logoUrl}</span>
    </div>
  );
}

describe("BrandingProvider", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("loads branding once and exposes a cache-busted logo URL", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(SETTINGS_RESPONSE), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    render(
      <BrandingProvider>
        <BrandingProbe />
      </BrandingProvider>
    );

    await waitFor(() => expect(screen.getByTestId("company-name")).toHaveTextContent("Persistent Brand Pvt Ltd"));
    expect(screen.getByTestId("address-lines")).toHaveTextContent("123 Payroll Street|Mumbai");
    expect(screen.getByTestId("logo-url").textContent).toContain("/uploads/logos/company-logo.png?v=");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/settings/");
  });
});

