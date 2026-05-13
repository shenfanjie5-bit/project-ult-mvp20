"""Compatibility aliases for historical L4 world-state stubs."""

from __future__ import annotations

from main_core.l4_world_state.rules import DefaultWorldStatePolicy


class DefaultWorldStatePolicyStub(DefaultWorldStatePolicy):
    """Backward-compatible name for the real default L4 policy."""


__all__ = ["DefaultWorldStatePolicyStub"]
