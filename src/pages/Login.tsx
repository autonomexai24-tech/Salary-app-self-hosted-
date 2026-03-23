import { useState } from "react";
// TODO [BACKEND]: Replace mock login with fetch("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) })
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Lock, LogIn, Shield, User } from "lucide-react";
import { useAuth, type AppRole } from "@/contexts/AuthContext";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const handleMockLogin = (role: AppRole) => {
    login(role);
    navigate("/");
  };

  return (
    <div className="min-h-screen flex">
      {/* Left: Branding panel */}
      <div className="hidden lg:flex lg:w-[45%] bg-[hsl(226,40%,14%)] text-white flex-col justify-between p-12 relative overflow-hidden">
        {/* Subtle grid pattern */}
        <div className="absolute inset-0 opacity-[0.04]" style={{ backgroundImage: "radial-gradient(circle, white 1px, transparent 1px)", backgroundSize: "24px 24px" }} />

        <div className="relative z-10">
          <div className="flex items-center gap-3 mb-2">
            <div className="h-10 w-10 rounded-xl bg-white/10 border border-white/10 flex items-center justify-center font-black text-lg">
              S
            </div>
            <span className="text-lg font-bold tracking-tight">Salary & Advance Tracker</span>
          </div>
        </div>

        <div className="relative z-10 space-y-4">
          <h1 className="text-[42px] font-black leading-[1.05] tracking-tight">
            Salary &<br />
            Advance Tracker.
          </h1>
          <p className="text-sm text-white/50 max-w-sm leading-relaxed">
            Smart attendance, automated advances, and one-click salary receipts.
          </p>
        </div>

        <div className="relative z-10 flex items-center gap-2 text-white/30 text-xs">
          <Shield className="h-3.5 w-3.5" />
          <span>256-bit Encrypted · SOC 2 Compliant</span>
        </div>
      </div>

      {/* Right: Login form */}
      <div className="flex-1 flex items-center justify-center bg-muted/30 p-6">
        <div className="w-full max-w-[400px] space-y-8">
          {/* Mobile branding */}
          <div className="lg:hidden flex items-center gap-3 justify-center mb-4">
            <div className="h-9 w-9 rounded-lg bg-primary flex items-center justify-center text-primary-foreground font-bold text-sm">S</div>
            <span className="text-lg font-bold text-foreground tracking-tight">Salary & Advance Tracker</span>
          </div>

          <Card className="shadow-xl border-border/50">
            <CardContent className="p-8 space-y-6">
              <div className="space-y-1">
                <h2 className="text-xl font-bold text-foreground tracking-tight">Welcome Back</h2>
                <p className="text-sm text-muted-foreground">Enter your credentials to access the dashboard.</p>
              </div>

              <div className="space-y-4">
                <div className="space-y-1.5">
                  <Label className="text-xs font-medium">User ID / Email</Label>
                  <div className="relative">
                    <User className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input
                      placeholder="admin@printworks.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="pl-9 h-10 text-sm"
                    />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs font-medium">Password</Label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input
                      type="password"
                      placeholder="••••••••"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="pl-9 h-10 text-sm"
                    />
                  </div>
                </div>

                <Button className="w-full h-10 text-sm gap-2 font-semibold" onClick={() => handleMockLogin("admin")}>
                  <LogIn className="h-4 w-4" />
                  Secure Login
                </Button>
              </div>

              <Separator />

              {/* Mock login buttons */}
              <div className="space-y-2">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-medium text-center">Prototype Testing</p>
                <div className="grid grid-cols-2 gap-2">
                  <Button variant="ghost" size="sm" className="h-9 text-xs border border-dashed border-border" onClick={() => handleMockLogin("admin")}>
                    <Shield className="h-3 w-3 mr-1.5 text-primary" />
                    Login as Admin
                  </Button>
                  <Button variant="ghost" size="sm" className="h-9 text-xs border border-dashed border-border" onClick={() => handleMockLogin("operator")}>
                    <User className="h-3 w-3 mr-1.5 text-muted-foreground" />
                    Login as Operator
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          <p className="text-[10px] text-muted-foreground text-center">
            © 2026 Salary & Advance Tracker. All rights reserved.
          </p>
        </div>
      </div>
    </div>
  );
}
