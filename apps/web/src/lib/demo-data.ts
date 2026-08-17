import type { DashboardSummary, NotamRequest } from "./types";

export const dashboardSummary: DashboardSummary = {
  requests_in_queue: 12,
  awaiting_specialist: 5,
  published_today: 18,
  estimated_due: 2,
  first_pass_quality: 99.4
};

const demoDefaults = {
  location_type: "AD" as const,
  requested_kind: "NOTAMN" as const,
  end_confirmed: false,
  end_permanent: false,
  end_estimated: false,
  lower_limit_sfc: false,
  upper_limit_unl: false
};

export const requests: NotamRequest[] = [
  {
    ...demoDefaults,
    id: "f2df9f7b-0fb4-4d87-8277-f878b91f4271",
    request_number: "REQ-0826-047",
    source: "email",
    status: "draft",
    originator_name: "AFRIQIYAH Operations",
    originator_reference: "OPS/NTM/0826/17",
    location_indicator: "DGAC",
    raw_text: "Temporary restricted area established due unmanned aircraft flight within 10 NM radius centred on 0550N 00010W. SFC to 2500 FT AGL.",
    requested_series: "A",
    safety_critical: false,
    received_at: "2026-08-15T14:18:00Z",
    updated_at: "2026-08-15T14:28:00Z"
  },
  {
    ...demoDefaults,
    id: "a7eb9ee1-7451-4505-bf4b-fd93bfaf8097",
    request_number: "REQ-0826-046",
    source: "upload",
    status: "review",
    originator_name: "Ghana Airports Company",
    location_indicator: "DGAA",
    raw_text: "Taxiway M closed due to work in progress.",
    requested_series: "A",
    safety_critical: true,
    received_at: "2026-08-15T14:07:00Z",
    updated_at: "2026-08-15T14:16:00Z"
  },
  {
    ...demoDefaults,
    id: "79a24034-bd99-4e03-8318-e4e3e285fb9c",
    request_number: "REQ-0826-045",
    source: "portal",
    status: "changes_requested",
    originator_name: "Tamale Airport",
    location_indicator: "DGLE",
    raw_text: "Work in progress on runway 05/23 strip.",
    requested_series: "B",
    safety_critical: false,
    received_at: "2026-08-15T13:51:00Z",
    updated_at: "2026-08-15T14:02:00Z"
  },
  {
    ...demoDefaults,
    id: "a2291432-9a6e-4fdb-a92b-f91b339d0982",
    request_number: "REQ-0826-044",
    source: "aftn",
    status: "approved",
    originator_name: "Lomé AIS",
    location_indicator: "DXXX",
    raw_text: "Aerodrome rescue and firefighting category restored.",
    requested_series: "A",
    safety_critical: false,
    received_at: "2026-08-15T13:38:00Z",
    updated_at: "2026-08-15T14:22:00Z"
  }
];
