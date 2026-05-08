"use client";

import { useState, useEffect, useRef } from "react";
import { apiFetch } from "@/lib/api";
import { Pencil } from "lucide-react";

type FieldType = "text" | "email" | "tel" | "textarea" | "number" | "date";

export interface InlineEditFieldProps {
  /** Endpoint path, e.g. "/api/contacts/abc-123" */
  url: string;
  /** Field name on the entity, e.g. "phone" */
  field: string;
  /** Current value (string, number, or null) */
  value: string | number | null;
  type?: FieldType;
  placeholder?: string;
  /** Callback after successful save */
  onSaved?: (newValue: unknown) => void;
  /** Display formatter for non-edit mode */
  formatDisplay?: (v: string | number | null) => string;
}

export function InlineEditField({
  url, field, value, type = "text", placeholder = "—", onSaved, formatDisplay,
}: InlineEditFieldProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<string>(value === null || value === undefined ? "" : String(value));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  useEffect(() => {
    setDraft(value === null || value === undefined ? "" : String(value));
  }, [value]);

  function valid(s: string): string | null {
    if (type === "email" && s && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(s)) return "Invalid email";
    if (type === "number" && s && Number.isNaN(Number(s))) return "Must be a number";
    return null;
  }

  async function save() {
    const err = valid(draft);
    if (err) { setError(err); return; }
    setSaving(true);
    setError(null);
    try {
      let payloadValue: string | number | null = draft;
      if (type === "number") payloadValue = draft === "" ? null : Number(draft);
      else if (draft === "") payloadValue = null;
      const body: Record<string, unknown> = { [field]: payloadValue };
      if (type === "date" && draft) body[field] = new Date(draft).toISOString();
      await apiFetch(url, { method: "PATCH", body: JSON.stringify(body) });
      onSaved?.(payloadValue);
      setEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  function cancel() {
    setDraft(value === null || value === undefined ? "" : String(value));
    setEditing(false);
    setError(null);
  }

  if (!editing) {
    const display = formatDisplay
      ? formatDisplay(value)
      : value !== null && value !== undefined && String(value) !== ""
        ? String(value)
        : "";
    return (
      <button
        onClick={() => setEditing(true)}
        className="group inline-flex items-center gap-1 text-left hover:text-foreground min-w-0"
      >
        <span className={`truncate ${display ? "" : "text-muted-foreground italic"}`}>
          {display || placeholder}
        </span>
        <Pencil className="h-3 w-3 opacity-0 group-hover:opacity-50 shrink-0" />
      </button>
    );
  }

  const sharedProps = {
    value: draft,
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setDraft(e.target.value),
    onBlur: save,
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && type !== "textarea") { e.preventDefault(); save(); }
      if (e.key === "Escape") cancel();
    },
    disabled: saving,
    className: "w-full rounded-md border bg-background px-2 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
  };

  return (
    <div className="space-y-1">
      {type === "textarea" ? (
        <textarea
          ref={inputRef as React.RefObject<HTMLTextAreaElement>}
          rows={3}
          {...sharedProps}
        />
      ) : (
        <input
          ref={inputRef as React.RefObject<HTMLInputElement>}
          type={type}
          {...sharedProps}
        />
      )}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
