import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ShieldCheck, Plus, UserX } from "lucide-react";
import {
  apiErrorMessage,
  createUser,
  listUsers,
} from "@/lib/api";
import { toast } from "sonner";

interface SystemUser {
  id: string;
  name: string;
  userId: string;
  role: "Admin" | "Operator";
}

export default function Settings() {
  // User management
  const [users, setUsers] = useState<SystemUser[]>([]);
  const [newName, setNewName] = useState("");
  const [newUserId, setNewUserId] = useState("");
  const [newRole, setNewRole] = useState<"Admin" | "Operator">("Operator");
  const [newPassword, setNewPassword] = useState("");

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

      <div className="grid grid-cols-1 gap-6">
        {/* Card A: User Management */}
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
