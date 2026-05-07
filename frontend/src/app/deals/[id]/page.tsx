"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ActivityForm } from "@/components/activity-form";
import { HistoryPanel } from "@/components/history-panel";
import { apiFetch } from "@/lib/api";
import {
  ArrowLeft, User, Building2, Calendar, Pencil, DollarSign, Clock,
  CheckSquare, Activity, MessageSquare, Mail, Trash2,
} from "lucide-react";

interface DealProfile {
  deal: {
    id: string;
    title: string;
    value: number;
    currency: string;
    stage: string;
    contact_id: string | null;
    company_id: string | null;
    owner_id: string | null;
    expected_close_date: string | null;
    notes: string | null;
    tags: Array<{ id: string; name: string; color: string }>;
    created_at: string;
    updated_at: string;
  };
  contact: { id: string; first_name: string; last_name: string; email: string | null } | null;
  company: { id: string; name: string; domain: string | null } | null;
  activities: Array<{
    id: string;
    type: string;
    subject: string;
    description: string | null;
    activity_date: string;
  }>;
  tasks: Array<{
    id: string;
    title: string;
    status: string;
    due_date: string | null;
    description: string | null;
  }>;
  stats: {
    total_activities: number;
    total_tasks: number;
    open_tasks: number;
    days_in_stage: number;
    days_open: number;
    last_activity_date: string | null;
  };
}

const stageColors: Record<string, string> = {
  lead: "bg-blue-100 text-blue-800",
  qualified: "bg-yellow-100 text-yellow-800",
  proposal: "bg-purple-100 text-purple-800",
  negotiation: "bg-orange-100 text-orange-800",
  closed_won: "bg-green-100 text-green-800",
  closed_lost: "bg-red-100 text-red-800",
};

const stageLabels: Record<string, string> = {
  lead: "Lead", qualified: "Qualified", proposal: "Proposal",
  negotiation: "Negotiation", closed_won: "Won", closed_lost: "Lost",
};

const statusLabels: Record<string, string> = {
  todo: "To Do", in_progress: "In Progress", done: "Done",
};

const activityIcon: Record<string, typeof MessageSquare> = {
  note: MessageSquare, call: MessageSquare, email: Mail, meeting: MessageSquare, other: MessageSquare,
};

export default function DealProfilePage() {
  const params = useParams();
  const router = useRouter();
  const dealId = params.id as string;
  const [profile, setProfile] = useState<DealProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [editOpen, setEditOpen] = useState(false);
  const [editForm, setEditForm] = useState({ title: "", value: "", currency: "USD", expected_close_date: "", notes: "" });
  const [editingNotes, setEditingNotes] = useState(false);
  const [notesValue, setNotesValue] = useState("");

  const load = useCallback(async () => {
    try {
      const data = await apiFetch<DealProfile>(`/api/deals/${dealId}/profile`);
      setProfile(data);
    } catch {
      router.replace("/deals");
    } finally {
      setLoading(false);
    }
  }, [dealId, router]);

  useEffect(() => { load(); }, [load]);

  function openEdit() {
    if (!profile) return;
    const d = profile.deal;
    setEditForm({
      title: d.title,
      value: String(d.value),
      currency: d.currency,
      expected_close_date: d.expected_close_date ? d.expected_close_date.slice(0, 10) : "",
      notes: d.notes || "",
    });
    setEditOpen(true);
  }

  async function handleEditSubmit(e: React.FormEvent) {
    e.preventDefault();
    await apiFetch(`/api/deals/${dealId}`, {
      method: "PATCH",
      body: JSON.stringify({
        title: editForm.title,
        value: parseFloat(editForm.value) || 0,
        currency: editForm.currency,
        expected_close_date: editForm.expected_close_date || null,
        notes: editForm.notes || null,
      }),
    });
    setEditOpen(false);
    load();
  }

  async function changeStage(newStage: string) {
    await apiFetch(`/api/deals/${dealId}/stage`, {
      method: "PATCH",
      body: JSON.stringify({ stage: newStage }),
    });
    load();
  }

  async function saveNotes() {
    await apiFetch(`/api/deals/${dealId}`, {
      method: "PATCH",
      body: JSON.stringify({ notes: notesValue }),
    });
    setEditingNotes(false);
    load();
  }

  async function handleDelete() {
    if (!confirm("Delete this deal? This cannot be undone.")) return;
    await apiFetch(`/api/deals/${dealId}`, { method: "DELETE" });
    router.replace("/deals");
  }

  if (loading || !profile) {
    return (
      <AppShell>
        <div className="flex h-64 items-center justify-center">
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </AppShell>
    );
  }

  const { deal, contact, company, activities, tasks, stats } = profile;

  return (
    <AppShell>
      <div className="space-y-6">
        <Link href="/deals" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" /> Back to Deals
        </Link>

        {/* Hero */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-bold">{deal.title}</h1>
              <Badge variant="secondary" className={`${stageColors[deal.stage] || ""}`}>
                {stageLabels[deal.stage] || deal.stage}
              </Badge>
            </div>
            <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
              <span className="flex items-center gap-1">
                <DollarSign className="h-4 w-4" />
                <span className="font-semibold text-foreground">
                  {deal.value.toLocaleString(undefined, { style: "currency", currency: deal.currency || "USD", maximumFractionDigits: 0 })}
                </span>
              </span>
              {deal.expected_close_date && (
                <span className="flex items-center gap-1">
                  <Calendar className="h-4 w-4" />
                  Close {new Date(deal.expected_close_date).toLocaleDateString()}
                </span>
              )}
              <span className="flex items-center gap-1">
                <Clock className="h-4 w-4" />
                Open {stats.days_open}d
              </span>
            </div>
            {deal.tags.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {deal.tags.map((t) => (
                  <Badge key={t.id} variant="secondary" style={{ backgroundColor: t.color + "20", color: t.color }} className="text-xs">
                    {t.name}
                  </Badge>
                ))}
              </div>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Select value={deal.stage} onValueChange={changeStage}>
              <SelectTrigger className="w-[160px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(stageLabels).map(([v, l]) => (
                  <SelectItem key={v} value={v}>{l}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button variant="outline" size="sm" onClick={openEdit}>
              <Pencil className="mr-1 h-4 w-4" /> Edit
            </Button>
            <Button variant="outline" size="sm" onClick={handleDelete}>
              <Trash2 className="h-4 w-4 text-destructive" />
            </Button>
          </div>
        </div>

        {/* Two-column layout */}
        <div className="grid gap-6 md:grid-cols-3">
          {/* Left column */}
          <div className="space-y-6 md:col-span-2">
            {/* Notes */}
            <Card>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">Notes</CardTitle>
                  {!editingNotes && (
                    <button
                      onClick={() => { setNotesValue(deal.notes || ""); setEditingNotes(true); }}
                      className="text-muted-foreground hover:text-foreground"
                    >
                      <Pencil className="h-3 w-3" />
                    </button>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                {editingNotes ? (
                  <div className="space-y-2">
                    <textarea
                      className="w-full rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      rows={4}
                      value={notesValue}
                      onChange={(e) => setNotesValue(e.target.value)}
                      placeholder="Add notes about this deal..."
                      autoFocus
                    />
                    <div className="flex gap-2">
                      <Button size="sm" onClick={saveNotes}>Save</Button>
                      <Button size="sm" variant="ghost" onClick={() => setEditingNotes(false)}>Cancel</Button>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm whitespace-pre-wrap">
                    {deal.notes || <span className="text-muted-foreground italic">No notes yet. Click the pencil to add some.</span>}
                  </p>
                )}
              </CardContent>
            </Card>

            {/* Activity Timeline */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Activity Timeline</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <ActivityForm dealId={dealId} onCreated={load} />
                {activities.length === 0 ? (
                  <p className="text-sm text-muted-foreground text-center py-4">No activities yet.</p>
                ) : (
                  <div className="space-y-3">
                    {activities.map((a) => {
                      const Icon = activityIcon[a.type] || MessageSquare;
                      return (
                        <div key={a.id} className="flex gap-3">
                          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted">
                            <Icon className="h-4 w-4 text-muted-foreground" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center justify-between gap-2">
                              <p className="text-sm font-medium truncate">{a.subject}</p>
                              <span className="text-xs text-muted-foreground shrink-0">
                                {new Date(a.activity_date).toLocaleDateString()}
                              </span>
                            </div>
                            {a.description && (
                              <p className="text-sm text-muted-foreground whitespace-pre-wrap mt-1">{a.description}</p>
                            )}
                            <p className="text-xs text-muted-foreground capitalize mt-1">{a.type}</p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Change History */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Change History</CardTitle>
              </CardHeader>
              <CardContent>
                <HistoryPanel entityType="deal" entityId={dealId} />
              </CardContent>
            </Card>
          </div>

          {/* Right column */}
          <div className="space-y-6">
            {/* Stats */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Overview</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2 text-muted-foreground"><Clock className="h-4 w-4" />Days Open</span>
                  <span className="font-semibold">{stats.days_open}</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2 text-muted-foreground"><Clock className="h-4 w-4" />Days in Stage</span>
                  <span className="font-semibold">{stats.days_in_stage}</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2 text-muted-foreground"><Activity className="h-4 w-4" />Activities</span>
                  <span className="font-semibold">{stats.total_activities}</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2 text-muted-foreground"><CheckSquare className="h-4 w-4" />Open Tasks</span>
                  <span className="font-semibold">{stats.open_tasks}</span>
                </div>
                {stats.last_activity_date && (
                  <div className="border-t pt-2 text-xs text-muted-foreground">
                    Last activity: {new Date(stats.last_activity_date).toLocaleDateString()}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Linked Contact */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Contact</CardTitle>
              </CardHeader>
              <CardContent>
                {contact ? (
                  <Link href={`/contacts/${contact.id}`} className="flex items-start gap-3 rounded-md border p-3 hover:bg-muted/50">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-semibold">
                      {(contact.first_name[0] || "") + (contact.last_name[0] || "")}
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">{contact.first_name} {contact.last_name}</p>
                      {contact.email && <p className="text-xs text-muted-foreground truncate">{contact.email}</p>}
                    </div>
                  </Link>
                ) : (
                  <p className="text-sm text-muted-foreground">No contact linked.</p>
                )}
              </CardContent>
            </Card>

            {/* Linked Company */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Company</CardTitle>
              </CardHeader>
              <CardContent>
                {company ? (
                  <Link href={`/companies/${company.id}`} className="flex items-start gap-3 rounded-md border p-3 hover:bg-muted/50">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-muted">
                      <Building2 className="h-4 w-4 text-muted-foreground" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">{company.name}</p>
                      {company.domain && <p className="text-xs text-muted-foreground truncate">{company.domain}</p>}
                    </div>
                  </Link>
                ) : (
                  <p className="text-sm text-muted-foreground">No company linked.</p>
                )}
              </CardContent>
            </Card>

            {/* Tasks */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Tasks ({tasks.length})</CardTitle>
              </CardHeader>
              <CardContent>
                {tasks.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No tasks yet.</p>
                ) : (
                  <div className="space-y-2">
                    {tasks.map((t) => (
                      <div key={t.id} className="flex items-center justify-between rounded-md border p-2">
                        <div className="min-w-0">
                          <p className={`text-sm font-medium truncate ${t.status === "done" ? "line-through text-muted-foreground" : ""}`}>{t.title}</p>
                          {t.due_date && (
                            <p className="text-xs text-muted-foreground">{new Date(t.due_date).toLocaleDateString()}</p>
                          )}
                        </div>
                        <Badge variant="secondary" className="text-xs">
                          {statusLabels[t.status] || t.status}
                        </Badge>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>

      {/* Edit Dialog */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Edit Deal</DialogTitle></DialogHeader>
          <form onSubmit={handleEditSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label>Title</Label>
              <Input value={editForm.title} onChange={(e) => setEditForm({ ...editForm, title: e.target.value })} required />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Value</Label>
                <Input type="number" step="0.01" value={editForm.value} onChange={(e) => setEditForm({ ...editForm, value: e.target.value })} />
              </div>
              <div className="space-y-2">
                <Label>Currency</Label>
                <Input value={editForm.currency} onChange={(e) => setEditForm({ ...editForm, currency: e.target.value })} />
              </div>
            </div>
            <div className="space-y-2">
              <Label>Expected Close Date</Label>
              <Input type="date" value={editForm.expected_close_date} onChange={(e) => setEditForm({ ...editForm, expected_close_date: e.target.value })} />
            </div>
            <div className="space-y-2">
              <Label>Notes</Label>
              <textarea
                className="w-full rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                rows={3}
                value={editForm.notes}
                onChange={(e) => setEditForm({ ...editForm, notes: e.target.value })}
              />
            </div>
            <Button type="submit" className="w-full">Save Changes</Button>
          </form>
        </DialogContent>
      </Dialog>
    </AppShell>
  );
}
