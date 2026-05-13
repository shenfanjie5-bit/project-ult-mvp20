from __future__ import annotations

from typing import Any

import pytest

import graph_engine.client as client_module
from graph_engine.client import Neo4jClient
from graph_engine.config import Neo4jConfig


class FakeRecord:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def data(self) -> dict[str, Any]:
        return self._data


class FakeTx:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, query: str, parameters: dict[str, Any]) -> list[FakeRecord]:
        self.calls.append((query, parameters))
        return [FakeRecord(row) for row in self.rows]


class FakeSession:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.tx = FakeTx(rows)

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def execute_read(self, callback: Any, query: str, parameters: dict[str, Any]) -> Any:
        return callback(self.tx, query, parameters)

    def execute_write(self, callback: Any, query: str, parameters: dict[str, Any]) -> Any:
        return callback(self.tx, query, parameters)


class FakeDriver:
    def __init__(self, rows: list[dict[str, Any]] | None = None, verify_error: Exception | None = None) -> None:
        self.rows = rows or [{"ok": True}]
        self.verify_error = verify_error
        self.closed = False
        self.session_databases: list[str] = []

    def session(self, database: str) -> FakeSession:
        self.session_databases.append(database)
        return FakeSession(self.rows)

    def verify_connectivity(self) -> None:
        if self.verify_error is not None:
            raise self.verify_error

    def close(self) -> None:
        self.closed = True


class FakeGraphDatabase:
    driver_calls: list[dict[str, Any]] = []
    driver_instance = FakeDriver()
    driver_error: Exception | None = None

    @classmethod
    def driver(cls, uri: str, **kwargs: Any) -> FakeDriver:
        if cls.driver_error is not None:
            raise cls.driver_error
        cls.driver_calls.append({"uri": uri, **kwargs})
        return cls.driver_instance


def test_client_initializes_without_opening_driver(neo4j_config: Neo4jConfig) -> None:
    client = Neo4jClient(neo4j_config)

    assert client.config == neo4j_config
    assert client._driver is None


def test_connect_creates_driver(monkeypatch: pytest.MonkeyPatch, neo4j_config: Neo4jConfig) -> None:
    FakeGraphDatabase.driver_calls = []
    FakeGraphDatabase.driver_instance = FakeDriver()
    FakeGraphDatabase.driver_error = None
    monkeypatch.setattr(client_module, "GraphDatabase", FakeGraphDatabase)

    client = Neo4jClient(neo4j_config)
    client.connect()

    assert client._driver is FakeGraphDatabase.driver_instance
    assert FakeGraphDatabase.driver_calls == [
        {
            "uri": "bolt://localhost:7687",
            "auth": ("neo4j", "test-password"),
            "max_connection_pool_size": 50,
            "connection_timeout": 30.0,
        }
    ]


def test_connect_wraps_driver_creation_errors(
    monkeypatch: pytest.MonkeyPatch,
    neo4j_config: Neo4jConfig,
) -> None:
    FakeGraphDatabase.driver_error = RuntimeError("boom")
    monkeypatch.setattr(client_module, "GraphDatabase", FakeGraphDatabase)

    with pytest.raises(ConnectionError):
        Neo4jClient(neo4j_config).connect()

    FakeGraphDatabase.driver_error = None


def test_verify_connectivity_returns_false_on_failure(neo4j_config: Neo4jConfig) -> None:
    client = Neo4jClient(neo4j_config)
    client._driver = FakeDriver(verify_error=RuntimeError("offline"))

    assert client.verify_connectivity() is False


def test_verify_connectivity_returns_true(neo4j_config: Neo4jConfig) -> None:
    client = Neo4jClient(neo4j_config)
    client._driver = FakeDriver()

    assert client.verify_connectivity() is True


def test_context_manager_connects_and_closes(
    monkeypatch: pytest.MonkeyPatch,
    neo4j_config: Neo4jConfig,
) -> None:
    driver = FakeDriver()
    FakeGraphDatabase.driver_instance = driver
    monkeypatch.setattr(client_module, "GraphDatabase", FakeGraphDatabase)

    with Neo4jClient(neo4j_config) as client:
        assert client._driver is driver

    assert driver.closed is True
    assert client._driver is None


def test_execute_read_returns_dict_rows(neo4j_config: Neo4jConfig) -> None:
    client = Neo4jClient(neo4j_config)
    driver = FakeDriver(rows=[{"node_id": "n1"}])
    client._driver = driver

    rows = client.execute_read("MATCH (n) RETURN n.node_id AS node_id", {"limit": 1})

    assert rows == [{"node_id": "n1"}]
    assert driver.session_databases == ["neo4j"]


def test_execute_write_returns_dict_rows(neo4j_config: Neo4jConfig) -> None:
    client = Neo4jClient(neo4j_config)
    client._driver = FakeDriver(rows=[{"created": 1}])

    rows = client.execute_write("CREATE (n) RETURN count(n) AS created")

    assert rows == [{"created": 1}]
