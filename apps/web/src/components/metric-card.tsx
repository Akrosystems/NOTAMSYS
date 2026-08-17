import type { LucideIcon } from "lucide-react";

export function MetricCard({ icon: Icon, value, label, detail, tone = "blue" }: { icon: LucideIcon; value: string | number; label: string; detail: string; tone?: string }) {
  return <article className="metric-card"><span className={`metric-icon ${tone}`}><Icon/></span><strong>{value}</strong><p>{label}</p><small>{detail}</small></article>;
}
