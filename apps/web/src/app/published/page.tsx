import { Send } from "lucide-react";
import { ModulePage } from "@/components/module-page";
import { QueueTable } from "@/components/queue-table";
import { getRequests } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function PublishedPage() {
  const [published, publishing] = await Promise.all([
    getRequests("published"),
    getRequests("publishing")
  ]);
  const seriesA = published.filter((item) => item.requested_series === "A").length;
  const seriesB = published.filter((item) => item.requested_series === "B").length;

  return (
    <ModulePage
      eyebrow="Distribution & monitoring"
      title="Published NOTAM"
      copy="Track per-channel delivery status (AFTN, GCAA web, email, AIXM) from the NOTAM detail page. A request only reaches Published once every required channel has acknowledged."
      icon={Send}
      cards={[
        { metric: String(seriesA).padStart(2, "0"), title: "Series A published", copy: "International distribution NOTAM published this session." },
        { metric: String(seriesB).padStart(2, "0"), title: "Series B published", copy: "Local/national distribution NOTAM published this session." },
        { metric: String(publishing.length).padStart(2, "0"), title: "Publishing in progress", copy: "Dispatched to at least one channel, awaiting acknowledgement from the rest before this counts as published." }
      ]}
    >
      <QueueTable requests={published} />
    </ModulePage>
  );
}
