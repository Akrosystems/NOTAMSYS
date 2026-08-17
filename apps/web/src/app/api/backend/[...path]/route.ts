import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.INTERNAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const token = (await cookies()).get("notamsys_access")?.value;
  if (!token) return NextResponse.json({ detail: "Authentication required" }, { status: 401 });
  const target = new URL(`${API_URL}/${path.join("/")}`);
  request.nextUrl.searchParams.forEach((value, key) => target.searchParams.append(key, value));
  const hasBody = !["GET", "HEAD"].includes(request.method);
  const response = await fetch(target, { method: request.method, headers: { Authorization: `Bearer ${token}`, "Content-Type": request.headers.get("content-type") ?? "application/json" }, body: hasBody ? await request.arrayBuffer() : undefined, cache: "no-store" });
  return new NextResponse(response.body, { status: response.status, headers: { "Content-Type": response.headers.get("content-type") ?? "application/json" } });
}

export const GET = proxy; export const POST = proxy; export const PUT = proxy; export const PATCH = proxy; export const DELETE = proxy;
