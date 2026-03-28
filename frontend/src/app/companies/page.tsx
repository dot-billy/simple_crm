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
import { Plus, Search, Download, Upload, Trash2 } from "lucide-react";

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
  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState({ name: "", domain: "", industry: "", size: "", phone: "" });

  const load = useCallback(() => {
    apiFetch<PaginatedCompanies>(`/api/companies?page=${page}&search=${encodeURIComponent(search)}`).then(setData);
  }, [page, search]);

  useEffect(() => { load(); }, [load]);

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

        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
            <table className="w-full min-w-[600px]">
              <thead>
                <tr className="border-b text-left text-sm text-muted-foreground">
                  <th className="p-4">Name</th>
                  <th className="p-4">Domain</th>
                  <th className="p-4">Industry</th>
                  <th className="p-4">Size</th>
                  <th className="p-4">Tags</th>
                  <th className="p-4 w-16"></th>
                </tr>
              </thead>
              <tbody>
                {data?.items.map((c) => (
                  <tr key={c.id} className="border-b hover:bg-muted/50">
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
                  <tr><td colSpan={6} className="p-8 text-center text-muted-foreground">No companies found</td></tr>
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
