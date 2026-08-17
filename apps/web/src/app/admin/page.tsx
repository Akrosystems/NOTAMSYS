import { ArrowRight, PlugZap, ShieldAlert, UserCog } from "lucide-react";
import Link from "next/link";
import { AdminConsole } from "@/components/admin-console";
import { BrandingConsole } from "@/components/branding-console";
import { getBranding, getSystemStatus, listUsers } from "@/lib/api";

export const dynamic = "force-dynamic";

const CONFIG_ROWS: { label: string; key: "environment" | "publication_mode" | "aip_provider" | "ocr_engine" | "storage_backend" | "public_intake_enabled" | "extraction_enabled"; envVar: string }[] = [
  { label: "Environment", key: "environment", envVar: "NOTAMSYS_ENVIRONMENT" },
  { label: "Publication mode", key: "publication_mode", envVar: "NOTAMSYS_PUBLICATION_MODE" },
  { label: "AIP reference data provider", key: "aip_provider", envVar: "NOTAMSYS_AIP_PROVIDER" },
  { label: "OCR engine", key: "ocr_engine", envVar: "NOTAMSYS_OCR_ENGINE" },
  { label: "Extraction enabled", key: "extraction_enabled", envVar: "NOTAMSYS_EXTRACTION_ENABLED" },
  { label: "Storage backend", key: "storage_backend", envVar: "NOTAMSYS_STORAGE_BACKEND" },
  { label: "Public intake enabled", key: "public_intake_enabled", envVar: "NOTAMSYS_PUBLIC_INTAKE_ENABLED" }
];

export default async function AdminPage() {
  try {
    const [users, status, branding] = await Promise.all([listUsers(), getSystemStatus(), getBranding()]);
    return (
      <div className="page-container">
        <section className="module-hero">
          <span><UserCog /></span>
          <div>
            <p className="eyebrow">Superadmin</p>
            <h1>Admin console</h1>
            <p>
              User management, ruleset activation, delivery retry and platform branding are the
              real, non-fabricated admin control surface. There is no &quot;connect to AFTN&quot;
              button because no such live circuit is configured yet -- channel adapters and the
              configuration below are controlled by environment variables on the API server,
              changed at deploy time and taking effect on restart. Branding, further down, is the
              exception: it&apos;s genuinely live and editable from this screen.
            </p>
          </div>
        </section>
        <BrandingConsole initialBranding={branding} />
        <section className="panel admin-config-panel">
          <div className="panel-heading">
            <div><h2>Live configuration</h2><p>Read from the running API right now -- not hardcoded here</p></div>
            <Link className="button secondary" href="/integrations">Per-channel status <ArrowRight/></Link>
          </div>
          <div className="config-rows">
            {CONFIG_ROWS.map((row) => <div className="config-row" key={row.key}>
              <span>{row.label}</span>
              <strong>{String(status[row.key])}</strong>
              <code>{row.envVar}</code>
            </div>)}
          </div>
          <div className="admin-config-footer"><PlugZap/><span>To change any of these, set the environment variable on the API process (see <code>.env.example</code> and <code>docs/OPERATIONAL_BOUNDARY.md</code>) and restart <code>uvicorn</code>. There is currently no in-app write path for these -- they gate capabilities that need real infrastructure (a Tesseract binary, an AFTN circuit, an SMTP relay) that a UI toggle can&apos;t conjure into existing.</span></div>
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
