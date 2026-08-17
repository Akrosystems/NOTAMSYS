"use client";

import {
  BookOpen, CheckCircle2, Database, Gauge, Inbox, PlugZap,
  Send, ShieldCheck, SquarePen, UserCog, X
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { getDashboard, getRuleVersions, getSystemStatus } from "@/lib/api";
import type { RuleVersionSummary, SystemStatus } from "@/lib/types";
import { useBranding } from "./branding-context";
import { DemoBanner } from "./demo-banner";
import { Topbar } from "./topbar";
import { useCurrentUser } from "./user-context";

const navigation = [
  { href: "/", label: "Operations", icon: Gauge },
  { href: "/requests", label: "Request inbox", icon: Inbox, countKey: "requests_in_queue" as const },
  { href: "/requests/new", label: "Prepare NOTAM", icon: SquarePen },
  { href: "/review", label: "Specialist review", icon: CheckCircle2, countKey: "awaiting_specialist" as const },
  { href: "/published", label: "Published", icon: Send }
];
const governance = [
  { href: "/quality", label: "Quality & audit", icon: ShieldCheck },
  { href: "/integrations", label: "Integrations", icon: PlugZap },
  { href: "/rules", label: "Rules library", icon: BookOpen }
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const user = useCurrentUser();
  const branding = useBranding();
  const [open, setOpen] = useState(false);
  const [counts, setCounts] = useState<{ requests_in_queue: number; awaiting_specialist: number } | null>(null);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [activeRuleset, setActiveRuleset] = useState<RuleVersionSummary | null>(null);
  const initialized = useRef(false);
  useEffect(() => setOpen(false), [path]);
  // Sidebar chrome (nav badge counts, system status, active ruleset) used
  // to refetch on every single navigation -- three extra API round trips
  // per click for data that rarely changes moment to moment. Fetch once
  // instead, guarded by a ref rather than an empty dep array: the app
  // always mounts at /login first (middleware redirects there), so a
  // true mount-once fetch would never fire since this early-returns on
  // /login -- this re-checks cheaply on each navigation until it
  // succeeds once past login, then never again.
  useEffect(() => {
    if (path === "/login" || path === "/submit" || initialized.current) return;
    initialized.current = true;
    getSystemStatus().then(setStatus).catch(() => setStatus(null));
    getRuleVersions().then((versions) => setActiveRuleset(versions.find((v) => v.active) ?? null)).catch(() => setActiveRuleset(null));
    getDashboard().then((summary) => setCounts(summary)).catch(() => setCounts(null));
  }, [path]);
  // Separate, genuinely mount-once effect for periodic count freshness --
  // counts are the one piece of sidebar chrome that's actually
  // time-sensitive; status/ruleset rarely change during a session.
  useEffect(() => {
    const timer = window.setInterval(() => {
      getDashboard().then((summary) => setCounts(summary)).catch(() => setCounts(null));
    }, 60_000);
    return () => window.clearInterval(timer);
  }, []);
  if (path === "/login" || path === "/submit") return <>{children}</>;
  const isActive = (href: string) => href === "/" ? path === "/" : path.startsWith(href);
  return (
    <div className="app-shell">
      <aside className={`sidebar ${open ? "is-open" : ""}`}>
        <div className="brand-row">
          {branding.logo_url ? <img className="brand-mark brand-logo" src={branding.logo_url} alt={branding.org_name}/> : <div className="brand-mark">{branding.org_name.charAt(0).toUpperCase()}</div>}
          <div><strong>{branding.org_name}</strong><span>{branding.org_subtitle}</span></div>
          <button className="icon-button sidebar-close" onClick={() => setOpen(false)} aria-label="Close menu"><X /></button>
        </div>
        <nav>
          <p className="nav-heading">Workspace</p>
          {navigation.map(({ href, label, icon: Icon, countKey }) => (
            <Link key={href} href={href} className={`nav-link ${isActive(href) ? "active" : ""}`}>
              <Icon /><span>{label}</span>{countKey && counts && counts[countKey] > 0 ? <em>{counts[countKey]}</em> : null}
            </Link>
          ))}
          <p className="nav-heading">Governance</p>
          {governance.map(({ href, label, icon: Icon }) => (
            <Link key={href} href={href} className={`nav-link ${isActive(href) ? "active" : ""}`}>
              <Icon /><span>{label}</span>
            </Link>
          ))}
          {user?.role === "system_admin" ? (
            <>
              <p className="nav-heading">Administration</p>
              <Link href="/admin" className={`nav-link ${isActive("/admin") ? "active" : ""}`}>
                <UserCog /><span>Admin console</span>
              </Link>
            </>
          ) : null}
        </nav>
        <div className="system-card">
          <div><i className="live-dot"/><strong>{status ? status.environment : "Connecting…"}</strong></div>
          <p>{status ? `Publication: ${status.publication_mode === "simulated_sync" ? "simulated (dev/test)" : "live adapters"}` : "Loading system status…"}</p>
          <small>{status ? `Storage: ${status.storage_backend}` : ""}</small>
        </div>
        <div className="sidebar-meta"><Database/><span>Ruleset {activeRuleset?.version ?? "—"}</span></div>
        <div className="built-by"><span>Built by</span><strong>AkroSystems</strong></div>
      </aside>
      {open ? <button className="sidebar-scrim" onClick={() => setOpen(false)} aria-label="Close navigation" /> : null}
      <div className="app-main">
        <DemoBanner />
        <Topbar onMenu={() => setOpen(true)} />
        <main>{children}</main>
      </div>
    </div>
  );
}
