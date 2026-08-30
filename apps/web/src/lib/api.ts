import { dashboardSummary, requests } from "./demo-data";
import type {
  ActiveNotam,
  AdminUser,
  AipDatasetSummary,
  AuditEventEntry,
  Branding,
  BrandingUpdateInput,
  DashboardSummary,
  DraftPayload,
  ExtractionPreviewResult,
  ExtractionRun,
  NotamDraftResult,
  NotamRequest,
  NotamRequestInput,
  PublicationDelivery,
  PublishedNotam,
  QCodeSuggestion,
  RuleCatalogEntry,
  RuleMatch,
  RuleVersionSummary,
  SystemStatus,
  User,
  UserCreateInput,
  UserPresence,
  UserUpdateInput,
  WorkflowStatus
} from "./types";

const API_URL = typeof window === "undefined" ? (process.env.INTERNAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1") : "/api/backend";
// Anonymous public intake (submit page) never has a session cookie -- it
// goes through a separate unauthenticated proxy that only reaches the
// backend's /public/* surface. See app/api/public/[...path]/route.ts.
const PUBLIC_API_URL = typeof window === "undefined" ? `${process.env.INTERNAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1"}/public` : "/api/public";

// Safety-critical: demo/fixture data must never silently stand in for a real
// backend response. Before this flag existed, every GET below caught *any*
// fetch failure -- auth expiry, backend outage, network blip -- and quietly
// substituted fabricated NOTAMs with no indication to the operator. That is
// indistinguishable from real data on screen. Demo fallback now only
// activates when explicitly opted into (local dev without a backend
// running), and every fallback logs loudly so it can never be mistaken for
// silence. See components/demo-banner.tsx for the on-screen indicator.
export const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

// Server Components call the backend directly (API_URL = INTERNAL_API_URL),
// bypassing the /api/backend BFF proxy that client-side fetches go through
// -- so they need to attach the session's Bearer token themselves, the same
// way the proxy does for the browser. `next/headers` only works in a server
// context; the window check keeps it out of the client bundle entirely
// (a bare top-level import would break "use client" components that import
// from this module, e.g. for saveDraft/workflowAction).
async function authHeader(): Promise<Record<string, string>> {
  if (typeof window !== "undefined") return {};
  const { cookies } = await import("next/headers");
  const store = await cookies();
  let token = store.get("notamsys_access")?.value;
  if (!token) {
    const refreshToken = store.get("notamsys_refresh")?.value;
    if (refreshToken) {
      const { refreshAccessToken } = await import("@/lib/session-refresh");
      token = (await refreshAccessToken(refreshToken)) ?? undefined;
    }
  }
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function parseApiError(errorBody: unknown, defaultMsg: string): string {
  if (!errorBody || typeof errorBody !== "object") return defaultMsg;
  const body = errorBody as Record<string, unknown>;
  if (typeof body.detail === "string") {
    return body.detail;
  }
  if (Array.isArray(body.detail)) {
    return body.detail
      .map((e: { loc?: string[]; msg?: string }) => `${e.loc?.slice(-1)[0] || "field"}: ${e.msg}`)
      .join("; ");
  }
  if (typeof body.detail === "object" && body.detail !== null) {
    const detailObj = body.detail as Record<string, unknown>;
    if (Array.isArray(detailObj.errors) && detailObj.errors.length > 0) {
      const prefix = typeof detailObj.message === "string" ? `${detailObj.message} — ` : "";
      return `${prefix}${detailObj.errors.join("; ")}`;
    }
    if (typeof detailObj.message === "string") return detailObj.message;
  }
  if (typeof body.message === "string") return body.message;
  return defaultMsg;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const auth = await authHeader();
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...auth, ...init?.headers },
    cache: "no-store"
  });
  if (!response.ok) {
    if (response.status === 401 && typeof window === "undefined") {
      const { redirect } = await import("next/navigation");
      redirect("/login?reason=expired");
    }
    const errorBody = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(parseApiError(errorBody, "NOTAMSYS request failed"));
  }
  return response.json() as Promise<T>;
}

async function publicRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${PUBLIC_API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store"
  });
  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(parseApiError(errorBody, "NOTAMSYS request failed"));
  }
  return response.json() as Promise<T>;
}

function demoFallback<T>(path: string, fallback: T): T {
  if (!DEMO_MODE) {
    throw new Error(`NOTAMSYS backend request to ${path} failed and demo mode is not enabled`);
  }
  console.warn(`[NOTAMSYS DEMO MODE] ${path} failed; substituting fixture data. Not real.`);
  return fallback;
}

export async function getDashboard(): Promise<DashboardSummary> {
  try { return await request<DashboardSummary>("/dashboard/summary"); }
  catch { return demoFallback("/dashboard/summary", dashboardSummary); }
}

export async function getRequests(status?: WorkflowStatus): Promise<NotamRequest[]> {
  const suffix = status ? `?status=${status}` : "";
  try { return await request<NotamRequest[]>(`/requests${suffix}`); }
  catch { return demoFallback(`/requests${suffix}`, status ? requests.filter((item) => item.status === status) : requests); }
}

export async function getRequest(id: string): Promise<NotamRequest> {
  try { return await request<NotamRequest>(`/requests/${id}`); }
  catch { return demoFallback(`/requests/${id}`, requests.find((item) => item.id === id) ?? requests[0]); }
}

export async function saveDraft(id: string, payload: DraftPayload): Promise<NotamDraftResult> {
  return request<NotamDraftResult>(`/requests/${id}/draft`, { method: "POST", body: JSON.stringify(payload) });
}

export async function workflowAction(id: string, action: "submit" | "approve" | "request-changes" | "publish", comment = ""): Promise<unknown> {
  return request(`/requests/${id}/${action}`, { method: "POST", body: JSON.stringify({ comment }) });
}

export async function getRulesCatalog(params?: { search?: string; status?: string }): Promise<RuleCatalogEntry[]> {
  const query = new URLSearchParams();
  if (params?.search) query.set("search", params.search);
  if (params?.status) query.set("status", params.status);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<RuleCatalogEntry[]>(`/rules/catalog${suffix}`);
}

export async function getRuleVersions(): Promise<RuleVersionSummary[]> {
  return request<RuleVersionSummary[]>("/rules/versions");
}

export async function getAuditEvents(params?: { entityType?: string; entityId?: string; limit?: number }): Promise<AuditEventEntry[]> {
  const query = new URLSearchParams();
  if (params?.entityType) query.set("entity_type", params.entityType);
  if (params?.entityId) query.set("entity_id", params.entityId);
  if (params?.limit) query.set("limit", String(params.limit));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<AuditEventEntry[]>(`/audit-events${suffix}`);
}

export async function getAipDataset(): Promise<AipDatasetSummary | null> {
  return request<AipDatasetSummary | null>("/reference/datasets");
}

export async function getSystemStatus(): Promise<SystemStatus> {
  return request<SystemStatus>("/system/status");
}

export async function createRequest(payload: NotamRequestInput): Promise<NotamRequest> {
  return request<NotamRequest>("/requests", { method: "POST", body: JSON.stringify(payload) });
}

export async function uploadAttachment(requestId: string, file: File): Promise<{ id: string; filename: string; sha256: string }> {
  const auth = await authHeader();
  const body = new FormData();
  body.append("file", file);
  const response = await fetch(`${API_URL}/requests/${requestId}/attachments`, { method: "POST", headers: auth, body, cache: "no-store" });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(typeof detail.detail === "string" ? detail.detail : "NOTAMSYS attachment upload failed");
  }
  return response.json();
}

export async function createPublicRequest(payload: NotamRequestInput): Promise<NotamRequest> {
  return publicRequest<NotamRequest>("/requests", { method: "POST", body: JSON.stringify(payload) });
}

export async function uploadPublicAttachment(requestId: string, file: File): Promise<{ id: string; filename: string; sha256: string }> {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch(`${PUBLIC_API_URL}/requests/${requestId}/attachments`, { method: "POST", body, cache: "no-store" });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(typeof detail.detail === "string" ? detail.detail : "NOTAMSYS attachment upload failed");
  }
  return response.json();
}

export async function getRuleByQcode(code: string): Promise<RuleMatch | null> {
  try { return await request<RuleMatch>(`/rules/qcode/${code}`); }
  catch { return null; }
}

export async function getQCodeSuggestions(narrative: string, locationIndicator?: string): Promise<QCodeSuggestion[]> {
  try {
    return await request<QCodeSuggestion[]>("/rules/qcode-suggestions", {
      method: "POST",
      body: JSON.stringify({ narrative, location_indicator: locationIndicator || undefined })
    });
  } catch {
    return [];
  }
}

export async function recordQCodeCorrection(payload: {
  request_id?: string;
  location_indicator?: string;
  narrative: string;
  suggested_q_code?: string;
  suggested_confidence?: number;
  chosen_q_code: string;
  suggestion_was_in_top5: boolean;
}): Promise<void> {
  try {
    await request("/rules/qcode-corrections", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  } catch {
    // Non-blocking telemetry
  }
}

export async function getExtraction(requestId: string): Promise<ExtractionRun | null> {
  return request<ExtractionRun | null>(`/requests/${requestId}/extraction`);
}

export async function rerunExtraction(requestId: string): Promise<ExtractionRun> {
  return request<ExtractionRun>(`/requests/${requestId}/extraction/rerun`, { method: "POST" });
}

// Stateless read of a photo/scan before a request exists -- lets the intake
// form pre-fill itself from a photographed hard-copy GCAA-AIS-NTM-FR01. No
// Attachment/ExtractionRun is created; the file is uploaded and extracted
// again for the real audit record once the officer actually submits.
export async function previewExtraction(file: File): Promise<ExtractionPreviewResult> {
  const auth = await authHeader();
  const body = new FormData();
  body.append("file", file);
  const response = await fetch(`${API_URL}/extraction/preview`, { method: "POST", headers: auth, body, cache: "no-store" });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(typeof detail.detail === "string" ? detail.detail : "Could not read the document.");
  }
  return response.json();
}

export async function acceptExtractedField(fieldId: string, value?: string): Promise<unknown> {
  return request(`/extraction/fields/${fieldId}/accept`, { method: "POST", body: JSON.stringify({ value: value ?? null }) });
}

// "Not logged in" is a legitimate state (public pages, expired session),
// not a masked failure -- unlike demoFallback() above, this deliberately
// swallows the error and returns null instead of throwing.
export async function getCurrentUser(): Promise<User | null> {
  try { return await request<User>("/auth/me"); }
  catch { return null; }
}

const DEFAULT_BRANDING: Branding = { org_name: "NOTAMSYS", org_subtitle: "Accra NOF", description: null, logo_url: null };

// The backend returns logo_url as a path relative to itself (e.g.
// "/branding/logo?v=123") since it doesn't know the frontend's proxy
// mount point -- every function that can hand back a Branding object
// (not just the initial fetch) must rewrite it the same way, or the
// admin console's own post-upload preview points at a URL that doesn't
// exist on this origin.
function rewriteLogoUrl(branding: Branding): Branding {
  if (!branding.logo_url) return branding;
  const version = branding.logo_url.split("v=")[1];
  return { ...branding, logo_url: `/api/branding/logo?v=${version}` };
}

// Server-only in practice (fetched once in layout.tsx and threaded through
// BrandingProvider) -- purely cosmetic, so unlike demoFallback() above this
// deliberately falls back to a hardcoded default rather than throwing when
// the backend is unreachable. Showing the default brand identity if the
// API is briefly down isn't fabricating operational data the way a fake
// NOTAM would be.
export async function getBranding(): Promise<Branding> {
  try {
    return rewriteLogoUrl(await request<Branding>("/branding"));
  } catch {
    return DEFAULT_BRANDING;
  }
}

export async function updateBranding(payload: BrandingUpdateInput): Promise<Branding> {
  return rewriteLogoUrl(await request<Branding>("/admin/branding", { method: "PATCH", body: JSON.stringify(payload) }));
}

export async function uploadBrandingLogo(file: File): Promise<Branding> {
  const auth = await authHeader();
  const body = new FormData();
  body.append("file", file);
  const response = await fetch(`${API_URL}/admin/branding/logo`, { method: "POST", headers: auth, body, cache: "no-store" });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(typeof detail.detail === "string" ? detail.detail : "Logo upload failed");
  }
  return rewriteLogoUrl(await response.json());
}

export async function removeBrandingLogo(): Promise<Branding> {
  return rewriteLogoUrl(await request<Branding>("/admin/branding/logo", { method: "DELETE" }));
}

export async function getActiveNotams(series?: "A" | "B"): Promise<ActiveNotam[]> {
  const query = series ? `?series=${series}` : "";
  try {
    return await request<ActiveNotam[]>(`/notams${query}`);
  } catch {
    return [];
  }
}

export async function getPublishedNotams(params?: {
  series?: "A" | "B";
  location?: string;
  status?: string;
  search?: string;
}): Promise<PublishedNotam[]> {
  const query = new URLSearchParams();
  if (params?.series) query.set("series", params.series);
  if (params?.location) query.set("location", params.location);
  if (params?.status) query.set("status", params.status);
  if (params?.search) query.set("search", params.search);
  const qStr = query.toString() ? `?${query.toString()}` : "";
  try {
    return await request<PublishedNotam[]>(`/notams${qStr}`);
  } catch {
    return [];
  }
}

export async function getRequestNotam(requestId: string): Promise<NotamDraftResult | null> {
  return request<NotamDraftResult | null>(`/requests/${requestId}/notam`);
}

export async function getDeliveries(notamId: string): Promise<PublicationDelivery[]> {
  return request<PublicationDelivery[]>(`/notams/${notamId}/deliveries`);
}

export async function retryDelivery(deliveryId: string): Promise<PublicationDelivery> {
  return request<PublicationDelivery>(`/deliveries/${deliveryId}/retry`, { method: "POST" });
}

export async function acknowledgeDelivery(deliveryId: string): Promise<PublicationDelivery> {
  return request<PublicationDelivery>(`/deliveries/${deliveryId}/acknowledge`, { method: "POST" });
}

export async function markRequestPublished(requestId: string): Promise<NotamRequest> {
  return request<NotamRequest>(`/requests/${requestId}/mark-published`, { method: "POST" });
}


export async function listUsers(): Promise<AdminUser[]> {
  return request<AdminUser[]>("/admin/users");
}

export async function createUser(payload: UserCreateInput): Promise<AdminUser> {
  return request<AdminUser>("/admin/users", { method: "POST", body: JSON.stringify(payload) });
}

export async function updateUser(id: string, payload: UserUpdateInput): Promise<AdminUser> {
  return request<AdminUser>(`/admin/users/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export async function getUsersPresence(): Promise<UserPresence[]> {
  try {
    return await request<UserPresence[]>("/users/presence");
  } catch {
    return [];
  }
}

export async function sendHeartbeat(): Promise<void> {
  try {
    await request("/users/heartbeat", { method: "POST" });
  } catch {
    // ignore
  }
}
