"""Compatibility exports for the implemented L6 alpha analyzer."""

from __future__ import annotations

from main_core.l6_alpha.single_prompt_analyzer import SinglePromptAnalyzer


class SinglePromptAnalyzerStub(SinglePromptAnalyzer):
    """Backward-compatible name for the issue #9 single-prompt analyzer."""


__all__ = ["SinglePromptAnalyzerStub"]
