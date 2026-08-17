import { NextResponse } from "next/server";
export async function POST() { const response = NextResponse.json({ ok: true }); response.cookies.delete("notamsys_access"); response.cookies.delete("notamsys_refresh"); return response; }
