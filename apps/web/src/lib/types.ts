export type Role = "originator" | "ais_officer" | "ais_specialist" | "nof_manager" | "qms_auditor" | "system_admin";
export type WorkflowStatus = "received" | "triage" | "draft" | "review" | "changes_requested" | "approved" | "publishing" | "published" | "rejected" | "cancelled";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  organization?: string;
}

export interface AdminUser extends User {
  is_active: boolean;
  created_at: string;
}

export interface UserCreateInput {
  email: string;
  full_name: string;
  role: Role;
  organization?: string;
  password: string;
}

export interface UserUpdateInput {
  role?: Role;
  is_active?: boolean;
}

export interface Branding {
  org_name: string;
  org_subtitle: string;
  description?: string | null;
  logo_url?: string | null;
}

export interface BrandingUpdateInput {
  org_name?: string;
  org_subtitle?: string;
  description?: string;
}

export type LocationType = "AD" | "FIR" | "AIRSPACE";
export type RequestedKind = "NOTAMN" | "NOTAMR" | "NOTAMC";
export type LimitType = "FL" | "AGL" | "AMSL";

// Mirrors GCAA-AIS-NTM-FR01 (NOTAM Request Form) field-for-field -- see
// that form's Item A)-G) and the originator block.
export interface NotamRequest {
  id: string;
  request_number: string;
  source: "portal" | "email" | "aftn" | "upload" | "hand_delivery" | "raw_text";
  status: WorkflowStatus;
  originator_name: string;
  originator_email?: string;
  originator_organisation?: string | null;
  originator_phone?: string | null;
  originator_reference?: string;
  location_type: LocationType;
  location_indicator: string;
  requested_kind: RequestedKind;
  referenced_notam_number?: string | null;
  start_at?: string | null;
  end_at?: string | null;
  end_confirmed: boolean;
  end_permanent: boolean;
  end_estimated: boolean;
  periods_of_activity?: string | null;
  raw_text: string;
  lower_limit_sfc: boolean;
  lower_limit_value?: string | null;
  lower_limit_type?: LimitType | null;
  upper_limit_unl: boolean;
  upper_limit_value?: string | null;
  upper_limit_type?: LimitType | null;
  requested_series?: "A" | "B";
  safety_critical: boolean;
  received_at: string;
  updated_at: string;
}

export interface DashboardSummary {
  requests_in_queue: number;
  awaiting_specialist: number;
  published_today: number;
  estimated_due: number;
  first_pass_quality: number;
}

export type VerificationStatus = "HAND_CURATED" | "VERIFIED_VISUAL" | "TRANSCRIBED_UNVERIFIED";

export interface RuleCatalogEntry {
  subject_code: string;
  subject: string;
  condition_code: string;
  condition: string;
  traffic: string;
  purpose: string;
  scope: string;
  source: string;
  verification_status: VerificationStatus;
  q_code: string;
}

export interface RuleVersionSummary {
  id: string;
  version: string;
  source_document: string;
  source_revision: string;
  checksum: string;
  verified_rule_count: number;
  total_rule_count: number;
  notes?: string;
  active: boolean;
  approved_by_id: string;
  approved_at: string;
}

export interface AuditEventEntry {
  id: string;
  entity_type: string;
  entity_id: string;
  action: string;
  actor_name: string;
  actor_role?: string;
  from_state?: string;
  to_state?: string;
  payload: Record<string, unknown>;
  correlation_id?: string;
  created_at: string;
}

export interface AipDatasetSummary {
  id: string;
  version: string;
  source: string;
  effective_date?: string;
  checksum: string;
  active: boolean;
  created_at: string;
}

export interface SystemStatus {
  environment: string;
  ocr_engine: string;
  extraction_enabled: boolean;
  publication_mode: string;
  channel_modes: { AFTN: string; GCAA_WEB: string; EMAIL: string };
  aip_provider: string;
  storage_backend: string;
  public_intake_enabled: boolean;
}

export interface NotamRequestInput {
  source?: "portal" | "email" | "aftn" | "upload" | "hand_delivery" | "raw_text";
  originator_name: string;
  originator_email?: string;
  originator_organisation?: string;
  originator_phone?: string;
  originator_reference?: string;
  location_type?: LocationType;
  location_indicator: string;
  requested_kind?: RequestedKind;
  referenced_notam_number?: string;
  start_at?: string;
  end_at?: string;
  end_confirmed?: boolean;
  end_permanent?: boolean;
  end_estimated?: boolean;
  periods_of_activity?: string;
  raw_text: string;
  lower_limit_sfc?: boolean;
  lower_limit_value?: string;
  lower_limit_type?: LimitType;
  upper_limit_unl?: boolean;
  upper_limit_value?: string;
  upper_limit_type?: LimitType;
  requested_series?: "A" | "B";
  safety_critical?: boolean;
}

export type ExtractorKind = "deterministic" | "ocr" | "nlp";
export type ExtractionStatus = "pending" | "running" | "complete" | "failed" | "requires_human_confirmation";

export interface ExtractedField {
  id: string;
  run_id: string;
  field_name: string;
  raw_text?: string;
  normalized_value?: string;
  confidence: number;
  page?: number;
  extractor: ExtractorKind;
  accepted_by_id?: string;
  accepted_at?: string;
}

export interface ExtractionRun {
  id: string;
  attachment_id: string;
  engine: string;
  status: ExtractionStatus;
  page_count?: number;
  error?: string;
  started_at?: string;
  finished_at?: string;
  fields: ExtractedField[];
}

export interface RuleMatch {
  subject_code: string;
  subject: string;
  condition_code: string;
  condition: string;
  traffic: string;
  purpose: string;
  scope: string;
  source: string;
  verification_status: VerificationStatus;
  q_code: string;
}

export interface ValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
  rule: RuleMatch | null;
  ruleset_version: string;
}

export interface NotamDraftResult {
  id: string;
  request_id: string;
  series: "A" | "B";
  kind: "NOTAMN" | "NOTAMR" | "NOTAMC";
  serial_number: number;
  year: number;
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
  item_c?: string;
  item_c_qualifier?: "EST" | "PERM" | null;
  item_d?: string;
  item_e: string;
  item_f?: string;
  item_g?: string;
  aip_supplement_reference?: string | null;
  formatted_message: string;
  validation_result: ValidationResult;
  ruleset_version: string;
}

export interface PublicationDelivery {
  id: string;
  notam_id: string;
  channel: string;
  destination: string;
  status: string;
  external_reference?: string;
  attempted_at?: string;
  acknowledged_at?: string;
  response_payload: Record<string, unknown>;
}

export interface DraftPayload {
  series: "A" | "B";
  kind: "NOTAMN" | "NOTAMR" | "NOTAMC";
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
  item_c_qualifier?: "EST" | "PERM";
  item_d?: string;
  item_e: string;
  item_f?: string;
  item_g?: string;
  aip_supplement_reference?: string;
}
