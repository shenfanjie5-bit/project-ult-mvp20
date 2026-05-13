"""Analyzer protocol contracts for §16.2."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, Protocol, runtime_checkable

from main_core.common.contexts import AlphaAnalysisContext
from main_core.common.schemas import AlphaResultSnapshot
from main_core.common.types import EntityId


@runtime_checkable
class AnalyzerInterface(Protocol):
    """L6 pluggable analyzer interface from §16.2.

    P2 analyzer implementations must use analyzer_type ``single_prompt_v1`` by
    default, as required by §16.3.
    """

    analyzer_type: ClassVar[str]

    def analyze(
        self,
        entity_id: EntityId,
        context: AlphaAnalysisContext,
    ) -> AlphaResultSnapshot:
        """Analyze one stock using an explicit entity and typed runtime context."""


class AnalyzerBase(ABC):
    """ABC inheritance entry point for concrete §16.2 analyzers."""

    @property
    @abstractmethod
    def analyzer_type(self) -> str:
        """Return the analyzer implementation identifier."""

    @abstractmethod
    def analyze(
        self,
        entity_id: EntityId,
        context: AlphaAnalysisContext,
    ) -> AlphaResultSnapshot:
        """Analyze one stock using an explicit entity and typed runtime context."""


__all__ = ["AnalyzerBase", "AnalyzerInterface"]
