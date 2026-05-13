"""Alpha analyzer result schema."""

from __future__ import annotations

from typing import Annotated, TypeAlias

from pydantic import Field

from contracts.core import (
    Confidence,
    ContractBaseModel,
    Direction,
    EvidenceRef,
    Score,
    VersionString,
)


NonEmptyAlphaString: TypeAlias = Annotated[str, Field(min_length=1)]


class AlphaResult(ContractBaseModel):
    """Frozen alpha analyzer output payload."""

    score: Score
    direction: Direction
    confidence: Confidence
    rationale: NonEmptyAlphaString
    evidence_refs: list[EvidenceRef] = Field(min_length=1)
    analyzer_name: NonEmptyAlphaString
    analyzer_version: VersionString


__all__ = ["AlphaResult"]
