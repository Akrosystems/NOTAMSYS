# Operational boundary

Single source of truth for what NOTAMSYS actually does versus what still
needs a real-world connection before this can run the Accra International
NOTAM Office. README.md, ARCHITECTURE.md and SECURITY.md link here instead
of each maintaining their own summary, so this table is the one place that
needs updating as capabilities change.

Update this table whenever a capability's status changes. A capability
moving from Stub to Partial or Real is exactly the kind of change that
belongs in a commit message, not just a memory of the work.

| Capability | Status | What's real | What's still needed |
|---|---|---|---|
| Workflow state machine | **Real** | Full received→triage→draft→review→approved→publishing→published lifecycle, enforced transitions, four-eyes control (a preparer cannot approve their own draft) | — |
| Audit trail | **Real** | Append-only `AuditEvent` rows for every transition, evidence attachment, extraction acceptance, rule activation and delivery retry | Export tooling, retention policy |
| Evidence storage | **Real** (local) / **Partial** (MinIO) | SHA-256 content-addressed local filesystem storage; `MinioStorage` adapter exists behind the same interface | MinIO not exercised against a live server in this environment |
| NOTAM Selection Criteria (Doc 8126 Appendix G) | **Real** | All 13 categories, 1250 rules, every row visually verified against a rendered source page (not just transcribed). 4 pre-existing errors found and corrected | Independent second-reviewer sign-off before calling this the licensed, approved ruleset (see `services/rules.py` dataset docstring) |
| Q-line construction rules (Doc 8126 Ch.6) | **Real** | Purpose closed-set enforcement, Item D length cap, referenced-NOTAM existence check, formatter REF-identifier fix | Limit rounding (needs raw-altitude input fields not yet in the schema), FIR multi-code handling |
| AIXM 5.1.1 output | **Real** (event-only profile) | Namespaced Event/EventTimeSlice XML with geodesic circle geometry, generated per NOTAM | Full Digital NOTAM feature modelling (RunwayElement, AirspaceStatus, etc.) — no local spec exists yet to build against (Doc 8126 Part IV is "under development") |
| AFTN/Comsoft publication | **Partial** | Real envelope construction + ITA-2 character validation (fully testable offline); file-drop adapter writes real envelopes for manual pickup by the Comsoft/CADAS terminal | No live AMHS/AFTN circuit — no credentials or spec exist for one |
| GCAA website / email distribution | **Stub** | Adapter interface exists; simulated success in dev/test | No CMS or SMTP integration exists |
| OCR/NLP document extraction | **Real** (local, PDF text-layer path tested) / **Unverified** (image OCR path) | Deterministic grammar parsers, GCAA-AIS-NTM-FR01 form template, Q-code narrative suggestion, local Tesseract engine behind a pluggable interface | The `tesseract` binary itself is not installed in this dev environment — only tested via `NullOcr` fixtures and the PDF-text-layer path, which needs no OCR at all |
| GCAA AIP reference data | **Partial** (seed only) | `AipDataset`/`Fir`/`Aerodrome` models, provider interface, non-blocking Item A existence check | The real GCAA AIP is inaccessible (SharePoint-restricted) — seed data is limited to facts already implied by pre-existing sample data, with coordinates deliberately left out rather than invented |
| Frontend: dashboard, request queue, review, published, quality, rules, integrations, admin | **Real** | All server-rendered from live backend endpoints, verified end-to-end against a running API; demo-data fallback only activates on explicit opt-in (`NEXT_PUBLIC_DEMO_MODE=true`), never silently. Q-code typeahead, extraction UI, and status/role-aware Approve/Request-changes/Publish/Retry controls are wired into the NOTAM workbench (not just Save/Submit). uupm.cc-referenced visual redesign applied (off-white surfaces, slate ink, orange action accent; semantic status colors unchanged). The workbench's assurance panel used to claim "Ghana AIP · Current AIRAC" as a verified-ok provenance item with nothing behind it -- it now reflects the real active AIP dataset (or its absence) and the real publication mode, same tone logic as `/integrations` | Design is a single from-scratch pass, not iterated against user feedback |
| NOTAM request intake (`/requests/new`, `/submit`) | **Real** | Both the authenticated officer intake and the public originator intake are the exact GCAA-AIS-NTM-FR01 form, field-for-field (Item A location type/value, NOTAM N/R/C with series/no/year reference, Item B/C start/end with Confirmed/PERM/EST, Item D periods of activity, Item E full text/first line, Item F/G limits with SFC/UNL and FL/AGL/AMSL type, full originator block). Both post to `POST /requests` or `POST /public/requests`, verified end-to-end including the 4-letter-ICAO-for-AD/FIR and reference-required-for-Replace/Cancel validation rules | Item B/C are captured as a single UTC datetime-local picker rather than the paper form's separate Date(YYMMDD)/Time(HHMM) boxes -- same data, friendlier widget, not a field-count deviation |
| AIRAC cycle / AIP Supplement cross-reference | **Stub** (AIRAC) / **Real** (AIP Supplement reference) | A NOTAM draft has a real `aip_supplement_reference` field, and saving a PERM NOTAM without one produces a real validation warning (`services/qline.py:validate_perm_aip_supplement`) | Computing "the current AIRAC cycle" itself is deliberately not implemented -- doing so needs a verified historical epoch date this project isn't confident enough in to assert without risking a wrong cycle number stated with false authority. If you need this, verify the epoch against GCAA's or ICAO's published AIRAC schedule before implementing it |
| Authentication & sessions | **Real** | Argon2 password hashing, short-lived JWT access + refresh tokens, httpOnly/Secure/SameSite cookies via the Next.js BFF, deactivated accounts rejected at login (not just on subsequent requests) | MFA, GCAA identity integration, refresh-token rotation/reuse detection |
| RBAC | **Real** | Every mutating endpoint role-gated; a declarative matrix test (`test_rbac_matrix.py`) cross-checks every endpoint × every role in one table, not just per-endpoint assertions | — |
| Superadmin (`SYSTEM_ADMIN`) | **Real** | Universal role-check bypass (`require_roles()`), seeded `admin@notamsys.app` account, user management (`/admin/users` list/create/role/active-status, all audited), can activate rulesets and retry deliveries like a NOF Manager, and can live-edit platform branding (logo/name/subtitle/description) from the admin console -- the one setting on that screen that's genuinely DB-backed and takes effect without a restart, unlike everything else there | No UI for revoking/rotating a user's password from the console (requires the user to be recreated or the DB touched directly) |

## What "Real" means here

A capability marked **Real** has working code, a test that exercises it
(not just imports it), and no known gap between what it claims to do and
what it does. It does not mean "approved for operational use" — see each
row's "what's still needed" column, and the safety/security stance in
SECURITY.md, for what operational sign-off would actually require.
