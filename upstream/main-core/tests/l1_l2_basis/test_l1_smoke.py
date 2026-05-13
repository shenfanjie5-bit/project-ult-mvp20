"""Smoke test for the L1/L2 fake-port contract."""

from __future__ import annotations

import ast
from pathlib import Path

from main_core.common.types import CycleId
from main_core.l1_l2_basis import read_calendar, read_entity_master, read_market_bars

from .conftest import FakeDataPlatformPort

PROJECT_ROOT = Path(__file__).resolve().parents[2]
L1_PACKAGE_ROOT = PROJECT_ROOT / "src" / "main_core" / "l1_l2_basis"
FORBIDDEN_STORAGE_IMPORTS = {"duckdb", "httpx", "psycopg", "pyiceberg", "requests"}


def test_fake_port_smoke_returns_one_active_entity_with_market_data(
    cycle_id: CycleId,
    active_entity,
    market_bar,
    calendar_day,
) -> None:
    port = FakeDataPlatformPort(
        market_bars=(market_bar,),
        calendar=(calendar_day,),
        entity_master=(active_entity,),
    )

    entities = read_entity_master(cycle_id, port=port)
    market_bars = read_market_bars(cycle_id, port=port)
    calendar = read_calendar(cycle_id, port=port)

    assert [entity.entity_id for entity in entities if entity.is_active] == [
        active_entity.entity_id
    ]
    assert market_bars == [market_bar]
    assert calendar == [calendar_day]
    assert port.entity_master_calls == [cycle_id]
    assert port.market_bar_calls == [cycle_id]
    assert port.calendar_calls == [cycle_id]


def test_l1_l2_basis_does_not_import_storage_or_provider_clients() -> None:
    imported_roots: set[str] = set()

    for path in sorted(L1_PACKAGE_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported_roots.add(node.module.split(".", 1)[0])

    assert imported_roots.isdisjoint(FORBIDDEN_STORAGE_IMPORTS)
