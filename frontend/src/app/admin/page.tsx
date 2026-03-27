"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Plus, Users, Key, ScrollText, Pencil } from "lucide-react";

interface UserItem {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

interface AuditItem {
  id: string;
  event_type: string;
  user_id: string | null;
  target_user_id: string | null;
  email: string | null;
  ip_address: string | null;
  detail: string | null;
  created_at: string;
}

interface AuditPage {
  items: AuditItem[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

const EVENT_BADGE: Record<string, "default" | "destructive" | "secondary" | "outline"> = {
  login_success: "default",
  login_failed: "destructive",
  user_created: "secondary",
  user_updated: "secondary",
  password_changed: "outline",
};

export default function AdminPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [tab, setTab] = useState<"users" | "password" | "audit">("users");

  useEffect(() => {
    if (user && user.role !== "admin") router.replace("/dashboard");
  }, [user, router]);

  if (!user || user.role !== "admin") return null;

  return (
    <AppShell>
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Admin Panel</h1>
        <div className="flex gap-2">
          <Button
            variant={tab === "users" ? "default" : "outline"}
            size="sm"
            onClick={() => setTab("users")}
          >
            <Users className="mr-2 h-4 w-4" />
            Users
          </Button>
          <Button
            variant={tab === "password" ? "default" : "outline"}
            size="sm"
            onClick={() => setTab("password")}
          >
            <Key className="mr-2 h-4 w-4" />
            Password
          </Button>
          <Button
            variant={tab === "audit" ? "default" : "outline"}
            size="sm"
            onClick={() => setTab("audit")}
          >
            <ScrollText className="mr-2 h-4 w-4" />
            Audit Log
          </Button>
        </div>

        {tab === "users" && <UsersTab />}
        {tab === "password" && <PasswordTab />}
        {tab === "audit" && <AuditTab />}
      </div>
    </AppShell>
  );
}

/* ------------------------------------------------------------------ */
/*  Users Tab                                                          */
/* ------------------------------------------------------------------ */

function UsersTab() {
  const [users, setUsers] = useState<UserItem[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [editUser, setEditUser] = useState<UserItem | null>(null);
  const [form, setForm] = useState({ email: "", full_name: "", password: "", role: "user" });
  const [editForm, setEditForm] = useState({ full_name: "", role: "", is_active: true });
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    apiFetch<UserItem[]>("/api/auth/users").then(setUsers).catch(() => {});
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await apiFetch("/api/auth/users", { method: "POST", body: JSON.stringify(form) });
      setShowCreate(false);
      setForm({ email: "", full_name: "", password: "", role: "user" });
      load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create user");
    }
  }

  async function handleEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!editUser) return;
    setError(null);
    try {
      await apiFetch(`/api/auth/users/${editUser.id}`, {
        method: "PATCH",
        body: JSON.stringify(editForm),
      });
      setEditUser(null);
      load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to update user");
    }
  }

  function openEdit(u: UserItem) {
    setEditForm({ full_name: u.full_name, role: u.role, is_active: u.is_active });
    setEditUser(u);
    setError(null);
  }

  return (
    <>
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Users ({users.length})</h2>
        <Button size="sm" onClick={() => { setShowCreate(true); setError(null); }}>
          <Plus className="mr-2 h-4 w-4" />
          Invite User
        </Button>
      </div>

      <Card>
        <CardContent className="p-0">
          <table className="w-full">
            <thead>
              <tr className="border-b text-left text-sm text-muted-foreground">
                <th className="p-4">Name</th>
                <th className="p-4">Email</th>
                <th className="p-4">Role</th>
                <th className="p-4">Status</th>
                <th className="p-4">Joined</th>
                <th className="p-4"></th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-b hover:bg-muted/50">
                  <td className="p-4 font-medium">{u.full_name}</td>
                  <td className="p-4 text-sm text-muted-foreground">{u.email}</td>
                  <td className="p-4">
                    <Badge variant="secondary" className="capitalize">{u.role}</Badge>
                  </td>
                  <td className="p-4">
                    <Badge variant={u.is_active ? "default" : "destructive"}>
                      {u.is_active ? "Active" : "Inactive"}
                    </Badge>
                  </td>
                  <td className="p-4 text-sm text-muted-foreground">
                    {new Date(u.created_at).toLocaleDateString()}
                  </td>
                  <td className="p-4">
                    <Button variant="ghost" size="icon" onClick={() => openEdit(u)}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {/* Create User Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Invite User</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleCreate} className="space-y-4">
            {error && <p className="text-sm text-destructive">{error}</p>}
            <div className="space-y-2">
              <Label>Email</Label>
              <Input
                type="email"
                required
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label>Full Name</Label>
              <Input
                required
                value={form.full_name}
                onChange={(e) => setForm({ ...form, full_name: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label>Password</Label>
              <Input
                type="password"
                required
                minLength={10}
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
              />
              <p className="text-xs text-muted-foreground">Min 10 chars, must include uppercase + digit</p>
            </div>
            <div className="space-y-2">
              <Label>Role</Label>
              <Select value={form.role} onValueChange={(v) => setForm({ ...form, role: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="admin">Admin</SelectItem>
                  <SelectItem value="manager">Manager</SelectItem>
                  <SelectItem value="user">User</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button type="submit" className="w-full">Create User</Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Edit User Dialog */}
      <Dialog open={!!editUser} onOpenChange={(open) => { if (!open) setEditUser(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit User — {editUser?.email}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleEdit} className="space-y-4">
            {error && <p className="text-sm text-destructive">{error}</p>}
            <div className="space-y-2">
              <Label>Full Name</Label>
              <Input
                required
                value={editForm.full_name}
                onChange={(e) => setEditForm({ ...editForm, full_name: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label>Role</Label>
              <Select value={editForm.role} onValueChange={(v) => setEditForm({ ...editForm, role: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="admin">Admin</SelectItem>
                  <SelectItem value="manager">Manager</SelectItem>
                  <SelectItem value="user">User</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="is_active"
                checked={editForm.is_active}
                onChange={(e) => setEditForm({ ...editForm, is_active: e.target.checked })}
                className="h-4 w-4 rounded border-gray-300"
              />
              <Label htmlFor="is_active">Active</Label>
            </div>
            <Button type="submit" className="w-full">Save Changes</Button>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  Password Tab                                                       */
/* ------------------------------------------------------------------ */

function PasswordTab() {
  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [msg, setMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    if (newPw !== confirmPw) {
      setMsg({ type: "error", text: "Passwords do not match" });
      return;
    }
    if (newPw.length < 10) {
      setMsg({ type: "error", text: "Password must be at least 10 characters" });
      return;
    }
    if (!/[A-Z]/.test(newPw)) {
      setMsg({ type: "error", text: "Password must contain an uppercase letter" });
      return;
    }
    if (!/\d/.test(newPw)) {
      setMsg({ type: "error", text: "Password must contain a digit" });
      return;
    }
    try {
      await apiFetch("/api/auth/me/password", {
        method: "PATCH",
        body: JSON.stringify({ current_password: currentPw, new_password: newPw }),
      });
      setMsg({ type: "success", text: "Password changed successfully" });
      setCurrentPw("");
      setNewPw("");
      setConfirmPw("");
    } catch (err: unknown) {
      setMsg({ type: "error", text: err instanceof Error ? err.message : "Failed to change password" });
    }
  }

  return (
    <Card className="max-w-md">
      <CardHeader>
        <CardTitle className="text-base">Change Password</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          {msg && (
            <p className={`text-sm ${msg.type === "success" ? "text-emerald-500" : "text-destructive"}`}>
              {msg.text}
            </p>
          )}
          <div className="space-y-2">
            <Label>Current Password</Label>
            <Input type="password" required value={currentPw} onChange={(e) => setCurrentPw(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>New Password</Label>
            <Input type="password" required minLength={10} value={newPw} onChange={(e) => setNewPw(e.target.value)} />
            <p className="text-xs text-muted-foreground">Min 10 chars, must include uppercase + digit</p>
          </div>
          <div className="space-y-2">
            <Label>Confirm New Password</Label>
            <Input type="password" required value={confirmPw} onChange={(e) => setConfirmPw(e.target.value)} />
          </div>
          <Button type="submit" className="w-full">Change Password</Button>
        </form>
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/*  Audit Log Tab                                                      */
/* ------------------------------------------------------------------ */

function AuditTab() {
  const [data, setData] = useState<AuditPage | null>(null);
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState("");

  const load = useCallback(() => {
    const params = new URLSearchParams({ page: String(page), per_page: "50" });
    if (filter) params.set("event_type", filter);
    apiFetch<AuditPage>(`/api/auth/audit-log?${params}`).then(setData).catch(() => {});
  }, [page, filter]);

  useEffect(() => { load(); }, [load]);

  return (
    <>
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Audit Log</h2>
        <Select
          value={filter}
          onValueChange={(v) => { setFilter(v === "all" ? "" : v); setPage(1); }}
        >
          <SelectTrigger className="w-48">
            <SelectValue placeholder="All events" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All events</SelectItem>
            <SelectItem value="login_success">Login Success</SelectItem>
            <SelectItem value="login_failed">Login Failed</SelectItem>
            <SelectItem value="user_created">User Created</SelectItem>
            <SelectItem value="user_updated">User Updated</SelectItem>
            <SelectItem value="password_changed">Password Changed</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <Card>
        <CardContent className="p-0">
          <table className="w-full">
            <thead>
              <tr className="border-b text-left text-sm text-muted-foreground">
                <th className="p-4">Time</th>
                <th className="p-4">Event</th>
                <th className="p-4">Email</th>
                <th className="p-4">IP Address</th>
                <th className="p-4">Detail</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((item) => (
                <tr key={item.id} className="border-b hover:bg-muted/50">
                  <td className="p-4 text-sm text-muted-foreground whitespace-nowrap">
                    {new Date(item.created_at).toLocaleString()}
                  </td>
                  <td className="p-4">
                    <Badge variant={EVENT_BADGE[item.event_type] ?? "outline"} className="whitespace-nowrap">
                      {item.event_type.replace(/_/g, " ")}
                    </Badge>
                  </td>
                  <td className="p-4 text-sm">{item.email ?? "—"}</td>
                  <td className="p-4 text-sm font-mono text-muted-foreground">{item.ip_address ?? "—"}</td>
                  <td className="p-4 text-sm text-muted-foreground">{item.detail ?? "—"}</td>
                </tr>
              ))}
              {data && data.items.length === 0 && (
                <tr>
                  <td colSpan={5} className="p-8 text-center text-muted-foreground">No audit entries found</td>
                </tr>
              )}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {data && data.pages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Page {data.page} of {data.pages} ({data.total} entries)
          </p>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              Previous
            </Button>
            <Button variant="outline" size="sm" disabled={page >= data.pages} onClick={() => setPage(page + 1)}>
              Next
            </Button>
          </div>
        </div>
      )}
    </>
  );
}
