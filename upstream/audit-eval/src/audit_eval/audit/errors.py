"""Typed errors for read-history replay queries."""


class ReplayQueryError(RuntimeError):
    """Base error for replay query reconstruction failures."""


class ReplayRecordNotFound(ReplayQueryError):
    """Raised when no replay record exists for a cycle/object binding."""


class ReplayModeError(ReplayQueryError):
    """Raised when a replay record is not configured for read-history replay."""


class AuditRecordMissing(ReplayQueryError):
    """Raised when a replay record references unavailable audit records."""


class ManifestBindingError(ReplayQueryError):
    """Raised when replay records are not bound to the published manifest."""


class SnapshotLoadError(ReplayQueryError):
    """Raised when a manifest-bound formal snapshot cannot be loaded."""


class DagsterSummaryMissing(ReplayQueryError):
    """Raised when Dagster run history is unavailable or incorrectly bound."""


class GraphSnapshotMissing(ReplayQueryError):
    """Raised when graph snapshot context is unavailable or incorrectly bound."""


__all__ = [
    "AuditRecordMissing",
    "DagsterSummaryMissing",
    "GraphSnapshotMissing",
    "ManifestBindingError",
    "ReplayModeError",
    "ReplayQueryError",
    "ReplayRecordNotFound",
    "SnapshotLoadError",
]
