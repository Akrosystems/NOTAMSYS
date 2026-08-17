import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.INTERNAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

// Unauthenticated -- the logo must render pre-login. Streams the image
// bytes through rather than redirecting, since the backend isn't
// necessarily reachable from the browser directly (see /api/branding).
export async function GET(request: NextRequest) {
  const target = new URL(`${API_URL}/branding/logo`);
  request.nextUrl.searchParams.forEach((value, key) => target.searchParams.append(key, value));
  const response = await fetch(target, { cache: "no-store" });
  if (!response.ok) return new NextResponse(null, { status: response.status });
  return new NextResponse(response.body, {
    status: response.status,
    headers: { "Content-Type": response.headers.get("content-type") ?? "image/png", "Cache-Control": "public, max-age=300" }
  });
}
