"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Check, CheckCheck, ChevronRight, FileText, History, RefreshCw, Save, ScanLine, Send, ShieldCheck, TriangleAlert, Undo2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { z } from "zod";
import type { AuditEventEntry, ExtractionRun, NotamDraftResult, NotamRequest, PublicationDelivery, RuleMatch, WorkflowStatus } from "@/lib/types";
import { acceptExtractedField, getAuditEvents, getDeliveries, getExtraction, getRequestNotam, getRuleByQcode, rerunExtraction, retryDelivery, saveDraft, workflowAction } from "@/lib/api";
import { StatusPill } from "./status-pill";
import { useCurrentUser } from "./user-context";

const schema = z.object({
  series: z.enum(["A", "B"]), kind: z.enum(["NOTAMN", "NOTAMR", "NOTAMC"]),
  fir: z.string().length(4), q_code: z.string().regex(/^Q[A-Z]{4}$/), traffic: z.string().min(1),
  purpose: z.string().min(1), scope: z.string().min(1), lower_limit: z.string().regex(/^\d{3}$/),
  upper_limit: z.string().regex(/^\d{3}$/), coordinates_radius: z.string().regex(/^\d{4}[NS]\d{5}[EW]\d{3}$/),
  item_a: z.string().min(4).max(8), item_b: z.string().min(16), item_c: z.string().min(16),
  item_c_qualifier: z.enum(["", "EST", "PERM"]), item_d: z.string(), item_e: z.string().min(3).max(1000),
  item_f: z.string(), item_g: z.string()
});
type FormData = z.infer<typeof schema>;

const defaults: FormData = {
  series:"A",kind:"NOTAMN",fir:"DGAC",q_code:"QRTCA",traffic:"IV",purpose:"BO",scope:"W",
  lower_limit:"000",upper_limit:"025",coordinates_radius:"0550N00010W010",item_a:"DGAC",
  item_b:"2026-08-17T06:00",item_c:"2026-08-20T18:00",item_c_qualifier:"",item_d:"",
  item_e:"THE FOLLOWING TEMPORARY RESTRICTED AREA ESTABLISHED DUE UNMANNED ACFT FLIGHT: CIRCLE RADIUS 10NM CENTRED ON 0550N 00010W. CTN ADVISED.",
  item_f:"SFC",item_g:"2500FT AGL"
};

const EDITABLE_STATUSES: WorkflowStatus[] = ["received", "triage", "draft", "changes_requested"];
const REVIEW_ROLES = ["ais_specialist", "nof_manager", "system_admin"];
const PUBLISH_ROLES = ["ais_officer", "ais_specialist", "nof_manager", "system_admin"];
const RETRY_ROLES = ["nof_manager", "system_admin"];
const STEP_STATE: Record<WorkflowStatus, { done: number; active: number }> = {
  received: { done: 0, active: 1 }, triage: { done: 0, active: 1 }, draft: { done: 0, active: 1 }, changes_requested: { done: 0, active: 1 },
  review: { done: 1, active: 2 }, approved: { done: 2, active: 3 }, publishing: { done: 2, active: 3 }, published: { done: 3, active: -1 },
  rejected: { done: -1, active: -1 }, cancelled: { done: -1, active: -1 }
};

function dtg(value: string){const date=new Date(`${value}:00Z`);return Number.isNaN(date.valueOf())?"YYMMDDHHMM":date.toISOString().slice(2,16).replace(/[-T:]/g,"")}
function toLocalInput(iso: string): string { return iso.slice(0, 16); }

export function NotamWorkbench({ request }: { request: NotamRequest }) {
  const router = useRouter();
  const user = useCurrentUser();
  const [tab,setTab]=useState<"editor"|"validation"|"history">("editor");
  const [notice,setNotice]=useState<string | null>(null);
  const [busy,setBusy]=useState(false);
  const [rule,setRule]=useState<RuleMatch | null>(null);
  const [ruleStatus,setRuleStatus]=useState<"idle"|"loading"|"found"|"missing">("idle");
  const [extraction,setExtraction]=useState<ExtractionRun | null>(null);
  const [extractionBusy,setExtractionBusy]=useState(false);
  const [extractionError,setExtractionError]=useState<string | null>(null);
  const [history,setHistory]=useState<AuditEventEntry[]>([]);
  const [historyLoading,setHistoryLoading]=useState(false);
  const [lastDraft,setLastDraft]=useState<NotamDraftResult | null>(null);
  const [reviewComment,setReviewComment]=useState("");
  const [deliveries,setDeliveries]=useState<PublicationDelivery[] | null>(null);
  const {register,handleSubmit,watch,reset,formState:{errors}}=useForm<FormData>({resolver:zodResolver(schema),defaultValues:defaults});
  const values=watch();
  const isEditable = EDITABLE_STATUSES.includes(request.status);

  useEffect(()=>{
    let cancelled=false;
    getRequestNotam(request.id).then((notam)=>{
      if(cancelled||!notam)return;
      setLastDraft(notam);
      if(EDITABLE_STATUSES.includes(request.status)){
        reset({
          series:notam.series,kind:notam.kind,fir:notam.fir,q_code:notam.q_code,
          traffic:notam.traffic,purpose:notam.purpose,scope:notam.scope,
          lower_limit:notam.lower_limit,upper_limit:notam.upper_limit,coordinates_radius:notam.coordinates_radius,
          item_a:notam.item_a,item_b:toLocalInput(notam.item_b),item_c:notam.item_c?toLocalInput(notam.item_c):"",
          item_c_qualifier:notam.item_c_qualifier??"",item_d:notam.item_d??"",item_e:notam.item_e,
          item_f:notam.item_f??"",item_g:notam.item_g??""
        });
      }
    }).catch(()=>{});
    getExtraction(request.id).then((run)=>{if(!cancelled)setExtraction(run)}).catch(()=>{if(!cancelled)setExtraction(null)});
    return ()=>{cancelled=true};
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[request.id]);

  useEffect(()=>{
    if((request.status!=="publishing"&&request.status!=="published")||!lastDraft)return;
    let cancelled=false;
    getDeliveries(lastDraft.id).then((rows)=>{if(!cancelled)setDeliveries(rows)}).catch(()=>{if(!cancelled)setDeliveries([])});
    return ()=>{cancelled=true};
  },[request.status,lastDraft]);

  useEffect(()=>{
    if(tab!=="history")return;
    let cancelled=false;
    setHistoryLoading(true);
    Promise.all([
      getAuditEvents({entityType:"notam_request",entityId:request.id,limit:25}),
      lastDraft?getAuditEvents({entityType:"notam",entityId:lastDraft.id,limit:25}):Promise.resolve([])
    ])
      .then(([requestEvents,notamEvents])=>{
        if(cancelled)return;
        const merged=[...requestEvents,...notamEvents].sort((a,b)=>new Date(b.created_at).getTime()-new Date(a.created_at).getTime());
        setHistory(merged);
      })
      .catch(()=>{if(!cancelled)setHistory([])})
      .finally(()=>{if(!cancelled)setHistoryLoading(false)});
    return ()=>{cancelled=true};
  },[tab,request.id,lastDraft]);

  useEffect(()=>{
    const code=values.q_code?.toUpperCase();
    if(!code||!/^Q[A-Z]{4}$/.test(code)){setRule(null);setRuleStatus("idle");return}
    setRuleStatus("loading");
    let cancelled=false;
    const timer=window.setTimeout(()=>{
      getRuleByQcode(code).then((match)=>{
        if(cancelled)return;
        setRule(match);
        setRuleStatus(match?"found":"missing");
      });
    },350);
    return ()=>{cancelled=true;window.clearTimeout(timer)};
  },[values.q_code]);

  const runExtraction=async()=>{
    setExtractionBusy(true);setExtractionError(null);
    try{const run=await rerunExtraction(request.id);setExtraction(run)}
    catch(err){setExtractionError(err instanceof Error?err.message:"Extraction could not be started.")}
    finally{setExtractionBusy(false)}
  };

  const acceptField=async(fieldId:string,value?:string)=>{
    try{
      await acceptExtractedField(fieldId,value);
      const refreshed=await getExtraction(request.id);
      setExtraction(refreshed);
    }catch(err){setExtractionError(err instanceof Error?err.message:"Could not accept field.")}
  };

  const submit=handleSubmit(async(data)=>{
    setBusy(true);
    try{
      const result=await saveDraft(request.id,{...data,item_b:new Date(`${data.item_b}:00Z`).toISOString(),item_c:new Date(`${data.item_c}:00Z`).toISOString(),item_c_qualifier:data.item_c_qualifier||undefined});
      setLastDraft(result);
      setNotice(result.validation_result.valid?"Draft saved to the controlled audit record.":"Draft saved with validation issues -- resolve before submitting.");
      setTab("validation");
    }catch(err){setNotice(err instanceof Error?err.message:"Draft could not be saved.")}
    finally{setBusy(false)}
  });
  const sendForReview=async()=>{
    setBusy(true);
    try{
      await submit();
      await workflowAction(request.id,"submit");
      setNotice("Request locked and submitted for independent specialist review.");
      router.refresh();
    }catch(err){setNotice(err instanceof Error?err.message:"Could not submit the request for review.")}
    finally{setBusy(false)}
  };
  const doApprove=async()=>{
    setBusy(true);
    try{
      await workflowAction(request.id,"approve",reviewComment);
      setNotice("Draft approved. It can now be published.");
      router.refresh();
    }catch(err){setNotice(err instanceof Error?err.message:"Could not approve this draft.")}
    finally{setBusy(false)}
  };
  const doRequestChanges=async()=>{
    if(!reviewComment.trim()){setNotice("A comment is required when requesting changes.");return}
    setBusy(true);
    try{
      await workflowAction(request.id,"request-changes",reviewComment);
      setNotice("Sent back to the preparing officer for correction.");
      router.refresh();
    }catch(err){setNotice(err instanceof Error?err.message:"Could not request changes.")}
    finally{setBusy(false)}
  };
  const doPublish=async()=>{
    setBusy(true);
    try{
      await workflowAction(request.id,"publish");
      setNotice("Publication started across all configured channels.");
      router.refresh();
    }catch(err){setNotice(err instanceof Error?err.message:"Could not publish this NOTAM.")}
    finally{setBusy(false)}
  };
  const doRetry=async(deliveryId:string)=>{
    try{
      const updated=await retryDelivery(deliveryId);
      setDeliveries((current)=>current?current.map((row)=>row.id===updated.id?updated:row):current);
    }catch(err){setNotice(err instanceof Error?err.message:"Retry failed.")}
  };

  const step = STEP_STATE[request.status];
  const preview=`(${lastDraft?`${lastDraft.series}${String(lastDraft.serial_number).padStart(4,"0")}/${String(lastDraft.year%100).padStart(2,"0")}`:"PREVIEW"} ${values.kind}\nQ)${values.fir}/${values.q_code}/${values.traffic}/${values.purpose}/${values.scope}/${values.lower_limit}/${values.upper_limit}/${values.coordinates_radius}\nA)${values.item_a} B)${dtg(values.item_b)} C)${dtg(values.item_c)}${values.item_c_qualifier}\nE)${values.item_e}\nF)${values.item_f} G)${values.item_g})`;

  const canReview = request.status==="review" && !!user && REVIEW_ROLES.includes(user.role);
  const canPublish = request.status==="approved" && !!user && PUBLISH_ROLES.includes(user.role);
  const canRetry = !!user && RETRY_ROLES.includes(user.role);

  return <div className="workbench">
    <header className="workbench-header">
      <div><StatusPill status={request.status}/><strong>{request.request_number}</strong><small>Received by {request.source} · immutable source retained</small></div>
      <div>
        {isEditable ? <>
          <button className="button secondary" onClick={submit}><Save/>Save draft</button>
          <button className="button primary" onClick={sendForReview} disabled={busy}><Send/>{busy?"Working…":"Submit for review"}</button>
        </> : null}
        {canPublish ? <button className="button primary" onClick={doPublish} disabled={busy}><Send/>{busy?"Publishing…":"Publish"}</button> : null}
        {!isEditable && !canReview && !canPublish ? <span className="workbench-readonly-note">Read only at this stage</span> : null}
      </div>
    </header>
    <div className="workflow-steps">{[["1","Ingest","Source captured"],["2","Prepare","Validate & format"],["3","Review","Specialist approval"],["4","Publish","AFTN & channels"]].map(([number,title,copy],index)=><div className={`workflow-step ${index<=step.done?"done":index===step.active?"active":""}`} key={title}><span>{index<=step.done?<Check/>:number}</span><strong>{title}</strong><small>{copy}</small>{index<3?<i/>:null}</div>)}</div>
    {notice?<div className="notice-bar"><ShieldCheck/><span>{notice}</span><button onClick={()=>setNotice(null)}>Dismiss</button></div>:null}
    {canReview ? <div className="review-action-bar">
      <div><strong>Independent review required</strong><p>A preparer can never approve their own draft. Comment is required to request changes.</p></div>
      <textarea placeholder="Review comment (required for Request changes)" value={reviewComment} onChange={(event)=>setReviewComment(event.target.value)}/>
      <div className="review-action-buttons">
        <button className="button secondary" onClick={doRequestChanges} disabled={busy}><Undo2/>Request changes</button>
        <button className="button primary" onClick={doApprove} disabled={busy}><CheckCheck/>Approve</button>
      </div>
    </div> : null}
    <div className="workbench-columns"><aside className="source-pane"><div className="pane-title"><div><h2>Source request</h2><p>Original evidence · read only</p></div><FileText/></div><div className="source-document"><div className="document-letterhead"><span>GCAA</span><strong>NOTAM REQUEST FORM</strong><small>GCAA-AIS-NTM-FR01 · Revision 1</small></div><dl><div><dt>Location</dt><dd>{request.location_indicator} / ACCRA FIR</dd></div><div><dt>Request</dt><dd>{request.requested_series?`Series ${request.requested_series}`:"NEW"}</dd></div><div className="wide"><dt>Full text</dt><dd>{request.raw_text}</dd></div><div><dt>Originator</dt><dd>{request.originator_name}</dd></div><div><dt>Reference</dt><dd>{request.originator_reference}</dd></div></dl></div>
      <div className="extraction-result">
        <ScanLine/>
        <div>
          <strong>Document extraction</strong>
          {extraction?<small>{extraction.fields.length} field(s) · status {extraction.status}{extraction.status==="failed"&&extraction.error?` · ${extraction.error}`:""}</small>:<small>No extraction run for this request yet</small>}
        </div>
        {isEditable ? <button type="button" onClick={runExtraction} disabled={extractionBusy}>{extractionBusy?"Running…":"Run again"}</button> : null}
      </div>
      {extractionError?<p className="form-error">{extractionError}</p>:null}
      {extraction&&extraction.fields.length>0?<div className="extraction-fields">{extraction.fields.map((field)=><div className="extraction-field-row" key={field.id}><span>{field.field_name}</span><strong>{field.normalized_value??field.raw_text??"—"}</strong><small>{field.confidence}%</small>{field.accepted_at?<em>Accepted</em>:<button type="button" onClick={()=>acceptField(field.id,field.normalized_value??undefined)}>Accept</button>}</div>)}</div>:null}
    </aside>
      <section className="editor-pane"><div className="editor-tabs"><button className={tab==="editor"?"active":""} onClick={()=>setTab("editor")}>{isEditable?"NOTAM editor":"Prepared NOTAM"}</button><button className={tab==="validation"?"active":""} onClick={()=>setTab("validation")}>Validation {lastDraft&&!lastDraft.validation_result.valid?<span>{lastDraft.validation_result.errors.length}</span>:null}</button><button className={tab==="history"?"active":""} onClick={()=>setTab("history")}>History</button></div>
      {tab==="editor" && isEditable ?<form onSubmit={submit} className="notam-form">
        <FormSection number="01" title="Identity & classification" copy="Series and message relationship"><div className="field-grid four"><Field label="Series" error={errors.series?.message}><select {...register("series")}><option value="A">Series A · International</option><option value="B">Series B · Local</option></select></Field><Field label="Message type"><select {...register("kind")}><option>NOTAMN</option><option>NOTAMR</option><option>NOTAMC</option></select></Field><Field label="Serial"><input value={lastDraft?`${lastDraft.series}${String(lastDraft.serial_number).padStart(4,"0")}/${String(lastDraft.year%100).padStart(2,"0")}`:"Assigned on save"} readOnly/></Field><Field label="FIR"><input {...register("fir")}/></Field></div></FormSection>
        <FormSection number="02" title="Q-line selection criteria" copy="ICAO Doc 8126, Part III, Appendix G"><div className="rule-match">
          <code>{values.q_code}</code>
          <div>
            {ruleStatus==="loading"?<strong>Looking up selection criteria…</strong>:null}
            {ruleStatus==="found"&&rule?<><strong>{rule.subject} · {rule.condition}</strong><p>Subject {rule.subject_code} + condition {rule.condition_code} · {rule.source}{rule.verification_status!=="VERIFIED_VISUAL"&&rule.verification_status!=="HAND_CURATED"?" · unverified transcription":""}</p></>:null}
            {ruleStatus==="missing"?<strong>No controlled selection-criteria mapping for this Q-code</strong>:null}
            {ruleStatus==="idle"?<strong>Enter a Q-code to look up selection criteria</strong>:null}
          </div>
          <button type="button" onClick={()=>setTab("validation")}>Explain <ChevronRight/></button>
        </div><div className="field-grid qline"><Field label="Q-code" error={errors.q_code?.message}><input {...register("q_code")}/></Field><Field label="Traffic"><input {...register("traffic")}/></Field><Field label="Purpose"><input {...register("purpose")}/></Field><Field label="Scope"><input {...register("scope")}/></Field><Field label="Lower"><input {...register("lower_limit")}/></Field><Field label="Upper"><input {...register("upper_limit")}/></Field><Field label="Coordinates / radius"><input {...register("coordinates_radius")}/></Field></div></FormSection>
        <FormSection number="03" title="Location & validity" copy="All values normalized to UTC"><div className="field-grid four"><Field label="Item A) location"><input {...register("item_a")}/></Field><Field label="Item B) start UTC"><input type="datetime-local" {...register("item_b")}/></Field><Field label="Item C) end UTC"><input type="datetime-local" {...register("item_c")}/></Field><Field label="Qualifier"><select {...register("item_c_qualifier")}><option value="">Confirmed</option><option>EST</option><option>PERM</option></select></Field></div></FormSection>
        <FormSection number="04" title="NOTAM text" copy="Operational plain language for PIB"><Field label="Item E)" error={errors.item_e?.message}><textarea rows={4} {...register("item_e")}/></Field><div className="field-grid two"><Field label="Item F) lower limit"><input {...register("item_f")}/></Field><Field label="Item G) upper limit"><input {...register("item_g")}/></Field></div></FormSection>
        <div className="transmission-preview"><div><strong>Transmission preview</strong><span>ICAO text NOTAM</span></div><pre>{lastDraft?lastDraft.formatted_message:preview}</pre></div>
      </form>:null}
      {tab==="editor" && !isEditable ? <div className="notam-readonly">
        {!lastDraft ? <div className="empty-state"><p>No NOTAM has been prepared for this request yet.</p></div> : <>
          <div className="transmission-preview"><div><strong>Prepared NOTAM</strong><span>ICAO text NOTAM · read only at this stage</span></div><pre>{lastDraft.formatted_message}</pre></div>
          {(request.status==="publishing"||request.status==="published") ? <div className="delivery-table">
            <h3>Channel delivery status</h3>
            {deliveries===null ? <p>Loading delivery status…</p> : null}
            {deliveries&&deliveries.length===0 ? <p>No deliveries recorded yet.</p> : null}
            {deliveries?.map((delivery)=><div className={`delivery-row status-${delivery.status}`} key={delivery.id}>
              <div><strong>{delivery.channel}</strong><small>{delivery.destination}</small></div>
              <span className={`delivery-status-tag status-${delivery.status}`}>{delivery.status}</span>
              {delivery.status==="failed"&&canRetry ? <button type="button" onClick={()=>doRetry(delivery.id)}><RefreshCw/>Retry</button> : null}
            </div>)}
          </div> : null}
        </>}
      </div> : null}
      {tab==="validation"?<div className="validation-pane">
        {!lastDraft?<div className="empty-state"><p>Save a draft to run selection-criteria and format validation.</p></div>:<>
          <div className="quality-score"><strong>{lastDraft.validation_result.valid?<Check/>:<TriangleAlert/>}</strong><div><h2>{lastDraft.validation_result.valid?"Draft passes validation":"Draft has blocking issues"}</h2><p>{lastDraft.validation_result.errors.length} blocking issue(s) · {lastDraft.validation_result.warnings.length} advisory item(s) · ruleset {lastDraft.ruleset_version}</p></div></div>
          {lastDraft.validation_result.errors.map((message)=><div className="validation-row fail" key={message}><span><TriangleAlert/></span><div><strong>{message}</strong></div></div>)}
          {lastDraft.validation_result.warnings.map((message)=><div className="validation-row warn" key={message}><span><TriangleAlert/></span><div><strong>{message}</strong></div></div>)}
          {lastDraft.validation_result.rule?<div className="validation-row pass"><span><Check/></span><div><strong>{lastDraft.validation_result.rule.subject} / {lastDraft.validation_result.rule.condition}</strong><p>Matched selection criteria for {lastDraft.validation_result.rule.q_code}.</p></div><small>{lastDraft.validation_result.rule.source}</small></div>:null}
        </>}
      </div>:null}
      {tab==="history"?<div className="history-pane">
        {historyLoading?<p>Loading history…</p>:null}
        {!historyLoading&&history.length===0?<p>No audit events recorded yet.</p>:null}
        {history.map((event)=><div className="history-row" key={event.id}><span>{new Date(event.created_at).toLocaleString(undefined,{hour:"2-digit",minute:"2-digit"})}</span><History/><div><strong>{event.action.replace(/_/g," ")}</strong><p>{event.actor_name}{event.from_state&&event.to_state?` · ${event.from_state} → ${event.to_state}`:""}</p></div></div>)}
      </div>:null}
      </section>
      <aside className="assurance-pane"><div className="pane-title"><div><h2>Assurance</h2><p>Live rules & evidence</p></div><span className="score-badge">{lastDraft?(lastDraft.validation_result.valid?"OK":"ISSUES"):"—"}</span></div><AssuranceBlock title="Mandatory gates" items={mandatoryGateItems(lastDraft)}/><AssuranceBlock title="Rule provenance" items={[{tone:"ok",label:"ICAO Doc 8126 · Appendix G"},{tone:"ok",label:"GCAA AIS Manual · Chapter 7"},{tone:"ok",label:"Ghana AIP · Current AIRAC"}]}/><AssuranceBlock title="Downstream products" items={[{tone:"ok",label:"ICAO text NOTAM · AMHS/AFTN"},{tone:"ok",label:"Digital NOTAM · AIXM 5.1.1"},{tone:"ok",label:"GCAA public web portal"},{tone:"ok",label:"Email distribution"}]}/></aside>
    </div></div>;
}

function Field({label,error,children}:{label:string;error?:string;children:React.ReactNode}){return <label className="field"><span>{label}</span>{children}{error?<small className="field-error">{error}</small>:null}</label>}
function FormSection({number,title,copy,children}:{number:string;title:string;copy:string;children:React.ReactNode}){return <section className="form-section"><header><span>{number}</span><div><h2>{title}</h2><p>{copy}</p></div><em><Check/> Complete</em></header>{children}</section>}

type AssuranceTone = "ok" | "warn" | "pending";
type AssuranceItem = { tone: AssuranceTone; label: string };

// The Mandatory gates panel used to always mark whichever item happened to
// be *last* in the array as the pending/warning one -- a leftover from an
// earlier fixed 4-item mock list. With real validation_result data the
// item count varies, so that positional guess frequently showed a green
// check next to text that said "not yet confirmed". Each item now carries
// its own explicit tone instead of being inferred from array position.
function mandatoryGateItems(lastDraft: NotamDraftResult | null): AssuranceItem[] {
  const gate: AssuranceItem = !lastDraft
    ? { tone: "pending", label: "Draft not yet prepared -- selection criteria not evaluated" }
    : lastDraft.validation_result.valid
      ? { tone: "ok", label: "Selection criteria satisfied" }
      : { tone: "warn", label: `Selection criteria not satisfied -- ${lastDraft.validation_result.errors.length} blocking issue(s)` };
  const warnings = (lastDraft?.validation_result.warnings ?? []).map((label): AssuranceItem => ({ tone: "warn", label }));
  return [gate, ...warnings];
}

function AssuranceBlock({title,items}:{title:string;items:AssuranceItem[]}){return <section className="assurance-block"><h3>{title}</h3>{items.map((item)=><div className={`assurance-row ${item.tone!=="ok"?item.tone:""}`} key={item.label}><span>{item.tone==="ok"?<Check/>:<TriangleAlert/>}</span><strong>{item.label}</strong></div>)}</section>}
