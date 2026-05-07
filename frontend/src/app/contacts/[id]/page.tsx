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
import { Timeline } from "@/components/timeline";
import { ActivityForm } from "@/components/activity-form";
import { CustomFields } from "@/components/custom-fields";
import { HistoryPanel } from "@/components/history-panel";
import { InlineEditField } from "@/components/inline-edit-field";
import { apiFetch } from "@/lib/api";
import {
  ArrowLeft, Mail, Phone, Briefcase, Building2, Tag, Calendar,
  Pencil, TrendingUp, CheckSquare, Activity, DollarSign,
} from "lucide-react";

interface ContactProfile {
  contact: {
    id: string;
    first_name: string;
    last_name: string;
    email: string | null;
    phone: string | null;
    job_title: string | null;
    company_id: string | null;
    source: string | null;
    notes: string | null;
    address: string | null;
    tags: Array<{ id: string; name: string; color: string }>;
    created_at: string;
    updated_at: string;
  };
  company: { id: string; name: string; domain: string | null } | null;
  deals: Array<{
    id: string;
    title: string;
    value: number;
    stage: string;
    expected_close_date: string | null;
    tags: Array<{ id: string; name: string; color: string }>;
  }>;
  tasks: Array<{
    id: string;
    title: string;
    status: string;
    due_date: string | null;
    description: string | null;
  }>;
  custom_fields: Array<{ id: string; definition_id: string; contact_id: string | null; company_id: string | null; value: string }>;
  custom_field_definitions: Array<{ id: string; name: string; field_type: string; entity_type: string; options: string | null; is_required: boolean }>;
  stats: {
    total_deals: number;
    total_deal_value: number;
    open_deals: number;
    won_deals: number;
    total_activities: number;
    total_tasks: number;
    open_tasks: number;
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

export default function ContactProfilePage() {
  const params = useParams();
  const router = useRouter();
  const contactId = params.id as string;
  const [profile, setProfile] = useState<ContactProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [editOpen, setEditOpen] = useState(false);
  const [editForm, setEditForm] = useState({ first_name: "", last_name: "", email: "", phone: "", job_title: "", source: "", notes: "" });
  const [editingNotes, setEditingNotes] = useState(false);
  const [notesValue, setNotesValue] = useState("");
  const [timelineKey, setTimelineKey] = useState(0);

  const load = useCallback(async () => {
    try {
      const data = await apiFetch<ContactProfile>(`/api/contacts/${contactId}/profile`);
      setProfile(data);
    } catch {
      router.replace("/contacts");
    } finally {
      setLoading(false);
    }
  }, [contactId, router]);

  useEffect(() => { load(); }, [load]);

  function openEdit() {
    if (!profile) return;
    const c = profile.contact;
    setEditForm({
      first_name: c.first_name, last_name: c.last_name,
      email: c.email || "", phone: c.phone || "",
      job_title: c.job_title || "", source: c.source || "",
      notes: c.notes || "",
    });
    setEditOpen(true);
  }

  async function handleEditSubmit(e: React.FormEvent) {
    e.preventDefault();
    await apiFetch(`/api/contacts/${contactId}`, {
      method: "PATCH",
      body: JSON.stringify(editForm),
    });
    setEditOpen(false);
    load();
  }

  async function saveNotes() {
    await apiFetch(`/api/contacts/${contactId}`, {
      method: "PATCH",
      body: JSON.stringify({ notes: notesValue }),
    });
    setEditingNotes(false);
    load();
  }

  function handleActivityCreated() {
    load();
    setTimelineKey((k) => k + 1);
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

  const { contact, company, deals, tasks, stats, custom_fields, custom_field_definitions } = profile;
  const initials = `${contact.first_name[0] || ""}${contact.last_name[0] || ""}`.toUpperCase();

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Back button */}
        <Link href="/contacts" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" /> Back to Contacts
        </Link>

        {/* Hero */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-4">
            <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-primary text-xl font-bold text-primary-foreground">
              {initials}
            </div>
            <div>
              <h1 className="text-2xl font-bold">{contact.first_name} {contact.last_name}</h1>
              <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                {contact.job_title && <span className="flex items-center gap-1"><Briefcase className="h-3 w-3" />{contact.job_title}</span>}
                {company && (
                  <Link href={`/companies/${company.id}`} className="flex items-center gap-1 text-primary hover:underline">
                    <Building2 className="h-3 w-3" />{company.name}
                  </Link>
                )}
              </div>
              {contact.tags.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {contact.tags.map((t) => (
                    <Badge key={t.id} variant="secondary" style={{ backgroundColor: t.color + "20", color: t.color }} className="text-xs">
                      {t.name}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={openEdit}>
            <Pencil className="mr-1 h-4 w-4" /> Edit
          </Button>
        </div>

        {/* Two-column layout */}
        <div className="grid gap-6 md:grid-cols-3">
          {/* Left column */}
          <div className="space-y-6 md:col-span-2">
            {/* Contact Info */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Contact Information</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div className="flex items-center gap-2 text-sm">
                    <Mail className="h-4 w-4 text-muted-foreground shrink-0" />
                    <InlineEditField
                      url={`/api/contacts/${contactId}`}
                      field="email"
                      value={contact.email}
                      type="email"
                      placeholder="Add email"
                      onSaved={load}
                    />
                  </div>
                  <div className="flex items-center gap-2 text-sm">
                    <Phone className="h-4 w-4 text-muted-foreground shrink-0" />
                    <InlineEditField
                      url={`/api/contacts/${contactId}`}
                      field="phone"
                      value={contact.phone}
                      type="tel"
                      placeholder="Add phone"
                      onSaved={load}
                    />
                  </div>
                  <div className="flex items-center gap-2 text-sm">
                    <Briefcase className="h-4 w-4 text-muted-foreground shrink-0" />
                    <InlineEditField
                      url={`/api/contacts/${contactId}`}
                      field="job_title"
                      value={contact.job_title}
                      placeholder="Add job title"
                      onSaved={load}
                    />
                  </div>
                  <div className="flex items-center gap-2 text-sm">
                    <Tag className="h-4 w-4 text-muted-foreground shrink-0" />
                    <InlineEditField
                      url={`/api/contacts/${contactId}`}
                      field="source"
                      value={contact.source}
                      placeholder="Add source"
                      onSaved={load}
                    />
                  </div>
                  <div className="flex items-center gap-2 text-sm">
                    <Calendar className="h-4 w-4 text-muted-foreground" />
                    <span>Added {new Date(contact.created_at).toLocaleDateString()}</span>
                  </div>
                  <div className="flex items-start gap-2 text-sm sm:col-span-2">
                    <span className="text-muted-foreground shrink-0 text-xs uppercase">Address</span>
                    <InlineEditField
                      url={`/api/contacts/${contactId}`}
                      field="address"
                      value={contact.address}
                      type="textarea"
                      placeholder="Add address"
                      onSaved={load}
                    />
                  </div>
                </div>

                {/* Notes */}
                <div className="border-t pt-3">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Notes</p>
                    {!editingNotes && (
                      <button
                        onClick={() => { setNotesValue(contact.notes || ""); setEditingNotes(true); }}
                        className="text-muted-foreground hover:text-foreground"
                      >
                        <Pencil className="h-3 w-3" />
                      </button>
                    )}
                  </div>
                  {editingNotes ? (
                    <div className="mt-2 space-y-2">
                      <textarea
                        className="w-full rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        rows={4}
                        value={notesValue}
                        onChange={(e) => setNotesValue(e.target.value)}
                        placeholder="Add notes about this contact..."
                        autoFocus
                      />
                      <div className="flex gap-2">
                        <Button size="sm" onClick={saveNotes}>Save</Button>
                        <Button size="sm" variant="ghost" onClick={() => setEditingNotes(false)}>Cancel</Button>
                      </div>
                    </div>
                  ) : (
                    <p className="mt-1 text-sm whitespace-pre-wrap">{contact.notes || <span className="text-muted-foreground italic">No notes yet. Click the pencil to add some.</span>}</p>
                  )}
                </div>

                {/* Custom Fields */}
                {custom_field_definitions.length > 0 && (
                  <div className="border-t pt-3">
                    <CustomFields
                      entityType="contact"
                      entityId={contactId}
                      definitions={custom_field_definitions}
                      values={custom_fields}
                      onUpdate={load}
                    />
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Timeline */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Activity Timeline</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <ActivityForm contactId={contactId} onCreated={handleActivityCreated} />
                <Timeline key={timelineKey} contactId={contactId} />
              </CardContent>
            </Card>

            {/* Change History */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Change History</CardTitle>
              </CardHeader>
              <CardContent>
                <HistoryPanel entityType="contact" entityId={contactId} />
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
                  <span className="flex items-center gap-2 text-muted-foreground"><DollarSign className="h-4 w-4" />Pipeline Value</span>
                  <span className="font-semibold">${stats.total_deal_value.toLocaleString()}</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2 text-muted-foreground"><TrendingUp className="h-4 w-4" />Open Deals</span>
                  <span className="font-semibold">{stats.open_deals}</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2 text-muted-foreground"><CheckSquare className="h-4 w-4" />Open Tasks</span>
                  <span className="font-semibold">{stats.open_tasks}</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2 text-muted-foreground"><Activity className="h-4 w-4" />Activities</span>
                  <span className="font-semibold">{stats.total_activities}</span>
                </div>
                {stats.last_activity_date && (
                  <div className="border-t pt-2 text-xs text-muted-foreground">
                    Last activity: {new Date(stats.last_activity_date).toLocaleDateString()}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Deals */}
            <Card>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">Deals ({deals.length})</CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                {deals.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No deals yet.</p>
                ) : (
                  <div className="space-y-2">
                    {deals.map((d) => (
                      <div key={d.id} className="flex items-center justify-between rounded-md border p-2">
                        <div className="min-w-0">
                          <p className="text-sm font-medium truncate">{d.title}</p>
                          <p className="text-xs text-muted-foreground">${d.value.toLocaleString()}</p>
                        </div>
                        <Badge variant="secondary" className={`text-xs ${stageColors[d.stage] || ""}`}>
                          {stageLabels[d.stage] || d.stage}
                        </Badge>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Tasks */}
            <Card>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">Tasks ({tasks.length})</CardTitle>
                </div>
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
          <DialogHeader><DialogTitle>Edit Contact</DialogTitle></DialogHeader>
          <form onSubmit={handleEditSubmit} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>First Name</Label>
                <Input value={editForm.first_name} onChange={(e) => setEditForm({ ...editForm, first_name: e.target.value })} required />
              </div>
              <div className="space-y-2">
                <Label>Last Name</Label>
                <Input value={editForm.last_name} onChange={(e) => setEditForm({ ...editForm, last_name: e.target.value })} required />
              </div>
            </div>
            <div className="space-y-2">
              <Label>Email</Label>
              <Input type="email" value={editForm.email} onChange={(e) => setEditForm({ ...editForm, email: e.target.value })} />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Phone</Label>
                <Input value={editForm.phone} onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })} />
              </div>
              <div className="space-y-2">
                <Label>Job Title</Label>
                <Input value={editForm.job_title} onChange={(e) => setEditForm({ ...editForm, job_title: e.target.value })} />
              </div>
            </div>
            <div className="space-y-2">
              <Label>Source</Label>
              <Input value={editForm.source} onChange={(e) => setEditForm({ ...editForm, source: e.target.value })} placeholder="e.g. website, referral" />
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
