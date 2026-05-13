"""Small Neo4j driver wrapper used by graph-engine modules."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from graph_engine.config import Neo4jConfig

try:  # pragma: no cover - exercised when the optional runtime dependency is unavailable.
    from neo4j import GraphDatabase  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover
    GraphDatabase = None  # type: ignore[assignment,misc]


class Neo4jClient:
    """Synchronous Neo4j client with explicit read/write transaction helpers."""

    def __init__(self, config: Neo4jConfig) -> None:
        self.config = config
        self._driver: Any | None = None

    def connect(self) -> None:
        """Create the underlying Neo4j driver."""

        if self._driver is not None:
            return
        if GraphDatabase is None:
            raise ConnectionError("neo4j package is not installed")

        try:
            self._driver = GraphDatabase.driver(
                self.config.uri,
                auth=(self.config.user, self.config.password),
                max_connection_pool_size=self.config.max_connection_pool_size,
                connection_timeout=self.config.connection_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - Neo4j driver raises several connection errors.
            raise ConnectionError(f"failed to create Neo4j driver: {exc}") from exc

    def close(self) -> None:
        """Close the underlying driver if it has been opened."""

        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def execute_read(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Run a read transaction and return records as dictionaries."""

        driver = self._ensure_driver()
        with driver.session(database=self.config.database) as session:
            return session.execute_read(self._run_query, query, parameters or {})

    def execute_write(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Run a write transaction and return records as dictionaries."""

        driver = self._ensure_driver()
        with driver.session(database=self.config.database) as session:
            return session.execute_write(self._run_query, query, parameters or {})

    def verify_connectivity(self) -> bool:
        """Return whether Neo4j is reachable without leaking driver exceptions."""

        try:
            driver = self._ensure_driver()
            driver.verify_connectivity()
        except Exception:  # noqa: BLE001 - this method intentionally converts failures to False.
            return False
        return True

    def __enter__(self) -> Neo4jClient:
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _ensure_driver(self) -> Any:
        if self._driver is None:
            self.connect()
        if self._driver is None:
            raise ConnectionError("Neo4j driver is not available")
        return self._driver

    @staticmethod
    def _run_query(tx: Any, query: str, parameters: dict[str, Any]) -> list[dict[str, Any]]:
        records = tx.run(query, parameters)
        return Neo4jClient._records_to_dicts(records)

    @staticmethod
    def _records_to_dicts(records: Iterable[Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for record in records:
            if hasattr(record, "data"):
                rows.append(record.data())
            else:
                rows.append(dict(record))
        return rows
