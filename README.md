# NOTAMSYS

NOTAMSYS is an open-source, full-stack system for controlled NOTAM origination, validation, approval, publication and tracking, built for the Accra International NOTAM Office by [AkroSystems](https://github.com/Akrosystems).

The codebase translates the GCAA Chapter 7 workflow into enforceable software states — a mandatory received→triage→draft→review→approved→publishing→published lifecycle with four-eyes control (a preparer can never approve their own draft) — while keeping ICAO NOTAM Selection Criteria decisions explainable, versioned and reviewable rather than a black box.

**This is not a certified aviation product.** It is a working reference implementation with an explicit, honest boundary between what's real and what's simulated — see [What's real vs. simulated](#whats-real-vs-simulated) below. No claim of "100% accuracy" or "unhackable" appears anywhere in this codebase or its docs, deliberately: neither is a property software can actually have. What NOTAMSYS provides instead is deterministic validation, mandatory human confirmation, separation of duties, full traceability and defense-in-depth. See [docs/SECURITY.md](docs/SECURITY.md).

## Features

- **Role-based workflow**: AIS Officer, AIS Specialist, NOF Manager, QMS Auditor, and a System Administrator superadmin role, each gated by a declarative RBAC matrix tested against every endpoint.
- **ICAO Doc 8126 NOTAM Selection Criteria**, all 13 categories / 1250 rules, versioned and checksummed, every row's verification status (visually confirmed vs. bulk-transcribed) shown honestly in the UI rather than presented as uniformly authoritative.
- **NOTAM workbench**: Q-code selection-criteria typeahead, live draft validation, document extraction with per-field confidence and acceptance, and status/role-aware Approve → Request changes → Publish → per-channel delivery retry controls.
- **Public and staff intake**: an anonymous public request form and an authenticated staff intake flow, both backed by real endpoints (not UI mockups).
- **Publication adapters**: real AFTN envelope construction and ITA-2 validation, a file-drop adapter for Comsoft/CADAS pickup, and real AIXM 5.1.1 event XML generation with geodesic geometry — all behind a common adapter interface so a live circuit can be added without touching the workflow engine.
- **Append-only audit trail** for every transition, evidence attachment, extraction acceptance, rule activation and delivery retry.
- **Admin console**: user management, ruleset activation, delivery retry and live platform branding (logo, name, subtitle, description — no restart needed) — the real, non-fabricated superadmin control surface. Channel adapters (AFTN/CMS/SMTP) are configured via environment variables at deploy time; see [docs/OPERATIONAL_BOUNDARY.md](docs/OPERATIONAL_BOUNDARY.md) for exactly what's live.

## Technology

- Frontend: Next.js App Router, React, TypeScript, React Hook Form, Zod and Lucide.
- Backend: Python 3.12, FastAPI, Pydantic, async SQLAlchemy and Alembic.
- Data: PostgreSQL, Redis and MinIO-compatible object storage.
- Jobs: Celery workers for extraction, integration and publication adapters.
- Operations: Docker Compose, structured logs, health checks, Ruff, Pytest, ESLint, Vitest and CI.

## Repository

```text
NOTAMSYS/
├── apps/
│   ├── api/                 FastAPI domain API, migrations, workers and tests
│   └── web/                 Next.js role-aware application and BFF routes
├── docs/
│   ├── reference/           Local-only controlled source manuals (excluded from this repo, see docs/reference/README.md)
│   ├── ARCHITECTURE.md
│   ├── DEPLOYMENT.md
│   ├── OPERATIONAL_BOUNDARY.md
│   ├── INTEGRATION_REQUIREMENTS.md  What to request from IT (email) and ATSEP (AFTN) to go live
│   ├── AFTN_BRIDGE.md       Connecting the real Comsoft/CADAS terminal
│   └── SECURITY.md
├── scripts/
│   ├── dev.ps1
│   └── aftn_bridge.py       Run on ATSEP's Comsoft box, not on the NOTAMSYS server
├── compose.yaml
├── package.json
├── pnpm-workspace.yaml
└── turbo.json
```

## Quick start with containers

1. Copy `.env.example` to `.env` and replace `NOTAMSYS_SECRET_KEY`.
2. Run:

```powershell
docker compose up --build
```

3. Open:

- Web application: `http://localhost:3000`
- API docs (Swagger UI): `http://localhost:8000/docs` — ReDoc at `/redoc`
- MinIO console: `http://localhost:9001`

Seed accounts use the development password `Notamsys!2026` — **change these before any real deployment**:

| Email | Role |
|---|---|
| `officer@notamsys.app` | AIS Officer |
| `specialist@notamsys.app` | AIS Specialist |
| `manager@notamsys.app` | NOF Manager |
| `qms@notamsys.app` | QMS Auditor |
| `admin@notamsys.app` | System Administrator (superadmin) |

## Local development

Running "the full application" means two servers up at once: the FastAPI backend (`:8000`) and the Next.js frontend (`:3000`), both pointed at the same Postgres database. Neither one alone is "the app" -- the frontend has nothing to talk to without the backend, and the backend has no UI of its own beyond `/docs`.

### Prerequisites

- Node.js 22+ and pnpm. `corepack enable` should provide the pinned version automatically, but needs write access to the Node install directory -- if it fails with an `EPERM`/permissions error (common without admin rights on Windows), use `npx pnpm@11.19.0 <command>` in place of `pnpm <command>` everywhere below instead
- Python 3.12
- A reachable PostgreSQL database -- either `docker compose up -d postgres redis minio` for just the infra containers (matches the credentials already in `.env.example`), or your own local Postgres install with a `notamsys` role/database created and `NOTAMSYS_DATABASE_URL` in `.env` updated to match its actual credentials

### One-line setup (Windows)

```powershell
./scripts/dev.ps1
```

Creates `.env` if missing, starts the Postgres/Redis/MinIO containers, installs dependencies, runs migrations and seeds the database, then opens the API in its own PowerShell window and runs the web dev server in the current one. Requires Docker for the infra containers; if you're using your own Postgres instead, comment out the `docker compose` line and make sure `.env`'s `NOTAMSYS_DATABASE_URL` already points at it.

### Manual setup (two terminals, any OS)

1. Copy `.env.example` to `.env` at the repo root, and make sure `NOTAMSYS_DATABASE_URL` points at a Postgres database that actually exists and is reachable -- the default assumes the Docker Compose Postgres service; if you're running your own instance, replace the user/password/host/port/database name to match what you actually created.

2. **Terminal 1 -- API:**

   ```powershell
   cd apps/api
   python -m venv .venv
   .venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
   pip install -e ".[dev]"
   alembic upgrade head
   python -m app.seed
   uvicorn app.main:app --reload
   ```

   Leave this running. `alembic upgrade head` creates every table; `python -m app.seed` is idempotent and does nothing on a database that already has users. If this connects to the wrong (or no) database, you'll get a connection error immediately, before the server ever starts.

3. **Terminal 2 -- web:**

   ```powershell
   pnpm install
   pnpm --filter @notamsys/web dev
   ```

4. Open `http://localhost:3000` and sign in with one of the [seed accounts](#quick-start-with-containers) above. API docs are at `http://localhost:8000/docs`.

Both terminals need to keep running for the app to work end to end -- closing either one breaks the other half.

## Deployment

`render.yaml` at the repo root is a [Render Blueprint](https://render.com/docs/blueprint-spec) that provisions the API, web app and a managed Postgres database together, with deploys gated on CI passing via `.github/workflows/deploy.yml`. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the one-time setup (connecting the repo, filling in two cross-service URLs Render can't predict, wiring the deploy-hook secrets) and what's deliberately left out (no idle Celery worker/Redis, since nothing in this codebase queues a task to one yet).

## Tests

```powershell
pnpm --filter @notamsys/web lint
pnpm --filter @notamsys/web test
pnpm --filter @notamsys/web build

cd apps/api
ruff check .
pytest
```

## What's real vs. simulated

The selection-criteria table covers all 13 Doc 8126 NOTAM Selection Criteria categories (1250 rules), every row visually verified against the source document. OCR/NLP extraction, AIXM 5.1.1 event XML, AFTN envelope construction with a file-drop adapter, the full review/approve/publish workflow, and superadmin user management are real and tested end-to-end. What's still a stub: a live AMHS/AFTN circuit (no credentials or spec exist for one), the GCAA website/email publication channels, and the real GCAA AIP (inaccessible during development — SharePoint-restricted). See [docs/OPERATIONAL_BOUNDARY.md](docs/OPERATIONAL_BOUNDARY.md) for the full capability-by-capability breakdown, kept current as the single source of truth rather than duplicated here — the running app also states this live at `/integrations` and `GET /system/status`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

Software cannot honestly guarantee 100% correctness for ambiguous or incorrect source information, and no system is unhackable. NOTAMSYS instead provides deterministic validation, source confidence thresholds, separation of duties, traceability, mandatory authorization, and defense-in-depth — see [docs/SECURITY.md](docs/SECURITY.md). Found a vulnerability? Please open a private security advisory on GitHub rather than a public issue.

## License

[MIT](LICENSE) — built by [AkroSystems](https://github.com/Akrosystems).
