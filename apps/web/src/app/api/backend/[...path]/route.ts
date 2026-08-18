import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { ACCESS_COOKIE_OPTIONS, refreshAccessToken } from "@/lib/session-refresh";

const API_URL = process.env.INTERNAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

// middleware.ts silently refreshes an expired access token, but its matcher
// deliberately excludes /api/* (this route included) -- so a client-side
// fetch made without a full page navigation (e.g. clicking "Save draft" on
// a page that's been open past the 30-minute access token lifetime) never
// passes through middleware at all. This is the same silent-refresh logic
// applied here instead, reactively: retry once with a fresh token if the
// backend says the current one is no good.
async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const cookieStore = await cookies();
  const refreshToken = cookieStore.get("notamsys_refresh")?.value;
  let token = cookieStore.get("notamsys_access")?.value;
  // Tracks any token minted during this request, proactively (cookie was
  // already missing) or reactively (cookie was present but the backend
  // rejected it) -- either way the browser needs the new one persisted,
  // not just used for this one fetch and silently discarded.
  let refreshedToken: string | null = null;
  if (!token && refreshToken) {
    refreshedToken = await refreshAccessToken(refreshToken);
    token = refreshedToken ?? undefined;
  }
  if (!token) return NextResponse.json({ detail: "Authentication required" }, { status: 401 });

  const target = new URL(`${API_URL}/${path.join("/")}`);
  request.nextUrl.searchParams.forEach((value, key) => target.searchParams.append(key, value));
  const hasBody = !["GET", "HEAD"].includes(request.method);
  const body = hasBody ? await request.arrayBuffer() : undefined;
  const contentType = request.headers.get("content-type") ?? "application/json";

  let response = await fetch(target, { method: request.method, headers: { Authorization: `Bearer ${token}`, "Content-Type": contentType }, body, cache: "no-store" });

  if (response.status === 401 && refreshToken && token !== refreshedToken) {
    refreshedToken = await refreshAccessToken(refreshToken);
    if (refreshedToken) {
      response = await fetch(target, { method: request.method, headers: { Authorization: `Bearer ${refreshedToken}`, "Content-Type": contentType }, body, cache: "no-store" });
    }
  }

  const outgoing = new NextResponse(response.body, { status: response.status, headers: { "Content-Type": response.headers.get("content-type") ?? "application/json" } });
  if (refreshedToken) outgoing.cookies.set("notamsys_access", refreshedToken, ACCESS_COOKIE_OPTIONS);
  return outgoing;
}

export const GET = proxy; export const POST = proxy; export const PUT = proxy; export const PATCH = proxy; export const DELETE = proxy;
