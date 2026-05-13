"""Common runtime contract type aliases."""

from typing import Any, Literal

JsonObject = dict[str, Any]
LayerName = Literal["L3", "L4", "L5", "L6", "L7", "L8"]
ReplayMode = Literal["read_history"]
RetrospectiveHorizon = Literal["T+1", "T+5", "T+20"]

__all__ = [
    "JsonObject",
    "LayerName",
    "ReplayMode",
    "RetrospectiveHorizon",
]
