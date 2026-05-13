"""Shared exception types for main-core."""


class MainCoreError(Exception):
    """Base exception for main-core failures."""


class InconclusiveError(MainCoreError):
    """Raised when a task must be marked inconclusive."""


class ManifestPublishError(MainCoreError):
    """Raised when manifest-backed publication fails."""


class BoundaryViolationError(MainCoreError):
    """Raised when a package boundary rule is violated."""


class AlphaAnalyzerError(MainCoreError):
    """Raised when an L6 analyzer contract is violated before provider work.

    Shared by single-prompt and multi-agent analyzers so that L6 callers can
    catch a single error type for analyzer configuration / contract violations.
    """


__all__ = [
    "AlphaAnalyzerError",
    "BoundaryViolationError",
    "InconclusiveError",
    "MainCoreError",
    "ManifestPublishError",
]
