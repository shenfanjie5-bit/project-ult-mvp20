"""Fail-closed guards for opt-in live-graph rollout paths."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from contracts.schemas import CandidateGraphDelta

from graph_engine.models import PromotionPlan

RolloutMode = Literal["disabled", "canary", "production"]

CONFIRM_ENV = "GRAPH_ENGINE_LIVE_GRAPH_ROLLOUT_CONFIRM"
CONFIRM_VALUE = "1"
HOLDINGS_RELATIONSHIP_ALLOWLIST = frozenset({"CO_HOLDING", "NORTHBOUND_HOLD"})

_SAFE_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,95}$")
_SAFE_DATABASE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,95}$")
_DISPOSABLE_DATABASE_MARKER_PATTERN = re.compile(
    r"(canary|proof|rollout|smoke|test)",
    re.IGNORECASE,
)
_UNSAFE_NAMES = frozenset(
    {
        "default",
        "live",
        "main",
        "neo4j",
        "prod",
        "production",
        "system",
    }
)


@dataclass(frozen=True)
class LiveGraphRolloutConfig:
    """Configuration required before any opt-in live graph rollout path runs."""

    namespace: str
    mode: RolloutMode
    neo4j_database: str
    allowed_relationship_types: set[str]
    artifact_root: Path


def validate_rollout_config(
    config: LiveGraphRolloutConfig,
    *,
    env: Mapping[str, str | None] | None = None,
) -> LiveGraphRolloutConfig:
    """Validate rollout gates before artifacts, Layer A writes, or Neo4j writes."""

    effective_env = os.environ if env is None else env
    if config.mode == "disabled":
        raise PermissionError("live graph rollout mode is disabled")
    if config.mode not in {"canary", "production"}:
        raise ValueError(f"unsupported live graph rollout mode: {config.mode!r}")
    if effective_env.get(CONFIRM_ENV) != CONFIRM_VALUE:
        raise PermissionError(f"{CONFIRM_ENV}=1 is required for live graph rollout")

    namespace = _validate_namespace(config.namespace)
    neo4j_database = _validate_neo4j_database(config.neo4j_database)
    allowed_relationship_types = _validate_relationship_allowlist(
        config.allowed_relationship_types,
    )
    artifact_root = _validate_artifact_root(config.artifact_root)

    return LiveGraphRolloutConfig(
        namespace=namespace,
        mode=config.mode,
        neo4j_database=neo4j_database,
        allowed_relationship_types=allowed_relationship_types,
        artifact_root=artifact_root,
    )


def validate_client_database_matches_config(
    client: Any,
    config: LiveGraphRolloutConfig,
) -> None:
    """Require the actual Neo4j client database to match the guarded database."""

    expected_database = _validate_neo4j_database(config.neo4j_database)
    actual_database = _client_database(client)
    if actual_database != expected_database:
        raise PermissionError(
            "Neo4j client database does not match live graph rollout database: "
            f"expected {expected_database!r}, actual {actual_database!r}",
        )


def validate_candidate_relationship_allowlist(
    deltas: Sequence[CandidateGraphDelta],
    allowed_relationship_types: set[str],
) -> None:
    """Fail closed unless all selected contract deltas are explicitly allowed."""

    allowed = _validate_relationship_allowlist(allowed_relationship_types)
    relation_types = sorted({delta.relation_type for delta in deltas})
    disallowed = [
        relation_type for relation_type in relation_types if relation_type not in allowed
    ]
    if disallowed:
        raise PermissionError(
            "candidate graph deltas contain relationship types outside the allowlist: "
            + ", ".join(disallowed),
        )


def validate_promotion_plan_relationship_allowlist(
    plan: PromotionPlan,
    allowed_relationship_types: set[str],
) -> None:
    """Fail closed unless all promoted Layer A edges are explicitly allowed."""

    allowed = _validate_relationship_allowlist(allowed_relationship_types)
    relation_types = sorted({edge.relationship_type for edge in plan.edge_records})
    disallowed = [
        relation_type for relation_type in relation_types if relation_type not in allowed
    ]
    if disallowed:
        raise PermissionError(
            "promotion plan contains relationship types outside the allowlist: "
            + ", ".join(disallowed),
        )


def _validate_namespace(namespace: str) -> str:
    value = str(namespace or "").strip()
    if not value:
        raise PermissionError("live graph rollout namespace is required")
    if not _SAFE_IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError("live graph rollout namespace must be a safe identifier")
    if value.lower() in _UNSAFE_NAMES:
        raise PermissionError(f"live graph rollout namespace {value!r} is not allowed")
    return value


def _validate_neo4j_database(database: str) -> str:
    value = str(database or "").strip()
    if not value:
        raise PermissionError("neo4j_database is required for live graph rollout")
    if not _SAFE_DATABASE_PATTERN.fullmatch(value):
        raise ValueError("neo4j_database must be a safe identifier")
    if value.lower() in _UNSAFE_NAMES:
        raise PermissionError(f"Neo4j database {value!r} is not allowed for rollout")
    if not _DISPOSABLE_DATABASE_MARKER_PATTERN.search(value):
        raise PermissionError(
            "Neo4j rollout database name must include canary, proof, rollout, "
            "smoke, or test",
        )
    return value


def _validate_relationship_allowlist(
    allowed_relationship_types: set[str],
) -> set[str]:
    if not allowed_relationship_types:
        raise PermissionError("allowed_relationship_types is required for rollout")
    values = {str(value).strip() for value in allowed_relationship_types}
    if "" in values:
        raise ValueError("allowed_relationship_types must not contain empty values")
    disallowed = sorted(values - HOLDINGS_RELATIONSHIP_ALLOWLIST)
    if disallowed:
        raise PermissionError(
            "allowed_relationship_types may only include holdings relationships: "
            + ", ".join(disallowed),
        )
    return values


def _validate_artifact_root(artifact_root: Path) -> Path:
    path = Path(artifact_root).expanduser().resolve(strict=False)
    if path.exists() and not path.is_dir():
        raise ValueError("artifact_root must be a directory")
    return path


def _client_database(client: Any) -> str:
    config = getattr(client, "config", None)
    database = getattr(config, "database", None)
    value = str(database or "").strip()
    if not value:
        raise PermissionError("Neo4j client database could not be verified")
    _validate_neo4j_database(value)
    return value
