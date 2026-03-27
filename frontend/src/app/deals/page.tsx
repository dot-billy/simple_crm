"use client";

import { useEffect, useState, useCallback } from "react";
import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiFetch, apiUpload } from "@/lib/api";
import { Plus, Trash2, GripVertical, Download, Upload } from "lucide-react";
import {
  DndContext,
  DragEndEvent,
  DragOverlay,
  DragStartEvent,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useDroppable } from "@dnd-kit/core";

interface Deal {
  id: string;
  title: string;
  value: number;
  currency: string;
  stage: string;
  contact_id: string | null;
  company_id: string | null;
  expected_close_date: string | null;
  tags: Array<{ id: string; name: string; color: string }>;
  created_at: string;
}

interface PaginatedDeals {
  items: Deal[];
  total: number;
  page: number;
  pages: number;
}

const stages = [
  { value: "lead", label: "Lead", color: "bg-blue-100 text-blue-800" },
  { value: "qualified", label: "Qualified", color: "bg-yellow-100 text-yellow-800" },
  { value: "proposal", label: "Proposal", color: "bg-purple-100 text-purple-800" },
  { value: "negotiation", label: "Negotiation", color: "bg-orange-100 text-orange-800" },
  { value: "closed_won", label: "Closed Won", color: "bg-green-100 text-green-800" },
  { value: "closed_lost", label: "Closed Lost", color: "bg-red-100 text-red-800" },
];

function DroppableColumn({
  stageValue,
  children,
}: {
  stageValue: string;
  children: React.ReactNode;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: `stage-${stageValue}` });
  return (
    <div
      ref={setNodeRef}
      className={`space-y-2 min-h-[100px] rounded-md p-1 transition-all ${
        isOver ? "ring-2 ring-primary bg-primary/5" : ""
      }`}
    >
      {children}
    </div>
  );
}

function SortableDealCard({
  deal,
  onDelete,
}: {
  deal: Deal;
  onDelete: (id: string) => void;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: deal.id, data: { stage: deal.stage } });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <Card
      ref={setNodeRef}
      style={style}
      className={`cursor-default ${isDragging ? "opacity-50" : ""}`}
    >
      <CardContent className="p-4">
        <div className="flex items-start justify-between">
          <div className="flex items-start gap-2 flex-1">
            <button
              {...attributes}
              {...listeners}
              className="mt-0.5 cursor-grab active:cursor-grabbing text-muted-foreground hover:text-foreground"
            >
              <GripVertical className="h-4 w-4" />
            </button>
            <div>
              <p className="font-medium text-sm">{deal.title}</p>
              <p className="text-lg font-bold text-primary">
                ${deal.value.toLocaleString()}
              </p>
            </div>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => onDelete(deal.id)}
          >
            <Trash2 className="h-3 w-3 text-destructive" />
          </Button>
        </div>
        {deal.tags.length > 0 && (
          <div className="flex gap-1 mt-2 flex-wrap">
            {deal.tags.map((t) => (
              <Badge
                key={t.id}
                variant="secondary"
                style={{ backgroundColor: t.color + "20", color: t.color }}
              >
                {t.name}
              </Badge>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function DealsPage() {
  const [data, setData] = useState<PaginatedDeals | null>(null);
  const [stageFilter, setStageFilter] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState({ title: "", value: "0", stage: "lead" });
  const [viewMode, setViewMode] = useState<"table" | "pipeline">("pipeline");
  const [activeDeal, setActiveDeal] = useState<Deal | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } })
  );

  const load = useCallback(() => {
    apiFetch<PaginatedDeals>(`/api/deals?per_page=100&stage=${stageFilter}`).then(setData);
  }, [stageFilter]);

  useEffect(() => { load(); }, [load]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    await apiFetch("/api/deals", {
      method: "POST",
      body: JSON.stringify({ title: form.title, value: parseFloat(form.value), stage: form.stage }),
    });
    setDialogOpen(false);
    setForm({ title: "", value: "0", stage: "lead" });
    load();
  }

  async function handleDelete(id: string) {
    await apiFetch(`/api/deals/${id}`, { method: "DELETE" });
    load();
  }

  async function handleExport() {
    const res = await fetch("/api/deals/export/csv", { credentials: "include" });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "deals.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    await apiUpload("/api/deals/import/csv", file);
    load();
  }

  function handleDragStart(event: DragStartEvent) {
    const deal = data?.items.find((d) => d.id === event.active.id);
    setActiveDeal(deal || null);
  }

  async function handleDragEnd(event: DragEndEvent) {
    setActiveDeal(null);
    const { active, over } = event;
    if (!over) return;

    const dealId = active.id as string;
    const deal = data?.items.find((d) => d.id === dealId);
    if (!deal) return;

    // Determine the target stage from the droppable id
    let newStage: string | null = null;
    const overId = over.id as string;

    if (overId.startsWith("stage-")) {
      newStage = overId.replace("stage-", "");
    } else {
      // Dropped on another deal card - find what stage that deal is in
      const targetDeal = data?.items.find((d) => d.id === overId);
      if (targetDeal) {
        newStage = targetDeal.stage;
      }
    }

    if (!newStage || newStage === deal.stage) return;

    // Optimistic update
    setData((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        items: prev.items.map((d) =>
          d.id === dealId ? { ...d, stage: newStage! } : d
        ),
      };
    });

    try {
      await apiFetch(`/api/deals/${dealId}/stage`, {
        method: "PATCH",
        body: JSON.stringify({ stage: newStage }),
      });
    } catch {
      // Revert on failure
      load();
    }
  }

  const dealsByStage = stages.map((s) => ({
    ...s,
    deals: data?.items.filter((d) => d.stage === s.value) || [],
  }));

  return (
    <AppShell>
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-3xl font-bold">Deals</h2>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={handleExport}>
              <Download className="mr-1 h-4 w-4" /> Export
            </Button>
            <label>
              <Button variant="outline" size="sm" asChild>
                <span><Upload className="mr-1 h-4 w-4" /> Import</span>
              </Button>
              <input type="file" accept=".csv" className="hidden" onChange={handleImport} />
            </label>
            <Button
              variant={viewMode === "pipeline" ? "default" : "outline"}
              size="sm"
              onClick={() => setViewMode("pipeline")}
            >
              Pipeline
            </Button>
            <Button
              variant={viewMode === "table" ? "default" : "outline"}
              size="sm"
              onClick={() => setViewMode("table")}
            >
              Table
            </Button>
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button size="sm"><Plus className="mr-1 h-4 w-4" /> Add Deal</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader><DialogTitle>New Deal</DialogTitle></DialogHeader>
                <form onSubmit={handleCreate} className="space-y-4">
                  <div className="space-y-2">
                    <Label>Title</Label>
                    <Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required />
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label>Value ($)</Label>
                      <Input type="number" value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} />
                    </div>
                    <div className="space-y-2">
                      <Label>Stage</Label>
                      <Select value={form.stage} onValueChange={(v) => setForm({ ...form, stage: v })}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {stages.map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  <Button type="submit" className="w-full">Create Deal</Button>
                </form>
              </DialogContent>
            </Dialog>
          </div>
        </div>

        {viewMode === "pipeline" ? (
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragStart={handleDragStart}
            onDragEnd={handleDragEnd}
          >
            <div className="flex gap-4 overflow-x-auto pb-4">
              {dealsByStage.map((col) => (
                <div key={col.value} className="min-w-[280px] flex-shrink-0">
                  <div className="mb-3 flex items-center justify-between">
                    <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${col.color}`}>
                      {col.label}
                    </span>
                    <span className="text-xs text-muted-foreground">{col.deals.length}</span>
                  </div>
                  <DroppableColumn stageValue={col.value}>
                    <SortableContext
                      items={col.deals.map((d) => d.id)}
                      strategy={verticalListSortingStrategy}
                    >
                      {col.deals.map((deal) => (
                        <SortableDealCard
                          key={deal.id}
                          deal={deal}
                          onDelete={handleDelete}
                        />
                      ))}
                    </SortableContext>
                  </DroppableColumn>
                </div>
              ))}
            </div>
            <DragOverlay>
              {activeDeal ? (
                <Card className="shadow-lg w-[280px]">
                  <CardContent className="p-4">
                    <div className="flex items-start gap-2">
                      <GripVertical className="h-4 w-4 mt-0.5 text-muted-foreground" />
                      <div>
                        <p className="font-medium text-sm">{activeDeal.title}</p>
                        <p className="text-lg font-bold text-primary">
                          ${activeDeal.value.toLocaleString()}
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ) : null}
            </DragOverlay>
          </DndContext>
        ) : (
          <Card>
            <CardContent className="p-0">
              <table className="w-full">
                <thead>
                  <tr className="border-b text-left text-sm text-muted-foreground">
                    <th className="p-4">Title</th>
                    <th className="p-4">Value</th>
                    <th className="p-4">Stage</th>
                    <th className="p-4">Close Date</th>
                    <th className="p-4 w-16"></th>
                  </tr>
                </thead>
                <tbody>
                  {data?.items.map((d) => {
                    const stageInfo = stages.find((s) => s.value === d.stage);
                    return (
                      <tr key={d.id} className="border-b hover:bg-muted/50">
                        <td className="p-4 font-medium">{d.title}</td>
                        <td className="p-4">${d.value.toLocaleString()}</td>
                        <td className="p-4">
                          <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${stageInfo?.color || ""}`}>
                            {stageInfo?.label || d.stage}
                          </span>
                        </td>
                        <td className="p-4 text-sm">{d.expected_close_date ? new Date(d.expected_close_date).toLocaleDateString() : "-"}</td>
                        <td className="p-4">
                          <Button variant="ghost" size="icon" onClick={() => handleDelete(d.id)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                        </td>
                      </tr>
                    );
                  })}
                  {data?.items.length === 0 && (
                    <tr><td colSpan={5} className="p-8 text-center text-muted-foreground">No deals found</td></tr>
                  )}
                </tbody>
              </table>
            </CardContent>
          </Card>
        )}
      </div>
    </AppShell>
  );
}
