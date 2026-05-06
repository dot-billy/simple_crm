"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiFetch } from "@/lib/api";
import { Plus, ChevronDown, ChevronUp } from "lucide-react";

const activityTypes = [
  { value: "note", label: "Note" },
  { value: "call", label: "Call" },
  { value: "email", label: "Email" },
  { value: "meeting", label: "Meeting" },
  { value: "other", label: "Other" },
];

interface ActivityFormProps {
  contactId?: string;
  dealId?: string;
  onCreated: () => void;
}

export function ActivityForm({ contactId, dealId, onCreated }: ActivityFormProps) {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState({ type: "note", subject: "", description: "" });

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.subject.trim()) return;
    setSubmitting(true);
    try {
      await apiFetch("/api/activities", {
        method: "POST",
        body: JSON.stringify({
          type: form.type,
          subject: form.subject,
          description: form.description || null,
          contact_id: contactId || null,
          deal_id: dealId || null,
        }),
      });
      setForm({ type: "note", subject: "", description: "" });
      setOpen(false);
      onCreated();
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) {
    return (
      <Button variant="outline" size="sm" onClick={() => setOpen(true)} className="w-full">
        <Plus className="mr-1 h-4 w-4" /> Log Activity
      </Button>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3 rounded-md border bg-muted/30 p-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium">Log Activity</p>
        <button type="button" onClick={() => setOpen(false)} className="text-muted-foreground hover:text-foreground">
          <ChevronUp className="h-4 w-4" />
        </button>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label className="text-xs">Type</Label>
          <Select value={form.type} onValueChange={(v) => setForm({ ...form, type: v })}>
            <SelectTrigger className="h-8 text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {activityTypes.map((t) => (
                <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Subject</Label>
          <Input
            className="h-8 text-sm"
            value={form.subject}
            onChange={(e) => setForm({ ...form, subject: e.target.value })}
            placeholder="Brief summary..."
            required
          />
        </div>
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Details</Label>
        <textarea
          className="w-full rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          rows={3}
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
          placeholder="Add details about this interaction..."
        />
      </div>
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={submitting}>
          {submitting ? "Saving..." : "Save Activity"}
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
