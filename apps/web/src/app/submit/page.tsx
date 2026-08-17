"use client";
import { ArrowLeft, CheckCircle2, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import { useBranding } from "@/components/branding-context";
import { emptyNotamRequestForm, NotamRequestFields, toNotamRequestInput, validateNotamRequestForm, type NotamRequestFormState } from "@/components/notam-request-fields";
import { createPublicRequest, uploadPublicAttachment } from "@/lib/api";

export default function SubmitPage() {
  const branding = useBranding();
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [referenceNumber, setReferenceNumber] = useState("");
  const [form, setForm] = useState<NotamRequestFormState>(emptyNotamRequestForm);
  const [file, setFile] = useState<File | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const patch = (next: Partial<NotamRequestFormState>) => setForm((current) => ({ ...current, ...next }));

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    const validationError = validateNotamRequestForm(form);
    if (validationError) return setError(validationError);
    setBusy(true);
    try {
      const created = await createPublicRequest(toNotamRequestInput(form, "portal"));
      if (file) await uploadPublicAttachment(created.id, file);
      setReferenceNumber(created.request_number);
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit the request.");
    } finally {
      setBusy(false);
    }
  };

  return <div className="public-shell"><header><Link href="/">{branding.logo_url ? <img className="brand-mark" src={branding.logo_url} alt={branding.org_name}/> : <span className="brand-mark">{branding.org_name.charAt(0).toUpperCase()}</span>}<strong>{branding.org_name}</strong></Link><span>GCAA Aeronautical Information Service</span></header><main>{done ? <section className="public-card confirmation"><CheckCircle2/><p className="eyebrow">Submission recorded</p><h1>Request received securely</h1><p>Reference <strong>{referenceNumber}</strong> has been issued. AIS will acknowledge receipt and may request clarification before publication.</p><Link className="button primary" href="/">Return to {branding.org_name}</Link></section> : <section className="public-card"><Link className="back-link" href="/"><ArrowLeft/>Back to operations</Link><p className="eyebrow">Authorized originator service</p><h1>Submit a NOTAM request</h1><p className="lead">GCAA-AIS-NTM-FR01, digitized field-for-field. Submission does not constitute publication -- one subject and one condition per request.</p><form className="public-form" onSubmit={submit}>
    <NotamRequestFields form={form} onChange={patch}/>
    <label className="wide file-field">Supporting evidence (optional)<input ref={input} type="file" accept=".pdf,.jpg,.jpeg,.png,.doc,.docx" onChange={(event) => setFile(event.target.files?.[0] ?? null)}/></label>
    <div className="public-security wide"><ShieldCheck/><span><strong>Controlled submission</strong>Your identity, authority, source evidence and every amendment are retained in the audit record.</span></div>
    {error ? <p className="form-error wide">{error}</p> : null}
    <button className="button primary wide" type="submit" disabled={busy}>{busy ? "Submitting…" : "Submit NOTAM request"}</button>
  </form></section>}</main><footer>{branding.org_name} · Built by AkroSystems · Times shown in UTC</footer></div>;
}
