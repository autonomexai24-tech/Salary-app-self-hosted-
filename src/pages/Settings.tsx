import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Building2, ImageIcon, Save, ShieldCheck, Plus, UserX } from "lucide-react";
import {
  ApiError,
  apiErrorMessage,
  createUser,
  listUsers,
} from "@/lib/api";
import { logBrandingAssetMissing, useBranding } from "@/contexts/BrandingContext";
import { toast } from "sonner";

interface SystemUser {
  id: string;
  name: string;
  userId: string;
  role: "Admin" | "Operator";
}

function brandingErrorDescription(error: unknown): string {
  if (error instanceof ApiError && ["network_error", "request_timeout"].includes(error.code ?? "")) {
    return "Backend unavailable";
  }
  return apiErrorMessage(error);
}

export default function Settings() {
  const {
    settings: brandingSettings,
    logoUrl,
    errorMessage: brandingLoadError,
    saveBranding: saveCentralBranding,
    uploadLogo,
  } = useBranding();

  // Branding
  const [companyName, setCompanyName] = useState("");
  const [companyAddress, setCompanyAddress] = useState("");
  const [localLogoPreview, setLocalLogoPreview] = useState<string | null>(null);
  const [isSavingBranding, setIsSavingBranding] = useState(false);

  // User management
  const [users, setUsers] = useState<SystemUser[]>([]);
  const [newName, setNewName] = useState("");
  const [newUserId, setNewUserId] = useState("");
  const [newRole, setNewRole] = useState<"Admin" | "Operator">("Operator");
  const [newPassword, setNewPassword] = useState("");

  useEffect(() => {
    if (!brandingSettings) return;
    setCompanyName(brandingSettings.company_name);
    setCompanyAddress(brandingSettings.address ?? "");
  }, [brandingSettings]);

  useEffect(() => {
    if (!brandingLoadError || brandingSettings) return;
    toast.error("Backend unavailable", {
      description: brandingLoadError,
    });
  }, [brandingLoadError, brandingSettings]);

  useEffect(() => {
    let cancelled = false;

    listUsers()
      .then((records) => {
        if (cancelled) return;
        setUsers(records.map((user) => ({
          id: user.id,
          name: user.full_name,
          userId: user.email,
          role: user.role === "admin" ? "Admin" : "Operator",
        })));
      })
      .catch((error) => {
        if (cancelled) return;
        toast.error("Could not load users", {
          description: apiErrorMessage(error),
        });
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const saveBranding = async () => {
    const normalizedName = companyName.trim();
    if (!normalizedName) {
      toast.error("Branding save failed", {
        description: "Registered company name is required.",
      });
      return;
    }

    setIsSavingBranding(true);
    try {
      const settings = await saveCentralBranding({
        company_name: normalizedName,
        address: companyAddress.trim() || null,
      });
      setCompanyName(settings.company_name);
      setCompanyAddress(settings.address ?? "");
      toast.success("Company branding saved");
    } catch (error) {
      toast.error("Branding save failed", {
        description: brandingErrorDescription(error),
      });
    } finally {
      setIsSavingBranding(false);
    }
  };

  const handleLogoFile = async (file: File) => {
    const localPreviewUrl = URL.createObjectURL(file);
    setLocalLogoPreview(localPreviewUrl);
    try {
      await uploadLogo(file);
      setLocalLogoPreview(null);
      toast.success("Company logo uploaded");
    } catch (error) {
      setLocalLogoPreview(null);
      toast.error("Logo upload failed", {
        description: brandingErrorDescription(error),
      });
    } finally {
      URL.revokeObjectURL(localPreviewUrl);
    }
  };

  const logoPreview = localLogoPreview ?? logoUrl;

  const addUser = async () => {
    if (!newName.trim() || !newUserId.trim() || !newPassword) return;
    if (newPassword.length < 10) {
      toast.error("Password must be at least 10 characters.");
      return;
    }
    try {
      const created = await createUser({
        fullName: newName.trim(),
        email: newUserId.trim(),
        password: newPassword,
        role: newRole === "Admin" ? "admin" : "staff",
      });
      setUsers(prev => [...prev, {
        id: created.id,
        name: created.full_name,
        userId: created.email,
        role: created.role === "admin" ? "Admin" : "Operator",
      }]);
      setNewName("");
      setNewUserId("");
      setNewPassword("");
      toast.success("User created");
    } catch (error) {
      toast.error("Could not create user", {
        description: apiErrorMessage(error),
      });
    }
  };

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">Settings</h1>
        <p className="text-sm text-muted-foreground mt-1">Global application configuration and user management.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Card A: Company Branding */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Building2 className="h-4 w-4 text-primary" />
              Company Branding
            </CardTitle>
            <CardDescription>This logo will appear on the Login Screen and all generated Payslips.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label className="text-xs">Registered Company Name</Label>
              <Input value={companyName} onChange={(e) => setCompanyName(e.target.value)} className="h-9 text-sm" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Registered Address</Label>
              <Textarea value={companyAddress} onChange={(e) => setCompanyAddress(e.target.value)} className="text-sm min-h-[72px] resize-none" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Company Logo</Label>
              <label className="flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-muted-foreground/25 bg-muted/30 p-6 cursor-pointer hover:border-primary/40 hover:bg-primary/5 transition-colors">
                {logoPreview ? (
                  <img src={logoPreview} alt="Company logo" className="max-h-16 max-w-[200px] object-contain" onError={() => logBrandingAssetMissing(logoPreview)} />
                ) : (
                  <>
                    <ImageIcon className="h-8 w-8 text-muted-foreground/50" />
                    <p className="text-xs font-medium text-muted-foreground">Click or Drag to Upload Logo</p>
                    <p className="text-[10px] text-muted-foreground/70">Recommended: 250×100px (PNG / JPG)</p>
                  </>
                )}
                <input type="file" accept="image/png,image/jpeg" className="hidden" onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleLogoFile(file);
                }} />
              </label>
            </div>
            <Button className="w-full mt-2" size="sm" onClick={saveBranding} disabled={isSavingBranding}>
              <Save className="h-3.5 w-3.5 mr-1.5" />
              Save Branding
            </Button>
          </CardContent>
        </Card>

        {/* Card B: User Management */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-primary" />
              System Users & Roles
            </CardTitle>
            <CardDescription>Create login IDs for your staff.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Add user row */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs">Name</Label>
                <Input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Full name" className="h-9 text-sm" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">User ID</Label>
                <Input value={newUserId} onChange={(e) => setNewUserId(e.target.value)} placeholder="login@email.com" className="h-9 text-sm" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Role</Label>
                <Select value={newRole} onValueChange={(v) => setNewRole(v as "Admin" | "Operator")}>
                  <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Admin">Admin</SelectItem>
                    <SelectItem value="Operator">Operator</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Password</Label>
                <Input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} placeholder="Minimum 10 characters" className="h-9 text-sm" minLength={10} />
              </div>
            </div>
            <Button size="sm" variant="outline" className="w-full" onClick={addUser} disabled={!newName.trim() || !newUserId.trim() || newPassword.length < 10}>
              <Plus className="h-3.5 w-3.5 mr-1.5" />
              Add User
            </Button>

            {/* Active users */}
            <div className="space-y-2 pt-2">
              <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-medium">Active Users</p>
              {users.map((u) => (
                <div key={u.id} className="flex items-center justify-between rounded-lg border px-4 py-3">
                  <div className="flex items-center gap-3">
                    <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center text-xs font-semibold text-primary">
                      {u.name.split(" ").map(w => w[0]).join("")}
                    </div>
                    <div>
                      <p className="text-sm font-medium text-foreground">{u.name}</p>
                      <p className="text-xs text-muted-foreground">{u.userId}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={u.role === "Admin" ? "default" : "secondary"} className="text-[10px]">{u.role}</Badge>
                    <Button variant="ghost" size="sm" className="h-7 text-xs text-destructive hover:text-destructive hover:bg-destructive/10" onClick={() => toast.info("User revoke is not available on the backend yet.")}>
                      <UserX className="h-3 w-3 mr-1" />
                      Revoke
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
