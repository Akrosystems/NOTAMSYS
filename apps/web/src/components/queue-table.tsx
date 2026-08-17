"use client";

import { MoreHorizontal, Search } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import type { NotamRequest } from "@/lib/types";
import { StatusPill } from "./status-pill";

export function QueueTable({ requests }: { requests: NotamRequest[] }) {
  const [search, setSearch] = useState("");
  const items = useMemo(() => requests.filter((item) => `${item.request_number} ${item.originator_name} ${item.location_indicator} ${item.raw_text}`.toLowerCase().includes(search.toLowerCase())), [requests, search]);
  return (
    <section className="panel queue-panel">
      <div className="panel-heading"><div><h2>Operational queue</h2><p>Live requests across preparation and approval</p></div><label className="search-input"><Search/><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search queue"/></label></div>
      <div className="table-scroll"><table><thead><tr><th>Request</th><th>Station / subject</th><th>Type</th><th>Received</th><th>Source</th><th>Status</th><th/></tr></thead><tbody>
        {items.map((item) => <tr key={item.id}>
          <td><Link className="table-link" href={`/requests/${item.id}`}>{item.request_number}</Link><small>{item.originator_reference ?? "Traceable source"}</small></td>
          <td><strong>{item.location_indicator} · {item.originator_name}</strong><small>{item.raw_text}</small></td>
          <td><span className={`series-tag series-${item.requested_series?.toLowerCase()}`}>{item.requested_series ?? "?"}</span> NOTAM</td>
          <td><strong>{new Date(item.received_at).toISOString().slice(11,16)}</strong><small>UTC</small></td>
          <td><span className="source-label">{item.source.replace("_", " ")}</span></td>
          <td><StatusPill status={item.status}/></td>
          <td><Link className="icon-button" href={`/requests/${item.id}`} aria-label={`Open ${item.request_number}`}><MoreHorizontal/></Link></td>
        </tr>)}
      </tbody></table></div>
      <div className="panel-footer"><span>Showing {items.length} active requests</span><Link href="/requests">View full queue →</Link></div>
    </section>
  );
}
