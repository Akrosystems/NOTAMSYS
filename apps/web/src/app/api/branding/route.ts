import { NextResponse } from "next/server";

const API_URL = process.env.INTERNAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

// Unauthenticated by design, like /api/public/[...path] -- branding must
// render on /login and /submit before any session exists. Separate from
// that proxy because it targets a real, non-/public/* backend path.
export async function GET() {
  const response = await fetch(`${API_URL}/branding`, { cache: "no-store" });
  const body = await response.text();
  return new NextResponse(body, { status: response.status, headers: { "Content-Type": "application/json" } });
}
