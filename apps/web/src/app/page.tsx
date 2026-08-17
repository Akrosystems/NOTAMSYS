import { Activity, CheckCircle2, Inbox, ShieldCheck, Timer, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { MetricCard } from "@/components/metric-card";
import { QueueTable } from "@/components/queue-table";
import { getAuditEvents, getCurrentUser, getDashboard, getRequests, getRuleVersions, getSystemStatus } from "@/lib/api";

// Operational data, not marketing content: must be fetched fresh on every
// request, never baked into the static build. Without this, `next build`
// tries to prerender the dashboard at build time with no backend available
// -- previously masked by lib/api.ts silently substituting demo data into
// the static export; now it fails the build loudly instead, which is correct.
export const dynamic = "force-dynamic";

function greeting(hourUtc: number): string {
  if (hourUtc < 12) return "Good morning";
  if (hourUtc < 18) return "Good afternoon";
  return "Good evening";
}

export default async function DashboardPage() {
  const [summary, requests, user, activity, activeVersions, status] = await Promise.all([
    getDashboard(),
    getRequests(),
    getCurrentUser(),
    getAuditEvents({ limit: 4 }),
    getRuleVersions().catch(() => []),
    getSystemStatus().catch(() => null)
  ]);
  const now = new Date();
  const needClassification = requests.filter((item) => item.status === "received").length;
  const safetyCriticalAwaiting = requests.filter((item) => item.status === "review" && item.safety_critical).length;
  const activeRuleset = activeVersions.find((version) => version.active) ?? null;
  const firstName = user?.full_name.split(" ")[0] ?? "";

  return <div className="page-container">
    <section className="page-header"><div><p className="eyebrow">{now.toLocaleDateString(undefined, { weekday: "long", year: "numeric", month: "long", day: "numeric", timeZone: "UTC" })}</p><h1>{greeting(now.getUTCHours())}{firstName ? `, ${firstName}` : ""}</h1><p>Operational picture for the Accra International NOTAM Office.</p></div><div className="page-actions"><Link className="button secondary" href="/submit">Public request form</Link><Link className="button primary" href="/requests/new">Process a request</Link></div></section>
    <section className="attention-banner"><TriangleAlert/><div><strong>{summary.estimated_due} estimated NOTAM require action</strong><p>Contact originators for replacement or cancellation before Item C).</p></div><Link href="/published">Open tracking</Link></section>
    <section className="metric-grid">
      <MetricCard icon={Inbox} value={summary.requests_in_queue} label="Requests in queue" detail={`${needClassification} awaiting triage`} />
      <MetricCard icon={Timer} value={summary.awaiting_specialist} label="Awaiting specialist" detail={`${safetyCriticalAwaiting} safety-critical`} tone="amber" />
      <MetricCard icon={CheckCircle2} value={summary.published_today} label="Published today" detail="Completed this session" tone="green" />
      <MetricCard icon={ShieldCheck} value={`${summary.first_pass_quality}%`} label="First-pass quality" detail="No correction cycle needed" tone="purple" />
    </section>
    <section className="dashboard-grid"><QueueTable requests={requests}/><aside className="panel activity-panel"><div className="panel-heading"><div><h2>Recent activity</h2><p>Live audit stream</p></div><Activity/></div><div className="activity-list">
      {activity.length === 0 ? <p className="empty-state">No audit events recorded yet.</p> : activity.map((event, index) => <div className="activity-row" key={event.id}><span className={`activity-dot tone-${index % 4}`}/><div><strong>{event.action.replace(/_/g, " ")}</strong><small>{event.actor_name} · {new Date(event.created_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })} UTC</small></div></div>)}
    </div><div className="shift-summary"><span><i className="live-dot"/> {status?.environment ?? "—"}</span><strong>Ruleset {activeRuleset?.version ?? "—"} · {status?.publication_mode === "simulated_sync" ? "Simulated publication" : "Live adapters"}</strong></div></aside></section>
  </div>;
}
