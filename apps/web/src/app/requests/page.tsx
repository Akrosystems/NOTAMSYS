import { Inbox } from "lucide-react";
import { ModulePage } from "@/components/module-page";
import { QueueTable } from "@/components/queue-table";
import { getRequests } from "@/lib/api";

export const dynamic = "force-dynamic";

function ageLabel(receivedAt: string): string {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(receivedAt).getTime()) / 60000));
  if (minutes < 60) return `${minutes} MIN`;
  if (minutes < 1440) return `${Math.round(minutes / 60)} HR`;
  return `${Math.round(minutes / 1440)} D`;
}

export default async function RequestsPage() {
  const requests = await getRequests();
  const awaitingTriage = requests.filter((item) => item.status === "received").length;
  const oldest = requests.reduce<string | null>((acc, item) => (!acc || item.received_at < acc ? item.received_at : acc), null);
  return <ModulePage eyebrow="Unified intake" title="Request inbox" copy="Acknowledge, classify and assign every source without losing the original evidence." icon={Inbox} cards={[
    { metric: `${String(requests.length).padStart(2, "0")} ACTIVE`, title: "Unified queue", copy: "Portal, AFTN, email, upload and hand-delivered requests share one traceable intake path." },
    { metric: `${String(awaitingTriage).padStart(2, "0")} NEW`, title: "Awaiting triage", copy: "Determine operational significance and the correct Series A or B distribution." },
    { metric: oldest ? ageLabel(oldest) : "—", title: "Oldest request", copy: "Safety-critical and ageing requests remain visible against operational SLAs." }
  ]}><QueueTable requests={requests}/></ModulePage>;
}
