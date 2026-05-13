from __future__ import annotations

from typing import Any

import pytest

import graph_engine.status.store as status_store_module
from graph_engine.status.store import PostgreSQLStatusStore


class FakePsycopg:
    def __init__(self) -> None:
        self.connect_calls: list[tuple[str, dict[str, Any]]] = []

    def connect(self, database_url: str, **connect_kwargs: Any) -> object:
        self.connect_calls.append((database_url, connect_kwargs))
        return object()


@pytest.mark.parametrize(
    ("database_url", "expected_psycopg_dsn"),
    [
        (
            "postgresql+psycopg://user:pass@localhost:5432/db",
            "postgresql://user:pass@localhost:5432/db",
        ),
        (
            "postgresql://user:pass@localhost:5432/db",
            "postgresql://user:pass@localhost:5432/db",
        ),
        (
            "postgres://user:pass@localhost:5432/db",
            "postgres://user:pass@localhost:5432/db",
        ),
        (
            "host=localhost port=5432 dbname=db user=user password=pass",
            "host=localhost port=5432 dbname=db user=user password=pass",
        ),
    ],
)
def test_from_database_url_normalizes_only_sqlalchemy_psycopg_scheme(
    monkeypatch: pytest.MonkeyPatch,
    database_url: str,
    expected_psycopg_dsn: str,
) -> None:
    fake_psycopg = FakePsycopg()

    def fake_import_module(module_name: str) -> object:
        if module_name != "psycopg":
            raise AssertionError(f"unexpected import: {module_name}")
        return fake_psycopg

    monkeypatch.setattr(status_store_module.importlib, "import_module", fake_import_module)

    store = PostgreSQLStatusStore.from_database_url(
        database_url,
        connect_kwargs={"connect_timeout": 2},
    )

    store._connection_factory()

    assert fake_psycopg.connect_calls == [
        (expected_psycopg_dsn, {"connect_timeout": 2}),
    ]
