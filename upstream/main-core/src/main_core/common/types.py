"""Shared runtime type aliases for main-core."""

from typing import Literal, NewType

CycleId = NewType("CycleId", str)
EntityId = NewType("EntityId", str)
Regime = Literal["risk_off", "neutral", "risk_on"]

__all__ = ["CycleId", "EntityId", "Regime"]
