import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.models import NotamKind

RULESET_VERSION = "8126-2022.2"

_DATASET_DIR = Path(__file__).resolve().parent.parent / "data" / "nsc"


@dataclass(frozen=True)
class SelectionRule:
    subject_code: str
    subject: str
    condition_code: str
    condition: str
    traffic: str
    purpose: str
    scope: str
    source: str
    # HAND_CURATED: deliberately entered by a human from the source document.
    # VERIFIED_VISUAL: bulk-transcribed then visually confirmed against a
    #   rendered page (Traffic/Purpose column alignment checked by eye).
    # TRANSCRIBED_UNVERIFIED: bulk-transcribed but not yet visually confirmed
    #   -- validate_selection() warns rather than silently trusting these.
    verification_status: str = "HAND_CURATED"

    @property
    def q_code(self) -> str:
        return f"Q{self.subject_code}{self.condition_code}"


def _dataset_path(version: str = RULESET_VERSION) -> Path:
    return _DATASET_DIR / f"{version}.json"


def load_dataset_payload(path: Path | None = None) -> dict[str, Any]:
    target = path or _dataset_path()
    payload: dict[str, Any] = json.loads(target.read_text(encoding="utf-8"))
    return payload


def load_dataset(path: Path | None = None) -> tuple[SelectionRule, ...]:
    payload = load_dataset_payload(path)
    return tuple(SelectionRule(**row) for row in payload["rules"])


def canonical_checksum(payload: dict[str, Any]) -> str:
    """Deterministic checksum of a dataset payload, independent of key/dict
    ordering, used to detect drift between a RuleVersion row and its content."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


class RuleCatalog:
    """In-process, hot-swappable selection-criteria catalog.

    The JSON dataset on disk is the reviewable, git-blamed source of truth;
    a RuleVersion database row is a checksummed, activatable copy of it.
    Activating a version (see api/router.py) calls reload() so the running
    process picks up the change without a redeploy.
    """

    def __init__(self, rules: tuple[SelectionRule, ...]) -> None:
        self._rules = rules
        self._by_pair: dict[tuple[str, str], SelectionRule] = {}
        self._by_qcode: dict[str, SelectionRule] = {}
        for rule in rules:
            self._by_qcode[rule.q_code] = rule
            self._by_pair[(rule.subject.casefold(), rule.condition.casefold())] = rule
            self._by_pair[(rule.subject_code.casefold(), rule.condition_code.casefold())] = rule

    @property
    def rules(self) -> tuple[SelectionRule, ...]:
        return self._rules

    def find(self, subject: str, condition: str) -> SelectionRule | None:
        return self._by_pair.get((subject.casefold().strip(), condition.casefold().strip()))

    def find_by_qcode(self, q_code: str) -> SelectionRule | None:
        return self._by_qcode.get(q_code.upper())

    def coverage(self) -> dict[str, int]:
        verified = sum(
            1
            for rule in self._rules
            if rule.verification_status in {"HAND_CURATED", "VERIFIED_VISUAL"}
        )
        return {"verified_rule_count": verified, "total_rule_count": len(self._rules)}


_catalog = RuleCatalog(load_dataset())


def get_catalog() -> RuleCatalog:
    return _catalog


def reload_catalog(rule_rows: list[dict[str, Any]]) -> None:
    """Hot-swap the process-wide catalog, e.g. after activating a new
    approved RuleVersion. Does not touch the on-disk dataset file."""
    global _catalog
    _catalog = RuleCatalog(tuple(SelectionRule(**row) for row in rule_rows))


def find_rule(subject: str, condition: str) -> SelectionRule | None:
    return _catalog.find(subject, condition)


def validate_selection(
    subject: str,
    condition: str,
    traffic: str,
    purpose: str,
    scope: str,
    kind: NotamKind = NotamKind.NEW,
) -> dict[str, object]:
    rule = find_rule(subject, condition)
    errors: list[str] = []
    warnings: list[str] = []
    if rule is None:
        errors.append("No controlled NOTAM Selection Criteria mapping was found")
        return {"valid": False, "errors": errors, "warnings": warnings, "rule": None}
    if rule.verification_status == "TRANSCRIBED_UNVERIFIED":
        warnings.append(
            f"Selection criteria row for {rule.q_code} was bulk-transcribed and not yet "
            f"visually verified against {rule.source} -- confirm before relying on it"
        )
    if kind == NotamKind.CANCEL:
        warnings.append("NOTAMC qualifiers must be identical to the original NOTAM")
    else:
        if traffic != rule.traffic:
            errors.append(f"Traffic must be {rule.traffic} for {rule.q_code}")
        if purpose != rule.purpose:
            errors.append(f"Purpose must be {rule.purpose} for {rule.q_code}")
        if scope != rule.scope:
            errors.append(f"Scope must be {rule.scope} for {rule.q_code}")
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "rule": {**asdict(rule), "q_code": rule.q_code},
        "ruleset_version": RULESET_VERSION,
    }
