"""Formal object schema envelope and registry."""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from types import MappingProxyType
from typing import Literal

from pydantic import Field

from contracts.core import (
    AwareDatetime,
    ContractBaseModel,
    CycleId,
    VersionString,
    Zone,
)
from contracts.errors import ContractError, ErrorCode


class FormalObjectName(str, Enum):
    """Stable names for the formal object family."""

    WORLD_STATE_SNAPSHOT = "world_state_snapshot"
    OFFICIAL_ALPHA_POOL = "official_alpha_pool"
    ALPHA_RESULT_SNAPSHOT = "alpha_result_snapshot"
    RECOMMENDATION_SNAPSHOT = "recommendation_snapshot"
    DASHBOARD_SNAPSHOT = "dashboard_snapshot"
    REPORT = "report"
    AUDIT_RECORD = "audit_record"
    REPLAY_RECORD = "replay_record"


class FormalObjectBase(ContractBaseModel):
    """Shared formal object envelope."""

    object_id: str = Field(min_length=1)
    object_name: FormalObjectName
    zone: Literal[Zone.FORMAL] = Zone.FORMAL
    version: VersionString
    created_at: AwareDatetime
    cycle_id: CycleId | None = None
    payload: dict[str, object]


class WorldStateSnapshot(FormalObjectBase):
    """World state snapshot formal object."""

    object_name: Literal[
        FormalObjectName.WORLD_STATE_SNAPSHOT
    ] = FormalObjectName.WORLD_STATE_SNAPSHOT


class OfficialAlphaPool(FormalObjectBase):
    """Official alpha pool formal object."""

    object_name: Literal[
        FormalObjectName.OFFICIAL_ALPHA_POOL
    ] = FormalObjectName.OFFICIAL_ALPHA_POOL


class AlphaResultSnapshot(FormalObjectBase):
    """Alpha result snapshot formal object."""

    object_name: Literal[
        FormalObjectName.ALPHA_RESULT_SNAPSHOT
    ] = FormalObjectName.ALPHA_RESULT_SNAPSHOT


class RecommendationSnapshot(FormalObjectBase):
    """Recommendation snapshot formal object."""

    object_name: Literal[
        FormalObjectName.RECOMMENDATION_SNAPSHOT
    ] = FormalObjectName.RECOMMENDATION_SNAPSHOT


class DashboardSnapshot(FormalObjectBase):
    """Dashboard snapshot formal object."""

    object_name: Literal[
        FormalObjectName.DASHBOARD_SNAPSHOT
    ] = FormalObjectName.DASHBOARD_SNAPSHOT


class Report(FormalObjectBase):
    """Report formal object."""

    object_name: Literal[FormalObjectName.REPORT] = FormalObjectName.REPORT


class AuditRecord(FormalObjectBase):
    """Audit record formal object."""

    object_name: Literal[FormalObjectName.AUDIT_RECORD] = FormalObjectName.AUDIT_RECORD


class ReplayRecord(FormalObjectBase):
    """Replay record formal object."""

    object_name: Literal[
        FormalObjectName.REPLAY_RECORD
    ] = FormalObjectName.REPLAY_RECORD


FORMAL_OBJECT_REGISTRY: Mapping[FormalObjectName, type[FormalObjectBase]] = (
    MappingProxyType(
        {
            FormalObjectName.WORLD_STATE_SNAPSHOT: WorldStateSnapshot,
            FormalObjectName.OFFICIAL_ALPHA_POOL: OfficialAlphaPool,
            FormalObjectName.ALPHA_RESULT_SNAPSHOT: AlphaResultSnapshot,
            FormalObjectName.RECOMMENDATION_SNAPSHOT: RecommendationSnapshot,
            FormalObjectName.DASHBOARD_SNAPSHOT: DashboardSnapshot,
            FormalObjectName.REPORT: Report,
            FormalObjectName.AUDIT_RECORD: AuditRecord,
            FormalObjectName.REPLAY_RECORD: ReplayRecord,
        }
    )
)

FORMAL_OBJECT_NAMES: tuple[FormalObjectName, ...] = tuple(FORMAL_OBJECT_REGISTRY)


def get_formal_object_model(name: FormalObjectName | str) -> type[FormalObjectBase]:
    """Return the Pydantic model registered for a formal object name."""

    try:
        object_name = (
            name if isinstance(name, FormalObjectName) else FormalObjectName(name)
        )
        return FORMAL_OBJECT_REGISTRY[object_name]
    except (KeyError, ValueError) as exc:
        requested_name = name.value if isinstance(name, FormalObjectName) else str(name)
        raise ContractError(
            ErrorCode.UNKNOWN_FORMAL_OBJECT,
            details={"object_name": requested_name},
        ) from exc


__all__ = [
    "FormalObjectName",
    "FormalObjectBase",
    "WorldStateSnapshot",
    "OfficialAlphaPool",
    "AlphaResultSnapshot",
    "RecommendationSnapshot",
    "DashboardSnapshot",
    "Report",
    "AuditRecord",
    "ReplayRecord",
    "FORMAL_OBJECT_REGISTRY",
    "FORMAL_OBJECT_NAMES",
    "get_formal_object_model",
]
