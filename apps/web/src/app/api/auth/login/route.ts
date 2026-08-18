import { NextResponse } from "next/server";
import { ACCESS_COOKIE_OPTIONS } from "@/lib/session-refresh";

const API_URL = process.env.INTERNAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export async function POST(request: Request) {
  const response = await fetch(`${API_URL}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(await request.json()), cache: "no-store" });
  if (!response.headers.get("content-type")?.includes("application/json")) {
    return NextResponse.json(
      { detail: `Upstream API at ${API_URL} did not return JSON (status ${response.status}) -- check INTERNAL_API_URL/NEXT_PUBLIC_API_URL.` },
      { status: 502 },
    );
  }
  const payload = await response.json();
  if (!response.ok) return NextResponse.json(payload, { status: response.status });
  const outgoing = NextResponse.json({ user: payload.user });
  outgoing.cookies.set("notamsys_access", payload.access_token, ACCESS_COOKIE_OPTIONS);
  // path: "/" (not the old "/api/auth") -- middleware and the authenticated
  // proxy both need this cookie on ordinary page/API requests to silently
  // refresh an expired access token. httpOnly/Secure/SameSite=Strict are
  // what actually protect it; the path scoping bought little beyond that
  // and was blocking the one thing this cookie exists for.
  outgoing.cookies.set("notamsys_refresh", payload.refresh_token, { httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "strict", path: "/", maxAge: 7 * 24 * 60 * 60 });
  return outgoing;
}
