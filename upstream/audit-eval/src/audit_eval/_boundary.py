"""Shared package boundary guards."""

from collections.abc import Mapping, Sequence

FORBIDDEN_WRITE_FIELDS: frozenset[str] = frozenset({"feature_weight_multiplier"})


class BoundaryViolationError(Exception):
    """Raised when a payload attempts to write a forbidden field."""


def assert_no_forbidden_write(payload: object, path: str = "$") -> None:
    """Reject payloads containing fields this package must never write."""
    forbidden_fields = tuple(_iter_forbidden_field_paths(payload, path))
    if forbidden_fields:
        fields = ", ".join(forbidden_fields)
        raise BoundaryViolationError(f"Forbidden write field(s): {fields}")


def _iter_forbidden_field_paths(payload: object, path: str = "$") -> tuple[str, ...]:
    if isinstance(payload, Mapping):
        paths: list[str] = []
        for key, value in payload.items():
            field_path = f"{path}.{key}"
            if isinstance(key, str) and key in FORBIDDEN_WRITE_FIELDS:
                paths.append(field_path)
            paths.extend(_iter_forbidden_field_paths(value, field_path))
        return tuple(paths)

    if isinstance(payload, Sequence) and not isinstance(
        payload,
        (str, bytes, bytearray),
    ):
        paths = []
        for index, value in enumerate(payload):
            paths.extend(_iter_forbidden_field_paths(value, f"{path}[{index}]"))
        return tuple(paths)

    return ()


__all__ = [
    "BoundaryViolationError",
    "FORBIDDEN_WRITE_FIELDS",
    "assert_no_forbidden_write",
]
