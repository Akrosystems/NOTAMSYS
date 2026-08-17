"""Deterministic AFTN envelope construction and ITA-2 validation. No live
circuit, credentials, or spec needed for any of this -- it's pure text
processing against publicly documented AFTN conventions and the addressees
the GCAA AIS Manual of Operations Chapter 7 specifies for Accra NOF.
"""

AFTN_LINE_WIDTH = 69
ACCRA_AFTN_ADDRESSEES = ("DGAANOTA", "DGAANOTB", "DGAANOTC")
DEFAULT_ORIGINATOR = "DGAAYNYX"
DEFAULT_PRIORITY = "GG"

# ITA-2 (Baudot-Murray telegraph alphabet) as used over AFTN: uppercase
# letters, digits, space, and a restricted punctuation set. No lowercase,
# no accented characters -- a common real-world failure mode when NOTAM
# text is typed with smart quotes or copy-pasted from a word processor.
_ITA2_CHARSET = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -.,()/:?'+=\n")


def validate_ita2(text: str) -> list[str]:
    errors: list[str] = []
    bad_chars = sorted({char for char in text if char not in _ITA2_CHARSET})
    if bad_chars:
        errors.append(
            "Message contains characters outside the AFTN ITA-2 set: "
            + ", ".join(repr(char) for char in bad_chars)
        )
    for line_number, line in enumerate(text.split("\n"), start=1):
        if len(line) > AFTN_LINE_WIDTH:
            errors.append(
                f"Line {line_number} is {len(line)} characters, exceeding the "
                f"{AFTN_LINE_WIDTH}-character AFTN line limit"
            )
    return errors


def build_envelope(
    formatted_message: str,
    addressees: tuple[str, ...] = ACCRA_AFTN_ADDRESSEES,
    originator: str = DEFAULT_ORIGINATOR,
    priority: str = DEFAULT_PRIORITY,
) -> str:
    """Builds the AFTN heading + body. `formatted_message` should already be
    the ICAO NOTAM text from services/formatter.py (uppercased, wrapped to
    69 characters). Raises ValueError if the resulting envelope isn't
    transmittable -- callers should treat that as a failed delivery, not a
    crash."""
    heading = f"{priority} {' '.join(addressees)}\n{originator}"
    envelope = f"{heading}\n{formatted_message.upper()}"
    errors = validate_ita2(envelope)
    if errors:
        raise ValueError("; ".join(errors))
    return envelope
