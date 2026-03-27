"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Bell } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { apiFetch } from "@/lib/api";

interface NotificationItem {
  id: string;
  title: string;
  message: string | null;
  entity_type: string | null;
  entity_id: string | null;
  is_read: boolean;
  created_at: string;
}

interface NotificationPage {
  items: NotificationItem[];
  total: number;
  unread_count: number;
}

function timeAgo(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const seconds = Math.floor((now - then) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function NotificationBell() {
  const [unreadCount, setUnreadCount] = useState(0);
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const fetchUnreadCount = useCallback(async () => {
    try {
      const data = await apiFetch<{ unread_count: number }>("/api/notifications/unread-count");
      setUnreadCount(data.unread_count);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    fetchUnreadCount();
    const interval = setInterval(fetchUnreadCount, 30000);
    return () => clearInterval(interval);
  }, [fetchUnreadCount]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  const loadNotifications = async () => {
    setLoading(true);
    try {
      const data = await apiFetch<NotificationPage>("/api/notifications?per_page=20");
      setNotifications(data.items);
      setUnreadCount(data.unread_count);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  const handleToggle = () => {
    const nextOpen = !open;
    setOpen(nextOpen);
    if (nextOpen) loadNotifications();
  };

  const markAsRead = async (id: string) => {
    try {
      await apiFetch(`/api/notifications/${id}/read`, { method: "PATCH" });
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true } : n))
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
    } catch {
      // ignore
    }
  };

  const markAllAsRead = async () => {
    try {
      await apiFetch("/api/notifications/mark-all-read", { method: "PATCH" });
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
    } catch {
      // ignore
    }
  };

  return (
    <div className="relative" ref={dropdownRef}>
      <Button variant="ghost" size="icon" className="relative" onClick={handleToggle}>
        <Bell className="h-4 w-4" />
        {unreadCount > 0 && (
          <Badge className="absolute -right-1 -top-1 h-5 min-w-[20px] items-center justify-center rounded-full px-1 text-[10px]">
            {unreadCount > 99 ? "99+" : unreadCount}
          </Badge>
        )}
      </Button>

      {open && (
        <div className="absolute bottom-full left-0 z-50 mb-2 w-80 rounded-md border bg-card shadow-lg">
          <div className="flex items-center justify-between border-b px-4 py-2">
            <p className="text-sm font-medium">Notifications</p>
            {unreadCount > 0 && (
              <button
                onClick={markAllAsRead}
                className="text-xs text-primary hover:underline"
              >
                Mark all as read
              </button>
            )}
          </div>

          <div className="max-h-[320px] overflow-y-auto">
            {loading && (
              <p className="py-6 text-center text-sm text-muted-foreground">Loading...</p>
            )}

            {!loading && notifications.length === 0 && (
              <p className="py-6 text-center text-sm text-muted-foreground">No notifications</p>
            )}

            {!loading &&
              notifications.map((n) => (
                <button
                  key={n.id}
                  onClick={() => !n.is_read && markAsRead(n.id)}
                  className={`flex w-full flex-col gap-0.5 border-b px-4 py-3 text-left transition-colors hover:bg-accent last:border-b-0 ${
                    !n.is_read ? "bg-accent/40" : ""
                  }`}
                >
                  <div className="flex items-center gap-2">
                    {!n.is_read && (
                      <span className="h-2 w-2 shrink-0 rounded-full bg-primary" />
                    )}
                    <span className="text-sm font-medium truncate">{n.title}</span>
                  </div>
                  {n.message && (
                    <p className="text-xs text-muted-foreground truncate">{n.message}</p>
                  )}
                  <p className="text-xs text-muted-foreground">{timeAgo(n.created_at)}</p>
                </button>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
