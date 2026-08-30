"use client";

import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  Copy,
  ExternalLink,
  Eye,
  FileText,
  Filter,
  History,
  Mail,
  MoreHorizontal,
  RefreshCw,
  Search,
  Send,
  ShieldAlert,
  ShieldCheck,
  X
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import type { NotamLifecycleStatus, PublishedNotam } from "@/lib/types";

const STATUS_CONFIG: Record<
  NotamLifecycleStatus,
  { label: string; bg: string; color: string; border: string; desc: string }
> = {
  ACTIVE: {
    label: "Active · In Force",
    bg: "rgba(16, 185, 129, 0.12)",
    color: "#10b981",
    border: "rgba(16, 185, 129, 0.3)",
    desc: "Currently active in flight briefing bulletins"
  },
  EXPIRING_SOON: {
    label: "Expiring Soon (< 48h)",
    bg: "rgba(245, 158, 11, 0.15)",
    color: "#f59e0b",
    border: "rgba(245, 158, 11, 0.4)",
    desc: "Reaching confirmed validity end time within 48 hours"
  },
  EST_ACTIVE: {
    label: "EST · In Force",
    bg: "rgba(59, 130, 246, 0.12)",
    color: "#3b82f6",
    border: "rgba(59, 130, 246, 0.3)",
    desc: "Estimated validity active -- requires replacement/cancellation before end"
  },
  EST_EXPIRING_SOON: {
    label: "EST Review Required (< 48h)",
    bg: "rgba(239, 68, 68, 0.15)",
    color: "#ef4444",
    border: "rgba(239, 68, 68, 0.4)",
    desc: "Estimated validity expiring in < 48h -- contact originator immediately"
  },
  EST_EXPIRED: {
    label: "EST Overdue · Action Needed",
    bg: "rgba(220, 38, 38, 0.2)",
    color: "#f87171",
    border: "rgba(220, 38, 38, 0.5)",
    desc: "Estimated date passed without cancellation/replacement per Doc 8126"
  },
  PERM: {
    label: "PERM · Permanent",
    bg: "rgba(168, 85, 247, 0.12)",
    color: "#a855f7",
    border: "rgba(168, 85, 247, 0.3)",
    desc: "Permanent change -- tracked against AIP Supplement cross-reference"
  },
  EXPIRED: {
    label: "Expired",
    bg: "rgba(107, 114, 128, 0.15)",
    color: "#9ca3af",
    border: "rgba(107, 114, 128, 0.3)",
    desc: "Confirmed validity period has passed"
  },
  REPLACED: {
    label: "Replaced (Superceded)",
    bg: "rgba(99, 102, 241, 0.12)",
    color: "#818cf8",
    border: "rgba(99, 102, 241, 0.3)",
    desc: "Superceded by a subsequent NOTAMR"
  },
  CANCELLED: {
    label: "Cancelled",
    bg: "rgba(239, 68, 68, 0.12)",
    color: "#f87171",
    border: "rgba(239, 68, 68, 0.3)",
    desc: "Revoked by a subsequent NOTAMC"
  },
  CANCELLATION_NOTICE: {
    label: "Cancellation Notice",
    bg: "rgba(244, 63, 94, 0.12)",
    color: "#fb7185",
    border: "rgba(244, 63, 94, 0.3)",
    desc: "NOTAMC message published to revoke a prior NOTAM"
  },
  PUBLISHING: {
    label: "Publishing Dispatch",
    bg: "rgba(234, 179, 8, 0.15)",
    color: "#eab308",
    border: "rgba(234, 179, 8, 0.4)",
    desc: "Dispatched to publication channels, awaiting complete confirmation"
  }
};

function formatUtc(isoString?: string | null): string {
  if (!isoString) return "—";
  try {
    const d = new Date(isoString);
    if (Number.isNaN(d.valueOf())) return isoString;
    return d.toISOString().slice(0, 16).replace("T", " ") + " UTC";
  } catch {
    return isoString;
  }
}

function timeRemainingLabel(itemC?: string | null, qualifier?: string | null): string {
  if (qualifier === "PERM") return "Permanent (PERM)";
  if (!itemC) return "Indefinite";
  try {
    const end = new Date(itemC).getTime();
    const now = Date.now();
    const diffMs = end - now;
    if (diffMs <= 0) {
      const pastHours = Math.round(Math.abs(diffMs) / (1000 * 3600));
      return `Expired ${pastHours > 24 ? `${Math.round(pastHours / 24)}d ago` : `${pastHours}h ago`}`;
    }
    const totalHours = Math.round(diffMs / (1000 * 3600));
    if (totalHours < 24) {
      return `${totalHours}h remaining`;
    }
    const days = Math.floor(totalHours / 24);
    const remHours = totalHours % 24;
    return `${days}d ${remHours}h remaining`;
  } catch {
    return "—";
  }
}

export function PublishedNotamRegistry({ initialNotams }: { initialNotams: PublishedNotam[] }) {
  const [notams] = useState<PublishedNotam[]>(initialNotams);
  const [search, setSearch] = useState("");
  const [seriesFilter, setSeriesFilter] = useState<"ALL" | "A" | "B">("ALL");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [locationFilter, setLocationFilter] = useState<string>("ALL");
  const [selectedNotam, setSelectedNotam] = useState<PublishedNotam | null>(null);
  const [outreachNotam, setOutreachNotam] = useState<PublishedNotam | null>(null);
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);

  // Derive unique location indicators for filter dropdown
  const uniqueLocations = useMemo(() => {
    const set = new Set<string>();
    notams.forEach((n) => {
      if (n.item_a) set.add(n.item_a.toUpperCase());
    });
    return Array.from(set).sort();
  }, [notams]);

  // Aggregate metrics
  const metrics = useMemo(() => {
    const active = notams.filter((n) => n.is_active);
    const expiringSoon = notams.filter(
      (n) => n.is_active && (n.lifecycle_status === "EXPIRING_SOON" || n.lifecycle_status === "EST_EXPIRING_SOON")
    );
    const estReview = notams.filter(
      (n) => n.item_c_qualifier === "EST" && (n.lifecycle_status === "EST_EXPIRING_SOON" || n.lifecycle_status === "EST_EXPIRED")
    );
    const perm = notams.filter((n) => n.item_c_qualifier === "PERM");
    const replacedCancelled = notams.filter((n) => n.lifecycle_status === "REPLACED" || n.lifecycle_status === "CANCELLED");

    return {
      total: notams.length,
      activeCount: active.length,
      seriesACount: notams.filter((n) => n.series === "A").length,
      seriesBCount: notams.filter((n) => n.series === "B").length,
      expiringSoonCount: expiringSoon.length,
      estReviewCount: estReview.length,
      permCount: perm.length,
      replacedCancelledCount: replacedCancelled.length
    };
  }, [notams]);

  // Filtered dataset
  const filteredNotams = useMemo(() => {
    return notams.filter((n) => {
      if (seriesFilter !== "ALL" && n.series !== seriesFilter) return false;
      if (locationFilter !== "ALL" && n.item_a.toUpperCase() !== locationFilter) return false;

      if (statusFilter === "ACTIVE" && !n.is_active) return false;
      if (statusFilter === "EXPIRING" && n.lifecycle_status !== "EXPIRING_SOON" && n.lifecycle_status !== "EST_EXPIRING_SOON") return false;
      if (statusFilter === "EST" && !n.lifecycle_status.startsWith("EST")) return false;
      if (statusFilter === "EST_REVIEW" && n.lifecycle_status !== "EST_EXPIRING_SOON" && n.lifecycle_status !== "EST_EXPIRED") return false;
      if (statusFilter === "PERM" && n.item_c_qualifier !== "PERM") return false;
      if (statusFilter === "REPLACED_CANCELLED" && n.lifecycle_status !== "REPLACED" && n.lifecycle_status !== "CANCELLED" && n.lifecycle_status !== "CANCELLATION_NOTICE") return false;

      if (search.trim()) {
        const query = search.toLowerCase().trim();
        const searchable = [
          n.identifier,
          n.q_code,
          n.item_a,
          n.item_e,
          n.originator_name ?? "",
          n.originator_reference ?? "",
          n.prepared_by_name ?? "",
          n.approved_by_name ?? "",
          n.request_number ?? ""
        ]
          .join(" ")
          .toLowerCase();
        if (!searchable.includes(query)) return false;
      }

      return true;
    });
  }, [notams, seriesFilter, statusFilter, locationFilter, search]);

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    setCopyFeedback(label);
    setTimeout(() => setCopyFeedback(null), 2500);
  };

  const generateOutreachTemplate = (n: PublishedNotam) => {
    const isEst = n.item_c_qualifier === "EST";
    const validityText = isEst
      ? `ESTIMATED validity ending at ${formatUtc(n.item_c)}`
      : `confirmed validity ending at ${formatUtc(n.item_c)}`;

    return `Subject: URGENT: Validity Confirmation Request - NOTAM ${n.identifier} (${n.item_a} / Ref: ${n.originator_reference || "N/A"})

Dear ${n.originator_name || "NOTAM Originator"},

NOTAM ${n.identifier} issued on your request (Ref: ${n.originator_reference || "N/A"}) for location ${n.item_a} is currently in force with ${validityText}.

OPERATIONAL SUMMARY:
${n.item_e}

Under ICAO Annex 15 and ICAO Doc 8126 standards, please confirm the operational status:
1. If work/activity has concluded: Please advise so NOTAM ${n.identifier} can be CANCELLED (via NOTAMC).
2. If work continues with a new schedule: Please provide the updated period so a replacement NOTAM (NOTAMR) can be issued.
3. If estimated validity needs extension: Please provide the revised estimated date-time.

Please reply to this notice at your earliest convenience to prevent unintended expiration or bulletin discrepancies.

Best regards,
GCAA AIS NOTAM Office
Accra Flight Information Region (DGAC)`;
  };

  return (
    <div className="published-registry">
      {/* Alert Banner for EST / Expiring Action Items */}
      {metrics.estReviewCount > 0 && (
        <div className="registry-alert-banner" role="alert">
          <div className="alert-content">
            <AlertTriangle className="alert-icon" />
            <div>
              <strong>{metrics.estReviewCount} NOTAM(s) with Estimated Validity (EST) require Originator outreach</strong>
              <p>ICAO Doc 8126 mandates contacting originators before EST expiration to replace or cancel ongoing notices.</p>
            </div>
          </div>
          <button
            type="button"
            className="button secondary alert-action-btn"
            onClick={() => setStatusFilter("EST_REVIEW")}
          >
            Filter EST Action Items
          </button>
        </div>
      )}

      {/* Proactive Operational Cards */}
      <section className="module-grid registry-kpi-grid">
        <article
          className={`module-card kpi-card ${statusFilter === "ACTIVE" ? "kpi-selected" : ""}`}
          onClick={() => setStatusFilter(statusFilter === "ACTIVE" ? "ALL" : "ACTIVE")}
        >
          <div className="kpi-header">
            <span>{String(metrics.activeCount).padStart(2, "0")}</span>
            <CheckCircle2 className="kpi-icon active-icon" />
          </div>
          <h2>Active in Force</h2>
          <p>Live international &amp; local NOTAMs actively broadcast in PIB bulletins.</p>
          <small>{metrics.seriesACount} Series A · {metrics.seriesBCount} Series B</small>
        </article>

        <article
          className={`module-card kpi-card ${statusFilter === "EXPIRING" ? "kpi-selected" : ""}`}
          onClick={() => setStatusFilter(statusFilter === "EXPIRING" ? "ALL" : "EXPIRING")}
        >
          <div className="kpi-header">
            <span className={metrics.expiringSoonCount > 0 ? "warn-text" : ""}>
              {String(metrics.expiringSoonCount).padStart(2, "0")}
            </span>
            <Clock className="kpi-icon warn-icon" />
          </div>
          <h2>Expiring Soon (&lt; 48h)</h2>
          <p>Approaching end-of-validity window. Monitor for continuation requests.</p>
          <small>{metrics.expiringSoonCount > 0 ? "Action recommended" : "All schedules normal"}</small>
        </article>

        <article
          className={`module-card kpi-card ${statusFilter === "EST_REVIEW" ? "kpi-selected" : ""}`}
          onClick={() => setStatusFilter(statusFilter === "EST_REVIEW" ? "ALL" : "EST_REVIEW")}
        >
          <div className="kpi-header">
            <span className={metrics.estReviewCount > 0 ? "danger-text" : ""}>
              {String(metrics.estReviewCount).padStart(2, "0")}
            </span>
            <ShieldAlert className="kpi-icon danger-icon" />
          </div>
          <h2>EST Review Required</h2>
          <p>Estimated expiration requires originator confirmation for NOTAMR/NOTAMC.</p>
          <small>{metrics.estReviewCount > 0 ? "Originator outreach needed" : "Zero overdue EST"}</small>
        </article>

        <article
          className={`module-card kpi-card ${statusFilter === "PERM" ? "kpi-selected" : ""}`}
          onClick={() => setStatusFilter(statusFilter === "PERM" ? "ALL" : "PERM")}
        >
          <div className="kpi-header">
            <span>{String(metrics.permCount).padStart(2, "0")}</span>
            <FileText className="kpi-icon perm-icon" />
          </div>
          <h2>Permanent (PERM)</h2>
          <p>Permanent changes with mandatory AIP Supplement cross-referencing.</p>
          <small>Tracked against AIRAC cycles</small>
        </article>
      </section>

      {/* Main Panel with Filter & Search Controls */}
      <section className="panel registry-main-panel">
        <div className="panel-heading registry-heading">
          <div className="title-area">
            <h2>Published NOTAM Registry &amp; Audit Log</h2>
            <p>Comprehensive record of all published, active, replaced, and cancelled NOTAMs with complete personnel provenance.</p>
          </div>
          <div className="search-and-filters">
            <label className="search-input registry-search">
              <Search />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search identifier, Q-code, location, originator, text…"
              />
              {search ? (
                <button type="button" className="clear-search-btn" onClick={() => setSearch("")}>
                  <X size={14} />
                </button>
              ) : null}
            </label>
          </div>
        </div>

        {/* Filter Control Bar */}
        <div className="registry-filter-bar">
          <div className="filter-group series-tabs">
            <span className="filter-label"><Filter size={13} /> Series:</span>
            <button
              type="button"
              className={`filter-chip ${seriesFilter === "ALL" ? "active" : ""}`}
              onClick={() => setSeriesFilter("ALL")}
            >
              All
            </button>
            <button
              type="button"
              className={`filter-chip ${seriesFilter === "A" ? "active" : ""}`}
              onClick={() => setSeriesFilter("A")}
            >
              Series A (Intl)
            </button>
            <button
              type="button"
              className={`filter-chip ${seriesFilter === "B" ? "active" : ""}`}
              onClick={() => setSeriesFilter("B")}
            >
              Series B (Local)
            </button>
          </div>

          <div className="filter-group status-chips">
            <span className="filter-label">Status:</span>
            <button
              type="button"
              className={`filter-chip ${statusFilter === "ALL" ? "active" : ""}`}
              onClick={() => setStatusFilter("ALL")}
            >
              All Statuses
            </button>
            <button
              type="button"
              className={`filter-chip chip-active ${statusFilter === "ACTIVE" ? "active" : ""}`}
              onClick={() => setStatusFilter("ACTIVE")}
            >
              In Force ({metrics.activeCount})
            </button>
            <button
              type="button"
              className={`filter-chip chip-warn ${statusFilter === "EXPIRING" ? "active" : ""}`}
              onClick={() => setStatusFilter("EXPIRING")}
            >
              Expiring &lt;48h ({metrics.expiringSoonCount})
            </button>
            <button
              type="button"
              className={`filter-chip chip-est ${statusFilter === "EST_REVIEW" ? "active" : ""}`}
              onClick={() => setStatusFilter("EST_REVIEW")}
            >
              EST Action ({metrics.estReviewCount})
            </button>
            <button
              type="button"
              className={`filter-chip chip-perm ${statusFilter === "PERM" ? "active" : ""}`}
              onClick={() => setStatusFilter("PERM")}
            >
              PERM ({metrics.permCount})
            </button>
            <button
              type="button"
              className={`filter-chip chip-history ${statusFilter === "REPLACED_CANCELLED" ? "active" : ""}`}
              onClick={() => setStatusFilter("REPLACED_CANCELLED")}
            >
              Replaced / Cancelled ({metrics.replacedCancelledCount})
            </button>
          </div>

          <div className="filter-group location-dropdown">
            <span className="filter-label">Location:</span>
            <select value={locationFilter} onChange={(e) => setLocationFilter(e.target.value)}>
              <option value="ALL">All Stations (FIR &amp; AD)</option>
              {uniqueLocations.map((loc) => (
                <option key={loc} value={loc}>
                  {loc}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Interactive Data Table */}
        <div className="table-scroll">
          <table className="registry-table">
            <thead>
              <tr>
                <th>Identifier &amp; Type</th>
                <th>Location &amp; Q-Code</th>
                <th>Subject / Plain Text (Item E)</th>
                <th>Validity &amp; Lifecycle</th>
                <th>Prepared &amp; Approved By</th>
                <th>Timestamps (UTC)</th>
                <th>Channels</th>
                <th style={{ textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredNotams.map((notam) => {
                const statusMeta = STATUS_CONFIG[notam.lifecycle_status] || STATUS_CONFIG.ACTIVE;
                const isEst = notam.item_c_qualifier === "EST";
                const isPerm = notam.item_c_qualifier === "PERM";

                return (
                  <tr key={notam.id} className={`registry-row ${!notam.is_active ? "row-inactive" : ""}`}>
                    {/* Column 1: Identifier, Series, Message Kind, Replacement Links */}
                    <td>
                      <div className="id-cell">
                        <strong className="notam-ident">{notam.identifier}</strong>
                        <span className={`kind-pill kind-${notam.kind.toLowerCase()}`}>{notam.kind}</span>
                      </div>
                      {notam.replaces_identifier ? (
                        <small className="supersede-note">
                          Replaces <code>{notam.replaces_identifier}</code>
                        </small>
                      ) : null}
                      {notam.replaced_by_identifier ? (
                        <small className="superseded-by-note">
                          Replaced by <code>{notam.replaced_by_identifier}</code>
                        </small>
                      ) : null}
                    </td>

                    {/* Column 2: Location, FIR, Q-Code */}
                    <td>
                      <div className="location-cell">
                        <span className="location-badge">{notam.item_a}</span>
                        <code className="qcode-badge">{notam.q_code}</code>
                      </div>
                      <small className="fir-qualifiers">
                        Q) {notam.traffic}/{notam.purpose}/{notam.scope}
                      </small>
                    </td>

                    {/* Column 3: Item E Text */}
                    <td className="narrative-cell">
                      <p className="narrative-snippet" title={notam.item_e}>
                        {notam.item_e}
                      </p>
                      {notam.originator_name ? (
                        <small className="originator-tag">
                          Org: {notam.originator_name} {notam.originator_reference ? `(${notam.originator_reference})` : ""}
                        </small>
                      ) : null}
                    </td>

                    {/* Column 4: Validity & Lifecycle Status */}
                    <td>
                      <span
                        className="lifecycle-status-pill"
                        style={{
                          backgroundColor: statusMeta.bg,
                          color: statusMeta.color,
                          borderColor: statusMeta.border
                        }}
                        title={statusMeta.desc}
                      >
                        {statusMeta.label}
                      </span>
                      <div className="validity-dates">
                        <small>B: {formatUtc(notam.item_b)}</small>
                        <small>
                          C: {isPerm ? "PERM" : notam.item_c ? `${formatUtc(notam.item_c)} ${isEst ? "(EST)" : ""}` : "—"}
                        </small>
                      </div>
                      <small className="time-remaining-subtext">
                        {timeRemainingLabel(notam.item_c, notam.item_c_qualifier)}
                      </small>
                    </td>

                    {/* Column 5: Personnel Audit (Preparer & 4-Eyes Approver) */}
                    <td>
                      <div className="personnel-cell">
                        <div>
                          <strong>Prep: {notam.prepared_by_name || "AIS Officer"}</strong>
                          <small>{notam.prepared_by_role ? notam.prepared_by_role.replace("_", " ") : "preparer"}</small>
                        </div>
                        <div>
                          <strong>Appr: {notam.approved_by_name || "Specialist"}</strong>
                          <small>{notam.approved_by_role ? notam.approved_by_role.replace("_", " ") : "4-eyes approval"}</small>
                        </div>
                      </div>
                    </td>

                    {/* Column 6: Timestamps */}
                    <td>
                      <div className="timestamp-cell">
                        <div>
                          <small>Published:</small>
                          <strong>{formatUtc(notam.published_at)}</strong>
                        </div>
                        <div>
                          <small>Received:</small>
                          <span>{formatUtc(notam.received_at)}</span>
                        </div>
                      </div>
                    </td>

                    {/* Column 7: Channel Delivery Badges — one badge per unique channel */}
                    <td>
                      <div className="channel-deliveries">
                        {notam.deliveries && notam.deliveries.length > 0 ? (() => {
                          // Status priority: acknowledged > dispatching > queued > failed
                          const STATUS_PRIORITY: Record<string, number> = {
                            acknowledged: 4,
                            dispatching: 3,
                            queued: 2,
                            failed: 1,
                          };
                          const best = new Map<string, { status: string; destination: string }>();
                          for (const d of notam.deliveries) {
                            const key = d.channel.replace("GCAA_", "");
                            const existing = best.get(key);
                            const rank = STATUS_PRIORITY[d.status] ?? 0;
                            const existingRank = existing ? (STATUS_PRIORITY[existing.status] ?? 0) : -1;
                            if (!existing || rank > existingRank) {
                              best.set(key, { status: d.status, destination: d.destination });
                            }
                          }
                          return Array.from(best.entries()).map(([channel, { status, destination }]) => (
                            <span
                              key={channel}
                              className={`channel-badge status-${status}`}
                              title={`${channel}: ${status} (${destination})`}
                            >
                              {channel}
                            </span>
                          ));
                        })() : (
                          <span className="channel-badge status-acknowledged">DISPATCHED</span>
                        )}
                      </div>
                    </td>

                    {/* Column 8: Actions */}
                    <td style={{ textAlign: "right" }}>
                      <div className="action-buttons-cell">
                        {/* If EST or expiring, prominent Outreach Action */}
                        {isEst || notam.lifecycle_status === "EXPIRING_SOON" ? (
                          <button
                            type="button"
                            className="button secondary icon-action-btn"
                            title="Contact Originator for Extension / Cancellation"
                            onClick={() => setOutreachNotam(notam)}
                          >
                            <Mail size={14} />
                          </button>
                        ) : null}

                        {/* View Full NOTAM Raw Details */}
                        <button
                          type="button"
                          className="button secondary icon-action-btn"
                          title="View ICAO formatted NOTAM & AIXM details"
                          onClick={() => setSelectedNotam(notam)}
                        >
                          <Eye size={14} />
                        </button>

                        {/* Link to Request Workbench for Full History */}
                        <Link
                          href={`/requests/${notam.request_id}`}
                          className="icon-button"
                          title="Open Request Workbench & Audit History"
                        >
                          <ExternalLink size={14} />
                        </Link>
                      </div>
                    </td>
                  </tr>
                );
              })}

              {filteredNotams.length === 0 ? (
                <tr>
                  <td colSpan={8} className="empty-table-state">
                    <div className="empty-state-content">
                      <Search size={28} />
                      <p>No published NOTAMs match your active search and filter criteria.</p>
                      <button
                        type="button"
                        className="button secondary"
                        onClick={() => {
                          setSearch("");
                          setSeriesFilter("ALL");
                          setStatusFilter("ALL");
                          setLocationFilter("ALL");
                        }}
                      >
                        Reset All Filters
                      </button>
                    </div>
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        <div className="panel-footer registry-footer">
          <span>
            Showing <strong>{filteredNotams.length}</strong> of <strong>{notams.length}</strong> recorded NOTAMs
          </span>
          <div className="footer-links">
            <Link href="/quality">View Immutable System Audit Log →</Link>
          </div>
        </div>
      </section>

      {/* MODAL 1: Originator Outreach Drawer / Modal for EST & Expiring NOTAMs */}
      {outreachNotam ? (
        <div className="modal-backdrop" onClick={() => setOutreachNotam(null)}>
          <div className="modal-card outreach-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title-wrap">
                <Mail className="modal-icon" />
                <div>
                  <h3>Originator Validity Outreach</h3>
                  <p>
                    Target NOTAM: <strong>{outreachNotam.identifier}</strong> ({outreachNotam.item_a})
                  </p>
                </div>
              </div>
              <button
                type="button"
                className="icon-button close-btn"
                onClick={() => setOutreachNotam(null)}
                aria-label="Close"
              >
                <X size={18} />
              </button>
            </div>

            <div className="modal-body">
              <div className="outreach-details-card">
                <div className="detail-item">
                  <small>Originator Name</small>
                  <strong>{outreachNotam.originator_name || "GCAA Operations"}</strong>
                </div>
                <div className="detail-item">
                  <small>Contact Email</small>
                  <strong>{outreachNotam.originator_email || "operations@gcaa.com.gh"}</strong>
                </div>
                <div className="detail-item">
                  <small>Originator Reference</small>
                  <strong>{outreachNotam.originator_reference || "N/A"}</strong>
                </div>
                <div className="detail-item">
                  <small>Current Schedule</small>
                  <span className="validity-highlight">
                    {outreachNotam.item_c_qualifier === "EST" ? "EST " : ""}
                    {formatUtc(outreachNotam.item_c)}
                  </span>
                </div>
              </div>

              <div className="outreach-guidance">
                <ShieldCheck size={16} />
                <p>
                  <strong>ICAO Doc 8126 Mandatory Standard:</strong> NOTAMs issued with estimated validity (EST) must be
                  cancelled or replaced prior to the estimated date-time of expiration.
                </p>
              </div>

              <div className="email-template-box">
                <div className="template-header">
                  <span>Pre-formatted Outreach Notification</span>
                  <button
                    type="button"
                    className="button secondary copy-btn"
                    onClick={() => copyToClipboard(generateOutreachTemplate(outreachNotam), "outreach_template")}
                  >
                    <Copy size={13} />
                    {copyFeedback === "outreach_template" ? "Copied!" : "Copy Email Template"}
                  </button>
                </div>
                <pre className="template-preview">{generateOutreachTemplate(outreachNotam)}</pre>
              </div>
            </div>

            <div className="modal-footer">
              <div className="footer-actions-left">
                <Link href={`/requests/new`} className="button secondary">
                  Prepare Replacement (NOTAMR)
                </Link>
              </div>
              <div className="footer-actions-right">
                <button type="button" className="button secondary" onClick={() => setOutreachNotam(null)}>
                  Close
                </button>
                <a
                  href={`mailto:${outreachNotam.originator_email || ""}?subject=${encodeURIComponent(
                    `URGENT: Validity Confirmation Request - NOTAM ${outreachNotam.identifier} (${outreachNotam.item_a})`
                  )}&body=${encodeURIComponent(generateOutreachTemplate(outreachNotam))}`}
                  className="button primary"
                >
                  <Send size={14} /> Open in Email Client
                </a>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {/* MODAL 2: Full NOTAM Detail Viewer (ICAO Message, Personnel & AIXM Payload) */}
      {selectedNotam ? (
        <div className="modal-backdrop" onClick={() => setSelectedNotam(null)}>
          <div className="modal-card notam-detail-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title-wrap">
                <FileText className="modal-icon" />
                <div>
                  <h3>
                    NOTAM {selectedNotam.identifier} · Official Record
                  </h3>
                  <p>Accra FIR (DGAC) · Ruleset {selectedNotam.ruleset_version}</p>
                </div>
              </div>
              <button
                type="button"
                className="icon-button close-btn"
                onClick={() => setSelectedNotam(null)}
                aria-label="Close"
              >
                <X size={18} />
              </button>
            </div>

            <div className="modal-body">
              {/* Provenance and Governance Metadata */}
              <div className="provenance-grid">
                <div className="provenance-item">
                  <small>Location / Aerodrome</small>
                  <strong>{selectedNotam.item_a} (Accra FIR)</strong>
                </div>
                <div className="provenance-item">
                  <small>Q-Code &amp; Meaning</small>
                  <strong>{selectedNotam.q_code}</strong>
                </div>
                <div className="provenance-item">
                  <small>Prepared By (Officer)</small>
                  <strong>{selectedNotam.prepared_by_name || "AIS Officer"}</strong>
                </div>
                <div className="provenance-item">
                  <small>Approved By (Specialist)</small>
                  <strong>{selectedNotam.approved_by_name || "AIS Specialist"}</strong>
                </div>
                <div className="provenance-item">
                  <small>Received Time (UTC)</small>
                  <strong>{formatUtc(selectedNotam.received_at)}</strong>
                </div>
                <div className="provenance-item">
                  <small>Published Time (UTC)</small>
                  <strong>{formatUtc(selectedNotam.published_at)}</strong>
                </div>
                <div className="provenance-item">
                  <small>Originator</small>
                  <strong>{selectedNotam.originator_name || "GCAA Operations"}</strong>
                </div>
                <div className="provenance-item">
                  <small>Reference Number</small>
                  <strong>{selectedNotam.originator_reference || "N/A"}</strong>
                </div>
              </div>

              {/* Formatted ICAO Text Box */}
              <div className="transmission-box">
                <div className="transmission-box-header">
                  <span className="box-title">ICAO Transmission Format</span>
                  <button
                    type="button"
                    className="button secondary copy-btn"
                    onClick={() => copyToClipboard(selectedNotam.formatted_message, "icao_text")}
                  >
                    <Copy size={13} />
                    {copyFeedback === "icao_text" ? "Copied!" : "Copy ICAO Text"}
                  </button>
                </div>
                <pre>{selectedNotam.formatted_message}</pre>
              </div>

              {/* AIXM 5.1.1 XML Snippet (if available) */}
              {selectedNotam.aixm_xml ? (
                <div className="aixm-box">
                  <div className="transmission-box-header">
                    <span className="box-title">Digital NOTAM · AIXM 5.1.1 Event XML</span>
                    <button
                      type="button"
                      className="button secondary copy-btn"
                      onClick={() => copyToClipboard(selectedNotam.aixm_xml || "", "aixm_xml")}
                    >
                      <Copy size={13} />
                      {copyFeedback === "aixm_xml" ? "Copied!" : "Copy AIXM XML"}
                    </button>
                  </div>
                  <pre className="aixm-preview">{selectedNotam.aixm_xml}</pre>
                </div>
              ) : null}
            </div>

            <div className="modal-footer">
              <Link href={`/requests/${selectedNotam.request_id}`} className="button secondary">
                <History size={14} /> View Audit History in Workbench
              </Link>
              <button type="button" className="button primary" onClick={() => setSelectedNotam(null)}>
                Done
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
