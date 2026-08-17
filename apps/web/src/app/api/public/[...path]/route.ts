import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.INTERNAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

// Unauthenticated counterpart to /api/backend -- forwards only to the
// backend's /public/* surface (anonymous NOTAM request intake), never
// attaches a session cookie, and never reaches any other backend path.
async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const target = new URL(`${API_URL}/public/${path.join("/")}`);
  request.nextUrl.searchParams.forEach((value, key) => target.searchParams.append(key, value));
  const hasBody = !["GET", "HEAD"].includes(request.method);
  const response = await fetch(target, {
    method: request.method,
    headers: { "Content-Type": request.headers.get("content-type") ?? "application/json" },
    body: hasBody ? await request.arrayBuffer() : undefined,
    cache: "no-store"
  });
  return new NextResponse(response.body, { status: response.status, headers: { "Content-Type": response.headers.get("content-type") ?? "application/json" } });
}

export const GET = proxy; export const POST = proxy;
