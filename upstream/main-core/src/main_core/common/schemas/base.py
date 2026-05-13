"""Shared Pydantic base class for main-core schema objects."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from copy import deepcopy
from types import MappingProxyType
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, model_serializer, model_validator


class FrozenDict(Mapping[Any, Any]):
    """Immutable mapping used to deep-freeze validated schema payloads."""

    def __init__(self, items: Mapping[Any, Any] | list[tuple[Any, Any]]) -> None:
        self._data = MappingProxyType(dict(items))

    def __getitem__(self, key: Any) -> Any:
        return self._data[key]

    def __iter__(self) -> Iterator[Any]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Mapping):
            return dict(self.items()) == dict(other.items())
        return False

    def __repr__(self) -> str:
        return f"{type(self).__name__}({dict(self._data)!r})"

    def __hash__(self) -> int:
        return hash(frozenset(self._data.items()))


def _freeze_value(value: Any) -> Any:
    frozen_value = value
    if isinstance(value, FrozenDict):
        frozen_value = value
    elif isinstance(value, Mapping):
        frozen_value = FrozenDict([(key, _freeze_value(item)) for key, item in value.items()])
    elif isinstance(value, (list, tuple)):
        frozen_value = tuple(_freeze_value(item) for item in value)
    elif isinstance(value, (frozenset, set)):
        frozen_value = frozenset(_freeze_value(item) for item in value)
    return frozen_value


def _thaw_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_value(item) for item in value]
    if isinstance(value, frozenset):
        return [_thaw_value(item) for item in value]
    return value


class FormalObjectBase(BaseModel):
    """Frozen schema base for formal and runtime contract objects."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)

    @model_validator(mode="after")
    def freeze_nested_containers(self) -> Self:
        """Recursively freeze validated container fields before sharing objects."""

        for field_name in type(self).model_fields:
            object.__setattr__(self, field_name, _freeze_value(getattr(self, field_name)))
        return self

    @model_serializer(mode="plain")
    def serialize_frozen_containers(self) -> dict[str, Any]:
        """Serialize immutable containers as ordinary JSON-compatible containers."""

        return {
            field_name: _thaw_value(getattr(self, field_name))
            for field_name in type(self).model_fields
        }

    def model_copy(
        self,
        *,
        update: Mapping[str, Any] | None = None,
        deep: bool = False,
    ) -> Self:
        """Copy through full validation so update values cannot bypass invariants."""

        payload = self.model_dump(mode="python")
        if update:
            payload.update(update)
        if deep:
            payload = deepcopy(payload)
        return type(self).model_validate(payload)

    def to_json(self) -> str:
        """Serialize the object using Pydantic's JSON representation."""

        return self.model_dump_json()

    @classmethod
    def from_json(cls, payload: str) -> Self:
        """Deserialize an object from Pydantic JSON."""

        return cls.model_validate_json(payload)


__all__ = ["FormalObjectBase"]
