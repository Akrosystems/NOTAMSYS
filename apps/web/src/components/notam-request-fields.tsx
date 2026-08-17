"use client";

import type { LimitType, LocationType, NotamRequestInput, RequestedKind } from "@/lib/types";

// Field-for-field state matching GCAA-AIS-NTM-FR01 (NOTAM Request Form).
// Shared between the authenticated officer intake (/requests/new) and the
// public originator intake (/submit) so the two forms can't drift out of
// sync with each other or with the paper form both replace.
export interface NotamRequestFormState {
  originatorName: string;
  originatorEmail: string;
  originatorOrganisation: string;
  originatorPhone: string;
  originatorReference: string;
  locationType: LocationType;
  locationIndicator: string;
  requestedKind: RequestedKind;
  referencedNotamNumber: string;
  startAt: string;
  endAt: string;
  endConfirmed: boolean;
  endPermanent: boolean;
  endEstimated: boolean;
  periodsOfActivity: string;
  rawText: string;
  lowerLimitSfc: boolean;
  lowerLimitValue: string;
  lowerLimitType: LimitType | "";
  upperLimitUnl: boolean;
  upperLimitValue: string;
  upperLimitType: LimitType | "";
  requestedSeries: "" | "A" | "B";
}

export const emptyNotamRequestForm: NotamRequestFormState = {
  originatorName: "", originatorEmail: "", originatorOrganisation: "", originatorPhone: "", originatorReference: "",
  locationType: "AD", locationIndicator: "", requestedKind: "NOTAMN", referencedNotamNumber: "",
  startAt: "", endAt: "", endConfirmed: false, endPermanent: false, endEstimated: false,
  periodsOfActivity: "", rawText: "",
  lowerLimitSfc: false, lowerLimitValue: "", lowerLimitType: "",
  upperLimitUnl: false, upperLimitValue: "", upperLimitType: "",
  requestedSeries: ""
};

export function toNotamRequestInput(form: NotamRequestFormState, source: NotamRequestInput["source"]): NotamRequestInput {
  return {
    source,
    originator_name: form.originatorName.trim(),
    originator_email: form.originatorEmail.trim() || undefined,
    originator_organisation: form.originatorOrganisation.trim() || undefined,
    originator_phone: form.originatorPhone.trim() || undefined,
    originator_reference: form.originatorReference.trim() || undefined,
    location_type: form.locationType,
    location_indicator: form.locationIndicator.trim(),
    requested_kind: form.requestedKind,
    referenced_notam_number: form.referencedNotamNumber.trim() || undefined,
    start_at: form.startAt ? new Date(`${form.startAt}:00Z`).toISOString() : undefined,
    end_at: form.endAt ? new Date(`${form.endAt}:00Z`).toISOString() : undefined,
    end_confirmed: form.endConfirmed,
    end_permanent: form.endPermanent,
    end_estimated: form.endEstimated,
    periods_of_activity: form.periodsOfActivity.trim() || undefined,
    raw_text: form.rawText.trim(),
    lower_limit_sfc: form.lowerLimitSfc,
    lower_limit_value: form.lowerLimitValue.trim() || undefined,
    lower_limit_type: form.lowerLimitType || undefined,
    upper_limit_unl: form.upperLimitUnl,
    upper_limit_value: form.upperLimitValue.trim() || undefined,
    upper_limit_type: form.upperLimitType || undefined,
    requested_series: form.requestedSeries || undefined
  };
}

export function validateNotamRequestForm(form: NotamRequestFormState): string | null {
  if (form.originatorName.trim().length < 2) return "Originator's Name is required.";
  if (!form.locationIndicator.trim()) return "Item A) Location is required.";
  if ((form.locationType === "AD" || form.locationType === "FIR") && !/^[A-Za-z]{4}$/.test(form.locationIndicator.trim())) {
    return `${form.locationType} location must be a 4-letter ICAO indicator.`;
  }
  if ((form.requestedKind === "NOTAMR" || form.requestedKind === "NOTAMC") && !form.referencedNotamNumber.trim()) {
    return "NOTAM Series & No./Year is required for Replace or Cancel.";
  }
  if (form.rawText.trim().length < 5) {
    return form.requestedKind === "NOTAMC" ? "Item E) First Line is required." : "Item E) Full Text is required.";
  }
  return null;
}

export function NotamRequestFields({ form, onChange }: { form: NotamRequestFormState; onChange: (patch: Partial<NotamRequestFormState>) => void }) {
  const isCancel = form.requestedKind === "NOTAMC";
  return <div className="notam-form-fields">
    <fieldset className="nrf-item">
      <legend>Item A) Location</legend>
      <div className="nrf-location-row">
        {(["AD", "FIR", "AIRSPACE"] as LocationType[]).map((type) => (
          <label key={type} className="nrf-radio"><input type="radio" name="locationType" checked={form.locationType === type} onChange={() => onChange({ locationType: type })}/>{type === "AIRSPACE" ? "Airspace" : type}</label>
        ))}
        <input className="nrf-location-value" required placeholder={form.locationType === "AIRSPACE" ? "e.g. Accra TMA" : "e.g. DGAA"} value={form.locationIndicator} onChange={(event) => onChange({ locationIndicator: event.target.value })}/>
      </div>
    </fieldset>

    <fieldset className="nrf-item nrf-kind">
      <legend>Type of NOTAM</legend>
      <label className="nrf-radio-row"><input type="radio" name="requestedKind" checked={form.requestedKind === "NOTAMN"} onChange={() => onChange({ requestedKind: "NOTAMN", referencedNotamNumber: "" })}/><strong>NOTAM N</strong> New</label>
      <label className="nrf-radio-row"><input type="radio" name="requestedKind" checked={form.requestedKind === "NOTAMR"} onChange={() => onChange({ requestedKind: "NOTAMR" })}/><strong>NOTAM R</strong> Replace (extend/amend)
        {form.requestedKind === "NOTAMR" ? <input className="nrf-inline-input" placeholder="NOTAM Series & No./Year" value={form.referencedNotamNumber} onChange={(event) => onChange({ referencedNotamNumber: event.target.value })}/> : null}
      </label>
      <label className="nrf-radio-row"><input type="radio" name="requestedKind" checked={form.requestedKind === "NOTAMC"} onChange={() => onChange({ requestedKind: "NOTAMC", endAt: "", endPermanent: false, endEstimated: false })}/><strong>NOTAM C</strong> Cancel <small>(Item B must be with immediate effect)</small>
        {form.requestedKind === "NOTAMC" ? <input className="nrf-inline-input" placeholder="NOTAM Series & No./Year" value={form.referencedNotamNumber} onChange={(event) => onChange({ referencedNotamNumber: event.target.value })}/> : null}
      </label>
    </fieldset>

    <div className="field-grid two">
      <label>Item B) Start time (UTC)<input required type="datetime-local" value={form.startAt} onChange={(event) => onChange({ startAt: event.target.value })}/></label>
      {!isCancel ? <label>Item C) End time (UTC) <small>leave blank for PERM</small><input type="datetime-local" disabled={form.endPermanent} value={form.endAt} onChange={(event) => onChange({ endAt: event.target.value })}/></label> : null}
    </div>
    {!isCancel ? <div className="nrf-end-qualifiers">
      <label className="nrf-check"><input type="checkbox" checked={form.endConfirmed} onChange={(event) => onChange({ endConfirmed: event.target.checked })}/>Confirmed</label>
      <label className="nrf-check"><input type="checkbox" checked={form.endPermanent} onChange={(event) => onChange({ endPermanent: event.target.checked, endAt: event.target.checked ? "" : form.endAt, endEstimated: event.target.checked ? false : form.endEstimated })}/>Permanent (PERM)</label>
      <label className="nrf-check"><input type="checkbox" checked={form.endEstimated} onChange={(event) => onChange({ endEstimated: event.target.checked, endPermanent: event.target.checked ? false : form.endPermanent })}/>Estimated (EST) <small>(requires replacement or cancellation)</small></label>
    </div> : null}

    <label className="nrf-wide">Item D) Periods of Activity <small>(optional)</small><textarea rows={2} placeholder="e.g. DAILY 0600-1800" value={form.periodsOfActivity} onChange={(event) => onChange({ periodsOfActivity: event.target.value })}/></label>

    <label className="nrf-wide">Item E) {isCancel ? "First Line (of Cancellation NOTAM)" : "Full Text (For New/Replacement NOTAM)"}<textarea required rows={5} placeholder="Affected facility, condition, limits and schedule. Indicate coordinates if location is not in AIP." value={form.rawText} onChange={(event) => onChange({ rawText: event.target.value })}/></label>

    <div className="field-grid two">
      <fieldset className="nrf-item">
        <legend>Item F) Lower Limit <small>(optional)</small></legend>
        <label className="nrf-check"><input type="checkbox" checked={form.lowerLimitSfc} onChange={(event) => onChange({ lowerLimitSfc: event.target.checked, lowerLimitValue: event.target.checked ? "" : form.lowerLimitValue })}/>SFC</label>
        <span className="nrf-or">or</span>
        <input className="nrf-limit-value" placeholder="value" disabled={form.lowerLimitSfc} value={form.lowerLimitValue} onChange={(event) => onChange({ lowerLimitValue: event.target.value })}/>
        <select value={form.lowerLimitType} onChange={(event) => onChange({ lowerLimitType: event.target.value as LimitType | "" })}>
          <option value="">Type…</option><option value="FL">Flight Level</option><option value="AGL">Feet AGL</option><option value="AMSL">Feet AMSL</option>
        </select>
      </fieldset>
      <fieldset className="nrf-item">
        <legend>Item G) Upper Limit <small>(optional)</small></legend>
        <label className="nrf-check"><input type="checkbox" checked={form.upperLimitUnl} onChange={(event) => onChange({ upperLimitUnl: event.target.checked, upperLimitValue: event.target.checked ? "" : form.upperLimitValue })}/>UNL</label>
        <span className="nrf-or">or</span>
        <input className="nrf-limit-value" placeholder="value" disabled={form.upperLimitUnl} value={form.upperLimitValue} onChange={(event) => onChange({ upperLimitValue: event.target.value })}/>
        <select value={form.upperLimitType} onChange={(event) => onChange({ upperLimitType: event.target.value as LimitType | "" })}>
          <option value="">Type…</option><option value="FL">Flight Level</option><option value="AGL">Feet AGL</option><option value="AMSL">Feet AMSL</option>
        </select>
      </fieldset>
    </div>

    <div className="field-grid two">
      <label>Originator&apos;s Name<input required value={form.originatorName} onChange={(event) => onChange({ originatorName: event.target.value })}/></label>
      <label>Email<input type="email" value={form.originatorEmail} onChange={(event) => onChange({ originatorEmail: event.target.value })}/></label>
      <label>Organisation/Rank<input value={form.originatorOrganisation} onChange={(event) => onChange({ originatorOrganisation: event.target.value })}/></label>
      <label>Reference Number<input value={form.originatorReference} onChange={(event) => onChange({ originatorReference: event.target.value })}/></label>
      <label>Phone Number<input value={form.originatorPhone} onChange={(event) => onChange({ originatorPhone: event.target.value })}/></label>
      <label>Requested series<select value={form.requestedSeries} onChange={(event) => onChange({ requestedSeries: event.target.value as "" | "A" | "B" })}><option value="">Let AIS determine</option><option value="A">Series A</option><option value="B">Series B</option></select></label>
    </div>
  </div>;
}
