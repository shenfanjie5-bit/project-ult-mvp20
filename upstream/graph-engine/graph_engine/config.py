"""Configuration loading for Neo4j live graph access."""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Neo4jConfig(BaseModel):
    """Runtime settings for the Neo4j driver."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    uri: str = Field(default="bolt://localhost:7687", min_length=1)
    user: str = Field(default="neo4j", min_length=1)
    password: str = Field(min_length=1)
    database: str = Field(default="neo4j", min_length=1)
    max_connection_pool_size: int = Field(default=50, gt=0)
    connection_timeout_seconds: float = Field(default=30.0, gt=0)


def load_config_from_env() -> Neo4jConfig:
    """Load Neo4j settings from the supported environment variables."""

    values: dict[str, Any] = {}
    env_mapping = {
        "NEO4J_URI": "uri",
        "NEO4J_USER": "user",
        "NEO4J_PASSWORD": "password",
        "NEO4J_DATABASE": "database",
    }
    for env_name, field_name in env_mapping.items():
        value = os.getenv(env_name)
        if value is not None:
            values[field_name] = value

    return Neo4jConfig(**values)
