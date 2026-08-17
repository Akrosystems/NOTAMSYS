import { BookOpen, ChevronLeft, ChevronRight, Search } from "lucide-react";
import Link from "next/link";
import { getRuleVersions, getRulesCatalog } from "@/lib/api";

export const dynamic = "force-dynamic";

const VERIFICATION_LABEL: Record<string, string> = {
  VERIFIED_VISUAL: "Verified",
  HAND_CURATED: "Hand-curated",
  TRANSCRIBED_UNVERIFIED: "Unverified"
};
// A page size, not a silent cap: the full catalog is already fetched in
// one request below (it's ~400KB of JSON, not worth re-fetching per page),
// so this only controls how many rows render per page -- every row stays
// reachable via Previous/Next, unlike the old fixed 150-row slice that
// just discarded anything past it with no way to see the rest.
const PAGE_SIZE = 150;

export default async function RulesPage({
  searchParams
}: {
  searchParams: Promise<{ q?: string; page?: string }>;
}) {
  const { q, page: pageParam } = await searchParams;
  const [versions, catalog] = await Promise.all([
    getRuleVersions(),
    getRulesCatalog(q ? { search: q } : undefined)
  ]);
  const active = versions.find((version) => version.active) ?? versions[0];
  const totalPages = Math.max(1, Math.ceil(catalog.length / PAGE_SIZE));
  const page = Math.min(totalPages, Math.max(1, Number(pageParam) || 1));
  const rows = catalog.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const pageLink = (target: number) => `/rules?${new URLSearchParams({ ...(q ? { q } : {}), page: String(target) })}`;

  return (
    <div className="page-container">
      <section className="module-hero">
        <span><BookOpen /></span>
        <div>
          <p className="eyebrow">Controlled knowledge</p>
          <h1>Rules library</h1>
          <p>ICAO Doc 8126 NOTAM Selection Criteria used by every automated draft validation, with per-row source citation and verification status.</p>
        </div>
      </section>
      <section className="module-grid">
        <article className="module-card">
          <span>{active?.version ?? "—"}</span>
          <h2>Active ruleset</h2>
          <p>{active?.source_document ?? "No ruleset version is active."}</p>
        </article>
        <article className="module-card">
          <span>{active ? `${active.verified_rule_count} / ${active.total_rule_count}` : "—"}</span>
          <h2>Visually verified</h2>
          <p>Rows confirmed against a rendered Doc 8126 page image, not just transcribed text.</p>
        </article>
        <article className="module-card">
          <span>{catalog.length}</span>
          <h2>{q ? "Matching rules" : "Total rules"}</h2>
          <p>{q ? `Filtered by "${q}"` : "Across all 13 NOTAM Selection Criteria categories."}</p>
        </article>
      </section>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Selection criteria catalog</h2>
            <p>Search by Q-code, subject, or condition</p>
          </div>
          <form className="search-input" method="get">
            <Search />
            <input type="search" name="q" placeholder="e.g. QMXLC, taxiway, closed" defaultValue={q ?? ""} />
          </form>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Q-code</th><th>Subject</th><th>Condition</th><th>Traffic</th>
                <th>Purpose</th><th>Scope</th><th>Source</th><th>Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((rule) => (
                <tr key={rule.q_code}>
                  <td><strong>{rule.q_code}</strong></td>
                  <td>{rule.subject}</td>
                  <td>{rule.condition}</td>
                  <td>{rule.traffic}</td>
                  <td>{rule.purpose}</td>
                  <td>{rule.scope}</td>
                  <td><small>{rule.source}</small></td>
                  <td>
                    <span className={`verification-tag verification-${rule.verification_status.toLowerCase()}`}>
                      {VERIFICATION_LABEL[rule.verification_status] ?? rule.verification_status}
                    </span>
                  </td>
                </tr>
              ))}
              {rows.length === 0 ? (
                <tr><td colSpan={8}><em>No rules match &quot;{q}&quot;. Try a Q-code, subject, or condition.</em></td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
        {catalog.length > 0 ? (
          <div className="panel-footer rules-pagination">
            <span>Showing {(page - 1) * PAGE_SIZE + 1}–{(page - 1) * PAGE_SIZE + rows.length} of {catalog.length} {q ? "matching" : "total"} rules</span>
            {totalPages > 1 ? (
              <div className="rules-pagination-controls">
                {page > 1 ? <Link className="button secondary" href={pageLink(page - 1)}><ChevronLeft/>Previous</Link> : <span className="button secondary disabled"><ChevronLeft/>Previous</span>}
                <span>Page {page} of {totalPages}</span>
                {page < totalPages ? <Link className="button secondary" href={pageLink(page + 1)}>Next<ChevronRight/></Link> : <span className="button secondary disabled">Next<ChevronRight/></span>}
              </div>
            ) : null}
          </div>
        ) : null}
      </section>
    </div>
  );
}
