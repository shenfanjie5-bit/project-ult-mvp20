from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_CONTRACTS_SRC = Path(__file__).resolve().parents[2] / "contracts" / "src"
if _CONTRACTS_SRC.exists():
    sys.path.insert(0, str(_CONTRACTS_SRC))

from graph_engine.client import Neo4jClient  # noqa: E402
from graph_engine.config import Neo4jConfig  # noqa: E402


@pytest.fixture
def neo4j_config() -> Neo4jConfig:
    return Neo4jConfig(password="test-password")


@pytest.fixture
def mock_neo4j_client() -> MagicMock:
    client = MagicMock(spec=Neo4jClient)
    client.execute_read.return_value = []
    client.execute_write.return_value = []
    return client
