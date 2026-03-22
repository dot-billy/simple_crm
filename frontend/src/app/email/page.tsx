"use client";

import { useEffect, useState, useCallback } from "react";
import DOMPurify from "dompurify";
import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { apiFetch } from "@/lib/api";
import {
  Mail,
  Send,
  RefreshCw,
  Search,
  ArrowDownLeft,
  ArrowUpRight,
  Eye,
  MousePointerClick,
  FileText,
  Trash2,
  BarChart3,
} from "lucide-react";

interface EmailMessage {
  id: string;
  gmail_message_id: string;
  gmail_thread_id: string | null;
  direction: string;
  from_email: string;
  to_emails: string;
  cc_emails: string | null;
  subject: string | null;
  snippet: string | null;
  body_html: string | null;
  contact_id: string | null;
  deal_id: string | null;
  has_tracking_pixel: boolean;
  email_date: string;
}

interface PaginatedEmails {
  items: EmailMessage[];
  total: number;
  page: number;
  pages: number;
}

interface TrackingStats {
  total_sent: number;
  total_opened: number;
  total_clicked: number;
  open_rate: number;
  click_rate: number;
}

interface TrackingEvent {
  id: string;
  email_id: string;
  event_type: string;
  url: string | null;
  ip_address: string | null;
  created_at: string;
}

interface EmailTemplate {
  id: string;
  name: string;
  subject: string;
  body_html: string;
  created_at: string;
}

interface SyncStatus {
  is_configured: boolean;
  last_sync_at: string | null;
  is_syncing: boolean;
}

type TabType = "inbox" | "compose" | "templates" | "tracking";

export default function EmailPage() {
  const [activeTab, setActiveTab] = useState<TabType>("inbox");
  const [emails, setEmails] = useState<PaginatedEmails | null>(null);
  const [search, setSearch] = useState("");
  const [directionFilter, setDirectionFilter] = useState("");
  const [page, setPage] = useState(1);
  const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [stats, setStats] = useState<TrackingStats | null>(null);
  const [templates, setTemplates] = useState<EmailTemplate[]>([]);
  const [selectedEmail, setSelectedEmail] = useState<EmailMessage | null>(null);
  const [trackingEvents, setTrackingEvents] = useState<TrackingEvent[]>([]);

  // Compose state
  const [composeOpen, setComposeOpen] = useState(false);
  const [composeForm, setComposeForm] = useState({
    to: "",
    cc: "",
    subject: "",
    body_html: "",
    enable_tracking: true,
  });
  const [sending, setSending] = useState(false);

  // Template state
  const [templateDialogOpen, setTemplateDialogOpen] = useState(false);
  const [templateForm, setTemplateForm] = useState({ name: "", subject: "", body_html: "" });

  const loadEmails = useCallback(() => {
    const params = new URLSearchParams({ page: String(page) });
    if (search) params.set("search", search);
    if (directionFilter) params.set("direction", directionFilter);
    apiFetch<PaginatedEmails>(`/api/email/messages?${params}`).then(setEmails);
  }, [page, search, directionFilter]);

  const loadSyncStatus = useCallback(() => {
    apiFetch<SyncStatus>("/api/email/sync/status").then(setSyncStatus);
  }, []);

  const loadStats = useCallback(() => {
    apiFetch<TrackingStats>("/api/email/tracking/stats").then(setStats);
  }, []);

  const loadTemplates = useCallback(() => {
    apiFetch<EmailTemplate[]>("/api/email/templates").then(setTemplates);
  }, []);

  useEffect(() => {
    loadEmails();
    loadSyncStatus();
  }, [loadEmails, loadSyncStatus]);

  useEffect(() => {
    if (activeTab === "tracking") loadStats();
    if (activeTab === "templates") loadTemplates();
  }, [activeTab, loadStats, loadTemplates]);

  async function handleSync() {
    setSyncing(true);
    try {
      await apiFetch<{ synced: number }>("/api/email/sync/trigger", {
        method: "POST",
      });
      loadEmails();
      loadSyncStatus();
    } catch (err) {
      // Sync not configured
    } finally {
      setSyncing(false);
    }
  }

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    setSending(true);
    try {
      const toList = composeForm.to.split(",").map((s) => s.trim()).filter(Boolean);
      const ccList = composeForm.cc ? composeForm.cc.split(",").map((s) => s.trim()).filter(Boolean) : [];
      await apiFetch("/api/email/send", {
        method: "POST",
        body: JSON.stringify({
          to: toList,
          cc: ccList.length > 0 ? ccList : null,
          subject: composeForm.subject,
          body_html: composeForm.body_html || `<p>${composeForm.body_html}</p>`,
          enable_tracking: composeForm.enable_tracking,
        }),
      });
      setComposeOpen(false);
      setComposeForm({ to: "", cc: "", subject: "", body_html: "", enable_tracking: true });
      loadEmails();
    } finally {
      setSending(false);
    }
  }

  async function handleCreateTemplate(e: React.FormEvent) {
    e.preventDefault();
    await apiFetch("/api/email/templates", {
      method: "POST",
      body: JSON.stringify(templateForm),
    });
    setTemplateDialogOpen(false);
    setTemplateForm({ name: "", subject: "", body_html: "" });
    loadTemplates();
  }

  async function handleDeleteTemplate(id: string) {
    await apiFetch(`/api/email/templates/${id}`, { method: "DELETE" });
    loadTemplates();
  }

  function applyTemplate(template: EmailTemplate) {
    setComposeForm({
      ...composeForm,
      subject: template.subject,
      body_html: template.body_html,
    });
    setActiveTab("compose");
    setComposeOpen(true);
  }

  async function viewEmailTracking(emailId: string) {
    const events = await apiFetch<TrackingEvent[]>(
      `/api/email/messages/${emailId}/tracking`
    );
    setTrackingEvents(events);
  }

  function parseEmails(json: string): string {
    try {
      return JSON.parse(json).join(", ");
    } catch {
      return json;
    }
  }

  const tabs: { key: TabType; label: string; icon: typeof Mail }[] = [
    { key: "inbox", label: "Inbox", icon: Mail },
    { key: "templates", label: "Templates", icon: FileText },
    { key: "tracking", label: "Tracking", icon: BarChart3 },
  ];

  return (
    <AppShell>
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-3xl font-bold">Email</h2>
          <div className="flex items-center gap-2">
            {syncStatus && (
              <span className="text-xs text-muted-foreground">
                {syncStatus.is_configured ? (
                  syncStatus.last_sync_at
                    ? `Last sync: ${new Date(syncStatus.last_sync_at).toLocaleTimeString()}`
                    : "Not synced yet"
                ) : (
                  "Gmail not configured"
                )}
              </span>
            )}
            <Button variant="outline" size="sm" onClick={handleSync} disabled={syncing}>
              <RefreshCw className={`mr-1 h-4 w-4 ${syncing ? "animate-spin" : ""}`} />
              Sync
            </Button>
            <Dialog open={composeOpen} onOpenChange={setComposeOpen}>
              <DialogTrigger asChild>
                <Button size="sm">
                  <Send className="mr-1 h-4 w-4" /> Compose
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-2xl">
                <DialogHeader>
                  <DialogTitle>Compose Email</DialogTitle>
                </DialogHeader>
                <form onSubmit={handleSend} className="space-y-4">
                  <div className="space-y-2">
                    <Label>To (comma-separated)</Label>
                    <Input
                      value={composeForm.to}
                      onChange={(e) => setComposeForm({ ...composeForm, to: e.target.value })}
                      placeholder="email@example.com"
                      required
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>CC (optional)</Label>
                    <Input
                      value={composeForm.cc}
                      onChange={(e) => setComposeForm({ ...composeForm, cc: e.target.value })}
                      placeholder="cc@example.com"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Subject</Label>
                    <Input
                      value={composeForm.subject}
                      onChange={(e) => setComposeForm({ ...composeForm, subject: e.target.value })}
                      required
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Body (HTML)</Label>
                    <textarea
                      className="flex min-h-[200px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      value={composeForm.body_html}
                      onChange={(e) => setComposeForm({ ...composeForm, body_html: e.target.value })}
                      placeholder="<p>Your email content here...</p>"
                      required
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="tracking"
                      checked={composeForm.enable_tracking}
                      onChange={(e) => setComposeForm({ ...composeForm, enable_tracking: e.target.checked })}
                      className="rounded"
                    />
                    <Label htmlFor="tracking">Enable open & click tracking</Label>
                  </div>
                  <Button type="submit" className="w-full" disabled={sending}>
                    {sending ? "Sending..." : "Send Email"}
                  </Button>
                </form>
              </DialogContent>
            </Dialog>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 border-b">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-2 border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === tab.key
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              <tab.icon className="h-4 w-4" />
              {tab.label}
            </button>
          ))}
        </div>

        {/* INBOX TAB */}
        {activeTab === "inbox" && (
          <div className="space-y-4">
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Search emails..."
                  className="pl-10"
                  value={search}
                  onChange={(e) => { setSearch(e.target.value); setPage(1); }}
                />
              </div>
              <Select value={directionFilter || "all"} onValueChange={(v) => { setDirectionFilter(v === "all" ? "" : v); setPage(1); }}>
                <SelectTrigger className="w-[140px]">
                  <SelectValue placeholder="All" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="inbound">Inbound</SelectItem>
                  <SelectItem value="outbound">Outbound</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1">
              {emails?.items.map((email) => (
                <div
                  key={email.id}
                  className="flex cursor-pointer items-center gap-3 rounded-md border p-3 hover:bg-muted/50"
                  onClick={() => setSelectedEmail(selectedEmail?.id === email.id ? null : email)}
                >
                  {email.direction === "inbound" ? (
                    <ArrowDownLeft className="h-4 w-4 text-blue-600 flex-shrink-0" />
                  ) : (
                    <ArrowUpRight className="h-4 w-4 text-green-600 flex-shrink-0" />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium truncate">
                        {email.direction === "inbound" ? email.from_email : parseEmails(email.to_emails)}
                      </span>
                      {email.has_tracking_pixel && (
                        <Eye className="h-3 w-3 text-muted-foreground flex-shrink-0" />
                      )}
                    </div>
                    <p className="text-sm truncate">{email.subject || "(no subject)"}</p>
                    <p className="text-xs text-muted-foreground truncate">{email.snippet}</p>
                  </div>
                  <span className="text-xs text-muted-foreground whitespace-nowrap">
                    {new Date(email.email_date).toLocaleDateString()}
                  </span>
                </div>
              ))}
              {emails?.items.length === 0 && (
                <Card>
                  <CardContent className="p-8 text-center text-muted-foreground">
                    No emails found. {!syncStatus?.is_configured && "Configure Gmail integration to start syncing."}
                  </CardContent>
                </Card>
              )}
            </div>

            {/* Email detail panel */}
            {selectedEmail && (
              <Card>
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <div>
                      <CardTitle className="text-lg">{selectedEmail.subject || "(no subject)"}</CardTitle>
                      <p className="text-sm text-muted-foreground mt-1">
                        From: {selectedEmail.from_email} | To: {parseEmails(selectedEmail.to_emails)}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {new Date(selectedEmail.email_date).toLocaleString()}
                      </p>
                    </div>
                    {selectedEmail.has_tracking_pixel && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => viewEmailTracking(selectedEmail.id)}
                      >
                        <Eye className="mr-1 h-4 w-4" /> Tracking
                      </Button>
                    )}
                  </div>
                </CardHeader>
                <CardContent>
                  {selectedEmail.body_html ? (
                    <div
                      className="prose prose-sm max-w-none"
                      dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(selectedEmail.body_html) }}
                    />
                  ) : (
                    <p className="text-sm whitespace-pre-wrap">{selectedEmail.snippet}</p>
                  )}

                  {trackingEvents.length > 0 && (
                    <div className="mt-4 border-t pt-4">
                      <h4 className="text-sm font-medium mb-2">Tracking Events</h4>
                      <div className="space-y-2">
                        {trackingEvents.map((ev) => (
                          <div key={ev.id} className="flex items-center gap-2 text-sm">
                            {ev.event_type === "opened" ? (
                              <Eye className="h-4 w-4 text-blue-600" />
                            ) : ev.event_type === "clicked" ? (
                              <MousePointerClick className="h-4 w-4 text-green-600" />
                            ) : (
                              <Send className="h-4 w-4 text-muted-foreground" />
                            )}
                            <span className="capitalize">{ev.event_type}</span>
                            {ev.url && <span className="text-xs text-muted-foreground truncate">({ev.url})</span>}
                            <span className="ml-auto text-xs text-muted-foreground">
                              {new Date(ev.created_at).toLocaleString()}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            {emails && emails.pages > 1 && (
              <div className="flex items-center justify-between">
                <p className="text-sm text-muted-foreground">{emails.total} emails total</p>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
                  <Button variant="outline" size="sm" disabled={page >= emails.pages} onClick={() => setPage(page + 1)}>Next</Button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* TEMPLATES TAB */}
        {activeTab === "templates" && (
          <div className="space-y-4">
            <div className="flex justify-end">
              <Dialog open={templateDialogOpen} onOpenChange={setTemplateDialogOpen}>
                <DialogTrigger asChild>
                  <Button size="sm"><FileText className="mr-1 h-4 w-4" /> New Template</Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader><DialogTitle>New Email Template</DialogTitle></DialogHeader>
                  <form onSubmit={handleCreateTemplate} className="space-y-4">
                    <div className="space-y-2">
                      <Label>Template Name</Label>
                      <Input value={templateForm.name} onChange={(e) => setTemplateForm({ ...templateForm, name: e.target.value })} required />
                    </div>
                    <div className="space-y-2">
                      <Label>Subject Line</Label>
                      <Input value={templateForm.subject} onChange={(e) => setTemplateForm({ ...templateForm, subject: e.target.value })} required />
                    </div>
                    <div className="space-y-2">
                      <Label>Body (HTML)</Label>
                      <textarea
                        className="flex min-h-[150px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                        value={templateForm.body_html}
                        onChange={(e) => setTemplateForm({ ...templateForm, body_html: e.target.value })}
                        required
                      />
                    </div>
                    <Button type="submit" className="w-full">Save Template</Button>
                  </form>
                </DialogContent>
              </Dialog>
            </div>

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {templates.map((tmpl) => (
                <Card key={tmpl.id}>
                  <CardHeader className="pb-2">
                    <div className="flex items-start justify-between">
                      <CardTitle className="text-sm">{tmpl.name}</CardTitle>
                      <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => handleDeleteTemplate(tmpl.id)}>
                        <Trash2 className="h-3 w-3 text-destructive" />
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm text-muted-foreground mb-2">Subject: {tmpl.subject}</p>
                    <Button variant="outline" size="sm" onClick={() => applyTemplate(tmpl)}>
                      Use Template
                    </Button>
                  </CardContent>
                </Card>
              ))}
              {templates.length === 0 && (
                <Card className="col-span-full">
                  <CardContent className="p-8 text-center text-muted-foreground">
                    No templates yet. Create one to speed up email composition.
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        )}

        {/* TRACKING TAB */}
        {activeTab === "tracking" && (
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">Sent (Tracked)</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-2xl font-bold">{stats?.total_sent ?? "..."}</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">Opened</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-2xl font-bold">{stats?.total_opened ?? "..."}</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">Clicked</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-2xl font-bold">{stats?.total_clicked ?? "..."}</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">Open Rate</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-2xl font-bold">{stats ? `${stats.open_rate.toFixed(1)}%` : "..."}</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">Click Rate</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-2xl font-bold">{stats ? `${stats.click_rate.toFixed(1)}%` : "..."}</p>
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardContent className="p-6">
                <p className="text-sm text-muted-foreground">
                  Tracking data is collected from emails sent with tracking enabled. Open tracking uses a 1x1 pixel,
                  and click tracking wraps links to record clicks before redirecting to the original URL.
                </p>
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </AppShell>
  );
}
