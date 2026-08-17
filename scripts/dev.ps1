$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root

if (-not (Test-Path -LiteralPath ".env")) {
    Copy-Item -LiteralPath ".env.example" -Destination ".env"
    Write-Host "Created .env from .env.example. Replace the development secret before shared use."
}

docker compose up -d postgres redis minio
pnpm install
Push-Location "apps/api"
if (-not (Test-Path -LiteralPath ".venv")) {
    python -m venv .venv
}
& ".venv\Scripts\python.exe" -m pip install -e ".[dev]"
& ".venv\Scripts\alembic.exe" upgrade head
& ".venv\Scripts\python.exe" -m app.seed
Pop-Location

# apps/api has no package.json, so it isn't a pnpm workspace member and
# `pnpm dev` (turbo dev) only ever starts the web app -- this used to
# silently leave the API never running. Start it in its own window so
# both apps' logs stay separate and either can be stopped independently,
# then run the web dev server in this window.
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\apps\api'; & '.venv\Scripts\Activate.ps1'; uvicorn app.main:app --reload"
Write-Host "API starting in a new window on http://localhost:8000 (docs at /docs)."
pnpm --filter @notamsys/web dev
