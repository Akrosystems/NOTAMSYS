"use client";

import { LockKeyhole, ShieldCheck } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return <form onSubmit={async (event) => {
    event.preventDefault(); setBusy(true); setError("");
    const data = new FormData(event.currentTarget);
    try {
      const response = await fetch("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: data.get("email"), password: data.get("password") }) });
      if (!response.ok) throw new Error("Invalid email or password");
      const next = searchParams.get("next");
      router.push(next && next.startsWith("/") && !next.startsWith("//") ? next : "/"); router.refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Authentication failed"); }
    finally { setBusy(false); }
  }}><span className="login-icon"><LockKeyhole/></span><h2>Sign in to NOTAMSYS</h2><p>Use your approved GCAA AIS account.</p><label>Email address<input name="email" type="email" required defaultValue="officer@notamsys.app"/></label><label>Password<input name="password" type="password" required defaultValue="Notamsys!2026"/></label>{error ? <p className="login-error">{error}</p> : null}<div className="login-options"><label><input type="checkbox"/>Remember this workstation</label><button type="button">Need access?</button></div><button className="button primary" disabled={busy}>{busy ? "Authenticating…" : "Sign in securely"}</button><div className="login-security"><ShieldCheck/><span>Access is logged and protected by role-based authorization.</span></div></form>;
}

export default function LoginPage() {
  return <div className="login-shell"><aside><div className="login-brand"><span className="brand-mark">N</span><strong>NOTAMSYS</strong></div><div><p className="eyebrow">Accra International NOTAM Office</p><h1>Operational information, controlled from source to publication.</h1><p>ICAO-aligned preparation, independent approval, AFTN publication and quality evidence in one secure workspace.</p></div><footer>Built by AkroSystems</footer></aside><main><Suspense fallback={null}><LoginForm/></Suspense></main></div>;
}
