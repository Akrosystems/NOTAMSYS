"use client";

import {
  BookOpen, CheckCircle2, Database, Gauge, Inbox, PlugZap,
  Send, ShieldCheck, SquarePen, UserCog, X
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { getDashboard, getRuleVersions, getSystemStatus } from "@/lib/api";
import type { RuleVersionSummary, SystemStatus } from "@/lib/types";
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
  const [open, setOpen] = useState(false);
  const [counts, setCounts] = useState<{ requests_in_queue: number; awaiting_specialist: number } | null>(null);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [activeRuleset, setActiveRuleset] = useState<RuleVersionSummary | null>(null);
  useEffect(() => setOpen(false), [path]);
  useEffect(() => {
    if (path === "/login" || path === "/submit") return;
    getDashboard().then((summary) => setCounts(summary)).catch(() => setCounts(null));
    getSystemStatus().then(setStatus).catch(() => setStatus(null));
    getRuleVersions().then((versions) => setActiveRuleset(versions.find((v) => v.active) ?? null)).catch(() => setActiveRuleset(null));
  }, [path]);
  if (path === "/login" || path === "/submit") return <>{children}</>;
  const isActive = (href: string) => href === "/" ? path === "/" : path.startsWith(href);
  return (
    <div className="app-shell">
      <aside className={`sidebar ${open ? "is-open" : ""}`}>
        <div className="brand-row">
          <div className="brand-mark">N</div>
          <div><strong>NOTAMSYS</strong><span>Accra NOF</span></div>
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
