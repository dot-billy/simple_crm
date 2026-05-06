"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { apiFetch } from "@/lib/api";

interface SearchResults {
  contacts: Array<{ id: string; first_name: string; last_name: string; email: string }>;
  companies: Array<{ id: string; name: string; domain: string }>;
  deals: Array<{ id: string; title: string; value: number; stage: string }>;
  tasks: Array<{ id: string; title: string; status: string }>;
}

export function SearchModal() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResults | null>(null);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef<NodeJS.Timeout | null>(null);
  const router = useRouter();

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  const doSearch = useCallback(async (q: string) => {
    if (!q.trim()) {
      setResults(null);
      return;
    }
    setLoading(true);
    try {
      const data = await apiFetch<SearchResults>(`/api/search?q=${encodeURIComponent(q)}`);
      setResults(data);
    } catch {
      setResults(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleChange = (value: string) => {
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doSearch(value), 300);
  };

  const navigate = (path: string) => {
    setOpen(false);
    setQuery("");
    setResults(null);
    router.push(path);
  };

  const handleOpenChange = (nextOpen: boolean) => {
    setOpen(nextOpen);
    if (!nextOpen) {
      setQuery("");
      setResults(null);
    }
  };

  const hasResults =
    results &&
    (results.contacts.length > 0 ||
      results.companies.length > 0 ||
      results.deals.length > 0 ||
      results.tasks.length > 0);

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="top-[20%] translate-y-0 sm:max-w-lg p-0 gap-0">
        <DialogTitle className="sr-only">Search</DialogTitle>
        <div className="flex items-center border-b px-3">
          <Search className="mr-2 h-4 w-4 shrink-0 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => handleChange(e.target.value)}
            placeholder="Search contacts, companies, deals, tasks..."
            className="border-0 focus-visible:ring-0 focus-visible:ring-offset-0"
            autoFocus
          />
        </div>

        <div className="max-h-[300px] overflow-y-auto p-2">
          {loading && (
            <p className="py-6 text-center text-sm text-muted-foreground">Searching...</p>
          )}

          {!loading && query && !hasResults && (
            <p className="py-6 text-center text-sm text-muted-foreground">No results found.</p>
          )}

          {!loading && hasResults && (
            <div className="space-y-3">
              {results.contacts.length > 0 && (
                <ResultGroup label="Contacts">
                  {results.contacts.map((c) => (
                    <ResultItem
                      key={c.id}
                      type="Contact"
                      name={`${c.first_name} ${c.last_name}`}
                      onClick={() => navigate(`/contacts`)}
                    />
                  ))}
                </ResultGroup>
              )}

              {results.companies.length > 0 && (
                <ResultGroup label="Companies">
                  {results.companies.map((c) => (
                    <ResultItem
                      key={c.id}
                      type="Company"
                      name={c.name}
                      onClick={() => navigate(`/companies`)}
                    />
                  ))}
                </ResultGroup>
              )}

              {results.deals.length > 0 && (
                <ResultGroup label="Deals">
                  {results.deals.map((d) => (
                    <ResultItem
                      key={d.id}
                      type="Deal"
                      name={`${d.title} — $${d.value.toLocaleString()}`}
                      onClick={() => navigate(`/deals`)}
                    />
                  ))}
                </ResultGroup>
              )}

              {results.tasks.length > 0 && (
                <ResultGroup label="Tasks">
                  {results.tasks.map((t) => (
                    <ResultItem
                      key={t.id}
                      type="Task"
                      name={t.title}
                      onClick={() => navigate(`/tasks`)}
                    />
                  ))}
                </ResultGroup>
              )}
            </div>
          )}

          {!loading && !query && (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Type to search...
            </p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function ResultGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-1 px-2 text-xs font-medium text-muted-foreground">{label}</p>
      {children}
    </div>
  );
}

function ResultItem({ type, name, onClick }: { type: string; name: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent"
    >
      <Badge variant="secondary" className="text-xs">
        {type}
      </Badge>
      <span className="truncate">{name}</span>
    </button>
  );
}
