from __future__ import annotations

import pytest
from pydantic import ValidationError

from graph_engine.config import Neo4jConfig, load_config_from_env


def test_neo4j_config_uses_defaults() -> None:
    config = Neo4jConfig(password="secret")

    assert config.uri == "bolt://localhost:7687"
    assert config.user == "neo4j"
    assert config.database == "neo4j"
    assert config.max_connection_pool_size == 50
    assert config.connection_timeout_seconds == 30.0


def test_load_config_from_env_reads_supported_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEO4J_URI", "bolt://neo4j.example:7687")
    monkeypatch.setenv("NEO4J_USER", "graph-user")
    monkeypatch.setenv("NEO4J_PASSWORD", "graph-secret")
    monkeypatch.setenv("NEO4J_DATABASE", "graph")

    config = load_config_from_env()

    assert config.uri == "bolt://neo4j.example:7687"
    assert config.user == "graph-user"
    assert config.password == "graph-secret"
    assert config.database == "graph"


def test_load_config_from_env_keeps_defaults_when_optional_env_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NEO4J_URI", raising=False)
    monkeypatch.delenv("NEO4J_USER", raising=False)
    monkeypatch.setenv("NEO4J_PASSWORD", "graph-secret")
    monkeypatch.delenv("NEO4J_DATABASE", raising=False)

    config = load_config_from_env()

    assert config.uri == "bolt://localhost:7687"
    assert config.user == "neo4j"
    assert config.password == "graph-secret"
    assert config.database == "neo4j"


def test_load_config_from_env_requires_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)

    with pytest.raises(ValidationError):
        load_config_from_env()


def test_neo4j_config_rejects_invalid_pool_size() -> None:
    with pytest.raises(ValidationError):
        Neo4jConfig(password="secret", max_connection_pool_size=0)
