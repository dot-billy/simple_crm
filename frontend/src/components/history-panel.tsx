"use client";

import { useEffect, useState, useCallback } from "react";
import { apiFetch } from "@/lib/api";
import { History } from "lucide-react";

interface AuditItem {
  id: string;
  event_type: string;
  email: string | null;
  entity_type: string | null;
  entity_id: string | null;
  before_state: string | null;
  after_state: string | null;
  detail: string | null;
  created_at: string;
}

interface AuditResponse {
  items: AuditItem[];
  total: number;
}

const eventLabels: Record<string, string> = {
  contact_created: "created", contact_updated: "updated", contact_deleted: "deleted",
  company_created: "created", company_updated: "updated", company_deleted: "deleted",
  deal_created: "created", deal_updated: "updated", deal_deleted: "deleted",
  deal_stage_changed: "stage changed",
  task_created: "created", task_updated: "updated", task_deleted: "deleted",
  activity_created: "logged activity", activity_deleted: "deleted activity",
};

interface HistoryPanelProps {
  entityType: "contact" | "company" | "deal";
  entityId: string;
}

export function HistoryPanel({ entityType, entityId }: HistoryPanelProps) {
  const [items, setItems] = useState<AuditItem[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const data = await apiFetch<AuditResponse>(
        `/api/audit?entity_type=${entityType}&entity_id=${entityId}&per_page=20`
      );
      setItems(data.items);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [entityType, entityId]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <p className="text-sm text-muted-foreground">Loading history...</p>;
  if (items.length === 0) return <p className="text-sm text-muted-foreground">No changes yet.</p>;

  return (
    <div className="space-y-3">
      {items.map((item) => {
        const label = eventLabels[item.event_type] || item.event_type;
        const before = item.before_state ? safeParse(item.before_state) : null;
        const after = item.after_state ? safeParse(item.after_state) : null;
        const changedFields = before && after
          ? Object.keys({ ...before, ...after }).filter((k) => before[k] !== after[k])
          : null;

        return (
          <div key={item.id} className="flex gap-3">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted">
              <History className="h-3.5 w-3.5 text-muted-foreground" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm">
                  <span className="font-medium">{item.email || "system"}</span>{" "}
                  <span className="text-muted-foreground">{label}</span>
                </p>
                <span className="text-xs text-muted-foreground shrink-0">
                  {new Date(item.created_at).toLocaleString()}
                </span>
              </div>
              {changedFields && changedFields.length > 0 && (
                <div className="mt-1 space-y-0.5">
                  {changedFields.map((f) => (
                    <p key={f} className="text-xs text-muted-foreground">
                      <span className="font-medium">{f}</span>:{" "}
                      <span className="line-through">{formatVal(before?.[f])}</span>{" → "}
                      <span>{formatVal(after?.[f])}</span>
                    </p>
                  ))}
                </div>
              )}
              {item.event_type.endsWith("_created") && (
                <p className="text-xs text-muted-foreground italic">created</p>
              )}
              {item.event_type.endsWith("_deleted") && (
                <p className="text-xs text-muted-foreground italic">deleted</p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function safeParse(s: string): Record<string, unknown> | null {
  try { return JSON.parse(s); } catch { return null; }
}

function formatVal(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "string") return v.length > 40 ? v.slice(0, 40) + "…" : v;
  return String(v);
}
