import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BrandingProvider, useBranding } from "./BrandingContext";

const SETTINGS_RESPONSE = {
  id: 1,
  company_name: "Persistent Brand Pvt Ltd",
  phone_number: "+919000000000",
  registered_address: "123 Payroll Street\nMumbai",
  logo_path: "company/logo.png",
  logo_url: "/uploads/company/logo.png",
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
    expect(screen.getByTestId("logo-url").textContent).toContain("/uploads/company/logo.png?v=");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/company/settings");
  });
});
