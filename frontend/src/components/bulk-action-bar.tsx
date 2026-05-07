"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiFetch } from "@/lib/api";
import { Trash2, Tag as TagIcon, X } from "lucide-react";

interface Tag { id: string; name: string; color: string }

export interface BulkActionBarProps {
  entity: "contacts" | "companies" | "deals" | "tasks";
  selectedIds: string[];
  onClear: () => void;
  onApplied: () => void;
  /** which actions this entity supports */
  actions: ("delete" | "add_tag" | "remove_tag" | "set_owner" | "set_stage" | "set_status")[];
}

const stageOptions = [
  { value: "lead", label: "Lead" },
  { value: "qualified", label: "Qualified" },
  { value: "proposal", label: "Proposal" },
  { value: "negotiation", label: "Negotiation" },
  { value: "closed_won", label: "Closed Won" },
  { value: "closed_lost", label: "Closed Lost" },
];

const statusOptions = [
  { value: "todo", label: "To Do" },
  { value: "in_progress", label: "In Progress" },
  { value: "done", label: "Done" },
];

export function BulkActionBar({ entity, selectedIds, onClear, onApplied, actions }: BulkActionBarProps) {
  const [tags, setTags] = useState<Tag[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (actions.includes("add_tag") || actions.includes("remove_tag")) {
      apiFetch<Tag[]>("/api/tags").then(setTags).catch(() => {});
    }
  }, [actions]);

  if (selectedIds.length === 0) return null;

  async function call(body: Record<string, unknown>) {
    setBusy(true);
    try {
      await apiFetch(`/api/${entity}/bulk`, {
        method: "POST",
        body: JSON.stringify({ ...body, ids: selectedIds }),
      });
      onApplied();
      onClear();
    } finally {
      setBusy(false);
    }
  }

  async function doDelete() {
    if (!confirm(`Delete ${selectedIds.length} ${entity}? This cannot be undone.`)) return;
    await call({ action: "delete" });
  }

  return (
    <div className="sticky top-0 z-10 flex flex-wrap items-center gap-2 rounded-md border bg-background p-3 shadow-sm">
      <span className="text-sm font-medium">{selectedIds.length} selected</span>
      <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClear}>
        <X className="h-4 w-4" />
      </Button>
      <div className="ml-auto flex flex-wrap items-center gap-2">
        {actions.includes("add_tag") && (
          <Select onValueChange={(v) => call({ action: "add_tag", tag_id: v })}>
            <SelectTrigger className="h-8 w-[150px] text-sm" disabled={busy}>
              <span className="inline-flex items-center gap-1"><TagIcon className="h-3 w-3" />Add tag</span>
            </SelectTrigger>
            <SelectContent>
              {tags.map((t) => <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>)}
            </SelectContent>
          </Select>
        )}
        {actions.includes("remove_tag") && (
          <Select onValueChange={(v) => call({ action: "remove_tag", tag_id: v })}>
            <SelectTrigger className="h-8 w-[150px] text-sm" disabled={busy}>
              <span className="inline-flex items-center gap-1"><TagIcon className="h-3 w-3" />Remove tag</span>
            </SelectTrigger>
            <SelectContent>
              {tags.map((t) => <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>)}
            </SelectContent>
          </Select>
        )}
        {actions.includes("set_stage") && (
          <Select onValueChange={(v) => call({ action: "set_stage", stage: v })}>
            <SelectTrigger className="h-8 w-[140px] text-sm" disabled={busy}>
              <span>Set stage</span>
            </SelectTrigger>
            <SelectContent>
              {stageOptions.map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
            </SelectContent>
          </Select>
        )}
        {actions.includes("set_status") && (
          <Select onValueChange={(v) => call({ action: "set_status", status: v })}>
            <SelectTrigger className="h-8 w-[140px] text-sm" disabled={busy}>
              <span>Set status</span>
            </SelectTrigger>
            <SelectContent>
              {statusOptions.map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
            </SelectContent>
          </Select>
        )}
        {actions.includes("delete") && (
          <Button variant="outline" size="sm" onClick={doDelete} disabled={busy}>
            <Trash2 className="mr-1 h-4 w-4 text-destructive" /> Delete
          </Button>
        )}
      </div>
    </div>
  );
}
