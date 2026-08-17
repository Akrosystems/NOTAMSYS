from functools import lru_cache

from pydantic import Field
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
    public_intake_enabled: bool = True
    aip_provider: str = "seed"  # "seed" | "dataset"
    aftn_drop_dir: str = "data/aftn-outbox"
    # Anonymous public submissions (POST /public/requests) are attributed to
    # this seeded service account rather than requiring created_by_id to be
    # nullable across the whole NotamRequest model for one intake path.
    public_portal_email: str = "portal@notamsys.app"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
