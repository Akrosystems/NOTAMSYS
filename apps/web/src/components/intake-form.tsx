"use client";

import { FileText, Keyboard, ScanLine, UploadCloud } from "lucide-react";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { createRequest, uploadAttachment } from "@/lib/api";

type Mode = "upload" | "form" | "raw";

export function IntakeForm() {
  const [mode, setMode] = useState<Mode>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [originatorName, setOriginatorName] = useState("");
  const [locationIndicator, setLocationIndicator] = useState("");
  const [originatorReference, setOriginatorReference] = useState("");
  const [requestedSeries, setRequestedSeries] = useState<"" | "A" | "B">("");
  const [operationalInfo, setOperationalInfo] = useState("");
  const [briefDescription, setBriefDescription] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const router = useRouter();

  const rawText = mode === "upload" ? briefDescription : operationalInfo;

  const start = async () => {
    setError(null);
    if (originatorName.trim().length < 2) return setError("Originator organization is required.");
    if (locationIndicator.trim().length !== 4) return setError("Location indicator must be 4 letters.");
    if (rawText.trim().length < 5) return setError(mode === "upload" ? "Add a brief description of the request." : "Operational information is required.");
    if (mode === "upload" && !file) return setError("Attach the source document.");
    setBusy(true);
    try {
      const created = await createRequest({
        source: mode === "upload" ? "upload" : mode === "raw" ? "raw_text" : "hand_delivery",
        originator_name: originatorName.trim(),
        location_indicator: locationIndicator.trim().toUpperCase(),
        originator_reference: originatorReference.trim() || undefined,
        raw_text: rawText.trim(),
        requested_series: requestedSeries || undefined
      });
      if (mode === "upload" && file) await uploadAttachment(created.id, file);
      router.push(`/requests/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit the request.");
      setBusy(false);
    }
  };

  return <div className="intake-layout"><section className="panel intake-panel"><div className="panel-heading"><div><p className="eyebrow">New intake</p><h1>Process a NOTAM request</h1><p>Capture digital submissions or digitize the controlled hardcopy form.</p></div></div>
    <div className="intake-tabs">
      <button className={mode === "upload" ? "active" : ""} onClick={() => setMode("upload")}><UploadCloud/><span><strong>Upload document</strong><small>Image, PDF or document</small></span></button>
      <button className={mode === "form" ? "active" : ""} onClick={() => setMode("form")}><FileText/><span><strong>Enter controlled form</strong><small>GCAA-AIS-NTM-FR01</small></span></button>
      <button className={mode === "raw" ? "active" : ""} onClick={() => setMode("raw")}><Keyboard/><span><strong>Paste raw request</strong><small>Email or AFTN text</small></span></button>
    </div>
    <div className="intake-fields"><label>Originator organization<input placeholder="Authorized organization" value={originatorName} onChange={(event) => setOriginatorName(event.target.value)}/></label><label>Location indicator<input placeholder="DGAA" maxLength={4} value={locationIndicator} onChange={(event) => setLocationIndicator(event.target.value.toUpperCase())}/></label><label>Originator reference<input placeholder="Traceable source reference" value={originatorReference} onChange={(event) => setOriginatorReference(event.target.value)}/></label><label>Requested series<select value={requestedSeries} onChange={(event) => setRequestedSeries(event.target.value as "" | "A" | "B")}><option value="">Let AIS determine</option><option value="A">Series A</option><option value="B">Series B</option></select></label></div>
    {mode === "upload" ? <><button className="upload-zone" onClick={() => input.current?.click()}><UploadCloud/><strong>{file?.name ?? "Drop request evidence here"}</strong><span>{file ? `${Math.round(file.size / 1024)} KB · ready for secure hashing` : "PDF, JPG, PNG or DOCX · maximum 20 MB"}</span><input ref={input} hidden type="file" accept=".pdf,.jpg,.jpeg,.png,.doc,.docx" onChange={(event) => setFile(event.target.files?.[0] ?? null)}/></button><div className="intake-fields"><label className="wide">Brief description<textarea placeholder="One-line summary of the request, for the record while extraction runs." value={briefDescription} onChange={(event) => setBriefDescription(event.target.value)}/></label></div></> : null}
    {mode === "form" ? <div className="intake-fields"><label className="wide">Operational information<textarea placeholder="One subject and one condition, including limits and schedule." value={operationalInfo} onChange={(event) => setOperationalInfo(event.target.value)}/></label></div> : null}
    {mode === "raw" ? <div className="raw-entry"><label>Raw request or AFTN message<textarea placeholder="Paste the received message exactly as supplied. The original is retained unchanged." value={operationalInfo} onChange={(event) => setOperationalInfo(event.target.value)}/></label></div> : null}
    {error ? <p className="form-error">{error}</p> : null}
    <div className="action-bar"><button className="button secondary" disabled={busy}>Save intake draft</button><button className="button primary" onClick={start} disabled={busy}>{busy ? "Securing evidence…" : "Start controlled processing"}</button></div>
  </section><aside className="panel intake-help"><ScanLine/><h2>Evidence-first ingestion</h2><p>NOTAMSYS hashes and preserves the original request before extraction. OCR/NLP suggestions never overwrite source evidence.</p><ul><li>Immediate receipt acknowledgement</li><li>Malware and file-type screening</li><li>Field-level confidence scores</li><li>Mandatory officer confirmation</li></ul></aside></div>;
}
