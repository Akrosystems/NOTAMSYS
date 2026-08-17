import type { LucideIcon } from "lucide-react";

export interface ModuleCard { metric: string; title: string; copy: string }

export function ModulePage({ eyebrow, title, copy, icon: Icon, cards, children }: { eyebrow: string; title: string; copy: string; icon: LucideIcon; cards: ModuleCard[]; children?: React.ReactNode }) {
  return <div className="page-container"><section className="module-hero"><span><Icon/></span><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>{copy}</p></div></section><section className="module-grid">{cards.map((card) => <article className="module-card" key={card.title}><span>{card.metric}</span><h2>{card.title}</h2><p>{card.copy}</p></article>)}</section>{children}</div>;
}
