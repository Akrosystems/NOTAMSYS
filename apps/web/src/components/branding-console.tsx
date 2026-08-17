"use client";

import { ImagePlus, Save, Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { removeBrandingLogo, updateBranding, uploadBrandingLogo } from "@/lib/api";
import type { Branding } from "@/lib/types";

export function BrandingConsole({ initialBranding }: { initialBranding: Branding }) {
  const router = useRouter();
  const [branding, setBranding] = useState(initialBranding);
  const [form, setForm] = useState({
    org_name: initialBranding.org_name,
    org_subtitle: initialBranding.org_subtitle,
    description: initialBranding.description ?? ""
  });
  const [savingText, setSavingText] = useState(false);
  const [uploadingLogo, setUploadingLogo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const saveText = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setSavingText(true);
    try {
      const updated = await updateBranding(form);
      setBranding(updated);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save branding.");
    } finally {
      setSavingText(false);
    }
  };

  const uploadLogo = async () => {
    const file = fileInput.current?.files?.[0];
    if (!file) return;
    setError(null);
    setUploadingLogo(true);
    try {
      const updated = await uploadBrandingLogo(file);
      setBranding(updated);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not upload logo.");
    } finally {
      setUploadingLogo(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  const removeLogo = async () => {
    setError(null);
    setUploadingLogo(true);
    try {
      const updated = await removeBrandingLogo();
      setBranding(updated);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove logo.");
    } finally {
      setUploadingLogo(false);
    }
  };

  return (
    <section className="panel admin-branding-panel">
      <div className="panel-heading"><div><h2>Platform branding</h2><p>Shown on the sidebar, login and public request pages -- changes apply immediately, no restart needed</p></div></div>
      <div className="branding-layout">
        <div className="branding-logo-block">
          {branding.logo_url ? <img src={branding.logo_url} alt={branding.org_name} className="branding-logo-preview"/> : <div className="branding-logo-preview branding-logo-placeholder">{form.org_name.charAt(0).toUpperCase() || "N"}</div>}
          <input ref={fileInput} type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" onChange={uploadLogo} disabled={uploadingLogo}/>
          <button type="button" className="button secondary" onClick={() => fileInput.current?.click()} disabled={uploadingLogo}>
            <ImagePlus/>{uploadingLogo ? "Working…" : "Upload logo"}
          </button>
          {branding.logo_url ? <button type="button" className="button secondary branding-remove-logo" onClick={removeLogo} disabled={uploadingLogo}><Trash2/>Remove</button> : null}
          <small>PNG, JPEG, WEBP or SVG</small>
        </div>
        <form className="intake-fields branding-fields" onSubmit={saveText}>
          <label>Organization name<input required maxLength={80} value={form.org_name} onChange={(event) => setForm({ ...form, org_name: event.target.value })}/></label>
          <label>Subtitle<input maxLength={120} value={form.org_subtitle} onChange={(event) => setForm({ ...form, org_subtitle: event.target.value })}/></label>
          <label className="wide">Description / tagline<textarea maxLength={2000} placeholder="Shown under the login page eyebrow, e.g. the office or authority name" value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })}/></label>
          <div className="wide"><button className="button primary" type="submit" disabled={savingText}><Save/>{savingText ? "Saving…" : "Save branding"}</button></div>
        </form>
      </div>
      {error ? <p className="form-error">{error}</p> : null}
    </section>
  );
}
