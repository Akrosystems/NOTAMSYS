import hashlib
import io
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.core.config import settings


@dataclass(frozen=True)
class StoredObject:
    key: str
    size: int
    sha256: str


class StorageBackend(Protocol):
    """Evidence storage boundary. Attachments are immutable once written and
    content-addressed by sha256; a backend must never overwrite an existing key."""

    async def put(self, request_id: uuid.UUID, filename: str, content: bytes) -> StoredObject: ...

    async def get(self, key: str) -> bytes: ...

    async def put_named(self, key: str, content: bytes) -> StoredObject:
        """Write to a fixed, caller-chosen key, overwriting any existing
        object there. For mutable singletons like the org branding logo --
        deliberately not content-addressed like put(), since the whole
        point is that re-uploading replaces the previous one at a stable
        key/URL rather than accumulating immutable evidence."""
        ...


def _content_addressed_key(request_id: uuid.UUID, filename: str, content: bytes) -> tuple[str, str]:
    digest = hashlib.sha256(content).hexdigest()
    safe_name = Path(filename).name.replace(" ", "_")
    return f"requests/{request_id}/{digest[:16]}-{safe_name}", digest


class EvidenceStorage:
    """Local filesystem evidence boundary; default for development and tests."""

    def __init__(self, root: Path = Path("data/evidence")) -> None:
        self.root = root

    async def put(self, request_id: uuid.UUID, filename: str, content: bytes) -> StoredObject:
        if len(content) > settings.max_upload_bytes:
            raise ValueError("Attachment exceeds configured upload limit")
        key, digest = _content_addressed_key(request_id, filename, content)
        target = self.root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(content)
        return StoredObject(key=key, size=len(content), sha256=digest)

    async def get(self, key: str) -> bytes:
        target = self.root / key
        if not target.exists():
            raise FileNotFoundError(key)
        return target.read_bytes()

    async def put_named(self, key: str, content: bytes) -> StoredObject:
        if len(content) > settings.max_upload_bytes:
            raise ValueError("Upload exceeds configured limit")
        digest = hashlib.sha256(content).hexdigest()
        target = self.root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return StoredObject(key=key, size=len(content), sha256=digest)


class MinioStorage:
    """MinIO/S3-compatible evidence boundary for production deployments.

    The `minio` client is synchronous; calls block the event loop briefly,
    matching the local backend's synchronous filesystem I/O. Acceptable at
    current scale — revisit with a thread offload if upload volume grows.
    """

    def __init__(self) -> None:
        from minio import Minio

        endpoint = settings.object_storage_endpoint
        secure = endpoint.startswith("https://")
        host = endpoint.removeprefix("https://").removeprefix("http://")
        self._client = Minio(
            host,
            access_key=settings.object_storage_access_key,
            secret_key=settings.object_storage_secret_key,
            secure=secure,
        )
        self._bucket = settings.object_storage_bucket
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)

    async def put(self, request_id: uuid.UUID, filename: str, content: bytes) -> StoredObject:
        if len(content) > settings.max_upload_bytes:
            raise ValueError("Attachment exceeds configured upload limit")
        key, digest = _content_addressed_key(request_id, filename, content)
        try:
            self._client.stat_object(self._bucket, key)
        except Exception:  # noqa: BLE001 - minio raises a broad S3Error for "not found"
            self._client.put_object(self._bucket, key, io.BytesIO(content), length=len(content))
        return StoredObject(key=key, size=len(content), sha256=digest)

    async def get(self, key: str) -> bytes:
        response = self._client.get_object(self._bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    async def put_named(self, key: str, content: bytes) -> StoredObject:
        if len(content) > settings.max_upload_bytes:
            raise ValueError("Upload exceeds configured limit")
        digest = hashlib.sha256(content).hexdigest()
        self._client.put_object(self._bucket, key, io.BytesIO(content), length=len(content))
        return StoredObject(key=key, size=len(content), sha256=digest)


def _build_storage() -> StorageBackend:
    if settings.storage_backend == "minio":
        return MinioStorage()
    return EvidenceStorage()


storage: StorageBackend = _build_storage()
