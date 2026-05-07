"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { apiFetch } from "@/lib/api";
import { Users, Building2, Handshake, DollarSign, TrendingUp, Target, Clock, Trophy } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
} from "recharts";

interface DashboardCharts {
  deals_over_time: Array<{ week: string; count: number }>;
  revenue_by_stage: Record<string, number>;
  contacts_by_source: Record<string, number>;
  task_completion: Record<string, number>;
}

interface DashboardData {
  total_contacts: number;
  total_companies: number;
  total_deals: number;
  total_deal_value: number;
  deals_by_stage: Record<string, number>;
  recent_activities: Array<{ id: string; type: string; subject: string; activity_date: string }>;
  upcoming_tasks: Array<{ id: string; title: string; status: string; due_date: string | null }>;
  charts: DashboardCharts;
}

interface PipelineMetrics {
  range_days: number;
  win_rate_pct: number;
  won_count: number;
  lost_count: number;
  velocity_days: number;
  forecast: number;
  open_value: number;
  open_count: number;
  funnel: Array<{ stage: string; count: number }>;
  avg_time_in_stage_days: Record<string, number>;
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

const COLORS = ["#6366f1", "#8b5cf6", "#a78bfa", "#c4b5fd", "#22c55e", "#ef4444"];

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [metrics, setMetrics] = useState<PipelineMetrics | null>(null);
  const [rangeDays, setRangeDays] = useState("90");

  useEffect(() => {
    apiFetch<DashboardData>("/api/dashboard").then(setData);
  }, []);

  useEffect(() => {
    apiFetch<PipelineMetrics>(`/api/dashboard/pipeline-metrics?days=${rangeDays}`).then(setMetrics);
  }, [rangeDays]);

  const barChartData = data
    ? Object.entries(data.deals_by_stage).map(([stage, count]) => ({
        stage: stageLabels[stage] || stage,
        count,
      }))
    : [];

  const pieChartData = data?.charts?.contacts_by_source
    ? Object.entries(data.charts.contacts_by_source).map(([name, value]) => ({
        name,
        value,
      }))
    : [];

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

        {/* Pipeline metrics */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xl font-semibold">Pipeline Metrics</h3>
            <Select value={rangeDays} onValueChange={setRangeDays}>
              <SelectTrigger className="w-[140px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="30">Last 30 days</SelectItem>
                <SelectItem value="90">Last 90 days</SelectItem>
                <SelectItem value="180">Last 6 months</SelectItem>
                <SelectItem value="365">Last 12 months</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">Win Rate</CardTitle>
                <Trophy className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold">{metrics ? `${metrics.win_rate_pct}%` : "..."}</p>
                {metrics && (
                  <p className="text-xs text-muted-foreground">{metrics.won_count} won / {metrics.lost_count} lost</p>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">Avg Velocity</CardTitle>
                <Clock className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold">{metrics ? `${metrics.velocity_days}d` : "..."}</p>
                <p className="text-xs text-muted-foreground">Created → Won</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">Forecast</CardTitle>
                <TrendingUp className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold">{metrics ? `$${metrics.forecast.toLocaleString()}` : "..."}</p>
                {metrics && (
                  <p className="text-xs text-muted-foreground">{metrics.open_count} open · ${metrics.open_value.toLocaleString()}</p>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">Open Pipeline</CardTitle>
                <Target className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold">{metrics ? `$${metrics.open_value.toLocaleString()}` : "..."}</p>
                <p className="text-xs text-muted-foreground">Sum of open deal values</p>
              </CardContent>
            </Card>
          </div>
          {metrics && Object.keys(metrics.avg_time_in_stage_days).length > 0 && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Avg Time in Stage</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-3">
                  {Object.entries(metrics.avg_time_in_stage_days).map(([stage, days]) => (
                    <div key={stage} className="rounded-md border px-3 py-2">
                      <p className="text-xs text-muted-foreground capitalize">{stageLabels[stage] || stage}</p>
                      <p className="text-lg font-semibold">{days}d</p>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Pipeline bar chart + Recent activities */}
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Pipeline breakdown - bar chart */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Pipeline by Stage</CardTitle>
            </CardHeader>
            <CardContent>
              {barChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={250}>
                  <BarChart data={barChartData}>
                    <XAxis dataKey="stage" tick={{ fontSize: 12 }} />
                    <YAxis allowDecimals={false} />
                    <Tooltip />
                    <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
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

        {/* Deals over time + Contacts by source */}
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Deals Over Time</CardTitle>
            </CardHeader>
            <CardContent>
              {data?.charts?.deals_over_time && data.charts.deals_over_time.length > 0 ? (
                <ResponsiveContainer width="100%" height={250}>
                  <LineChart data={data.charts.deals_over_time}>
                    <XAxis dataKey="week" tick={{ fontSize: 12 }} />
                    <YAxis allowDecimals={false} />
                    <Tooltip />
                    <Line
                      type="monotone"
                      dataKey="count"
                      stroke="#6366f1"
                      strokeWidth={2}
                      dot={{ fill: "#6366f1" }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-sm text-muted-foreground">No deal history yet</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Contacts by Source</CardTitle>
            </CardHeader>
            <CardContent>
              {pieChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={250}>
                  <PieChart>
                    <Pie
                      data={pieChartData}
                      cx="50%"
                      cy="50%"
                      outerRadius={90}
                      dataKey="value"
                      nameKey="name"
                      label={({ name, percent }) =>
                        `${name} ${(percent * 100).toFixed(0)}%`
                      }
                    >
                      {pieChartData.map((_, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-sm text-muted-foreground">No contact sources yet</p>
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
