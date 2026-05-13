"""JSON helpers for browser-safe API payloads."""

from __future__ import annotations

import json
import math
from typing import Any


def json_safe(value: Any) -> Any:
    """Return a JSON-compatible copy with non-finite floats converted to null.

    Python's ``json.dumps`` emits NaN/Infinity by default, but browsers reject
    those tokens in ``response.json()``. API responses and SSE frames must be
    strict JSON so the frontend can reliably parse overlay snapshots.
    """

    if isinstance(value, float):
        return None if not math.isfinite(value) else value
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def dumps_strict_json(value: Any) -> str:
    return json.dumps(
        json_safe(value),
        ensure_ascii=False,
        default=str,
        allow_nan=False,
    )
