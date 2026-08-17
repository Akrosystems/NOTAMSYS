"use client";

import { createContext, useContext } from "react";
import type { Branding } from "@/lib/types";

const DEFAULT_BRANDING: Branding = { org_name: "NOTAMSYS", org_subtitle: "Accra NOF", description: null, logo_url: null };

const BrandingContext = createContext<Branding>(DEFAULT_BRANDING);

export function BrandingProvider({ branding, children }: { branding: Branding; children: React.ReactNode }) {
  return <BrandingContext.Provider value={branding}>{children}</BrandingContext.Provider>;
}

export function useBranding(): Branding {
  return useContext(BrandingContext);
}
