"""Suggests Q-code candidates for free-text NOTAM content (e.g. Item E /
'Full Text') by matching against the active selection-criteria catalog
(services/rules.py). Always returns a ranked list, never a single silent
answer -- an AIS Officer picks (or rejects all of) the suggestions."""

from app.services.rules import SelectionRule, get_catalog

_SCORE_CEILING = 4  # exact subject phrase (2) + exact condition phrase (2)
_MIN_SCORE = 2  # below this, a single coincidental word overlap is noise, not a suggestion


def suggest_q_codes(narrative: str, limit: int = 3) -> list[dict[str, object]]:
    text = narrative.casefold()
    text_words = set(text.split())
    scored: list[tuple[int, SelectionRule]] = []
    for rule in get_catalog().rules:
        subject, condition = rule.subject.casefold(), rule.condition.casefold()
        score = 0
        if subject in text:
            score += 2
        if condition in text:
            score += 2
        score += len(set(subject.split()) & text_words)
        score += len(set(condition.split()) & text_words)
        if score >= _MIN_SCORE:
            scored.append((score, rule))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {
            "q_code": rule.q_code,
            "subject": rule.subject,
            "condition": rule.condition,
            "traffic": rule.traffic,
            "purpose": rule.purpose,
            "scope": rule.scope,
            "verification_status": rule.verification_status,
            "score": score,
            "confidence": min(90, round(score / _SCORE_CEILING * 90)),
        }
        for score, rule in scored[:limit]
    ]
