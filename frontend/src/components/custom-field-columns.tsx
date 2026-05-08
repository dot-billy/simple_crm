"use client";

import { useEffect, useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { apiFetch } from "@/lib/api";
import { Columns3 } from "lucide-react";

export interface CustomFieldDefinition {
  id: string;
  name: string;
  field_type: string;
  entity_type: string;
}

interface CustomFieldColumnsProps {
  entity: "contact" | "company";
  /** ids of fields to show, in selected order */
  visibleFieldIds: string[];
  /** filter value per field id */
  filters: Record<string, string>;
  onChangeVisibility: (ids: string[]) => void;
  onChangeFilter: (fieldId: string, value: string) => void;
}

export function useCustomFieldColumns(entity: "contact" | "company") {
  const [definitions, setDefinitions] = useState<CustomFieldDefinition[]>([]);
  const storageKey = `cf-columns-${entity}`;
  const filterKey = `cf-filters-${entity}`;
  const [visible, setVisible] = useState<string[]>(() => {
    if (typeof window === "undefined") return [];
    try { return JSON.parse(localStorage.getItem(storageKey) || "[]"); } catch { return []; }
  });
  const [filters, setFilters] = useState<Record<string, string>>(() => {
    if (typeof window === "undefined") return {};
    try { return JSON.parse(localStorage.getItem(filterKey) || "{}"); } catch { return {}; }
  });

  useEffect(() => {
    apiFetch<CustomFieldDefinition[]>(`/api/custom-fields/definitions?entity_type=${entity}`)
      .then(setDefinitions)
      .catch(() => setDefinitions([]));
  }, [entity]);

  const setVisibleAndStore = useCallback((ids: string[]) => {
    setVisible(ids);
    localStorage.setItem(storageKey, JSON.stringify(ids));
  }, [storageKey]);

  const setFilterAndStore = useCallback((id: string, value: string) => {
    setFilters((prev) => {
      const next = { ...prev };
      if (value) next[id] = value; else delete next[id];
      localStorage.setItem(filterKey, JSON.stringify(next));
      return next;
    });
  }, [filterKey]);

  return { definitions, visible, filters, setVisible: setVisibleAndStore, setFilter: setFilterAndStore };
}

export function ColumnPicker({ entity, visibleFieldIds, onChangeVisibility }: CustomFieldColumnsProps) {
  const { definitions } = useCustomFieldColumns(entity);
  const [open, setOpen] = useState(false);

  if (definitions.length === 0) return null;

  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        <Columns3 className="mr-1 h-4 w-4" /> Columns
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Custom field columns</DialogTitle></DialogHeader>
          <div className="space-y-2">
            {definitions.map((d) => {
              const checked = visibleFieldIds.includes(d.id);
              return (
                <label key={d.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(e) => {
                      if (e.target.checked) onChangeVisibility([...visibleFieldIds, d.id]);
                      else onChangeVisibility(visibleFieldIds.filter((x) => x !== d.id));
                    }}
                  />
                  <span>{d.name}</span>
                  <span className="text-xs text-muted-foreground">({d.field_type})</span>
                </label>
              );
            })}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
