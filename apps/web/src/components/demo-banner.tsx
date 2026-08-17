"use client";

import { AlertTriangle } from "lucide-react";
import { DEMO_MODE } from "@/lib/api";

/** Persistent, impossible-to-miss indicator that the app is running on
 * fixture data, not a live backend. Only ever renders when
 * NEXT_PUBLIC_DEMO_MODE=true is explicitly set -- see lib/api.ts for why
 * this replaced a silent fallback that could show fabricated NOTAMs
 * indistinguishably from real ones. */
export function DemoBanner() {
  if (!DEMO_MODE) return null;
  return (
    <div className="demo-banner" role="alert">
      <AlertTriangle />
      <span>DEMO DATA &mdash; not connected to a live NOTAMSYS backend. Nothing shown is operational.</span>
    </div>
  );
}
