import type { WorkflowStatus } from "@/lib/types";

const labels: Record<WorkflowStatus, string> = {
  received: "Received", triage: "Triage", draft: "Drafting", review: "In review",
  changes_requested: "Correction", approved: "Approved", publishing: "Publishing",
  published: "Published", rejected: "Rejected", cancelled: "Cancelled"
};

export function StatusPill({ status }: { status: WorkflowStatus }) {
  return <span className={`status-pill status-${status}`}>{labels[status]}</span>;
}
