import { ShieldCheck } from "lucide-react";
import { getAuditEvents } from "@/lib/api";

export const dynamic = "force-dynamic";

const ACTION_LABEL: Record<string, string> = {
  request_received: "Request received",
  receipt_acknowledged: "Receipt acknowledged",
  evidence_attached: "Evidence attached",
  draft_saved: "Draft saved",
  triage_started: "Triage started",
  draft_started: "Draft started",
  draft_revision_started: "Draft revision started",
  submitted_for_review: "Submitted for review",
  changes_requested: "Changes requested",
  draft_approved: "Draft approved",
  publication_started: "Publication started",
  publication_completed: "Publication completed",
  publication_failed: "Publication failed",
  delivery_retried: "Delivery retried",
  extraction_field_accepted: "Extraction field accepted",
  extraction_rerun: "Extraction re-run",
  rule_version_activated: "Rule version activated"
};

export default async function QualityPage({
  searchParams
}: {
  searchParams: Promise<{ entity?: string }>;
}) {
  const { entity } = await searchParams;
  const events = await getAuditEvents({ entityType: entity, limit: 200 });
  const entityTypes = Array.from(new Set(events.map((event) => event.entity_type))).sort();

  return (
    <div className="page-container">
      <section className="module-hero">
        <span><ShieldCheck /></span>
        <div>
          <p className="eyebrow">Quality management system</p>
          <h1>Quality &amp; audit</h1>
          <p>Every workflow transition, evidence attachment and approval is an immutable, append-only record. This is that record, not a summary of it.</p>
        </div>
      </section>
      <section className="module-grid">
        <article className="module-card">
          <span>{events.length}</span>
          <h2>{entity ? `${entity} events shown` : "Recent events"}</h2>
          <p>Most recent first, across the entire office unless filtered below.</p>
        </article>
        <article className="module-card">
          <span>{entityTypes.length}</span>
          <h2>Entity types tracked</h2>
          <p>{entityTypes.join(", ") || "None yet"}</p>
        </article>
        <article className="module-card">
          <span>Append-only</span>
          <h2>Audit chain integrity</h2>
          <p>No update or delete path exists for audit_events -- every row is a permanent record of who did what, when.</p>
        </article>
      </section>
      <section className="panel">
        <div className="panel-heading"><div><h2>Audit trail</h2><p>Actor, action, and state transition for every tracked entity</p></div></div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr><th>Time (UTC)</th><th>Entity</th><th>Action</th><th>Actor</th><th>Transition</th></tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <tr key={event.id}>
                  <td><strong>{new Date(event.created_at).toISOString().slice(11, 19)}</strong><small>{new Date(event.created_at).toISOString().slice(0, 10)}</small></td>
                  <td>{event.entity_type}</td>
                  <td>{ACTION_LABEL[event.action] ?? event.action}</td>
                  <td><strong>{event.actor_name}</strong><small>{event.actor_role ?? ""}</small></td>
                  <td>{event.from_state && event.to_state ? <small>{event.from_state} → {event.to_state}</small> : <small>—</small>}</td>
                </tr>
              ))}
              {events.length === 0 ? <tr><td colSpan={5}><em>No audit events recorded yet.</em></td></tr> : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
