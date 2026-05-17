import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  ApiError,
  apiErrorMessage,
  readCompanyProfile,
  resolveApiAssetUrl,
  updateCompanyProfile,
  uploadCompanyProfileLogo,
  type BackendCompanyProfile,
} from "@/lib/api";

interface BrandingContextValue {
  settings: BackendCompanyProfile | null;
  companyName: string;
  companyAddress: string;
  companyAddressLines: string[];
  logoUrl: string | null;
  isLoading: boolean;
  errorMessage: string | null;
  refreshBranding: () => Promise<BackendCompanyProfile | null>;
  saveBranding: (payload: { company_name: string; phone_number?: string | null; registered_address: string | null }) => Promise<BackendCompanyProfile>;
  uploadLogo: (file: File) => Promise<BackendCompanyProfile>;
}

const DEFAULT_COMPANY_NAME = "Your Company";
const BrandingContext = createContext<BrandingContextValue | null>(null);

function brandingMessage(error: unknown): string {
  if (error instanceof ApiError && ["network_error", "request_timeout"].includes(error.code ?? "")) {
    return "Backend unavailable";
  }
  return apiErrorMessage(error);
}

function logBrandingError(action: string, error: unknown, level: "error" | "warn" = "error"): void {
  console[level](action, {
    message: brandingMessage(error),
    error,
  });
}

export function logBrandingAssetMissing(url: string | null): void {
  console.error("Static asset missing", { url });
}

function versionedLogoUrl(settings: BackendCompanyProfile | null): string | null {
  const resolved = resolveApiAssetUrl(settings?.logo_url);
  if (!resolved || !settings?.logo_updated_at) return resolved;
  const separator = resolved.includes("?") ? "&" : "?";
  return `${resolved}${separator}v=${encodeURIComponent(settings.logo_updated_at)}`;
}

export function BrandingProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<BackendCompanyProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const refreshBranding = useCallback(async () => {
    setIsLoading(true);
    try {
      const nextSettings = await readCompanyProfile();
      setSettings(nextSettings);
      setErrorMessage(null);
      return nextSettings;
    } catch (error) {
      logBrandingError("Backend unavailable while loading branding", error, "warn");
      setErrorMessage(brandingMessage(error));
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshBranding();
  }, [refreshBranding]);

  const saveBranding = useCallback(async (payload: { company_name: string; phone_number?: string | null; registered_address: string | null }) => {
    try {
      const nextSettings = await updateCompanyProfile(payload);
      setSettings(nextSettings);
      setErrorMessage(null);
      return nextSettings;
    } catch (error) {
      logBrandingError("Branding save failed", error);
      setErrorMessage(brandingMessage(error));
      throw error;
    }
  }, []);

  const uploadLogo = useCallback(async (file: File) => {
    try {
      const nextSettings = await uploadCompanyProfileLogo(file);
      setSettings(nextSettings);
      setErrorMessage(null);
      return nextSettings;
    } catch (error) {
      logBrandingError("Logo upload failed", error);
      setErrorMessage(brandingMessage(error));
      throw error;
    }
  }, []);

  const value = useMemo<BrandingContextValue>(() => {
    const companyName = settings?.company_name?.trim() || DEFAULT_COMPANY_NAME;
    const companyAddress = settings?.registered_address ?? "";

    return {
      settings,
      companyName,
      companyAddress,
      companyAddressLines: companyAddress.split(/\r?\n/).filter((line) => line.trim()),
      logoUrl: versionedLogoUrl(settings),
      isLoading,
      errorMessage,
      refreshBranding,
      saveBranding,
      uploadLogo,
    };
  }, [errorMessage, isLoading, refreshBranding, saveBranding, settings, uploadLogo]);

  return (
    <BrandingContext.Provider value={value}>
      {children}
    </BrandingContext.Provider>
  );
}

export function useBranding() {
  const ctx = useContext(BrandingContext);
  if (!ctx) throw new Error("useBranding must be used within BrandingProvider");
  return ctx;
}
