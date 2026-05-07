"use client";

import { useEffect, useState, useCallback } from "react";
import { apiFetch } from "@/lib/api";
import { MessageSquare, Mail, CheckSquare } from "lucide-react";
import { Button } from "@/components/ui/button";

interface TimelineItem {
  id: string;
  type: "activity" | "email" | "task";
  title: string;
  description: string | null;
  date: string;
  metadata: Record<string, unknown>;
}

interface TimelineResponse {
  items: TimelineItem[];
  total: number;
  page: number;
  pages: number;
}

const typeConfig: Record<
  TimelineItem["type"],
  { icon: typeof MessageSquare; color: string; bg: string }
> = {
  activity: { icon: MessageSquare, color: "text-indigo-600", bg: "bg-indigo-100" },
  email: { icon: Mail, color: "text-blue-600", bg: "bg-blue-100" },
  task: { icon: CheckSquare, color: "text-green-600", bg: "bg-green-100" },
};

interface TimelineProps {
  contactId?: string;
  companyId?: string;
}

export function Timeline({ contactId, companyId }: TimelineProps) {
  const [items, setItems] = useState<TimelineItem[]>([]);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);

  const basePath = contactId
    ? `/api/contacts/${contactId}/timeline`
    : `/api/companies/${companyId}/timeline`;

  const load = useCallback(
    async (pageNum: number) => {
      setLoading(true);
      try {
        const res = await apiFetch<TimelineResponse>(
          `${basePath}?per_page=50&page=${pageNum}`
        );
        if (pageNum === 1) {
          setItems(res.items);
        } else {
          setItems((prev) => [...prev, ...res.items]);
        }
        setHasMore(res.page < res.pages);
      } finally {
        setLoading(false);
      }
    },
    [basePath]
  );

  useEffect(() => {
    setPage(1);
    load(1);
  }, [load]);

  function handleLoadMore() {
    const next = page + 1;
    setPage(next);
    load(next);
  }

  if (loading && items.length === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">Loading timeline...</p>;
  }

  if (!loading && items.length === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">No timeline entries yet.</p>;
  }

  return (
    <div className="space-y-0">
      <div className="relative">
        {/* Vertical line */}
        <div className="absolute left-5 top-0 bottom-0 w-px bg-border" />

        <div className="space-y-6">
          {items.map((item) => {
            const config = typeConfig[item.type] || typeConfig.activity;
            const Icon = config.icon;
            return (
              <div key={`${item.type}-${item.id}`} className="relative flex gap-4 pl-0">
                {/* Icon bubble */}
                <div
                  className={`relative z-10 flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${config.bg}`}
                >
                  <Icon className={`h-4 w-4 ${config.color}`} />
                </div>

                {/* Content */}
                <div className="min-w-0 flex-1 pt-1">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-medium truncate">{item.title}</p>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {new Date(item.date).toLocaleDateString()}
                    </span>
                  </div>
                  {item.description && (
                    <p className="mt-1 text-sm text-muted-foreground line-clamp-2">
                      {item.description}
                    </p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {hasMore && (
        <div className="pt-4 text-center">
          <Button variant="outline" size="sm" onClick={handleLoadMore} disabled={loading}>
            {loading ? "Loading..." : "Load more"}
          </Button>
        </div>
      )}
    </div>
  );
}
