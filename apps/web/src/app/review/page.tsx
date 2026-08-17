import { CheckCircle2 } from "lucide-react";
import { ModulePage } from "@/components/module-page";
import { QueueTable } from "@/components/queue-table";
import { getRequests } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ReviewPage() {
  const [pending, changesRequested] = await Promise.all([
    getRequests("review"),
    getRequests("changes_requested")
  ]);
  const critical = pending.filter((item) => item.safety_critical);

  return (
    <ModulePage
      eyebrow="Four-eyes control"
      title="Specialist review"
      copy="Compare evidence, rule decisions and the transmission message before electronic approval. A preparer can never approve their own draft."
      icon={CheckCircle2}
      cards={[
        {
          metric: String(pending.length).padStart(2, "0"),
          title: "Approval queue",
          copy: "Independent review of the request source, draft, qualifiers, sequence and formatted output."
        },
        {
          metric: String(critical.length).padStart(2, "0"),
          title: "Safety-critical pending",
          copy: "Requests flagged safety-critical at intake, awaiting the same mandatory gates."
        },
        {
          metric: String(changesRequested.length).padStart(2, "0"),
          title: "Returned for correction",
          copy: "Drafts sent back to the preparing officer, awaiting revision before re-submission."
        }
      ]}
    >
      <QueueTable requests={pending} />
    </ModulePage>
  );
}
