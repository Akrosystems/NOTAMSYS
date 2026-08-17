import { CheckCircle2, CircleAlert, PlugZap, XCircle } from "lucide-react";
import { getAipDataset, getRuleVersions, getSystemStatus } from "@/lib/api";

export const dynamic = "force-dynamic";

type State = "live" | "partial" | "stub";

function StateBadge({ state }: { state: State }) {
  const config = {
    live: { icon: CheckCircle2, label: "Live", className: "state-live" },
    partial: { icon: CircleAlert, label: "Partial", className: "state-partial" },
    stub: { icon: XCircle, label: "Not connected", className: "state-stub" }
  }[state];
  const Icon = config.icon;
  return <span className={`state-badge ${config.className}`}><Icon />{config.label}</span>;
}

export default async function IntegrationsPage() {
  const [status, aipDataset, ruleVersions] = await Promise.all([
    getSystemStatus(),
    getAipDataset().catch(() => null),
    getRuleVersions().catch(() => [])
  ]);
  const activeRuleVersion = ruleVersions.find((version) => version.active);
  const simulated = status.publication_mode === "simulated_sync";

  const rows: { title: string; detail: string; state: State }[] = [
    {
      title: "AFTN / Comsoft (CADAS)",
      detail: simulated
        ? "Simulated dev/test mode: envelopes are built and ITA-2 validated, but not transmitted anywhere."
        : "File-drop adapter: writes a validated AFTN envelope to a watched directory for manual pickup by the Comsoft terminal. No live circuit is connected.",
      state: "partial"
    },
    {
      title: "AIXM 5.1.1 / Digital NOTAM",
      detail: "Event-only profile. Real namespaced XML with geodesic circle geometry is generated per NOTAM and written to evidence storage on publish.",
      state: "live"
    },
    {
      title: "GCAA website (gcaa.com.gh/notam)",
      detail: simulated
        ? "Simulated dev/test mode: this channel always succeeds so publication can complete without a live CMS."
        : "No CMS integration exists yet -- this channel honestly fails until one is connected.",
      state: simulated ? "partial" : "stub"
    },
    {
      title: "Email distribution (aisnotam@caa.com.gh)",
      detail: simulated
        ? "Simulated dev/test mode: this channel always succeeds so publication can complete without a live SMTP relay."
        : "No SMTP relay is configured yet -- this channel honestly fails until one is connected.",
      state: simulated ? "partial" : "stub"
    },
    {
      title: "OCR / document extraction",
      detail: status.extraction_enabled
        ? `Enabled, engine: ${status.ocr_engine}. Local-only by design -- nothing leaves GCAA infrastructure.`
        : `Disabled (engine configured: ${status.ocr_engine}, local-only). Toggle via NOTAMSYS_EXTRACTION_ENABLED.`,
      state: status.extraction_enabled ? "partial" : "stub"
    },
    {
      title: "GCAA AIP reference data",
      detail: aipDataset
        ? `Dataset "${aipDataset.version}" active (source: ${aipDataset.source}). Seed data only -- coordinates are left null rather than invented until the real AIP is accessible.`
        : "No AIP dataset is active.",
      state: aipDataset?.source === "seed" ? "partial" : aipDataset ? "live" : "stub"
    }
  ];

  return (
    <div className="page-container">
      <section className="module-hero">
        <span><PlugZap /></span>
        <div>
          <p className="eyebrow">Interoperability</p>
          <h1>Connected services</h1>
          <p>What&apos;s actually live versus simulated or not yet connected -- stated plainly rather than assumed. See docs/ARCHITECTURE.md for the full operational boundary.</p>
        </div>
      </section>
      <section className="module-grid">
        <article className="module-card">
          <span>{activeRuleVersion?.version ?? "—"}</span>
          <h2>Selection criteria</h2>
          <p>{activeRuleVersion ? `${activeRuleVersion.verified_rule_count} of ${activeRuleVersion.total_rule_count} rules visually verified against Doc 8126.` : "No ruleset active."}</p>
        </article>
        <article className="module-card">
          <span>{status.publication_mode}</span>
          <h2>Publication mode</h2>
          <p>Controls whether channel adapters simulate success or attempt real (currently unconnected) delivery.</p>
        </article>
        <article className="module-card">
          <span>{status.environment}</span>
          <h2>Environment</h2>
          <p>Storage backend: {status.storage_backend}. Public intake: {status.public_intake_enabled ? "enabled" : "disabled"}.</p>
        </article>
      </section>
      <section className="panel integrations-panel">
        <div className="panel-heading"><div><h2>Channel and service status</h2><p>Updated on every page load from live configuration, not hardcoded</p></div></div>
        <div className="integration-rows">
          {rows.map((row) => (
            <div className="integration-row" key={row.title}>
              <div><strong>{row.title}</strong><p>{row.detail}</p></div>
              <StateBadge state={row.state} />
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
