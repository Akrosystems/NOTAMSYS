"""Document-extraction pipeline: OCR/text ingestion, deterministic field
parsers, and narrative Q-code suggestion.

Nothing in this package writes to a NOTAM draft directly. Every result is a
confidence-scored, provenance-tagged proposal (services/extraction/pipeline.py
:ExtractedFieldCandidate) that an AIS Officer must explicitly accept -- see
the /requests/{id}/extraction/fields/{field_id}/accept endpoint. Safety-
critical values (dates, coordinates, limits, location indicators) are parsed
by deterministic grammars, never guessed by a statistical model.
"""
