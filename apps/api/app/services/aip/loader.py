"""Loads app/data/aip/*.json into memory for seeding. Mirrors the pattern
in services/rules.py: the JSON file is the reviewable source of truth, the
database row is a checksummed, activatable copy of it."""

import hashlib
import json
from pathlib import Path
from typing import Any

_DATASET_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "aip"


def load_dataset_payload(filename: str = "gcaa-seed.json") -> dict[str, Any]:
    target = _DATASET_DIR / filename
    payload: dict[str, Any] = json.loads(target.read_text(encoding="utf-8"))
    return payload


def canonical_checksum(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
