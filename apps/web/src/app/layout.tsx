import type { Metadata } from "next";
import { DM_Sans, IBM_Plex_Mono } from "next/font/google";
import { AppShell } from "@/components/app-shell";
import { UserProvider } from "@/components/user-context";
import { getCurrentUser } from "@/lib/api";
import "./globals.css";

export const dynamic = "force-dynamic";

const sans = DM_Sans({ subsets: ["latin"], variable: "--font-sans" });
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: { default: "NOTAMSYS", template: "%s | NOTAMSYS" },
  description: "Controlled NOTAM origination, assurance, approval and publication for the Accra International NOTAM Office.",
  applicationName: "NOTAMSYS"
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const user = await getCurrentUser();
  return (
    // suppressHydrationWarning is required here, not optional: the inline
    // script below sets data-theme from localStorage before React
    // hydrates, so the server-rendered <html> (which has no access to
    // localStorage) and the live DOM legitimately differ on this one
    // attribute by design. Without this, React logs a hydration-mismatch
    // error on every load even though nothing is actually broken -- see
    // https://react.dev/link/hydration-mismatch and Next's documented
    // dark-mode-without-flash pattern.
    <html lang="en" className={`${sans.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        {/* Applies the stored theme before first paint so toggling
            light/dark never flashes the wrong palette on reload. */}
        <script
          dangerouslySetInnerHTML={{
            __html:
              "try{var t=localStorage.getItem('notamsys-theme');if(t)document.documentElement.setAttribute('data-theme',t);}catch(e){}"
          }}
        />
      </head>
      <body><UserProvider user={user}><AppShell>{children}</AppShell></UserProvider></body>
    </html>
  );
}
