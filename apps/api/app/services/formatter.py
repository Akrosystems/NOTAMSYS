from datetime import UTC, datetime

from app.models import NotamKind
from app.schemas import NotamDraftCreate


def dtg(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%y%m%d%H%M")


def wrap_notam_text(text: str, prefix: str = "", width: int = 69) -> str:
    """Wraps text so that the first line (including `prefix`) and all subsequent lines
    are strictly within `width` characters."""
    words = " ".join(text.upper().split()).split(" ")
    lines: list[str] = []
    current = prefix
    for word in words:
        candidate = f"{current} {word}".strip() if current else word
        if len(candidate) > width and current != prefix and current != "":
            lines.append(current)
            current = word
        elif len(candidate) > width and (current == prefix or current == ""):
            avail = width - len(current)
            if avail > 0:
                lines.append(f"{current}{word[:avail]}")
                remainder = word[avail:]
            else:
                lines.append(current)
                remainder = word
            while len(remainder) > width:
                lines.append(remainder[:width])
                remainder = remainder[width:]
            current = remainder
        else:
            current = candidate
    if current and current != prefix:
        lines.append(current)
    return "\n".join(lines)


def format_notam(
    draft: NotamDraftCreate,
    serial: int,
    year: int,
    replaced_identifier: str | None = None,
) -> str:
    """`replaced_identifier` is the prior NOTAM's identifier (e.g. "A0165/26"),
    required for NOTAMR/NOTAMC per Doc 8126: the replaced/cancelled NOTAM's
    identifier follows the kind directly, with no "REF" literal -- e.g.
    "(A0166/26 NOTAMR A0165/26". Passing None when the draft's `kind`
    requires it is a caller bug, not a formatting choice."""
    identifier = f"{draft.series.value}{serial:04d}/{year % 100:02d}"
    relationship = ""
    if draft.kind in {NotamKind.REPLACE, NotamKind.CANCEL} and replaced_identifier:
        relationship = f" {replaced_identifier}"
    c_value = (
        "PERM"
        if draft.item_c_qualifier == "PERM"
        else (f"{dtg(draft.item_c)}{draft.item_c_qualifier or ''}" if draft.item_c else "")
    )
    sections = [
        f"({identifier} {draft.kind.value}{relationship}",
        (
            f"Q){draft.fir}/{draft.q_code}/{draft.traffic}/{draft.purpose}/{draft.scope}/"
            f"{draft.lower_limit}/{draft.upper_limit}/{draft.coordinates_radius}"
        ),
        f"A){draft.item_a} B){dtg(draft.item_b)} C){c_value}",
    ]
    if draft.item_d:
        sections.append(wrap_notam_text(draft.item_d, prefix="D)"))
    sections.append(wrap_notam_text(draft.item_e, prefix="E)"))
    if draft.item_f:
        sections.append(wrap_notam_text(draft.item_f, prefix="F)"))
    if draft.item_g:
        sections.append(wrap_notam_text(draft.item_g, prefix="G)"))
    if sections:
        last_section = sections[-1]
        lines = last_section.split("\n")
        if len(lines[-1]) + 1 <= 69:
            lines[-1] = f"{lines[-1]})"
        else:
            lines.append(")")
        sections[-1] = "\n".join(lines)
    return "\n".join(sections)


def build_aixm_event(draft: NotamDraftCreate, identifier: str) -> dict[str, object]:
    return {
        "model": "AIXM 5.1.1",
        "specification": "Digital NOTAM 2.0",
        "event": {
            "identifier": identifier,
            "interpretation": "TEMPDELTA" if draft.item_c_qualifier != "PERM" else "PERMDELTA",
            "validTime": {
                "beginPosition": draft.item_b.astimezone(UTC).isoformat(),
                "endPosition": draft.item_c.astimezone(UTC).isoformat() if draft.item_c else None,
            },
            "location": draft.item_a,
            "qCode": draft.q_code,
            "description": draft.item_e,
        },
    }
