"use client";

import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiFetch } from "@/lib/api";
import { Check, Pencil, X } from "lucide-react";

function parseOptions(raw: string | null): string[] {
  if (!raw) return [];
  const trimmed = raw.trim();
  if (trimmed.startsWith("[")) {
    try {
      const parsed = JSON.parse(trimmed);
      if (Array.isArray(parsed)) return parsed.map(String);
    } catch {
      // fall through to comma-separated parsing
    }
  }
  return trimmed.split(",").map((s) => s.trim()).filter(Boolean);
}

interface CustomFieldDefinition {
  id: string;
  name: string;
  field_type: string;
  entity_type: string;
  options: string | null;
  is_required: boolean;
}

interface CustomFieldValue {
  id: string;
  definition_id: string;
  contact_id: string | null;
  company_id: string | null;
  value: string;
}

interface CustomFieldsProps {
  entityType: "contact" | "company";
  entityId: string;
  definitions: CustomFieldDefinition[];
  values: CustomFieldValue[];
  onUpdate: () => void;
}

export function CustomFields({ entityType, entityId, definitions, values, onUpdate }: CustomFieldsProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [saving, setSaving] = useState(false);

  if (definitions.length === 0) return null;

  function getValueForDef(defId: string): string {
    return values.find((v) => v.definition_id === defId)?.value || "";
  }

  function startEdit(defId: string) {
    setEditingId(defId);
    setEditValue(getValueForDef(defId));
  }

  async function saveField(defId: string) {
    setSaving(true);
    try {
      await apiFetch("/api/custom-fields/values", {
        method: "POST",
        body: JSON.stringify({
          definition_id: defId,
          ...(entityType === "contact" ? { contact_id: entityId } : { company_id: entityId }),
          value: editValue,
        }),
      });
      setEditingId(null);
      onUpdate();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-2">
      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Custom Fields</p>
      {definitions.map((def) => {
        const currentValue = getValueForDef(def.id);
        const isEditing = editingId === def.id;
        const options = parseOptions(def.options);

        return (
          <div key={def.id} className="flex items-start justify-between gap-2">
            <div className="min-w-0 flex-1">
              <p className="text-xs text-muted-foreground">{def.name}</p>
              {isEditing ? (
                <div className="mt-1 flex items-center gap-1">
                  {def.field_type === "select" ? (
                    <Select value={editValue} onValueChange={setEditValue}>
                      <SelectTrigger className="h-7 text-xs"><SelectValue placeholder="Select..." /></SelectTrigger>
                      <SelectContent>
                        {options.map((opt: string) => (
                          <SelectItem key={opt} value={opt}>{opt}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : def.field_type === "boolean" ? (
                    <Select value={editValue} onValueChange={setEditValue}>
                      <SelectTrigger className="h-7 text-xs"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="true">Yes</SelectItem>
                        <SelectItem value="false">No</SelectItem>
                      </SelectContent>
                    </Select>
                  ) : (
                    <Input
                      className="h-7 text-xs"
                      type={def.field_type === "number" ? "number" : def.field_type === "date" ? "date" : "text"}
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      autoFocus
                    />
                  )}
                  <button onClick={() => saveField(def.id)} disabled={saving} className="text-green-600 hover:text-green-800">
                    <Check className="h-3.5 w-3.5" />
                  </button>
                  <button onClick={() => setEditingId(null)} className="text-muted-foreground hover:text-foreground">
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              ) : (
                <p className="text-sm">
                  {def.field_type === "boolean"
                    ? currentValue === "true" ? "Yes" : currentValue === "false" ? "No" : "-"
                    : currentValue || "-"}
                </p>
              )}
            </div>
            {!isEditing && (
              <button onClick={() => startEdit(def.id)} className="mt-3 text-muted-foreground hover:text-foreground">
                <Pencil className="h-3 w-3" />
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
