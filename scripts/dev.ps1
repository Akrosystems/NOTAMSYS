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
python -m pip install -e ".[dev]"
alembic upgrade head
python -m app.seed
Pop-Location
pnpm dev
