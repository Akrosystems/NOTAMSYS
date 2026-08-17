"use client";

import { ScanLine, UploadCloud } from "lucide-react";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { createRequest, uploadAttachment } from "@/lib/api";
import { emptyNotamRequestForm, NotamRequestFields, toNotamRequestInput, validateNotamRequestForm, type NotamRequestFormState } from "./notam-request-fields";

export function IntakeForm() {
  const [form, setForm] = useState<NotamRequestFormState>(emptyNotamRequestForm);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const router = useRouter();

  const patch = (next: Partial<NotamRequestFormState>) => setForm((current) => ({ ...current, ...next }));

  const start = async () => {
    setError(null);
    const validationError = validateNotamRequestForm(form);
    if (validationError) return setError(validationError);
    setBusy(true);
    try {
      const created = await createRequest(toNotamRequestInput(form, file ? "upload" : "hand_delivery"));
      if (file) await uploadAttachment(created.id, file);
      router.push(`/requests/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit the request.");
      setBusy(false);
    }
  };

  return <div className="intake-layout"><section className="panel intake-panel">
    <div className="panel-heading"><div><p className="eyebrow">New intake</p><h1>Process a NOTAM request</h1><p>GCAA-AIS-NTM-FR01, digitized field-for-field. Attach the original document as evidence if one exists.</p></div></div>
    <button className="upload-zone" onClick={() => input.current?.click()}><UploadCloud/><strong>{file?.name ?? "Attach source document (optional)"}</strong><span>{file ? `${Math.round(file.size / 1024)} KB · ready for secure hashing` : "PDF, JPG, PNG or DOCX · maximum 20 MB"}</span><input ref={input} hidden type="file" accept=".pdf,.jpg,.jpeg,.png,.doc,.docx" onChange={(event) => setFile(event.target.files?.[0] ?? null)}/></button>
    <NotamRequestFields form={form} onChange={patch}/>
    {error ? <p className="form-error">{error}</p> : null}
    <div className="action-bar"><button className="button primary" onClick={start} disabled={busy}>{busy ? "Securing evidence…" : "Start controlled processing"}</button></div>
  </section><aside className="panel intake-help"><ScanLine/><h2>Evidence-first ingestion</h2><p>NOTAMSYS hashes and preserves the original request before extraction. OCR/NLP suggestions never overwrite source evidence.</p><ul><li>Immediate receipt acknowledgement</li><li>Malware and file-type screening</li><li>Field-level confidence scores</li><li>Mandatory officer confirmation</li></ul></aside></div>;
}
