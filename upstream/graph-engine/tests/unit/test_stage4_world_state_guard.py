"""Stage 4 audit #11: world_state(N-1) enforcement at compute_graph_snapshot."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


_GRAPH_ENGINE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_GRAPH_ENGINE_ROOT))

from graph_engine.providers.phase1 import (  # noqa: E402
    _validate_world_state_ref_is_not_current_cycle,
)


def test_guard_rejects_world_state_ref_pointing_at_current_cycle() -> None:
    with pytest.raises(ValueError, match="Layer C must read world_state"):
        _validate_world_state_ref_is_not_current_cycle(
            "world-state:CYCLE_20260501",
            "CYCLE_20260501",
        )


def test_guard_accepts_previous_cycle_ref() -> None:
    # Resolved N-1 ref must pass.
    _validate_world_state_ref_is_not_current_cycle(
        "world-state:CYCLE_20260430",
        "CYCLE_20260501",
    )


def test_guard_accepts_world_state_latest_sentinel() -> None:
    # `world-state:latest` is intentionally vague — the orchestrator's
    # Phase 1 wiring is responsible for ensuring the resolved value is
    # not the current cycle. The guard does not block here so existing
    # callers using the default sentinel continue to work.
    _validate_world_state_ref_is_not_current_cycle(
        "world-state:latest",
        "CYCLE_20260501",
    )


def test_guard_no_op_when_ref_or_cycle_missing() -> None:
    # Empty inputs are tolerated — defensive default for tests that
    # exercise the snapshot path with placeholder fixtures.
    _validate_world_state_ref_is_not_current_cycle("", "CYCLE_20260501")
    _validate_world_state_ref_is_not_current_cycle("world-state:CYCLE_X", "")
    _validate_world_state_ref_is_not_current_cycle("", "")


def test_guard_accepts_unrelated_ref_shapes() -> None:
    # The guard only rejects literal `world-state:{current_cycle_id}`.
    # Other shapes (custom storage refs, snapshot URIs) pass — graph-engine
    # does not own the ref grammar; that's a contracts concern.
    _validate_world_state_ref_is_not_current_cycle(
        "iceberg://world_state/CYCLE_20260430",
        "CYCLE_20260501",
    )
    _validate_world_state_ref_is_not_current_cycle(
        "world-state:CYCLE_20260501_alt",
        "CYCLE_20260501",
    )
