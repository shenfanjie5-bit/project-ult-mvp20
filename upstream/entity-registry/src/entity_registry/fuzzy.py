"""Fuzzy candidate generation for mention resolution."""

from __future__ import annotations

import importlib
import re
import unicodedata
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, field_validator

from entity_registry.aliases import normalize_alias_text
from entity_registry.core import AliasType, validate_entity_id
from entity_registry.storage import AliasRepository, EntityRepository

if TYPE_CHECKING:
    from entity_registry.resolution_types import ResolutionContext


class FuzzyMatcherUnavailable(RuntimeError):
    """Raised when the configured fuzzy backend is not available."""


class FuzzyCandidate(BaseModel):
    """One candidate produced by fuzzy alias matching."""

    canonical_entity_id: str
    alias_text: str
    alias_type: AliasType
    score: float
    source: str
    blocking_key: str | None = None

    @field_validator("canonical_entity_id")
    @classmethod
    def validate_canonical_entity_id(cls, value: str) -> str:
        if not validate_entity_id(value):
            raise ValueError("canonical_entity_id must use the ENT_* namespace")
        return value

    @field_validator("alias_text", "source")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("text fields must not be empty")
        return cleaned

    @field_validator("score")
    @classmethod
    def validate_score(cls, value: float) -> float:
        if value < 0.0 or value > 1.0:
            raise ValueError("score must be between 0.0 and 1.0")
        return value


class FuzzyMatcher(Protocol):
    """Runtime contract for generating fuzzy mention candidates."""

    def generate_candidates(
        self,
        raw_mention_text: str,
        *,
        context: "ResolutionContext | dict[str, object] | None" = None,
        limit: int = 10,
    ) -> list[FuzzyCandidate]: ...


class NullFuzzyMatcher:
    """Fuzzy matcher used when no candidate backend is configured."""

    auto_resolve_score = 1.0

    def generate_candidates(
        self,
        raw_mention_text: str,
        *,
        context: "ResolutionContext | dict[str, object] | None" = None,
        limit: int = 10,
    ) -> list[FuzzyCandidate]:
        return []


class SimpleFuzzyMatcher:
    """Local alias-table fuzzy matcher using deterministic text similarity."""

    def __init__(
        self,
        *,
        entity_repo: EntityRepository,
        alias_repo: AliasRepository,
        min_score: float = 0.80,
        auto_resolve_score: float = 0.96,
    ) -> None:
        if min_score < 0.0 or min_score > 1.0:
            raise ValueError("min_score must be between 0.0 and 1.0")
        if auto_resolve_score < 0.0 or auto_resolve_score > 1.0:
            raise ValueError("auto_resolve_score must be between 0.0 and 1.0")

        self._entity_repo = entity_repo
        self._alias_repo = alias_repo
        self.min_score = min_score
        self.auto_resolve_score = auto_resolve_score

    def generate_candidates(
        self,
        raw_mention_text: str,
        *,
        context: "ResolutionContext | dict[str, object] | None" = None,
        limit: int = 10,
    ) -> list[FuzzyCandidate]:
        if limit <= 0:
            return []

        raw_blocking_key = build_alias_blocking_key(raw_mention_text)
        candidates: list[FuzzyCandidate] = []
        for alias in self._alias_repo.list_all():
            if self._entity_repo.get(alias.canonical_entity_id) is None:
                continue

            blocking_key = build_alias_blocking_key(alias.alias_text)
            score = score_alias_similarity(raw_mention_text, alias.alias_text)
            if (
                raw_blocking_key
                and blocking_key
                and raw_blocking_key != blocking_key
                and score < 1.0
            ):
                continue
            if score < self.min_score:
                continue

            candidates.append(
                FuzzyCandidate(
                    canonical_entity_id=alias.canonical_entity_id,
                    alias_text=alias.alias_text,
                    alias_type=alias.alias_type,
                    score=score,
                    source="simple",
                    blocking_key=blocking_key or None,
                )
            )

        return _dedupe_sort_and_limit_candidates(candidates, limit)


class SplinkFuzzyMatcher:
    """Splink-backed fuzzy matcher placeholder.

    This adapter is intentionally separate from SimpleFuzzyMatcher so a caller
    cannot accidentally get local difflib behavior from a Splink-named backend.
    """

    def __init__(
        self,
        *,
        entity_repo: EntityRepository,
        alias_repo: AliasRepository,
        min_score: float = 0.80,
        auto_resolve_score: float = 0.96,
    ) -> None:
        if min_score < 0.0 or min_score > 1.0:
            raise ValueError("min_score must be between 0.0 and 1.0")
        if auto_resolve_score < 0.0 or auto_resolve_score > 1.0:
            raise ValueError("auto_resolve_score must be between 0.0 and 1.0")

        self._entity_repo = entity_repo
        self._alias_repo = alias_repo
        self.min_score = min_score
        self.auto_resolve_score = auto_resolve_score
        self._splink_checked = False

    def generate_candidates(
        self,
        raw_mention_text: str,
        *,
        context: "ResolutionContext | dict[str, object] | None" = None,
        limit: int = 10,
    ) -> list[FuzzyCandidate]:
        if limit <= 0:
            return []
        self._ensure_splink_available()
        raise NotImplementedError(
            "SplinkFuzzyMatcher requires a real Splink candidate generator; "
            "use SimpleFuzzyMatcher for local heuristic matching",
        )

    def _ensure_splink_available(self) -> None:
        if self._splink_checked:
            return
        try:
            importlib.import_module("splink")
        except ImportError as exc:
            raise FuzzyMatcherUnavailable(
                "Splink is not installed; install entity-registry with the "
                "'fuzzy' extra or use SimpleFuzzyMatcher"
            ) from exc
        self._splink_checked = True


def build_alias_blocking_key(alias_text: str) -> str:
    """Build a small stable blocking key for alias candidate pruning."""

    normalized = _normalize_for_similarity(alias_text)
    if not normalized:
        return ""
    if normalized.isascii():
        return normalized[:4]
    return normalized[:2]


def score_alias_similarity(raw_mention_text: str, alias_text: str) -> float:
    """Return a deterministic text-similarity score for tests and ordering."""

    raw = _normalize_for_similarity(raw_mention_text)
    alias = _normalize_for_similarity(alias_text)
    if not raw or not alias:
        return 0.0
    if raw == alias:
        return 1.0

    ratio = SequenceMatcher(a=raw, b=alias).ratio()
    containment_score = 0.0
    if raw in alias or alias in raw:
        containment_score = min(len(raw), len(alias)) / max(len(raw), len(alias))
        containment_score *= 0.98
    return round(max(ratio, containment_score), 6)


def _dedupe_sort_and_limit_candidates(
    candidates: list[FuzzyCandidate],
    limit: int,
) -> list[FuzzyCandidate]:
    semantic_best: dict[tuple[str, str, str], FuzzyCandidate] = {}
    for candidate in candidates:
        key = (
            candidate.canonical_entity_id,
            candidate.alias_text,
            candidate.source,
        )
        current = semantic_best.get(key)
        if current is None or _candidate_sort_key(candidate) < _candidate_sort_key(
            current
        ):
            semantic_best[key] = candidate

    entity_best: dict[str, FuzzyCandidate] = {}
    for candidate in semantic_best.values():
        current = entity_best.get(candidate.canonical_entity_id)
        if current is None or _candidate_sort_key(candidate) < _candidate_sort_key(
            current
        ):
            entity_best[candidate.canonical_entity_id] = candidate

    return sorted(entity_best.values(), key=_candidate_sort_key)[:limit]


def _candidate_sort_key(candidate: FuzzyCandidate) -> tuple[float, str, str]:
    return (-candidate.score, candidate.canonical_entity_id, candidate.alias_text)


def _normalize_for_similarity(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", normalize_alias_text(value))
    normalized = normalized.lower()
    normalized = re.sub(r"\s+", "", normalized)
    normalized = re.sub(r"[()（）【】\[\]·.,，。_-]", "", normalized)
    return normalized


__all__ = [
    "FuzzyCandidate",
    "FuzzyMatcher",
    "FuzzyMatcherUnavailable",
    "NullFuzzyMatcher",
    "SimpleFuzzyMatcher",
    "SplinkFuzzyMatcher",
    "build_alias_blocking_key",
    "score_alias_similarity",
]
