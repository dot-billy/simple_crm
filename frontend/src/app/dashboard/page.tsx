"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import { Users, Building2, Handshake, DollarSign } from "lucide-react";

interface DashboardData {
  total_contacts: number;
  total_companies: number;
  total_deals: number;
  total_deal_value: number;
  deals_by_stage: Record<string, number>;
  recent_activities: Array<{ id: string; type: string; subject: string; activity_date: string }>;
  upcoming_tasks: Array<{ id: string; title: string; status: string; due_date: string | null }>;
}

const stageLabels: Record<string, string> = {
  lead: "Lead",
  qualified: "Qualified",
  proposal: "Proposal",
  negotiation: "Negotiation",
  closed_won: "Closed Won",
  closed_lost: "Closed Lost",
};

const stageColors: Record<string, string> = {
  lead: "bg-blue-100 text-blue-800",
  qualified: "bg-yellow-100 text-yellow-800",
  proposal: "bg-purple-100 text-purple-800",
  negotiation: "bg-orange-100 text-orange-800",
  closed_won: "bg-green-100 text-green-800",
  closed_lost: "bg-red-100 text-red-800",
};

export default function DashboardPage() {
  const { token } = useAuth();
  const [data, setData] = useState<DashboardData | null>(null);

  useEffect(() => {
    if (token) {
      apiFetch<DashboardData>("/api/dashboard", { token }).then(setData);
    }
  }, [token]);

  return (
    <AppShell>
      <div className="space-y-6">
        <h2 className="text-3xl font-bold">Dashboard</h2>

        {/* Stats cards */}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Contacts</CardTitle>
              <Users className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">{data?.total_contacts ?? "..."}</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Companies</CardTitle>
              <Building2 className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">{data?.total_companies ?? "..."}</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Deals</CardTitle>
              <Handshake className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">{data?.total_deals ?? "..."}</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Pipeline Value</CardTitle>
              <DollarSign className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">
                {data ? `$${data.total_deal_value.toLocaleString()}` : "..."}
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Pipeline + Recent */}
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Pipeline breakdown */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Pipeline by Stage</CardTitle>
            </CardHeader>
            <CardContent>
              {data?.deals_by_stage && Object.keys(data.deals_by_stage).length > 0 ? (
                <div className="space-y-3">
                  {Object.entries(data.deals_by_stage).map(([stage, count]) => (
                    <div key={stage} className="flex items-center justify-between">
                      <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ${stageColors[stage] || ""}`}>
                        {stageLabels[stage] || stage}
                      </span>
                      <span className="text-sm font-medium">{count}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No deals yet</p>
              )}
            </CardContent>
          </Card>

          {/* Recent activities */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Recent Activities</CardTitle>
            </CardHeader>
            <CardContent>
              {data?.recent_activities && data.recent_activities.length > 0 ? (
                <div className="space-y-3">
                  {data.recent_activities.map((a) => (
                    <div key={a.id} className="flex items-center gap-3">
                      <Badge variant="outline" className="capitalize">{a.type}</Badge>
                      <span className="flex-1 truncate text-sm">{a.subject}</span>
                      <span className="text-xs text-muted-foreground">
                        {new Date(a.activity_date).toLocaleDateString()}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No recent activities</p>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Upcoming tasks */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Upcoming Tasks</CardTitle>
          </CardHeader>
          <CardContent>
            {data?.upcoming_tasks && data.upcoming_tasks.length > 0 ? (
              <div className="space-y-2">
                {data.upcoming_tasks.map((t) => (
                  <div key={t.id} className="flex items-center justify-between rounded-md border p-3">
                    <span className="text-sm">{t.title}</span>
                    <div className="flex items-center gap-2">
                      <Badge variant="secondary" className="capitalize">{t.status.replace("_", " ")}</Badge>
                      {t.due_date && (
                        <span className="text-xs text-muted-foreground">
                          {new Date(t.due_date).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No upcoming tasks</p>
            )}
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
