# Deploying to Render

`render.yaml` at the repo root is a [Render Blueprint](https://render.com/docs/blueprint-spec) that provisions the API and web app together. Render can't be driven from this repo alone, though -- a few one-time steps need your Render account.

## What's in the Blueprint (and what isn't)

- **`notamsys-api`** -- the FastAPI backend, built from `apps/api/Dockerfile`. Runs `alembic upgrade head` before starting on every deploy, so the schema is always current.
- **`notamsys-web`** -- the Next.js frontend, built from `apps/web/Dockerfile`.
- **No managed Postgres in the Blueprint.** A Render free account allows only one active free-tier database account-wide -- if that's already spoken for by another project, use an external provider instead (Neon, Supabase, or your own instance both work; the app normalizes whatever connection string style they hand you). `NOTAMSYS_DATABASE_URL` is a manual env var on `notamsys-api` for exactly this reason. If you don't have that constraint, add a `databases:` block back to `render.yaml` and switch it to `fromDatabase` instead -- see git history for the exact shape.
- **No Celery worker, no Redis.** Nothing in this codebase currently dispatches a Celery task -- every call site invokes the same underlying function inline instead of queuing it (see `apps/api/app/worker.py`'s docstrings). Deploying an idle worker with nothing feeding it would just be paying for infrastructure that does nothing.

## One-time setup

1. **Connect the repo.** In the Render dashboard: **New > Blueprint**, pick this repository. Render reads `render.yaml` and shows you the two resources above before creating anything.

2. **Fill in the seven env vars Render will prompt for** (none of these are safe to hardcode in `render.yaml`, which is committed to a public repo -- real credentials don't belong there, and the two cross-service URLs can't be predicted since Render only guarantees your requested service name if it isn't already taken by someone else):
   - On `notamsys-api`: `NOTAMSYS_DATABASE_URL` = your Postgres connection string (Neon/Supabase/etc. give you a `postgresql://...` or `postgres://...` URL -- paste it as-is, `Settings.normalize_database_url` handles the `+asyncpg` dialect and any `sslmode`/`channel_binding` query params asyncpg doesn't natively understand).
   - On `notamsys-api`: `NOTAMSYS_CORS_ORIGINS` = the web service's URL, e.g. `https://notamsys-web.onrender.com`
   - On `notamsys-api`: **`NOTAMSYS_OBJECT_STORAGE_ENDPOINT`/`_ACCESS_KEY`/`_SECRET_KEY`/`_BUCKET`** -- required, not optional. `NOTAMSYS_STORAGE_BACKEND=minio` in `render.yaml` means the API connects to this bucket **at startup**, before it serves a single request -- deploying with these unset or wrong makes the service crash-loop, not just leave evidence storage disabled. Get these from an S3-compatible provider first (Cloudflare R2's free tier is the fastest -- create a bucket, then an R2 API token with read/write access to it; the "S3 API" endpoint it gives you is `NOTAMSYS_OBJECT_STORAGE_ENDPOINT`). Have all four ready *before* you sync the Blueprint or trigger a deploy.
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

## What's real now versus what still needs credentials

- **Uploaded evidence survives restarts and redeploys.** `notamsys-api` has no persistent disk -- Render's free plan doesn't support them at all -- so this deploys against `NOTAMSYS_STORAGE_BACKEND=minio` (a real S3-compatible bucket) instead of the local filesystem Render wipes on every deploy. Requires the four `NOTAMSYS_OBJECT_STORAGE_*` values from step 2 above to already be set correctly; see that step for what happens if they're wrong. If you'd rather use a persistent disk on a paid plan instead, switch `NOTAMSYS_STORAGE_BACKEND` back to `local` and add:
    ```yaml
    disk:
      name: notamsys-api-data
      mountPath: /app/data
      sizeGB: 1
    ```
- **OCR/scanned-document extraction is on** (`NOTAMSYS_EXTRACTION_ENABLED=true`, `NOTAMSYS_OCR_ENGINE=tesseract`). `apps/api/Dockerfile` installs the `tesseract-ocr`/`tesseract-ocr-eng` system packages and the `.[ocr]` Python extras (PyMuPDF/pytesseract/Pillow) -- both PDF text-layer extraction and scanned-image OCR now run for real on upload, not just the text-layer path. See [OPERATIONAL_BOUNDARY.md](OPERATIONAL_BOUNDARY.md) for what's independently verified versus what's real-but-unverified-in-this-exact-deployment (the Tesseract binary itself was only checked to be a standard Debian package name, not run end-to-end here -- confirm the first real upload after deploying actually extracts something before relying on it).
- **AFTN/Comsoft and email publication channels stay simulated by default** (`NOTAMSYS_PUBLICATION_MODE=simulated_sync`) -- GCAA website has no CMS to integrate with at all yet, so it can't go further than simulated regardless. AFTN and Email specifically have a real path once credentials exist:
  - **AFTN** -- `docs/AFTN_BRIDGE.md`. Set `NOTAMSYS_AFTN_MODE=async_adapters` and `NOTAMSYS_AFTN_BRIDGE_API_KEY` on `notamsys-api`, then run `scripts/aftn_bridge.py` on ATSEP's own Comsoft box (not on Render).
  - **Email (outbound)** -- set `NOTAMSYS_EMAIL_MODE=async_adapters` plus `NOTAMSYS_SMTP_HOST`/`PORT`/`USERNAME`/`PASSWORD`/`FROM_ADDRESS` once IT provides SMTP credentials for the distribution mailbox. See `docs/INTEGRATION_REQUIREMENTS.md` for exactly what to ask for.
  - **Email (inbound)** -- a separate, genuinely new capability: `python -m app.email_poller` reads NOTAM request emails from a shared mailbox once `NOTAMSYS_IMAP_HOST`/`PORT`/`USERNAME`/`PASSWORD` are set. This needs its own always-running process -- either a second Render **Background Worker** service (additional cost, not in `render.yaml` by default) pointed at the same image with start command `python -m app.email_poller`, or an external scheduler hitting a wrapper on an interval. It refuses to start at all if IMAP isn't configured, so there's no risk of silently running with nothing to do.
  - GCAA website distribution has no real path yet -- no CMS exists to integrate against.
- **Whatever free-tier limits your external Postgres provider has still apply** -- e.g. Neon's free plan auto-suspends an idle compute (the first request after suspension is slower while it wakes back up, not an app-level problem) and caps storage. Check your provider's own limits rather than assuming this app's config works around them.
- **Render's free plan spins a service down after 15 minutes of no traffic.** This project tried a GitHub Actions scheduled workflow pinging both services every 10 minutes to keep that idle timer from firing -- confirmed live to be unreliable and removed: GitHub's scheduled-cron triggers on a public/free-tier repo are low-priority and slipped by 28-43 minutes between runs in practice, comfortably missing the 15-minute deadline and causing real production outages (users unable to log in). Use an external uptime monitor instead:
  - **UptimeRobot** (free tier, 5-minute interval) -- create a free account at uptimerobot.com, add two **HTTP(s)** monitors: one for `https://notamsys-api.onrender.com/health` and one for `https://notamsys-web.onrender.com/`, both on a 5-minute check interval. UptimeRobot is a purpose-built monitoring service (not a best-effort scheduler sharing capacity with millions of other jobs), so it's far more reliable for this than GitHub Actions was -- though still not a guarantee, since it's still an external ping racing the same 15-minute deadline.
  - This does *not* touch Neon's separate auto-suspend above.
  - The only fully guaranteed fix, with no ping-racing-a-deadline risk at all, is upgrading the service(s) to a paid Render plan.
