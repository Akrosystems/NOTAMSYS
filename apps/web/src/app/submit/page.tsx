"use client";
import { ArrowLeft, CheckCircle2, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import { useBranding } from "@/components/branding-context";
import { createPublicRequest, uploadPublicAttachment } from "@/lib/api";

const ACTION_LABEL: Record<string, string> = { replace: "Replace active NOTAM", cancel: "Cancel active NOTAM" };

export default function SubmitPage() {
  const branding = useBranding();
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [referenceNumber, setReferenceNumber] = useState("");
  const [originatorName, setOriginatorName] = useState("");
  const [originatorEmail, setOriginatorEmail] = useState("");
  const [locationIndicator, setLocationIndicator] = useState("");
  const [originatorReference, setOriginatorReference] = useState("");
  const [requestedSeries, setRequestedSeries] = useState<"" | "A" | "B">("");
  const [action, setAction] = useState<"new" | "replace" | "cancel">("new");
  const [effectiveFrom, setEffectiveFrom] = useState("");
  const [effectiveUntil, setEffectiveUntil] = useState("");
  const [operationalInfo, setOperationalInfo] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    if (originatorName.trim().length < 2) return setError("Organization / your name is required.");
    if (locationIndicator.trim().length !== 4) return setError("Location indicator must be 4 letters.");
    if (originatorReference.trim().length < 1) return setError("Originator reference is required.");
    if (operationalInfo.trim().length < 5) return setError("Operational information is required.");
    setBusy(true);
    const rawText = [
      operationalInfo.trim(),
      effectiveFrom ? `Requested effective from: ${effectiveFrom} UTC` : null,
      effectiveUntil ? `Requested effective until: ${effectiveUntil} UTC` : null,
      action !== "new" ? `Requested action: ${ACTION_LABEL[action]}` : null
    ].filter(Boolean).join("\n");
    try {
      const created = await createPublicRequest({
        originator_name: originatorName.trim(),
        originator_email: originatorEmail.trim() || undefined,
        location_indicator: locationIndicator.trim().toUpperCase(),
        originator_reference: originatorReference.trim(),
        raw_text: rawText,
        requested_series: requestedSeries || undefined
      });
      if (file) await uploadPublicAttachment(created.id, file);
      setReferenceNumber(created.request_number);
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit the request.");
    } finally {
      setBusy(false);
    }
  };

  return <div className="public-shell"><header><Link href="/">{branding.logo_url ? <img className="brand-mark" src={branding.logo_url} alt={branding.org_name}/> : <span className="brand-mark">{branding.org_name.charAt(0).toUpperCase()}</span>}<strong>{branding.org_name}</strong></Link><span>GCAA Aeronautical Information Service</span></header><main>{done ? <section className="public-card confirmation"><CheckCircle2/><p className="eyebrow">Submission recorded</p><h1>Request received securely</h1><p>Reference <strong>{referenceNumber}</strong> has been issued. AIS will acknowledge receipt and may request clarification before publication.</p><Link className="button primary" href="/">Return to {branding.org_name}</Link></section> : <section className="public-card"><Link className="back-link" href="/"><ArrowLeft/>Back to operations</Link><p className="eyebrow">Authorized originator service</p><h1>Submit a NOTAM request</h1><p className="lead">Submission does not constitute publication. One subject and one condition per request.</p><div className="public-steps"><span className="active">1</span><strong>Request details</strong><i/><span>2</span><strong>Verify identity</strong><i/><span>3</span><strong>Submit</strong></div><form className="public-form" onSubmit={submit}>
    <label>Organization / your name<input required placeholder="Authorized organization or your name" value={originatorName} onChange={(event) => setOriginatorName(event.target.value)}/></label>
    <label>Contact email (optional)<input type="email" placeholder="ops@example.com" value={originatorEmail} onChange={(event) => setOriginatorEmail(event.target.value)}/></label>
    <label>Requested series<select value={requestedSeries} onChange={(event) => setRequestedSeries(event.target.value as "" | "A" | "B")}><option value="">Let AIS determine</option><option value="A">Series A · International</option><option value="B">Series B · National</option></select></label>
    <label>Action<select value={action} onChange={(event) => setAction(event.target.value as "new" | "replace" | "cancel")}><option value="new">New NOTAM</option><option value="replace">Replace active NOTAM</option><option value="cancel">Cancel active NOTAM</option></select></label>
    <label>Location indicator<input required placeholder="e.g. DGAA" maxLength={4} value={locationIndicator} onChange={(event) => setLocationIndicator(event.target.value.toUpperCase())}/></label>
    <label>Originator reference<input required placeholder="Traceable reference" value={originatorReference} onChange={(event) => setOriginatorReference(event.target.value)}/></label>
    <label>Effective from (UTC)<input type="datetime-local" value={effectiveFrom} onChange={(event) => setEffectiveFrom(event.target.value)}/></label>
    <label>Effective until (UTC)<input type="datetime-local" value={effectiveUntil} onChange={(event) => setEffectiveUntil(event.target.value)}/></label>
    <label className="wide">Operational information<textarea required rows={5} placeholder="Affected facility, condition, limits and schedule." value={operationalInfo} onChange={(event) => setOperationalInfo(event.target.value)}/></label>
    <label className="wide file-field">Supporting evidence<input ref={input} type="file" accept=".pdf,.jpg,.jpeg,.png,.doc,.docx" onChange={(event) => setFile(event.target.files?.[0] ?? null)}/></label>
    <div className="public-security wide"><ShieldCheck/><span><strong>Controlled submission</strong>Your identity, authority, source evidence and every amendment are retained in the audit record.</span></div>
    {error ? <p className="form-error wide">{error}</p> : null}
    <button className="button primary wide" type="submit" disabled={busy}>{busy ? "Submitting…" : "Continue to identity verification"}</button>
  </form></section>}</main><footer>{branding.org_name} · Built by AkroSystems · Times shown in UTC</footer></div>;
}
