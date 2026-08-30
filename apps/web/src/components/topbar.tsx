"use client";

import { Bell, Check, ChevronDown, Clock3, Copy, LogOut, Menu, Moon, Share2, Sun, Users } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { getAuditEvents, getUsersPresence, sendHeartbeat } from "@/lib/api";
import { formatUtcDateTime } from "@/lib/time";
import type { AuditEventEntry, UserPresence } from "@/lib/types";
import { useCurrentUser } from "./user-context";

const labels: Record<string, string> = {
  "/": "Operations", "/requests": "Request inbox", "/requests/new": "Prepare NOTAM",
  "/review": "Specialist review", "/published": "Published", "/quality": "Quality & audit",
  "/integrations": "Integrations", "/rules": "Rules library", "/admin": "Admin console"
};

const ROLE_LABEL: Record<string, string> = {
  originator: "Originator", ais_officer: "AIS Officer", ais_specialist: "AIS Specialist",
  nof_manager: "NOF Manager", qms_auditor: "QMS Auditor", system_admin: "System Administrator"
};

type Theme = "light" | "dark";

function currentTheme(): Theme {
  if (typeof document === "undefined") return "light";
  const stored = document.documentElement.getAttribute("data-theme");
  if (stored === "dark" || stored === "light") return stored;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("light");
  useEffect(() => setTheme(currentTheme()), []);
  const toggle = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("notamsys-theme", next); } catch { /* private browsing */ }
  };
  return (
    <button className="icon-button theme-toggle" onClick={toggle} aria-label="Toggle dark mode">
      {theme === "dark" ? <Sun /> : <Moon />}
    </button>
  );
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "") + (parts[parts.length - 1]?.[0] ?? "")).toUpperCase();
}

function formatLastSeen(ts: string | null | undefined): string {
  if (!ts) return "Never";
  const diff = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
  if (diff < 60) return "Just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function PresencePanel() {
  const [open, setOpen] = useState(false);
  const [users, setUsers] = useState<UserPresence[] | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onClickOutside = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const load = () => getUsersPresence().then(setUsers).catch(() => setUsers([]));

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next) load();
  };

  // Refresh presence list every 30s while panel is open
  useEffect(() => {
    if (!open) return;
    const timer = window.setInterval(load, 30_000);
    return () => clearInterval(timer);
  }, [open]);

  // Send heartbeat every 60s to keep current user online
  useEffect(() => {
    sendHeartbeat();
    const timer = window.setInterval(sendHeartbeat, 60_000);
    return () => clearInterval(timer);
  }, []);

  const onlineCount = users?.filter((u) => u.is_online).length ?? 0;

  return (
    <div className="presence-button" ref={ref}>
      <button className="icon-button presence-button-icon" aria-label="Team presence" onClick={toggle} id="topbar-presence-btn">
        <Users />
        {onlineCount > 0 ? <span className="online-badge" /> : null}
      </button>
      {open ? (
        <div className="presence-panel" role="dialog" aria-label="Team presence">
          <div className="presence-panel-header">
            <strong>Team Presence</strong>
            {users !== null ? (
              <span className="presence-online-count">{onlineCount} online</span>
            ) : (
              <span>Loading…</span>
            )}
          </div>
          <div className="presence-user-list">
            {users === null ? (
              <div style={{ padding: "14px", fontSize: "10px", color: "var(--muted)" }}>Loading…</div>
            ) : users.length === 0 ? (
              <div style={{ padding: "14px", fontSize: "10px", color: "var(--muted)" }}>No active users.</div>
            ) : (
              users.map((u) => {
                const statusLower = u.status_label.toLowerCase() as "online" | "away" | "offline";
                return (
                  <div className="presence-user-row" key={u.id}>
                    <div className="presence-avatar-wrap">
                      <div className="presence-avatar">{initials(u.full_name)}</div>
                      <span className={`presence-dot ${statusLower}`} />
                    </div>
                    <div className="presence-user-info">
                      <strong>{u.full_name}</strong>
                      <small>{ROLE_LABEL[u.role] ?? u.role}</small>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <span className={`presence-status-label ${statusLower}`}>{u.status_label}</span>
                      <div className="presence-last-seen">{formatLastSeen(u.last_seen_at)}</div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ShareIntakeLink() {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [url, setUrl] = useState("/submit");
  const ref = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => { if (typeof window !== "undefined") setUrl(`${window.location.origin}/submit`); }, []);
  useEffect(() => {
    const onClick = (event: MouseEvent) => { if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      inputRef.current?.select();
    }
  };
  return (
    <div className="activity-bell" ref={ref}>
      <button className="icon-button" aria-label="Share public intake link" onClick={() => setOpen((value) => !value)}><Share2/></button>
      {open ? <div className="share-dropdown">
        <strong>Public NOTAM request link</strong>
        <p>Send this to an originator who needs to submit a request -- no account required. Submissions land in the request inbox as usual.</p>
        <div className="share-link-row">
          <input ref={inputRef} readOnly value={url} onFocus={(event) => event.target.select()}/>
          <button onClick={copy}>{copied ? <Check/> : <Copy/>}{copied ? "Copied" : "Copy"}</button>
        </div>
      </div> : null}
    </div>
  );
}

function ActivityBell() {
  const [open, setOpen] = useState(false);
  const [events, setEvents] = useState<AuditEventEntry[] | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onClick = (event: MouseEvent) => { if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);
  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next && events === null) getAuditEvents({ limit: 5 }).then(setEvents).catch(() => setEvents([]));
  };
  return (
    <div className="activity-bell" ref={ref}>
      <button className="icon-button alert-button" aria-label="Recent activity" onClick={toggle}><Bell/>{events && events.length > 0 ? <i/> : null}</button>
      {open ? <div className="activity-dropdown">
        <strong>Recent activity</strong>
        {events === null ? <p>Loading…</p> : null}
        {events && events.length === 0 ? <p>No recent activity.</p> : null}
        {events?.map((event) => <div className="activity-dropdown-row" key={event.id}>
          <span>{event.action.replace(/_/g, " ")}</span>
          <small>{event.actor_name} · {formatUtcDateTime(event.created_at)}</small>
        </div>)}
      </div> : null}
    </div>
  );
}

function UserMenu() {
  const user = useCurrentUser();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onClick = (event: MouseEvent) => { if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);
  const logout = async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
    router.refresh();
  };
  if (!user) return null;
  return (
    <div className="user-menu" ref={ref}>
      <button className="user-button" onClick={() => setOpen((value) => !value)}>
        <span className="avatar">{initials(user.full_name)}</span>
        <span><strong>{user.full_name}</strong><small>{ROLE_LABEL[user.role] ?? user.role}</small></span>
        <ChevronDown/>
      </button>
      {open ? <div className="user-dropdown">
        <div className="user-dropdown-header"><strong>{user.full_name}</strong><small>{user.email}</small></div>
        <button onClick={logout}><LogOut/>Log out</button>
      </div> : null}
    </div>
  );
}

export function Topbar({ onMenu }: { onMenu: () => void }) {
  const path = usePathname();
  const [clock, setClock] = useState("--:--:--");
  useEffect(() => {
    const tick = () => setClock(new Date().toUTCString().slice(17, 25));
    tick(); const timer = window.setInterval(tick, 1000); return () => clearInterval(timer);
  }, []);
  const label = path.startsWith("/requests/") ? "NOTAM preparation" : labels[path] ?? "NOTAMSYS";
  return (
    <header className="topbar">
      <button className="icon-button mobile-menu" onClick={onMenu} aria-label="Open menu"><Menu /></button>
      <div className="breadcrumbs"><span>GCAA / Aeronautical Information Service</span><strong>{label}</strong></div>
      <div className="topbar-actions">
        <div className="utc-clock"><Clock3/><span><small>UTC</small><strong>{clock}</strong></span></div>
        <ThemeToggle />
        <PresencePanel />
        <ShareIntakeLink />
        <ActivityBell />
        <UserMenu />
      </div>
    </header>
  );
}
