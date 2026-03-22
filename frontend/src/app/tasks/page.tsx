"use client";

import { useEffect, useState, useCallback } from "react";
import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import { Plus, Trash2, CheckCircle2, Circle, Clock } from "lucide-react";

interface Task {
  id: string;
  title: string;
  description: string | null;
  status: string;
  due_date: string | null;
  assigned_to: string | null;
  created_at: string;
}

interface PaginatedTasks {
  items: Task[];
  total: number;
  page: number;
  pages: number;
}

const statusConfig: Record<string, { label: string; icon: typeof Circle; color: string }> = {
  todo: { label: "To Do", icon: Circle, color: "text-muted-foreground" },
  in_progress: { label: "In Progress", icon: Clock, color: "text-blue-600" },
  done: { label: "Done", icon: CheckCircle2, color: "text-green-600" },
};

export default function TasksPage() {
  const { token } = useAuth();
  const [data, setData] = useState<PaginatedTasks | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState({ title: "", description: "", due_date: "" });

  const load = useCallback(() => {
    if (!token) return;
    apiFetch<PaginatedTasks>(`/api/tasks?page=${page}&status=${statusFilter}`, { token }).then(setData);
  }, [token, page, statusFilter]);

  useEffect(() => { load(); }, [load]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    const body: Record<string, string> = { title: form.title };
    if (form.description) body.description = form.description;
    if (form.due_date) body.due_date = new Date(form.due_date).toISOString();
    await apiFetch("/api/tasks", { method: "POST", body: JSON.stringify(body), token: token! });
    setDialogOpen(false);
    setForm({ title: "", description: "", due_date: "" });
    load();
  }

  async function handleStatusChange(id: string, status: string) {
    await apiFetch(`/api/tasks/${id}`, { method: "PATCH", body: JSON.stringify({ status }), token: token! });
    load();
  }

  async function handleDelete(id: string) {
    await apiFetch(`/api/tasks/${id}`, { method: "DELETE", token: token! });
    load();
  }

  return (
    <AppShell>
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-3xl font-bold">Tasks</h2>
          <div className="flex items-center gap-2">
            <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v === "all" ? "" : v); setPage(1); }}>
              <SelectTrigger className="w-[150px]">
                <SelectValue placeholder="All statuses" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                <SelectItem value="todo">To Do</SelectItem>
                <SelectItem value="in_progress">In Progress</SelectItem>
                <SelectItem value="done">Done</SelectItem>
              </SelectContent>
            </Select>
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button size="sm"><Plus className="mr-1 h-4 w-4" /> Add Task</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader><DialogTitle>New Task</DialogTitle></DialogHeader>
                <form onSubmit={handleCreate} className="space-y-4">
                  <div className="space-y-2">
                    <Label>Title</Label>
                    <Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required />
                  </div>
                  <div className="space-y-2">
                    <Label>Description</Label>
                    <Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
                  </div>
                  <div className="space-y-2">
                    <Label>Due Date</Label>
                    <Input type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
                  </div>
                  <Button type="submit" className="w-full">Create Task</Button>
                </form>
              </DialogContent>
            </Dialog>
          </div>
        </div>

        <div className="space-y-2">
          {data?.items.map((task) => {
            const config = statusConfig[task.status] || statusConfig.todo;
            const Icon = config.icon;
            return (
              <Card key={task.id}>
                <CardContent className="flex items-center gap-4 p-4">
                  <button onClick={() => {
                    const next = task.status === "todo" ? "in_progress" : task.status === "in_progress" ? "done" : "todo";
                    handleStatusChange(task.id, next);
                  }}>
                    <Icon className={`h-5 w-5 ${config.color}`} />
                  </button>
                  <div className="flex-1">
                    <p className={`font-medium ${task.status === "done" ? "line-through text-muted-foreground" : ""}`}>
                      {task.title}
                    </p>
                    {task.description && <p className="text-sm text-muted-foreground">{task.description}</p>}
                  </div>
                  {task.due_date && (
                    <span className="text-xs text-muted-foreground">
                      Due {new Date(task.due_date).toLocaleDateString()}
                    </span>
                  )}
                  <Badge variant="secondary" className="capitalize">{config.label}</Badge>
                  <Button variant="ghost" size="icon" onClick={() => handleDelete(task.id)}>
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </CardContent>
              </Card>
            );
          })}
          {data?.items.length === 0 && (
            <Card>
              <CardContent className="p-8 text-center text-muted-foreground">No tasks found</CardContent>
            </Card>
          )}
        </div>

        {data && data.pages > 1 && (
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">{data.total} tasks total</p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
              <Button variant="outline" size="sm" disabled={page >= data.pages} onClick={() => setPage(page + 1)}>Next</Button>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
