import uuid

import pytest

from app.services.storage import EvidenceStorage


async def test_put_get_round_trip(tmp_path) -> None:
    backend = EvidenceStorage(root=tmp_path)
    request_id = uuid.uuid4()
    content = b"NOTAM REQUEST FORM CONTENT"
    stored = await backend.put(request_id, "request.pdf", content)
    assert await backend.get(stored.key) == content


async def test_sha256_and_key_stable_for_identical_content(tmp_path) -> None:
    backend = EvidenceStorage(root=tmp_path)
    request_id = uuid.uuid4()
    content = b"identical bytes"
    first = await backend.put(request_id, "a.txt", content)
    second = await backend.put(request_id, "a.txt", content)
    assert first.sha256 == second.sha256
    assert first.key == second.key


async def test_get_missing_key_raises(tmp_path) -> None:
    backend = EvidenceStorage(root=tmp_path)
    with pytest.raises(FileNotFoundError):
        await backend.get("requests/does-not-exist/00-missing.txt")


async def test_oversize_upload_rejected(tmp_path, monkeypatch) -> None:
    from app.services import storage as storage_module

    monkeypatch.setattr(storage_module.settings, "max_upload_bytes", 4)
    backend = EvidenceStorage(root=tmp_path)
    with pytest.raises(ValueError):
        await backend.put(uuid.uuid4(), "big.txt", b"way too large")
