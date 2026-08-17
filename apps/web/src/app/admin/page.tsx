import { ShieldAlert, UserCog } from "lucide-react";
import { AdminConsole } from "@/components/admin-console";
import { listUsers } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function AdminPage() {
  try {
    const users = await listUsers();
    return (
      <div className="page-container">
        <section className="module-hero">
          <span><UserCog /></span>
          <div>
            <p className="eyebrow">Superadmin</p>
            <h1>Admin console</h1>
            <p>
              User management, ruleset activation and delivery retry are the real, non-fabricated
              admin control surface -- see the Integrations page for what&apos;s live versus
              simulated. There is no &quot;connect to AFTN&quot; button because no such live
              circuit is configured yet; channel adapters are set via environment variables at
              deploy time (see docs/OPERATIONAL_BOUNDARY.md).
            </p>
          </div>
        </section>
        <AdminConsole initialUsers={users} />
      </div>
    );
  } catch {
    return (
      <div className="page-container">
        <section className="module-hero">
          <span><ShieldAlert /></span>
          <div>
            <p className="eyebrow">Superadmin</p>
            <h1>Access denied</h1>
            <p>The admin console is restricted to the System Administrator role. The backend rejected this request.</p>
          </div>
        </section>
      </div>
    );
  }
}
