"""Service entrypoint for single-stock L6 alpha analysis."""

from __future__ import annotations

from main_core.common.contexts import AlphaAnalysisContext
from main_core.common.protocols import AnalyzerInterface
from main_core.common.schemas import AlphaResultSnapshot
from main_core.common.types import EntityId
from main_core.l6_alpha.reasoner_port import StaticAlphaReasonerPort
from main_core.l6_alpha.single_prompt_analyzer import SinglePromptAnalyzer


def analyze_stock(
    entity_id: EntityId,
    context: AlphaAnalysisContext,
    *,
    analyzer: AnalyzerInterface | None = None,
) -> AlphaResultSnapshot:
    """Analyze one stock using the P2 single-prompt analyzer by default."""

    active_analyzer = analyzer or SinglePromptAnalyzer(StaticAlphaReasonerPort())
    return active_analyzer.analyze(entity_id, context)


__all__ = ["analyze_stock"]
