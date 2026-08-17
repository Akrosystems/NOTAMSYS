# Deploying to Render

`render.yaml` at the repo root is a [Render Blueprint](https://render.com/docs/blueprint-spec) that provisions the API and web app together. Render can't be driven from this repo alone, though -- a few one-time steps need your Render account.

## What's in the Blueprint (and what isn't)

- **`notamsys-api`** -- the FastAPI backend, built from `apps/api/Dockerfile`. Runs `alembic upgrade head` before starting on every deploy, so the schema is always current.
- **`notamsys-web`** -- the Next.js frontend, built from `apps/web/Dockerfile`.
- **No managed Postgres in the Blueprint.** A Render free account allows only one active free-tier database account-wide -- if that's already spoken for by another project, use an external provider instead (Neon, Supabase, or your own instance both work; the app normalizes whatever connection string style they hand you). `NOTAMSYS_DATABASE_URL` is a manual env var on `notamsys-api` for exactly this reason. If you don't have that constraint, add a `databases:` block back to `render.yaml` and switch it to `fromDatabase` instead -- see git history for the exact shape.
- **No Celery worker, no Redis.** Nothing in this codebase currently dispatches a Celery task -- every call site invokes the same underlying function inline instead of queuing it (see `apps/api/app/worker.py`'s docstrings). Deploying an idle worker with nothing feeding it would just be paying for infrastructure that does nothing.

## One-time setup

1. **Connect the repo.** In the Render dashboard: **New > Blueprint**, pick this repository. Render reads `render.yaml` and shows you the two resources above before creating anything.

2. **Fill in the three env vars Render will prompt for** (none of these are safe to hardcode in `render.yaml`, which is committed to a public repo -- a real connection string doesn't belong there, and the two cross-service URLs can't be predicted since Render only guarantees your requested service name if it isn't already taken by someone else):
   - On `notamsys-api`: `NOTAMSYS_DATABASE_URL` = your Postgres connection string (Neon/Supabase/etc. give you a `postgresql://...` or `postgres://...` URL -- paste it as-is, `Settings.normalize_database_url` handles the `+asyncpg` dialect and any `sslmode`/`channel_binding` query params asyncpg doesn't natively understand).
   - On `notamsys-api`: `NOTAMSYS_CORS_ORIGINS` = the web service's URL, e.g. `https://notamsys-web.onrender.com`
   - On `notamsys-web`: `INTERNAL_API_URL` and `NEXT_PUBLIC_API_URL` = the API service's URL + `/api/v1`, e.g. `https://notamsys-api.onrender.com/api/v1`

   If you don't have the two service URLs yet, create the Blueprint anyway (Render assigns URLs immediately, before the first deploy finishes), note them, then fill these in under each service's **Environment** tab and trigger a manual deploy once.

3. **Seed the database once.** This is deliberately not automatic -- an unattended auto-seed would mean every deployment starts with the same publicly-known demo password (`Notamsys!2026`). From the `notamsys-api` service's **Shell** tab in the Render dashboard:

   ```bash
   python -m app.seed
   ```

   Then log in as `admin@notamsys.app` and change every seeded account's password before treating this as more than a demo.

4. **Wire up CI-gated deploys.** `render.yaml` sets `autoDeploy: false` on both services on purpose -- deploys should happen because tests passed, not on every push regardless. `.github/workflows/deploy.yml` triggers a deploy only after the `CI` workflow succeeds on `main`. It needs two repo secrets:
   - Get each service's Deploy Hook URL from its Render dashboard: **Settings > Deploy Hook**.
   - In GitHub: **Settings > Secrets and variables > Actions**, add `RENDER_API_DEPLOY_HOOK` and `RENDER_WEB_DEPLOY_HOOK` with those values.

   Without this step, `render.yaml`'s services exist but nothing redeploys them automatically on new commits -- you'd need to click **Manual Deploy** in the Render dashboard yourself.

## What you still don't get for free

- **Uploaded evidence files don't survive a restart or redeploy.** `notamsys-api` has no persistent disk -- Render's free plan doesn't support them at all, and attaching one makes the Blueprint fail to validate on that tier. `NOTAMSYS_STORAGE_BACKEND=local` writes to the container's filesystem, which Render wipes on every deploy and periodically recycles even without one. This is fine for trying the app out; it's not fine for anything you need to keep. Two ways to fix it once that matters:
  - Upgrade `notamsys-api`'s plan to Starter or above in `render.yaml`, then add back:
    ```yaml
    disk:
      name: notamsys-api-data
      mountPath: /app/data
      sizeGB: 1
    ```
  - Or switch `NOTAMSYS_STORAGE_BACKEND` to `minio` and point `NOTAMSYS_OBJECT_STORAGE_*` at a real S3-compatible bucket (AWS S3, Cloudflare R2, Backblaze B2, or your own MinIO) -- works on the free plan since nothing is written to local disk.
- **OCR/scanned-document extraction** stays off (`NOTAMSYS_EXTRACTION_ENABLED=false`). The Docker image doesn't install the `ocr` extras group (PyMuPDF/pytesseract/Pillow) or a `tesseract` binary -- turning extraction on without also rebuilding the image with those would fail at the first upload. See [OPERATIONAL_BOUNDARY.md](OPERATIONAL_BOUNDARY.md).
- **AFTN/Comsoft, GCAA website and email publication channels** stay simulated (`NOTAMSYS_PUBLICATION_MODE=simulated_sync`) -- there's no live circuit or CMS/SMTP credentials to point at yet, on Render or anywhere else.
- **Whatever free-tier limits your external Postgres provider has still apply** -- e.g. Neon's free plan auto-suspends an idle compute (the first request after suspension is slower while it wakes back up, not an app-level problem) and caps storage. Check your provider's own limits rather than assuming this app's config works around them.
- **Render's free plan spins a service down after 15 minutes of no traffic.** `.github/workflows/keep-alive.yml` pings both services' public URLs every 10 minutes to keep that idle timer from firing -- an unofficial workaround (Render doesn't publish or guarantee this), not a config option. It does *not* touch Neon's separate auto-suspend above, and GitHub's scheduled-cron timing can slip by several minutes under load, so it reduces cold starts rather than eliminating them. The only guaranteed fix is upgrading the service(s) to a paid Render plan.
