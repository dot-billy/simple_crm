"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { apiFetch, apiUpload } from "@/lib/api";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, Search, Download, Upload, Trash2, ArrowUpDown, ChevronUp, ChevronDown } from "lucide-react";
import { BulkActionBar } from "@/components/bulk-action-bar";

interface Company {
  id: string;
  name: string;
  domain: string | null;
  industry: string | null;
  size: string | null;
  phone: string | null;
  tags: Array<{ id: string; name: string; color: string }>;
  created_at: string;
}

interface PaginatedCompanies {
  items: Company[];
  total: number;
  page: number;
  pages: number;
}

export default function CompaniesPage() {
  const [data, setData] = useState<PaginatedCompanies | null>(null);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState("created_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [tagFilter, setTagFilter] = useState("");
  const [industryFilter, setIndustryFilter] = useState("");
  const [tags, setTags] = useState<Array<{ id: string; name: string; color: string }>>([]);
  const [industries, setIndustries] = useState<string[]>([]);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState({ name: "", domain: "", industry: "", size: "", phone: "" });
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const load = useCallback(() => {
    const params = new URLSearchParams({
      page: String(page),
      search,
      sort_by: sortBy,
      sort_dir: sortDir,
    });
    if (tagFilter) params.set("tag_id", tagFilter);
    if (industryFilter) params.set("industry", industryFilter);
    apiFetch<PaginatedCompanies>(`/api/companies?${params}`).then(setData);
  }, [page, search, sortBy, sortDir, tagFilter, industryFilter]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    apiFetch<Array<{ id: string; name: string; color: string }>>("/api/tags").then(setTags);
    apiFetch<string[]>("/api/companies/industries").then(setIndustries);
  }, []);

  function handleSort(column: string) {
    if (sortBy === column) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortBy(column);
      setSortDir("asc");
    }
    setPage(1);
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    await apiFetch("/api/companies", { method: "POST", body: JSON.stringify(form) });
    setDialogOpen(false);
    setForm({ name: "", domain: "", industry: "", size: "", phone: "" });
    load();
  }

  async function handleDelete(id: string) {
    await apiFetch(`/api/companies/${id}`, { method: "DELETE" });
    load();
  }

  async function handleExport() {
    const res = await fetch(
      "/api/companies/export/csv",
      { credentials: "include" }
    );
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "companies.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    await apiUpload("/api/companies/import/csv", file);
    load();
  }

  return (
    <AppShell>
      <div className="space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <h2 className="text-2xl font-bold sm:text-3xl">Companies</h2>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" onClick={handleExport}>
              <Download className="mr-1 h-4 w-4" /> Export
            </Button>
            <label>
              <Button variant="outline" size="sm" asChild>
                <span><Upload className="mr-1 h-4 w-4" /> Import</span>
              </Button>
              <input type="file" accept=".csv" className="hidden" onChange={handleImport} />
            </label>
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button size="sm"><Plus className="mr-1 h-4 w-4" /> Add Company</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>New Company</DialogTitle></DialogHeader>
              <form onSubmit={handleCreate} className="space-y-4">
                <div className="space-y-2">
                  <Label>Company Name</Label>
                  <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Domain</Label>
                    <Input value={form.domain} onChange={(e) => setForm({ ...form, domain: e.target.value })} placeholder="example.com" />
                  </div>
                  <div className="space-y-2">
                    <Label>Industry</Label>
                    <Input value={form.industry} onChange={(e) => setForm({ ...form, industry: e.target.value })} />
                  </div>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Size</Label>
                    <Input value={form.size} onChange={(e) => setForm({ ...form, size: e.target.value })} placeholder="e.g. 50-100" />
                  </div>
                  <div className="space-y-2">
                    <Label>Phone</Label>
                    <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
                  </div>
                </div>
                <Button type="submit" className="w-full">Create Company</Button>
              </form>
            </DialogContent>
          </Dialog>
          </div>
        </div>

        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input placeholder="Search companies..." className="pl-10" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Select value={tagFilter || "all"} onValueChange={(v) => { setTagFilter(v === "all" ? "" : v); setPage(1); }}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="All tags" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All tags</SelectItem>
              {tags.map((t) => (
                <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={industryFilter || "all"} onValueChange={(v) => { setIndustryFilter(v === "all" ? "" : v); setPage(1); }}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="All industries" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All industries</SelectItem>
              {industries.map((i) => (
                <SelectItem key={i} value={i}>{i}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <BulkActionBar
          entity="companies"
          selectedIds={selectedIds}
          onClear={() => setSelectedIds([])}
          onApplied={load}
          actions={["add_tag", "remove_tag", "delete"]}
        />

        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
            <table className="w-full min-w-[600px]">
              <thead>
                <tr className="border-b text-left text-sm text-muted-foreground">
                  <th className="p-4 w-10">
                    <input
                      type="checkbox"
                      checked={!!data && data.items.length > 0 && data.items.every((c) => selectedIds.includes(c.id))}
                      onChange={(e) => {
                        if (!data) return;
                        if (e.target.checked) setSelectedIds(Array.from(new Set([...selectedIds, ...data.items.map((c) => c.id)])));
                        else setSelectedIds(selectedIds.filter((id) => !data.items.some((c) => c.id === id)));
                      }}
                    />
                  </th>
                  <th className="p-4">
                    <button className="flex items-center gap-1 hover:text-foreground" onClick={() => handleSort("name")}>
                      Name
                      {sortBy === "name" ? (sortDir === "asc" ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />) : <ArrowUpDown className="h-4 w-4 opacity-40" />}
                    </button>
                  </th>
                  <th className="p-4">
                    <button className="flex items-center gap-1 hover:text-foreground" onClick={() => handleSort("domain")}>
                      Domain
                      {sortBy === "domain" ? (sortDir === "asc" ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />) : <ArrowUpDown className="h-4 w-4 opacity-40" />}
                    </button>
                  </th>
                  <th className="p-4">
                    <button className="flex items-center gap-1 hover:text-foreground" onClick={() => handleSort("industry")}>
                      Industry
                      {sortBy === "industry" ? (sortDir === "asc" ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />) : <ArrowUpDown className="h-4 w-4 opacity-40" />}
                    </button>
                  </th>
                  <th className="p-4">Size</th>
                  <th className="p-4">Tags</th>
                  <th className="p-4 w-16"></th>
                </tr>
              </thead>
              <tbody>
                {data?.items.map((c) => (
                  <tr key={c.id} className="border-b hover:bg-muted/50">
                    <td className="p-4">
                      <input
                        type="checkbox"
                        checked={selectedIds.includes(c.id)}
                        onChange={(e) => {
                          if (e.target.checked) setSelectedIds([...selectedIds, c.id]);
                          else setSelectedIds(selectedIds.filter((id) => id !== c.id));
                        }}
                      />
                    </td>
                    <td className="p-4 font-medium"><Link href={`/companies/${c.id}`} className="text-primary hover:underline">{c.name}</Link></td>
                    <td className="p-4 text-sm">{c.domain || "-"}</td>
                    <td className="p-4 text-sm">{c.industry || "-"}</td>
                    <td className="p-4 text-sm">{c.size || "-"}</td>
                    <td className="p-4">
                      <div className="flex gap-1">
                        {c.tags.map((t) => (
                          <Badge key={t.id} variant="secondary" style={{ backgroundColor: t.color + "20", color: t.color }}>{t.name}</Badge>
                        ))}
                      </div>
                    </td>
                    <td className="p-4">
                      <Button variant="ghost" size="icon" onClick={() => handleDelete(c.id)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                    </td>
                  </tr>
                ))}
                {data?.items.length === 0 && (
                  <tr><td colSpan={7} className="p-8 text-center text-muted-foreground">No companies found</td></tr>
                )}
              </tbody>
            </table>
            </div>
          </CardContent>
        </Card>

        {data && data.pages > 1 && (
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">{data.total} companies total</p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
              <Button variant="outline" size="sm" disabled={page >= data.pages} onClick={() => setPage(page + 1)}>Next</Button>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
