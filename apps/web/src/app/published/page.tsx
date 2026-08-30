import { Send } from "lucide-react";
import { PublishedNotamRegistry } from "@/components/published-notam-registry";
import { getPublishedNotams } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function PublishedPage() {
  const notams = await getPublishedNotams();

  return (
    <div className="page-container published-page-container">
      <section className="module-hero">
        <span><Send /></span>
        <div>
          <p className="eyebrow">Distribution, Lifecycle &amp; Validity Monitoring</p>
          <h1>Published NOTAMs Registry</h1>
          <p>
            Real-time tracking of all active, expiring, replaced, and cancelled NOTAMs across Accra FIR (DGAC).
            Monitor validity windows, track four-eyes approvals, and conduct proactive originator outreach for EST notices.
          </p>
        </div>
      </section>

      <PublishedNotamRegistry initialNotams={notams} />
    </div>
  );
}

