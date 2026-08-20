"use client";

import { ScanLine, UploadCloud } from "lucide-react";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { createRequest, previewExtraction, uploadAttachment } from "@/lib/api";
import type { ExtractionPreviewField } from "@/lib/types";
import { emptyNotamRequestForm, NotamRequestFields, toNotamRequestInput, validateNotamRequestForm, type NotamRequestFormState } from "./notam-request-fields";

// GCAA-AIS-NTM-FR01's field labels map onto the intake form -- see
// services/extraction/form_template.py (the source of these field_name
// values) and parsers.py (location_indicator, originator block). Only
// fields this form actually has are mapped; item_b/item_c use the paper
// form's split Date+Time boxes combined into a DTG (YYMMDDHHMM).
function dtgToLocalInput(dtg: string): string | null {
  if (!/^\d{10}$/.test(dtg)) return null;
  const yy = dtg.slice(0, 2), mm = dtg.slice(2, 4), dd = dtg.slice(4, 6), hh = dtg.slice(6, 8), mi = dtg.slice(8, 10);
  return `20${yy}-${mm}-${dd}T${hh}:${mi}`;
}

function applyLimit(normalized: string): { value: string; type: "" | "FL" | "AGL" | "AMSL"; special: boolean } {
  const v = normalized.toUpperCase();
  if (v === "SFC" || v === "UNL") return { value: "", type: "", special: true };
  const fl = v.match(/^FL(\d{2,3})$/);
  if (fl) return { value: fl[1], type: "FL", special: false };
  const ft = v.match(/^(\d{3,5})FT(AGL|AMSL)$/);
  if (ft) return { value: ft[1], type: ft[2] as "AGL" | "AMSL", special: false };
  return { value: v, type: "", special: false };
}

const ACTION_TO_KIND: Record<string, NotamRequestFormState["requestedKind"]> = {
  NEW: "NOTAMN", REPLACE: "NOTAMR", CANCEL: "NOTAMC"
};

function bestPerField(fields: ExtractionPreviewField[]): Map<string, ExtractionPreviewField> {
  const best = new Map<string, ExtractionPreviewField>();
  for (const field of fields) {
    if (field.normalized_value == null) continue;
    const current = best.get(field.field_name);
    if (!current || field.confidence > current.confidence) best.set(field.field_name, field);
  }
  return best;
}

// Only fills fields the officer hasn't already typed into -- a photo
// uploaded after some manual entry never overwrites what's already there.
function applyExtraction(form: NotamRequestFormState, fields: ExtractionPreviewField[]): { next: NotamRequestFormState; filled: string[] } {
  const best = bestPerField(fields);
  const next = { ...form };
  const filled: string[] = [];
  const set = (key: keyof NotamRequestFormState, value: NotamRequestFormState[keyof NotamRequestFormState], label: string) => {
    const current = next[key];
    if (current === "" || current === false) { (next[key] as typeof value) = value; filled.push(label); }
  };

  const location = best.get("location_indicator");
  if (location?.normalized_value) set("locationIndicator", location.normalized_value, "Item A) Location");

  const action = best.get("action");
  if (action?.normalized_value && ACTION_TO_KIND[action.normalized_value]) set("requestedKind", ACTION_TO_KIND[action.normalized_value], "Type of NOTAM");

  const replaces = best.get("replaces_notam_identifier");
  if (replaces?.normalized_value) set("referencedNotamNumber", replaces.normalized_value, "NOTAM Series & No./Year");

  const itemB = best.get("item_b");
  if (itemB?.normalized_value) {
    const local = dtgToLocalInput(itemB.normalized_value);
    if (local) set("startAt", local, "Item B) Start time");
  }
  const itemC = best.get("item_c");
  if (itemC?.normalized_value) {
    const local = dtgToLocalInput(itemC.normalized_value);
    if (local) set("endAt", local, "Item C) End time");
  }

  const itemE = best.get("item_e");
  if (itemE?.normalized_value) set("rawText", itemE.normalized_value, "Item E) Full Text");

  const itemF = best.get("item_f");
  if (itemF?.normalized_value) {
    const parsed = applyLimit(itemF.normalized_value);
    if (parsed.special) set("lowerLimitSfc", true, "Item F) Lower Limit");
    else if (parsed.value) { set("lowerLimitValue", parsed.value, "Item F) Lower Limit"); if (parsed.type) next.lowerLimitType = parsed.type; }
  }
  const itemG = best.get("item_g");
  if (itemG?.normalized_value) {
    const parsed = applyLimit(itemG.normalized_value);
    if (parsed.special) set("upperLimitUnl", true, "Item G) Upper Limit");
    else if (parsed.value) { set("upperLimitValue", parsed.value, "Item G) Upper Limit"); if (parsed.type) next.upperLimitType = parsed.type; }
  }

  const name = best.get("originator_name");
  if (name?.normalized_value) set("originatorName", name.normalized_value, "Originator's Name");
  const org = best.get("originator_organization");
  if (org?.normalized_value) set("originatorOrganisation", org.normalized_value, "Organisation/Rank");
  const email = best.get("originator_email");
  if (email?.normalized_value) set("originatorEmail", email.normalized_value, "Email");
  const reference = best.get("originator_reference");
  if (reference?.normalized_value) set("originatorReference", reference.normalized_value, "Reference Number");

  return { next, filled };
}

export function IntakeForm() {
  const [form, setForm] = useState<NotamRequestFormState>(emptyNotamRequestForm);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reading, setReading] = useState(false);
  const [prefillSummary, setPrefillSummary] = useState<string[] | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const router = useRouter();

  const patch = (next: Partial<NotamRequestFormState>) => setForm((current) => ({ ...current, ...next }));

  const pickFile = async (picked: File | null) => {
    setFile(picked);
    setPrefillSummary(null);
    if (!picked) return;
    setReading(true);
    try {
      const result = await previewExtraction(picked);
      const { next, filled } = applyExtraction(form, result.fields);
      setForm(next);
      setPrefillSummary(filled);
    } catch {
      // Extraction unavailable or the file couldn't be read -- fail soft.
      // The photo is still attached as evidence; the officer fills the
      // form manually exactly as before.
      setPrefillSummary([]);
    } finally {
      setReading(false);
    }
  };

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
    <div className="panel-heading"><div><p className="eyebrow">New intake</p><h1>Process a NOTAM request</h1><p>GCAA-AIS-NTM-FR01, digitized field-for-field. Photograph or attach the original document to pre-fill the form below, or fill it in by hand.</p></div></div>
    <button className="upload-zone" onClick={() => input.current?.click()} disabled={reading}><UploadCloud/><strong>{reading ? "Reading document…" : (file?.name ?? "Attach source document (optional)")}</strong><span>{file && !reading ? `${Math.round(file.size / 1024)} KB · ready for secure hashing` : "PDF, JPG, PNG or DOCX · maximum 20 MB"}</span><input ref={input} hidden type="file" accept=".pdf,.jpg,.jpeg,.png,.doc,.docx" onChange={(event) => pickFile(event.target.files?.[0] ?? null)}/></button>
    {prefillSummary && prefillSummary.length > 0 ? <p className="intake-prefill-note">Pre-filled {prefillSummary.length} field{prefillSummary.length === 1 ? "" : "s"} from the photo ({prefillSummary.join(", ")}) — please review before submitting.</p> : null}
    {prefillSummary && prefillSummary.length === 0 ? <p className="intake-prefill-note">Couldn&apos;t read this document automatically — the file is still attached as evidence; please fill the form in by hand.</p> : null}
    <NotamRequestFields form={form} onChange={patch}/>
    {error ? <p className="form-error">{error}</p> : null}
    <div className="action-bar"><button className="button primary" onClick={start} disabled={busy || reading}>{busy ? "Securing evidence…" : "Start controlled processing"}</button></div>
  </section><aside className="panel intake-help"><ScanLine/><h2>Evidence-first ingestion</h2><p>NOTAMSYS hashes and preserves the original request before extraction. A photo of a hard-copy form can pre-fill the fields below, but every value stays fully editable and the source evidence is never overwritten.</p><ul><li>Immediate receipt acknowledgement</li><li>Malware and file-type screening</li><li>Field-level confidence scores</li><li>Mandatory officer confirmation</li></ul></aside></div>;
}
