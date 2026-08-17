# Security and safety controls

## Identity and authorization

- Argon2 password hashing through `pwdlib`.
- Short-lived access JWT and scoped refresh cookie.
- HTTP-only, Secure and SameSite=Strict session cookies through the Next.js backend-for-frontend.
- Backend role enforcement for originator, AIS Officer, Specialist, NOF Manager, QMS Auditor and administrator.
- Four-eyes approval blocks the preparer from approving their own NOTAM.

## Evidence and auditability

- SHA-256 content address for every attachment.
- Immutable source evidence separated from extracted and edited fields.
- Append-only audit events record actor, state transition, timestamp, payload and correlation identifier.
- Ruleset version and source reference are persisted with each NOTAM.

## Required production work

- Integrate GCAA identity and multi-factor authentication.
- Use managed secrets/KMS and rotate signing keys.
- Enforce antivirus/content-disarm screening before extraction.
- Add database row-level policies and privileged-action step-up authentication.
- Send security and audit events to the approved monitoring/SIEM platform.
- Complete threat modelling, penetration testing, dependency scanning and operational accreditation.
- Establish backup restoration, disaster recovery and AFTN outage procedures.
- Rate-limit and content-validate the public NOTAM submission endpoint (`POST /public/requests` is live and persists real requests attributed to a seeded portal account, but has no rate limiting yet).
- Add a UI path for admin-initiated password resets/rotation (currently requires recreating the account or a direct database change).

No AI output is accepted as authoritative without deterministic validation and authorized human review. No claim of "unhackable" is made or should be made about this or any system — the honest target is defense-in-depth, tested controls, and a completed penetration test, not an absolute guarantee.
