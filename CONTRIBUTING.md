# Contributing to NOTAMSYS

Thanks for looking at NOTAMSYS. This is a reference implementation of a real-world NOTAM office workflow, not a toy — see [docs/OPERATIONAL_BOUNDARY.md](docs/OPERATIONAL_BOUNDARY.md) before assuming a capability is finished, and please keep that file honest as you change things.

## Ground rules

- **No unearned claims.** Don't describe a stub or simulated adapter as "working," and don't add fallback data that could be mistaken for a live backend response (see `apps/web/src/lib/api.ts`'s `DEMO_MODE` gate for why this matters here specifically).
- **Update `docs/OPERATIONAL_BOUNDARY.md`** in the same PR whenever a capability moves between Stub / Partial / Real.
- **Safety-critical fields stay deterministic.** OCR/NLP extraction may only *propose* values for dates, coordinates, limits and Q-codes — never auto-fill them without an explicit human acceptance step.

## Setup

```powershell
pnpm install
cd apps/api
python -m pip install -e ".[dev]"
```

See the README's [Local development](README.md#local-development) section for running both stacks.

## Before opening a PR

```powershell
# Backend
cd apps/api
ruff check .
pytest

# Frontend
pnpm --filter @notamsys/web lint
pnpm --filter @notamsys/web test
pnpm --filter @notamsys/web build
```

- New backend endpoints that mutate state need a role-gate entry added to `apps/api/tests/test_rbac_matrix.py`.
- New Alembic migrations must be generated via `alembic revision --autogenerate` against a temp database and hand-reviewed — never edit the frozen initial migration.
- Frontend pages that call the backend need `export const dynamic = "force-dynamic"` unless they're genuinely static, or `next build` will try to prerender them with no backend available.

## Reporting a vulnerability

Please use GitHub's private security advisory feature rather than a public issue.
