"""Semantic vector embedding matcher for ICAO Doc 8126 NOTAM Selection Criteria.

Uses local sentence-transformers (all-MiniLM-L6-v2) to map free-text narrative descriptions
to the most relevant ICAO Doc 8126 Selection Criteria rules based on semantic meaning,
enabling accurate Q-code matching even when originators use non-standard terminology.

Tier 2 of the three-tier suggestion pipeline (keyword_rules -> lexical -> semantic).
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from app.services.rules import SelectionRule, get_catalog

logger = logging.getLogger(__name__)

_MODEL_NAME = "all-MiniLM-L6-v2"
_EMBEDDING_CACHE: dict[str, Any] = {}

# Module-level flag: True while sentence-transformers weights are being
# downloaded/loaded for the first time. Used by /system/status so the
# frontend can show a loader instead of silently waiting for suggestions.
_model_loading: bool = False


# ---------------------------------------------------------------------------
# Subject-code synonym map: expands each rule's embedding text so the vector
# model can match non-standard phrasing to the correct subject code.
# ---------------------------------------------------------------------------
_SUBJECT_SYNONYMS: dict[str, list[str]] = {
    "MW": ["strip", "runway strip", "runway shoulder", "shoulder",
           "east side of runway", "west side of runway", "side of runway",
           "runway edge area", "grassed area beside runway"],
    "MR": ["runway", "rwy", "runway pavement", "runway surface",
           "on the runway", "runway centreline"],
    "MX": ["taxiway", "twy", "taxi track", "taxiway pavement"],
    "MN": ["apron", "ramp", "parking area", "aircraft parking"],
    "MT": ["threshold", "thr", "runway threshold", "displaced threshold"],
    "MS": ["stopway", "swy", "runway stopway"],
    "MC": ["clearway", "cwy", "runway clearway"],
    "MU": ["turning bay", "runway turning bay", "aircraft turning area"],
    "MK": ["parking bay", "parking stand", "designated parking"],
    "MP": ["aircraft stand", "stand", "parking position"],
    "MM": ["marking", "daylight marking", "runway marking", "taxiway marking"],
    "MO": ["stop bar", "stopbar", "runway holding position light"],
    "MY": ["rapid exit taxiway", "ret", "rapid exit", "high speed turn-off"],
    "MA": ["movement area", "manoeuvring area", "airfield movement area"],
    "FA": ["aerodrome", "airport", "airfield", "ad"],
    "FH": ["helipad", "helideck", "helicopter landing area", "alighting area"],
    "FP": ["heliport", "helicopter airport"],
    "LA": ["approach lighting", "approach light system", "als", "alsf", "malsr"],
    "LB": ["papi", "vasi", "visual approach slope indicator", "precision approach path indicator"],
    "LR": ["runway edge light", "runway lighting", "redl", "reil", "runway lights"],
    "LT": ["taxiway lighting", "taxiway light", "tgl", "centerline light"],
    "LE": ["aerodrome beacon", "rotating beacon", "bcn"],
    "LO": ["obstacle light", "obstruction light", "warning light on structure"],
    "IA": ["ils", "instrument landing system", "full ils"],
    "IC": ["localizer", "loc", "ils localizer"],
    "ID": ["glide path", "glide slope", "gp", "ils glide path"],
    "NA": ["vor", "vhf omnidirectional range", "dvor"],
    "ND": ["dme", "distance measuring equipment"],
    "NB": ["ndb", "non-directional beacon", "non-directional radio beacon"],
    "CA": ["frequency change", "frequency", "freq", "radio frequency"],
    "CF": ["atis", "automatic terminal information service"],
    "OA": ["radar", "psr", "ssr", "approach radar", "surveillance radar"],
}


def _build_rule_text(rule: SelectionRule) -> str:
    """Builds a rich natural-language description of a rule for embedding.

    Includes synonym phrases so the embedding model associates the rule with
    common field phrasing variants (e.g. 'strip' for MW, 'east side of' etc.)
    """
    base = f"{rule.subject} {rule.condition}"
    synonyms = _SUBJECT_SYNONYMS.get(rule.subject_code, [])
    context = f"(traffic: {rule.traffic}, purpose: {rule.purpose}, scope: {rule.scope})"
    if synonyms:
        return f"{base} {context} — also known as: {', '.join(synonyms)}"
    return f"{base} {context}"


class SemanticRuleMatcher:
    """Computes semantic similarity between free-text narratives and ICAO Doc 8126 rules."""

    def __init__(self, model_name: str = _MODEL_NAME) -> None:
        self.model_name = model_name
        self._model: Any = None
        self._rules: tuple[SelectionRule, ...] = ()
        self._rule_embeddings: Any = None
        self._initialized = False

    @property
    def model_status(self) -> str:
        """Returns 'loading', 'ready', or 'unavailable' for the frontend loader."""
        if _model_loading:
            return "loading"
        if self._initialized and self._model is not None:
            return "ready"
        if self._initialized and self._model is None:
            return "unavailable"
        # Not yet triggered -- report loading so the UI knows to expect it
        return "loading"

    def _initialize(self) -> bool:
        global _model_loading
        if self._initialized:
            return self._model is not None

        self._initialized = True
        _model_loading = True
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            logger.info("Initializing semantic embedding model %s", self.model_name)
            self._model = SentenceTransformer(self.model_name)
            catalog = get_catalog()
            self._rules = catalog.rules

            # Build synonym-enriched rule text for each rule so the embedding
            # model matches non-standard phrasing (e.g. "strip" -> MW, etc.)
            rule_texts = [_build_rule_text(r) for r in self._rules]
            self._rule_embeddings = self._model.encode(
                rule_texts, convert_to_tensor=True, show_progress_bar=False
            )
            return True
        except Exception as exc:  # pragma: no cover
            logger.warning("Semantic model initialization skipped or failed: %s", exc)
            self._model = None
            return False
        finally:
            _model_loading = False

    def search(self, query: str, top_k: int = 5) -> list[tuple[SelectionRule, float]]:
        """Returns top_k (SelectionRule, similarity_score) pairs for the given narrative query."""
        if not query or not query.strip():
            return []

        if not self._initialize() or self._model is None:
            return []

        try:
            import numpy as np
            from sentence_transformers import util  # type: ignore

            query_embedding = self._model.encode(query, convert_to_tensor=True)
            cosine_scores = util.cos_sim(query_embedding, self._rule_embeddings)[0]

            scores_np = cosine_scores.cpu().numpy()
            top_indices = np.argsort(-scores_np)[:top_k]

            results: list[tuple[SelectionRule, float]] = []
            for idx in top_indices:
                score = float(scores_np[idx])
                if score > 0.35:  # Relevance threshold
                    results.append((self._rules[idx], score))
            return results
        except Exception as exc:  # pragma: no cover
            logger.warning("Semantic search error: %s", exc)
            return []


@lru_cache
def get_semantic_matcher() -> SemanticRuleMatcher:
    return SemanticRuleMatcher()

