"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Check, CheckCheck, ChevronRight, FileText, History, RefreshCw, Save, ScanLine, Send, ShieldCheck, TriangleAlert, Undo2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { z } from "zod";
import type { ActiveNotam, AipDatasetSummary, AuditEventEntry, ExtractionRun, NotamDraftResult, NotamRequest, PublicationDelivery, QCodeSuggestion, RuleMatch, SystemStatus, WorkflowStatus } from "@/lib/types";
import { acceptExtractedField, acknowledgeDelivery, getActiveNotams, getAipDataset, getAuditEvents, getDeliveries, getExtraction, getQCodeSuggestions, getRequestNotam, getRuleByQcode, getSystemStatus, markRequestPublished, recordQCodeCorrection, rerunExtraction, retryDelivery, saveDraft, workflowAction } from "@/lib/api";
import { formatUtcDateTime } from "@/lib/time";
import { StatusPill } from "./status-pill";
import { useCurrentUser } from "./user-context";
import { UtcDateTimeInput } from "./utc-datetime-input";

// Explicit interface matching form field values -- all optional/empty-able
// fields are declared here as string (react-hook-form always sends strings from
// input elements). Sanitization/defaulting is done in the submit handler.
interface FormData {
  series: "A" | "B";
  kind: "NOTAMN" | "NOTAMR" | "NOTAMC";
  replaces_notam_id?: string;
  fir: string;
  q_code: string;
  traffic: string;
  purpose: string;
  scope: string;
  lower_limit: string;
  upper_limit: string;
  coordinates_radius: string;
  item_a: string;
  item_b: string;
  item_c: string;
  item_c_qualifier: "" | "EST" | "PERM";
  item_d: string;
  item_e: string;
  item_f: string;
  item_g: string;
  aip_supplement_reference: string;
}

// Zod schema validates the form before submission.
// All fields are plain z.string() so the input type matches FormData exactly.
// Limits/coordinates may be empty -- they default in the submit handler.
const schema = z.object({
  series: z.enum(["A", "B"]), kind: z.enum(["NOTAMN", "NOTAMR", "NOTAMC"]),
  replaces_notam_id: z.string().optional(),
  fir: z.string().length(4), q_code: z.string().regex(/^Q[A-Z]{4}$/), traffic: z.string().min(1),
  purpose: z.string().min(1), scope: z.string().min(1),
  lower_limit: z.string(),
  upper_limit: z.string(),
  coordinates_radius: z.string(),
  item_a: z.string().min(4).max(8), item_b: z.string().min(16), item_c: z.string(),
  item_c_qualifier: z.enum(["", "EST", "PERM"]), item_d: z.string(), item_e: z.string().min(3).max(1000),
  item_f: z.string(), item_g: z.string(), aip_supplement_reference: z.string()
});

// Seeds the form from the actual request when no draft has been saved yet
// (every newly-entered request, before the officer types anything) -- never
// fall back to a fabricated sample NOTAM here. A previous version used a
// hardcoded constant for this, which meant every undrafted request showed
// the same fake NOTAM text/location as if it were real (confirmed live:
// officers saw identical "TEMPORARY RESTRICTED AREA... UNMANNED ACFT"
// content on unrelated requests). Fields with no direct source on the
// request (q_code, traffic, purpose, scope, coordinates_radius, limits)
// are left blank rather than guessed, since a wrong guess here is worse
// than an empty required field the officer must fill in.
function defaultsFromRequest(request: NotamRequest): FormData {
  return {
    series: request.requested_series ?? "A", kind: request.requested_kind,
    replaces_notam_id: "",
    // GCAA administers exactly one FIR (confirmed live: GET /reference/firs
    // returns a single "DGAC" / Accra FIR row) -- defaulting to it isn't a
    // guess about this request's content, it's a fixed fact of what this
    // deployment serves, same as before this file seeded from a hardcoded
    // constant. Q-code/traffic/purpose/scope stay blank: those genuinely
    // depend on the request's content and have no single correct default.
    fir: "DGAC", q_code: "", traffic: "", purpose: "", scope: "",
    lower_limit: request.lower_limit_sfc ? "000" : "", upper_limit: request.upper_limit_unl ? "999" : "",
    coordinates_radius: "", item_a: request.location_indicator,
    item_b: request.start_at ? toLocalInput(request.start_at) : "",
    item_c: request.end_permanent || !request.end_at ? "" : toLocalInput(request.end_at),
    item_c_qualifier: request.end_permanent ? "PERM" : request.end_estimated ? "EST" : "",
    item_d: request.periods_of_activity ?? "", item_e: request.raw_text,
    item_f: "", item_g: "", aip_supplement_reference: ""
  };
}

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
  const [notamLoadError,setNotamLoadError]=useState<string | null>(null);
  const [reviewComment,setReviewComment]=useState("");
  const [deliveries,setDeliveries]=useState<PublicationDelivery[] | null>(null);
  const [systemStatus,setSystemStatus]=useState<SystemStatus | null>(null);
  const [aipDataset,setAipDataset]=useState<AipDatasetSummary | null>(null);
  const [activeNotams,setActiveNotams]=useState<ActiveNotam[]>([]);
  const [qCodeSuggestions,setQCodeSuggestions]=useState<QCodeSuggestion[]>([]);
  const {register,handleSubmit,watch,reset,setValue,getValues,trigger,formState:{errors}}=useForm<FormData>({resolver:zodResolver(schema),defaultValues:defaultsFromRequest(request)});
  const values=watch();
  const isEditable = EDITABLE_STATUSES.includes(request.status);

  const loadNotam=(onCancelled?:()=>boolean)=>{
    setNotamLoadError(null);
    return getRequestNotam(request.id).then((notam)=>{
      if(onCancelled?.())return;
      setLastDraft(notam);
      if(!EDITABLE_STATUSES.includes(request.status))return;
      if(notam){
        reset({
          series:notam.series,kind:notam.kind,replaces_notam_id:notam.replaces_notam_id??"",fir:notam.fir,q_code:notam.q_code,
          traffic:notam.traffic,purpose:notam.purpose,scope:notam.scope,
          lower_limit:notam.lower_limit,upper_limit:notam.upper_limit,coordinates_radius:notam.coordinates_radius,
          item_a:notam.item_a,item_b:toLocalInput(notam.item_b),item_c:notam.item_c?toLocalInput(notam.item_c):"",
          item_c_qualifier:notam.item_c_qualifier??"",item_d:notam.item_d??"",item_e:notam.item_e,
          item_f:notam.item_f??"",item_g:notam.item_g??"",aip_supplement_reference:notam.aip_supplement_reference??""
        });
      } else {
        // No draft saved yet for this request -- seed from the request's
        // own data instead of leaving whatever the form last showed
        // (stale data from a previously viewed request, or the initial
        // mount defaults) on screen as if it belonged to this one.
        reset(defaultsFromRequest(request));
      }
    }).catch((err)=>{if(!onCancelled?.())setNotamLoadError(err instanceof Error?err.message:"Couldn't load the prepared NOTAM.")});
  };

  useEffect(()=>{
    let cancelled=false;
    loadNotam(()=>cancelled);
    getExtraction(request.id).then((run)=>{if(!cancelled)setExtraction(run)}).catch(()=>{if(!cancelled)setExtraction(null)});
    getSystemStatus().then((s)=>{if(!cancelled)setSystemStatus(s)}).catch(()=>{});
    getAipDataset().then((d)=>{if(!cancelled)setAipDataset(d)}).catch(()=>{if(!cancelled)setAipDataset(null)});
    getActiveNotams().then((list)=>{
      if(cancelled)return;
      setActiveNotams(list);
      if(request.referenced_notam_number && !getValues("replaces_notam_id")){
        const match = list.find((n) => n.identifier.toUpperCase() === request.referenced_notam_number?.toUpperCase());
        if(match) setValue("replaces_notam_id", match.id);
      }
    }).catch(()=>{if(!cancelled)setActiveNotams([])});
    return ()=>{cancelled=true};
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[request.id]);

  // Poll system status every 2 s while the semantic model is still loading
  // weights, then stop automatically once it becomes "ready" or "unavailable".
  // Without this the banner stays visible even after the backend finishes.
  useEffect(()=>{
    if(systemStatus?.semantic_model_status !== "loading")return;
    const timer=window.setInterval(()=>{
      getSystemStatus().then((s)=>{
        setSystemStatus(s);
        if(s.semantic_model_status !== "loading")window.clearInterval(timer);
      }).catch(()=>{});
    },2000);
    return ()=>window.clearInterval(timer);
  },[systemStatus?.semantic_model_status]);

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

  // Q-code suggestions from whatever narrative text is currently in Item E
  // -- covers both intake paths (typed by hand or seeded from a
  // photographed form) uniformly, since it reads the live form content
  // rather than only the original upload. Never applied automatically:
  // an officer picks one (or ignores all of them), same as the backend
  // contract in services/extraction/narrative.py. Stops suggesting once a
  // Q-code is already present, so it doesn't nag over a deliberate choice.
  useEffect(()=>{
    if(!isEditable||values.q_code||!values.item_e||values.item_e.trim().length<8){setQCodeSuggestions([]);return}
    let cancelled=false;
    const timer=window.setTimeout(()=>{
      getQCodeSuggestions(values.item_e, values.item_a).then((list)=>{if(!cancelled)setQCodeSuggestions(list)});
    },500);
    return ()=>{cancelled=true;window.clearTimeout(timer)};
  },[values.item_e,values.item_a,values.q_code,isEditable]);

  const applyQCodeSuggestion=(suggestion:QCodeSuggestion)=>{
    const topSuggestion = qCodeSuggestions[0];
    const isOverride = topSuggestion && topSuggestion.q_code !== suggestion.q_code;
    
    // Asynchronously record selection/correction feedback
    recordQCodeCorrection({
      request_id: request?.id,
      location_indicator: values.item_a,
      narrative: values.item_e || "",
      suggested_q_code: topSuggestion?.q_code,
      suggested_confidence: topSuggestion?.confidence,
      chosen_q_code: suggestion.q_code,
      suggestion_was_in_top5: true,
    });

    setValue("q_code",suggestion.q_code,{shouldValidate:true,shouldDirty:true});
    setValue("traffic",suggestion.traffic,{shouldValidate:true,shouldDirty:true});
    setValue("purpose",suggestion.purpose,{shouldDirty:true});
    setValue("scope",suggestion.scope,{shouldDirty:true});
    setValue("lower_limit",suggestion.lower_limit||"000",{shouldValidate:true,shouldDirty:true});
    setValue("upper_limit",suggestion.upper_limit||"999",{shouldValidate:true,shouldDirty:true});
    setValue("coordinates_radius",suggestion.coordinates_radius||"0536N00010W025",{shouldValidate:true,shouldDirty:true});
    setQCodeSuggestions([]);
  };

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

  // Core save logic extracted so both the "Save draft" button and
  // "Submit for review" can share it -- and crucially so sendForReview
  // can await a real rejection when saving fails, instead of the silent
  // swallow that react-hook-form's handleSubmit produces internally.
  const saveDraftData=async(data: Parameters<typeof handleSubmit>[0] extends (d: infer D) => unknown ? D : never)=>{
    const isoItemB = data.item_b ? new Date(`${data.item_b}:00Z`).toISOString() : undefined;
    const isPerm = data.item_c_qualifier === "PERM";
    const isCancel = data.kind === "NOTAMC";
    const isReplace = data.kind === "NOTAMR";
    const hasItemC = data.item_c && data.item_c.trim().length >= 16;
    const isoItemC = (!isCancel && !isPerm && hasItemC)
      ? new Date(`${data.item_c}:00Z`).toISOString()
      : undefined;
    const payload = data as unknown as FormData;
    const result=await saveDraft(request.id,{
      series: payload.series, kind: payload.kind,
      replaces_notam_id: (isCancel || isReplace) ? (payload.replaces_notam_id || undefined) : undefined,
      fir: payload.fir,
      q_code: payload.q_code, traffic: payload.traffic, purpose: payload.purpose, scope: payload.scope,
      lower_limit: payload.lower_limit || "000",
      upper_limit: payload.upper_limit || "999",
      coordinates_radius: payload.coordinates_radius || "0536N00010W025",
      item_a: payload.item_a,
      item_b: isoItemB!,
      item_c: isoItemC,
      item_c_qualifier: isCancel ? undefined : (payload.item_c_qualifier || undefined),
      item_d: payload.item_d || undefined,
      item_e: payload.item_e,
      item_f: payload.item_f || undefined,
      item_g: payload.item_g || undefined,
      aip_supplement_reference: payload.aip_supplement_reference || undefined,
    });
    setLastDraft(result);
    return result;
  };

  // "Save draft" button: validates the form then saves, showing notice inline.
  const submit=handleSubmit(async(data)=>{
    setBusy(true);
    try{
      const result=await saveDraftData(data);
      setNotice(result.validation_result.valid?"Draft saved to the controlled audit record.":"Draft saved with validation issues -- resolve before submitting.");
      setTab("validation");
    }catch(err){setNotice(err instanceof Error?err.message:"Draft could not be saved.")}
    finally{setBusy(false)}
  });

  // "Submit for review": validates + saves draft first, then transitions.
  // Using getValues() + trigger() instead of handleSubmit() so we get a
  // real promise rejection when the form is invalid or the save fails --
  // handleSubmit swallows errors internally and always resolves, which
  // previously let workflowAction run even when no draft was saved.
  const sendForReview=async()=>{
    setBusy(true);
    try{
      const valid=await trigger();
      if(!valid){setNotice("Please fix the highlighted fields before submitting.");setBusy(false);return}
      const data=getValues();
      await saveDraftData(data as Parameters<typeof saveDraftData>[0]);
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
      const result=await workflowAction(request.id,"publish") as NotamRequest;
      if(result.status==="published")setNotice("Published successfully to every configured channel.");
      else if(result.status==="publishing")setNotice("Published, but one or more channels failed -- see delivery status below and retry.");
      else if(result.status==="approved")setNotice("Publish failed on every channel -- reverted to Approved. Check channel configuration and try again.");
      else setNotice("Publication started.");
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
  const doMarkPublished=async()=>{
    setBusy(true);
    try{
      await markRequestPublished(request.id);
      setNotice("Marked as published. Manual confirmation recorded in audit trail.");
      router.refresh();
    }catch(err){setNotice(err instanceof Error?err.message:"Could not mark as published.")}
    finally{setBusy(false)}
  };
  const doManualDeliveryAck=async(deliveryId:string)=>{
    try{
      const updated=await acknowledgeDelivery(deliveryId);
      setDeliveries((current)=>current?current.map((row)=>row.id===updated.id?updated:row):current);
      setNotice(`Channel ${updated.channel} marked as delivered.`);
      router.refresh();
    }catch(err){setNotice(err instanceof Error?err.message:"Could not acknowledge delivery.")}
  };

  const step = STEP_STATE[request.status];
  let itemCPreview = "";
  if (values.kind !== "NOTAMC") {
    if (values.item_c_qualifier === "PERM") {
      itemCPreview = " C)PERM";
    } else if (values.item_c && values.item_c.length >= 16) {
      itemCPreview = ` C)${dtg(values.item_c)}${values.item_c_qualifier || ""}`;
    }
  }
  const selectedReplaced = activeNotams.find((n) => n.id === values.replaces_notam_id);
  const replacedIdentifier = (values.kind === "NOTAMR" || values.kind === "NOTAMC") && selectedReplaced ? ` ${selectedReplaced.identifier}` : "";
  const preview=`(${lastDraft?`${lastDraft.series}${String(lastDraft.serial_number).padStart(4,"0")}/${String(lastDraft.year%100).padStart(2,"0")}`:"PREVIEW"} ${values.kind}${replacedIdentifier}\nQ)${values.fir}/${values.q_code}/${values.traffic}/${values.purpose}/${values.scope}/${values.lower_limit}/${values.upper_limit}/${values.coordinates_radius}\nA)${values.item_a} B)${dtg(values.item_b)}${itemCPreview}\nE)${values.item_e}\nF)${values.item_f} G)${values.item_g})`;

  const canReview = request.status==="review" && !!user && REVIEW_ROLES.includes(user.role);
  const canPublish = request.status==="approved" && !!user && PUBLISH_ROLES.includes(user.role);
  const canManagePublish = !!user && PUBLISH_ROLES.includes(user.role);
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
        {(request.status === "publishing" || (request.status === "approved" && deliveries && deliveries.some(d => d.status === "failed"))) && canManagePublish ? (
          <button className="button secondary" onClick={doMarkPublished} disabled={busy}><CheckCheck/>{busy ? "Updating…" : "Mark as published"}</button>
        ) : null}
        {!isEditable && !canReview && !canPublish && request.status !== "publishing" ? <span className="workbench-readonly-note">Read only at this stage</span> : null}
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
    <div className="workbench-columns"><aside className="source-pane"><div className="pane-title"><div><h2>Source request</h2><p>Original evidence · read only</p></div><FileText/></div>
      <div className="source-document">
        <div className="document-letterhead"><span>GCAA</span><strong>NOTAM REQUEST FORM</strong><small>GCAA-AIS-NTM-FR01 · Revision 1</small></div>
        <dl>
          <div><dt>Location</dt><dd>{request.location_indicator} ({request.location_type || "AD"})</dd></div>
          <div><dt>Request Type</dt><dd>{request.requested_kind || "NOTAMN"}{request.requested_series ? ` · Series ${request.requested_series}` : ""}{request.referenced_notam_number ? ` (Ref: ${request.referenced_notam_number})` : ""}</dd></div>
          <div><dt>Start UTC (Item B)</dt><dd>{request.start_at ? formatUtcDateTime(request.start_at) : "—"}</dd></div>
          <div><dt>End UTC (Item C)</dt><dd>{request.end_permanent ? "PERM (Permanent)" : request.end_at ? `${formatUtcDateTime(request.end_at)} ${request.end_estimated ? "(EST)" : "(Confirmed)"}` : "—"}</dd></div>
          {request.periods_of_activity ? <div className="wide"><dt>Periods of Activity (Item D)</dt><dd>{request.periods_of_activity}</dd></div> : null}
          <div className="wide"><dt>Full text (Item E)</dt><dd>{request.raw_text}</dd></div>
          {(request.lower_limit_value || request.lower_limit_sfc || request.upper_limit_value || request.upper_limit_unl) ? (
            <div className="wide">
              <dt>Limits (Item F/G)</dt>
              <dd>
                Lower: {request.lower_limit_sfc ? "SFC" : request.lower_limit_value ? `${request.lower_limit_value} ${request.lower_limit_type || ""}` : "000"} · 
                Upper: {request.upper_limit_unl ? "UNL" : request.upper_limit_value ? `${request.upper_limit_value} ${request.upper_limit_type || ""}` : "999"}
              </dd>
            </div>
          ) : null}
          <div><dt>Originator</dt><dd>{request.originator_name}{request.originator_organisation ? ` (${request.originator_organisation})` : ""}</dd></div>
          <div><dt>Originator Reference</dt><dd>{request.originator_reference || "—"}</dd></div>
          {(request.originator_email || request.originator_phone) ? (
            <div className="wide">
              <dt>Contact</dt>
              <dd>{[request.originator_email, request.originator_phone].filter(Boolean).join(" · ")}</dd>
            </div>
          ) : null}
        </dl>
      </div>
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
        <FormSection number="01" title="Identity & classification" copy="Series and message relationship">
          <div className="field-grid four">
            <Field label="Series" error={errors.series?.message}><select {...register("series")}><option value="A">Series A · International</option><option value="B">Series B · Local</option></select></Field>
            <Field label="Message type"><select {...register("kind")}><option value="NOTAMN">NOTAMN · New</option><option value="NOTAMR">NOTAMR · Replace</option><option value="NOTAMC">NOTAMC · Cancel</option></select></Field>
            <Field label="Serial"><input value={lastDraft?`${lastDraft.series}${String(lastDraft.serial_number).padStart(4,"0")}/${String(lastDraft.year%100).padStart(2,"0")}`:"Assigned on save"} readOnly/></Field>
            <Field label="FIR"><input {...register("fir")}/></Field>
            {(values.kind === "NOTAMR" || values.kind === "NOTAMC") ? (
              <Field label={values.kind === "NOTAMR" ? "Replaces NOTAM" : "Cancels NOTAM"} error={errors.replaces_notam_id?.message}>
                <select {...register("replaces_notam_id")}>
                  <option value="">Select target NOTAM…</option>
                  {activeNotams.map((notam) => (
                    <option key={notam.id} value={notam.id}>
                      {notam.identifier} ({notam.item_a})
                    </option>
                  ))}
                </select>
              </Field>
            ) : null}
          </div>
        </FormSection>
        <FormSection number="02" title="Q-line selection criteria" copy="ICAO Doc 8126, Part III, Appendix G">
        {systemStatus?.semantic_model_status === "loading" && isEditable ? (
          <div className="semantic-loading-banner">
            <span className="semantic-loading-spinner" aria-hidden="true" />
            <span>Loading semantic model weights — Q-code suggestions will appear shortly</span>
          </div>
        ) : null}
        {qCodeSuggestions.length>0?<div className="qcode-suggestions"><strong>Suggested Q-codes from Item E — pick one or ignore</strong><div className="qcode-suggestion-list">{qCodeSuggestions.map((suggestion)=><button type="button" key={suggestion.q_code} className={`qcode-suggestion-chip ${suggestion.confidence >= 80 ? "qcode-chip-high-conf" : ""}`} onClick={()=>applyQCodeSuggestion(suggestion)}><code>{suggestion.q_code}</code><span>{suggestion.subject} · {suggestion.condition}{suggestion.confidence >= 80 ? <span className="high-conf-tag">Recommended Match</span> : null}<em style={{display:"block",fontSize:"0.74rem",opacity:0.85,marginTop:"2px",fontWeight:"normal"}}>Q) {suggestion.traffic}/{suggestion.purpose}/{suggestion.scope}/{suggestion.lower_limit||"000"}/{suggestion.upper_limit||"999"}/{suggestion.coordinates_radius||"0536N00010W025"}</em></span><small>{suggestion.confidence}%</small></button>)}</div></div>:null}

        <div className="rule-match">
          <code>{values.q_code}</code>
          <div>
            {ruleStatus==="loading"?<strong>Looking up selection criteria…</strong>:null}
            {ruleStatus==="found"&&rule?<><strong>{rule.subject} · {rule.condition}</strong><p>Subject {rule.subject_code} + condition {rule.condition_code} · {rule.source}{rule.verification_status!=="VERIFIED_VISUAL"&&rule.verification_status!=="HAND_CURATED"?" · unverified transcription":""}</p></>:null}
            {ruleStatus==="missing"?<strong>No controlled selection-criteria mapping for this Q-code</strong>:null}
            {ruleStatus==="idle"?<strong>Enter a Q-code to look up selection criteria</strong>:null}
          </div>
          <button type="button" onClick={()=>setTab("validation")}>Explain <ChevronRight/></button>
        </div><div className="field-grid qline"><Field label="Q-code" error={errors.q_code?.message}><input {...register("q_code")}/></Field><Field label="Traffic"><input {...register("traffic")}/></Field><Field label="Purpose"><input {...register("purpose")}/></Field><Field label="Scope"><input {...register("scope")}/></Field><Field label="Lower"><input {...register("lower_limit")}/></Field><Field label="Upper"><input {...register("upper_limit")}/></Field><Field label="Coordinates / radius"><input {...register("coordinates_radius")}/></Field></div></FormSection>
        <FormSection number="03" title="Location & validity" copy="All values normalized to UTC"><div className="field-grid four"><Field label="Item A) location"><input {...register("item_a")}/></Field><Field label="Item B) start UTC" error={errors.item_b?.message}><UtcDateTimeInput value={values.item_b} onChange={(val)=>setValue("item_b",val,{shouldValidate:true,shouldDirty:true})} required/></Field><Field label={values.kind==="NOTAMC"?"Item C) end UTC (Omitted for NOTAMC)":values.item_c_qualifier==="PERM"?"Item C) end UTC (Omitted for PERM)":"Item C) end UTC"} error={errors.item_c?.message}><UtcDateTimeInput value={values.item_c} onChange={(val)=>setValue("item_c",val,{shouldValidate:true,shouldDirty:true})} disabled={values.kind==="NOTAMC"||values.item_c_qualifier==="PERM"}/></Field><Field label="Qualifier"><select disabled={values.kind==="NOTAMC"} {...register("item_c_qualifier")}><option value="">Confirmed</option><option>EST</option><option>PERM</option></select></Field></div>
        {values.item_c_qualifier==="PERM" && values.kind!=="NOTAMC"?<div className="field-grid two"><Field label="AIP Supplement reference"><input placeholder="e.g. AIP SUP 04/26" {...register("aip_supplement_reference")}/></Field></div>:null}
        </FormSection>
        <FormSection number="04" title="NOTAM text" copy="Operational plain language for PIB"><Field label="Item E)" error={errors.item_e?.message}><textarea rows={4} {...register("item_e")}/></Field><div className="field-grid two"><Field label="Item F) lower limit"><input {...register("item_f")}/></Field><Field label="Item G) upper limit"><input {...register("item_g")}/></Field></div></FormSection>
        <div className="transmission-preview"><div><strong>Transmission preview</strong><span>ICAO text NOTAM</span></div><pre>{lastDraft?lastDraft.formatted_message:preview}</pre></div>
      </form>:null}
      {tab==="editor" && !isEditable ? <div className="notam-readonly">
        {!lastDraft ? <div className="empty-state">
          {notamLoadError ? <>
            <p>Couldn&apos;t load the prepared NOTAM -- {notamLoadError}</p>
            <button type="button" onClick={()=>loadNotam()}><RefreshCw/>Retry</button>
          </> : <p>No NOTAM has been prepared for this request yet.</p>}
        </div> : <>
          {/* Side-by-Side Specialist Review & Verification Center */}
          <div className="review-comparison-container">
            <div className="review-comparison-header">
              <div>
                <h3>Specialist Four-Eyes Verification</h3>
                <p>Verify that the drafted ICAO NOTAM faithfully represents the originator&apos;s request before approving for publication.</p>
              </div>
              <span className={`status-tag status-${request.status}`}>Status: {request.status.toUpperCase()}</span>
            </div>

            <div className="review-comparison-grid">
              {/* Left Column: Originator Request */}
              <div className="review-panel">
                <div className="review-panel-title"><FileText size={14}/> Originator Request ({request.request_number})</div>
                <table className="review-table">
                  <tbody>
                    <tr><th>Location</th><td><strong>{request.location_indicator}</strong> ({request.location_type || "AD"})</td></tr>
                    <tr><th>Type / Kind</th><td>{request.requested_kind || "NOTAMN"}{request.referenced_notam_number ? ` (Ref: ${request.referenced_notam_number})` : ""}</td></tr>
                    <tr><th>Validity</th><td>
                      B) {request.start_at ? formatUtcDateTime(request.start_at) : "—"}<br/>
                      C) {request.end_permanent ? "PERM" : request.end_at ? `${formatUtcDateTime(request.end_at)} ${request.end_estimated ? "(EST)" : "(Confirmed)"}` : "—"}
                    </td></tr>
                    {request.periods_of_activity ? <tr><th>Schedule (D)</th><td className="preserve-wrap mono">{request.periods_of_activity}</td></tr> : null}
                    <tr><th>Text (Item E)</th><td className="preserve-wrap">{request.raw_text}</td></tr>
                    <tr><th>Limits (F/G)</th><td className="mono">
                      Lower: {request.lower_limit_sfc ? "SFC" : request.lower_limit_value || "000"}<br/>
                      Upper: {request.upper_limit_unl ? "UNL" : request.upper_limit_value || "999"}
                    </td></tr>
                    <tr><th>Originator</th><td>{request.originator_name} {request.originator_reference ? `(${request.originator_reference})` : ""}</td></tr>
                  </tbody>
                </table>
              </div>

              {/* Right Column: Prepared NOTAM Draft */}
              <div className="review-panel">
                <div className="review-panel-title"><ShieldCheck size={14}/> Prepared NOTAM ({lastDraft.series}{String(lastDraft.serial_number).padStart(4,"0")}/{String(lastDraft.year%100).padStart(2,"0")} {lastDraft.kind})</div>
                <table className="review-table">
                  <tbody>
                    <tr><th>Location (A)</th><td><strong>{lastDraft.item_a}</strong> (FIR: {lastDraft.fir})</td></tr>
                    <tr><th>Q-Line</th><td className="mono">
                      <strong>{lastDraft.q_code}</strong> ({lastDraft.traffic}/{lastDraft.purpose}/{lastDraft.scope})<br/>
                      <small style={{ color: "var(--navy)", fontWeight: "normal" }}>
                        {lastDraft.validation_result?.rule ? `${lastDraft.validation_result.rule.subject} · ${lastDraft.validation_result.rule.condition}` : "Doc 8126 Criteria"}
                      </small>
                    </td></tr>
                    <tr><th>Validity</th><td>
                      B) {lastDraft.item_b ? formatUtcDateTime(lastDraft.item_b) : "—"}<br/>
                      C) {lastDraft.item_c ? `${formatUtcDateTime(lastDraft.item_c)} ${lastDraft.item_c_qualifier || ""}` : (lastDraft.item_c_qualifier || "PERM")}
                    </td></tr>
                    {lastDraft.item_d ? <tr><th>Schedule (D)</th><td className="preserve-wrap mono">{lastDraft.item_d}</td></tr> : null}
                    <tr><th>Text (Item E)</th><td className="preserve-wrap">{lastDraft.item_e}</td></tr>
                    <tr><th>Limits (F/G)</th><td className="mono">
                      Lower: {lastDraft.lower_limit || "000"} · Upper: {lastDraft.upper_limit || "999"}<br/>
                      Coords/Radius: {lastDraft.coordinates_radius}
                    </td></tr>
                    <tr><th>Validation</th><td>
                      {lastDraft.validation_result?.valid ? (
                        <span style={{ color: "var(--green)", fontWeight: "bold" }}>✓ Satisfied (Doc 8126 App G)</span>
                      ) : (
                        <span style={{ color: "var(--red)", fontWeight: "bold" }}>⚠ {lastDraft.validation_result?.errors?.length || 0} issues</span>
                      )}
                    </td></tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* Inline Review Action Decision Box */}
            {canReview ? (
              <div className="review-inline-actions">
                <div>
                  <strong>Specialist Approval Decision</strong>
                  <p style={{ margin: "2px 0 0", fontSize: "11px", color: "var(--muted)" }}>
                    Add review notes or revision feedback below. Comments are required when requesting changes.
                  </p>
                </div>
                <textarea
                  placeholder="Review comments (mandatory for Request changes, optional for Approve)..."
                  value={reviewComment}
                  onChange={(event) => setReviewComment(event.target.value)}
                />
                <div style={{ display: "flex", gap: "10px", justifyContent: "flex-end" }}>
                  <button type="button" className="button secondary" onClick={doRequestChanges} disabled={busy}>
                    <Undo2 size={14}/> Request changes
                  </button>
                  <button type="button" className="button primary" onClick={doApprove} disabled={busy}>
                    <CheckCheck size={14}/> Approve NOTAM
                  </button>
                </div>
              </div>
            ) : null}
          </div>

          <div className="transmission-preview">
            <div><strong>ICAO Transmission Output</strong><span>AFTN / AMHS format</span></div>
            <pre>{lastDraft.formatted_message}</pre>
          </div>

          {(request.status==="publishing"||request.status==="published") ? <div className="delivery-table">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
              <h3 style={{ margin: 0 }}>Channel delivery status</h3>
              {request.status === "publishing" && canManagePublish ? (
                <button type="button" className="button secondary" style={{ fontSize: "0.75rem", padding: "4px 8px" }} onClick={doMarkPublished} disabled={busy}>
                  <CheckCheck size={14}/> Mark all delivered
                </button>
              ) : null}
            </div>
            {deliveries===null ? <p>Loading delivery status…</p> : null}
            {deliveries&&deliveries.length===0 ? <p>No deliveries recorded yet.</p> : null}
            {deliveries?.map((delivery)=><div className={`delivery-row status-${delivery.status}`} key={delivery.id}>
              <div>
                <strong>{delivery.channel}</strong>
                <small>{delivery.destination}{delivery.response_payload?.manual_acknowledgement ? " · manual confirmation" : ""}</small>
              </div>
              <span className={`delivery-status-tag status-${delivery.status}`}>{delivery.status}</span>
              <div style={{ display: "flex", gap: "6px" }}>
                {delivery.status==="failed" ? <>
                  <button type="button" onClick={()=>doRetry(delivery.id)}><RefreshCw/>Retry</button>
                  {canManagePublish ? (
                    <button type="button" onClick={()=>doManualDeliveryAck(delivery.id)}><Check/>Mark delivered</button>
                  ) : null}
                </> : null}
              </div>
            </div>)}
          </div> : null}
        </>}
      </div> : null}
      {tab==="validation"?<div className="validation-pane">
        {!lastDraft?<>
          {rule?<div className="validation-row pass"><span><Check/></span><div><strong>{rule.subject} / {rule.condition}</strong><p>Matched selection criteria for {rule.q_code}. Traffic {rule.traffic} · Purpose {rule.purpose} · Scope {rule.scope}. Re-checked in full once a draft is saved.</p></div><small>{rule.source}</small></div>
          :ruleStatus==="missing"?<div className="empty-state"><p>No controlled selection-criteria mapping for this Q-code yet.</p></div>
          :<div className="empty-state"><p>Enter a Q-code to see its selection criteria, or save a draft to run full format validation.</p></div>}
        </>:<>
          <div className="quality-score"><strong>{lastDraft.validation_result.valid?<Check/>:<TriangleAlert/>}</strong><div><h2>{lastDraft.validation_result.valid?"Draft passes validation":"Draft has blocking issues"}</h2><p>{lastDraft.validation_result.errors.length} blocking issue(s) · {lastDraft.validation_result.warnings.length} advisory item(s) · ruleset {lastDraft.ruleset_version}</p></div></div>
          {lastDraft.validation_result.errors.map((message)=><div className="validation-row fail" key={message}><span><TriangleAlert/></span><div><strong>{message}</strong></div></div>)}
          {lastDraft.validation_result.warnings.map((message)=><div className="validation-row warn" key={message}><span><TriangleAlert/></span><div><strong>{message}</strong></div></div>)}
          {lastDraft.validation_result.rule?<div className="validation-row pass"><span><Check/></span><div><strong>{lastDraft.validation_result.rule.subject} / {lastDraft.validation_result.rule.condition}</strong><p>Matched selection criteria for {lastDraft.validation_result.rule.q_code}.</p></div><small>{lastDraft.validation_result.rule.source}</small></div>:null}
        </>}
      </div>:null}
      {tab==="history"?<div className="history-pane">
        {historyLoading?<p>Loading history…</p>:null}
        {!historyLoading&&history.length===0?<p>No audit events recorded yet.</p>:null}
        {history.map((event)=><div className="history-row" key={event.id}><span>{formatUtcDateTime(event.created_at)}</span><History/><div><strong>{event.action.replace(/_/g," ")}</strong><p>{event.actor_name}{event.from_state&&event.to_state?` · ${event.from_state} → ${event.to_state}`:""}</p></div></div>)}
      </div>:null}
      </section>
      <aside className="assurance-pane"><div className="pane-title"><div><h2>Assurance</h2><p>Live rules & evidence</p></div><span className="score-badge">{lastDraft?(lastDraft.validation_result.valid?"OK":"ISSUES"):"—"}</span></div><AssuranceBlock title="Mandatory gates" items={mandatoryGateItems(lastDraft)}/><AssuranceBlock title="Rule provenance" items={provenanceItems(aipDataset)}/><AssuranceBlock title="Downstream products" items={downstreamItems(systemStatus)}/></aside>
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

// These two used to be hardcoded all-"ok" lists, including a "Ghana AIP ·
// Current AIRAC" line that claimed live AIRAC currency no part of this
// system actually tracks. Same tone logic as /integrations, so this panel
// can't drift from what that page honestly discloses.
function provenanceItems(aipDataset: AipDatasetSummary | null): AssuranceItem[] {
  return [
    { tone: "ok", label: "ICAO Doc 8126 · Appendix G" },
    { tone: "ok", label: "GCAA AIS Manual · Chapter 7" },
    aipDataset
      ? { tone: aipDataset.source === "seed" ? "warn" : "ok", label: `Accra FIR AIP · ${aipDataset.version}${aipDataset.source === "seed" ? " (seed data, not AIRAC-current)" : ""}` }
      : { tone: "warn", label: "Accra FIR AIP · no dataset active" }
  ];
}

// Each channel's real/simulated mode is independent (Settings.mode_for_channel)
// -- "not simulated" does not mean "will succeed". GCAA_WEB and Email have no
// live backend at all, so in real mode they're a guaranteed failure, not an
// "ok" this panel used to claim; only AIXM is unconditionally live. Mirrors
// the per-channel disclosure the Integrations page already gets right.
function downstreamItems(status: SystemStatus | null): AssuranceItem[] {
  const modes = status?.channel_modes;
  const aftnSimulated = !modes || modes.AFTN === "simulated_sync";
  const webSimulated = !modes || modes.GCAA_WEB === "simulated_sync";
  const emailSimulated = !modes || modes.EMAIL === "simulated_sync";
  return [
    { tone: "warn", label: `ICAO text NOTAM · AMHS/AFTN${aftnSimulated ? " (simulated)" : " (file-drop, unconfirmed)"}` },
    { tone: "ok", label: "Digital NOTAM · AIXM 5.1.1" },
    { tone: "warn", label: `GCAA public web portal${webSimulated ? " (simulated)" : " (not connected)"}` },
    { tone: "warn", label: `Email distribution${emailSimulated ? " (simulated)" : " (not connected)"}` }
  ];
}

function AssuranceBlock({title,items}:{title:string;items:AssuranceItem[]}){return <section className="assurance-block"><h3>{title}</h3>{items.map((item)=><div className={`assurance-row ${item.tone!=="ok"?item.tone:""}`} key={item.label}><span>{item.tone==="ok"?<Check/>:<TriangleAlert/>}</span><strong>{item.label}</strong></div>)}</section>}
