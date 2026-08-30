from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import router
from app.core.config import settings
from app.core.database import Base, engine

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    Path("data").mkdir(exist_ok=True)
    if settings.environment == "development" and settings.database_url.startswith("sqlite"):
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    logger.info("application_started", environment=settings.environment)
    yield
    await engine.dispose()


OPENAPI_TAGS = [
    {"name": "authentication", "description": "Login, session, and current-user identity."},
    {"name": "requests", "description": "NOTAM request intake, attachments, and lookup by authenticated staff."},
    {"name": "public", "description": "Unauthenticated public NOTAM request intake (see docs/SECURITY.md for its threat model)."},
    {"name": "notams", "description": "Reading and drafting the prepared NOTAM attached to a request."},
    {"name": "workflow", "description": "State-machine transitions: submit, request changes, approve. Four-eyes control is enforced here."},
    {"name": "publication", "description": "Publish, per-channel delivery status, and delivery retry. See /system/status for which channels are live vs. simulated."},
    {"name": "extraction", "description": "Option A Hybrid Pipeline: deterministic regex parsers (DTGs, coordinates, limits, ICAO codes), RapidFuzz Levenshtein OCR typo-correction with ICAO Doc 8400/OPADD Ed 4.1 abbreviation normalizer, and local sentence-transformers (all-MiniLM-L6-v2) semantic embeddings against Doc 8126 selection criteria. Runs automatically on attachment upload. Re-run and field acceptance endpoints let officers correct or confirm extracted values. Toggle via NOTAMSYS_EXTRACTION_ENABLED."},
    {"name": "rules", "description": "ICAO Doc 8126 NOTAM Selection Criteria catalog and versioned ruleset activation."},
    {"name": "reference", "description": "AIP-derived reference data: FIRs, aerodromes, active dataset."},
    {"name": "quality", "description": "Append-only audit trail."},
    {"name": "admin", "description": "Superadmin-only user management. Every SYSTEM_ADMIN action is audited like any other."},
    {"name": "dashboard", "description": "Aggregate operational metrics."},
    {"name": "system", "description": "Live capability/configuration status -- what's real vs. simulated, not hardcoded."},
]

app = FastAPI(
    title="NOTAMSYS API",
    summary="Controlled NOTAM origination, assurance, approval and publication",
    description=(
        "Backend for NOTAMSYS, an open-source NOTAM office system built by AkroSystems. "
        "Extraction uses an Option A Hybrid Pipeline (deterministic regex safety parsers + "
        "RapidFuzz OCR typo-correction + local sentence-transformers semantic embeddings against "
        "ICAO Doc 8126 Selection Criteria). AIP reference data is sourced from the Ghana AIP "
        "7th Edition (2026) and expanded with FIR neighbour data (ASECNA AIM). "
        "See /integrations (frontend) or /system/status (this API) for an honest, "
        "live statement of what's real versus simulated -- nothing here claims more "
        "than it does."
    ),
    version="0.1.0",
    contact={"name": "AkroSystems", "url": "https://akrosystems.com"},
    license_info={"name": "MIT", "url": "https://github.com/Akrosystems/NOTAMSYS/blob/main/LICENSE"},
    openapi_tags=OPENAPI_TAGS,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Correlation-ID"],
)
app.include_router(router)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": "notamsys-api", "version": "0.1.0"}
