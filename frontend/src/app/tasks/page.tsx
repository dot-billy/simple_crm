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
import { apiFetch } from "@/lib/api";
import { Plus, Trash2, CheckCircle2, Circle, Clock, CheckSquare } from "lucide-react";
import { EmptyState } from "@/components/empty-state";
import { BulkActionBar } from "@/components/bulk-action-bar";
import { SavedViewsPicker } from "@/components/saved-views-picker";

interface Task {
  id: string;
  title: string;
  description: string | null;
  status: string;
  priority?: string;
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
  const [data, setData] = useState<PaginatedTasks | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState({ title: "", description: "", due_date: "", recurrence_rule: "none", reminder_minutes_before: "", priority: "medium" });
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const load = useCallback(() => {
    apiFetch<PaginatedTasks>(`/api/tasks?page=${page}&status=${statusFilter}`).then(setData);
  }, [page, statusFilter]);

  useEffect(() => { load(); }, [load]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    const body: Record<string, string | number> = { title: form.title };
    if (form.description) body.description = form.description;
    if (form.due_date) body.due_date = new Date(form.due_date).toISOString();
    if (form.recurrence_rule && form.recurrence_rule !== "none") body.recurrence_rule = form.recurrence_rule;
    if (form.reminder_minutes_before) body.reminder_minutes_before = parseInt(form.reminder_minutes_before, 10);
    if (form.priority && form.priority !== "medium") body.priority = form.priority;
    await apiFetch("/api/tasks", { method: "POST", body: JSON.stringify(body) });
    setDialogOpen(false);
    setForm({ title: "", description: "", due_date: "", recurrence_rule: "none", reminder_minutes_before: "", priority: "medium" });
    load();
  }

  async function handleStatusChange(id: string, status: string) {
    await apiFetch(`/api/tasks/${id}`, { method: "PATCH", body: JSON.stringify({ status }) });
    load();
  }

  async function handleDelete(id: string) {
    await apiFetch(`/api/tasks/${id}`, { method: "DELETE" });
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
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label>Priority</Label>
                      <Select value={form.priority} onValueChange={(v) => setForm({ ...form, priority: v })}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="low">Low</SelectItem>
                          <SelectItem value="medium">Medium</SelectItem>
                          <SelectItem value="high">High</SelectItem>
                          <SelectItem value="urgent">Urgent</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label>Recurrence</Label>
                      <Select value={form.recurrence_rule} onValueChange={(v) => setForm({ ...form, recurrence_rule: v })}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="none">None</SelectItem>
                          <SelectItem value="daily">Daily</SelectItem>
                          <SelectItem value="weekly">Weekly</SelectItem>
                          <SelectItem value="monthly">Monthly</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label>Reminder (min before)</Label>
                    <Input
                      type="number"
                      min="0"
                      value={form.reminder_minutes_before}
                      onChange={(e) => setForm({ ...form, reminder_minutes_before: e.target.value })}
                      placeholder="e.g. 60"
                    />
                  </div>
                  <Button type="submit" className="w-full">Create Task</Button>
                </form>
              </DialogContent>
            </Dialog>
          </div>
        </div>

        <SavedViewsPicker
          entity="task"
          currentFilters={{ statusFilter }}
          onApply={(f) => {
            if (typeof f.statusFilter === "string") setStatusFilter(f.statusFilter);
            setPage(1);
          }}
        />

        <BulkActionBar
          entity="tasks"
          selectedIds={selectedIds}
          onClear={() => setSelectedIds([])}
          onApplied={load}
          actions={["set_status", "delete"]}
        />

        <div className="space-y-2">
          {data?.items.map((task) => {
            const config = statusConfig[task.status] || statusConfig.todo;
            const Icon = config.icon;
            return (
              <Card key={task.id}>
                <CardContent className="flex items-center gap-4 p-4">
                  <input
                    type="checkbox"
                    checked={selectedIds.includes(task.id)}
                    onChange={(e) => {
                      if (e.target.checked) setSelectedIds([...selectedIds, task.id]);
                      else setSelectedIds(selectedIds.filter((id) => id !== task.id));
                    }}
                  />
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
                  {task.priority && task.priority !== "medium" && (
                    <Badge variant="secondary" className={`capitalize ${
                      task.priority === "urgent" ? "bg-red-100 text-red-800" :
                      task.priority === "high" ? "bg-orange-100 text-orange-800" :
                      "bg-gray-100 text-gray-700"
                    }`}>
                      {task.priority}
                    </Badge>
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
              <CardContent className="p-0">
                <EmptyState
                  icon={CheckSquare}
                  title={statusFilter ? "No tasks with this status" : "No tasks yet"}
                  description={statusFilter ? "Try a different status filter." : "Click Add Task to create one."}
                />
              </CardContent>
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
