from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../../.env", ".env"), env_prefix="NOTAMSYS_", extra="ignore"
    )

    app_name: str = "NOTAMSYS API"
    environment: str = "development"
    secret_key: str = Field("development-only-change-this-secret", min_length=32)
    access_token_minutes: int = 30
    refresh_token_days: int = 7
    database_url: str = "sqlite+aiosqlite:///./data/notamsys.db"
    redis_url: str = "redis://localhost:6379/0"
    object_storage_endpoint: str = "http://localhost:9000"
    object_storage_access_key: str = "notamsys"
    object_storage_secret_key: str = "notamsys-development"
    object_storage_bucket: str = "notamsys-evidence"
    cors_origins: str = "http://localhost:3000"
    max_upload_bytes: int = 20 * 1024 * 1024

    # Documented off-switches for capabilities that are stubbed or partially
    # built. Each one is read by the module it gates; flipping it here should
    # never require a code change. See docs/ARCHITECTURE.md operational boundary.
    storage_backend: str = "local"  # "local" | "minio"
    ocr_engine: str = "tesseract"  # "tesseract" | "cloud" | "disabled"
    extraction_enabled: bool = False
    publication_mode: str = "simulated_sync"  # "simulated_sync" | "async_adapters"
    # Per-channel overrides -- unset (None) falls back to publication_mode
    # above. A real rollout needs AFTN live while GCAA_WEB/Email stay
    # simulated (or any other combination) at the same time; one global
    # switch can't express that, so each channel can be pinned independently
    # without disturbing the others' default.
    aftn_mode: str | None = None
    gcaa_web_mode: str | None = None
    email_mode: str | None = None
    public_intake_enabled: bool = True
    aip_provider: str = "seed"  # "seed" | "dataset"
    aftn_drop_dir: str = "data/aftn-outbox"
    # Anonymous public submissions (POST /public/requests) are attributed to
    # this seeded service account rather than requiring created_by_id to be
    # nullable across the whole NotamRequest model for one intake path.
    public_portal_email: str = "portal@notamsys.app"

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        # Managed Postgres providers (Render, Heroku-style, Railway, Neon,
        # Supabase) hand out a plain postgres://... or postgresql://...
        # connection string -- this app's async SQLAlchemy engine needs the
        # +asyncpg dialect explicitly, or it falls back to a sync driver
        # that isn't even installed here. Rewriting once at startup means
        # every deployment target's DATABASE_URL just works without a
        # manual find-replace.
        if value.startswith("postgres://"):
            value = "postgresql+asyncpg://" + value.removeprefix("postgres://")
        elif value.startswith("postgresql://"):
            value = "postgresql+asyncpg://" + value.removeprefix("postgresql://")
        elif not value.startswith("postgresql+asyncpg://"):
            return value  # not a Postgres URL (e.g. sqlite for local dev) -- leave alone

        # Those same providers' connection strings also default to libpq-
        # style query params (sslmode=require, sometimes channel_binding=
        # require) that asyncpg's connect() doesn't recognize at all --
        # confirmed live against a real Neon database: passing sslmode
        # through raises "unexpected keyword argument 'sslmode'" and the
        # app never starts. asyncpg wants ssl=require instead; channel_
        # binding has no asyncpg equivalent, so it's dropped rather than
        # guessed at.
        parts = urlsplit(value)
        query = dict(parse_qsl(parts.query))
        if "sslmode" in query:
            query["ssl"] = query.pop("sslmode")
        query.pop("channel_binding", None)
        return urlunsplit(parts._replace(query=urlencode(query)))

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def mode_for_channel(self, channel: str) -> str:
        override = {
            "AFTN": self.aftn_mode,
            "GCAA_WEB": self.gcaa_web_mode,
            "EMAIL": self.email_mode,
        }.get(channel)
        return override or self.publication_mode


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
