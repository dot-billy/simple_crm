"use client";

import { useEffect, useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch } from "@/lib/api";
import { Bookmark, Save, Trash2 } from "lucide-react";

export type Filters = Record<string, unknown>;

interface SavedView {
  id: string;
  user_id: string;
  entity_type: string;
  name: string;
  filters: Filters;
  is_shared: boolean;
  created_at: string;
}

interface SavedViewsPickerProps {
  entity: "contact" | "company" | "deal" | "task";
  currentFilters: Filters;
  onApply: (f: Filters) => void;
}

export function SavedViewsPicker({ entity, currentFilters, onApply }: SavedViewsPickerProps) {
  const [views, setViews] = useState<SavedView[]>([]);
  const [saveOpen, setSaveOpen] = useState(false);
  const [manageOpen, setManageOpen] = useState(false);
  const [name, setName] = useState("");
  const [shared, setShared] = useState(false);
  const [meId, setMeId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await apiFetch<SavedView[]>(`/api/saved-views?entity_type=${entity}`);
      setViews(data);
    } catch {
      setViews([]);
    }
  }, [entity]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    apiFetch<{ id: string }>("/api/auth/me").then((u) => setMeId(u.id)).catch(() => {});
  }, []);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    await apiFetch("/api/saved-views", {
      method: "POST",
      body: JSON.stringify({ entity_type: entity, name, filters: currentFilters, is_shared: shared }),
    });
    setSaveOpen(false);
    setName("");
    setShared(false);
    load();
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this saved view?")) return;
    await apiFetch(`/api/saved-views/${id}`, { method: "DELETE" });
    load();
  }

  return (
    <div className="flex items-center gap-2">
      <Select onValueChange={(v) => {
        const view = views.find((x) => x.id === v);
        if (view) onApply(view.filters);
      }}>
        <SelectTrigger className="w-[180px]">
          <span className="inline-flex items-center gap-1"><Bookmark className="h-3.5 w-3.5" />Saved views</span>
        </SelectTrigger>
        <SelectContent>
          {views.length === 0 && <div className="px-2 py-1.5 text-sm text-muted-foreground">No saved views</div>}
          {views.map((v) => (
            <SelectItem key={v.id} value={v.id}>
              {v.name}{v.is_shared ? " · shared" : ""}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Button variant="outline" size="sm" onClick={() => setSaveOpen(true)}>
        <Save className="mr-1 h-4 w-4" /> Save view
      </Button>
      {views.length > 0 && (
        <Button variant="outline" size="sm" onClick={() => setManageOpen(true)}>
          Manage
        </Button>
      )}

      <Dialog open={saveOpen} onOpenChange={setSaveOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Save current view</DialogTitle></DialogHeader>
          <form onSubmit={handleSave} className="space-y-4">
            <div className="space-y-2">
              <Label>Name</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} required placeholder="e.g. Hot leads" />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={shared} onChange={(e) => setShared(e.target.checked)} />
              Share with all users
            </label>
            <Button type="submit" className="w-full">Save</Button>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={manageOpen} onOpenChange={setManageOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Manage saved views</DialogTitle></DialogHeader>
          <div className="space-y-2">
            {views.map((v) => (
              <div key={v.id} className="flex items-center justify-between rounded-md border p-2">
                <div>
                  <p className="text-sm font-medium">{v.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {v.is_shared ? "shared" : "private"}
                    {v.user_id !== meId ? " · by another user" : ""}
                  </p>
                </div>
                {v.user_id === meId && (
                  <Button variant="ghost" size="icon" onClick={() => handleDelete(v.id)}>
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                )}
              </div>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
