"""合同共享枚举与类型基元。"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, TypeAlias

from pydantic import AfterValidator, Field


class ExType(str, Enum):
    """Ex payload 类型。"""

    EX_0 = "Ex-0"
    EX_1 = "Ex-1"
    EX_2 = "Ex-2"
    EX_3 = "Ex-3"


class Direction(str, Enum):
    """信号或 alpha 方向。"""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class Severity(str, Enum):
    """错误或诊断严重级别。"""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Zone(str, Enum):
    """合同对象归属区域。"""

    FORMAL = "formal"
    ANALYTICAL = "analytical"


class HeartbeatStatus(str, Enum):
    """Ex-0 心跳状态。"""

    OK = "ok"
    DEGRADED = "degraded"
    FAILED = "failed"


NonEmptyString: TypeAlias = Annotated[str, Field(min_length=1)]


def _validate_aware_datetime(value: datetime) -> datetime:
    """Require timezone-aware datetimes across contract models."""

    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(
            "[CONTRACT_VALIDATION_ERROR] datetime must be timezone-aware"
        )

    return value


AwareDatetime: TypeAlias = Annotated[datetime, AfterValidator(_validate_aware_datetime)]

EntityId: TypeAlias = NonEmptyString
SubsystemId: TypeAlias = NonEmptyString
CycleId: TypeAlias = NonEmptyString
FactId: TypeAlias = NonEmptyString
SignalId: TypeAlias = NonEmptyString
DeltaId: TypeAlias = NonEmptyString
NodeId: TypeAlias = NonEmptyString
EvidenceRef: TypeAlias = NonEmptyString
VersionString: TypeAlias = NonEmptyString
SectorId: TypeAlias = NonEmptyString
Confidence: TypeAlias = Annotated[
    float,
    Field(strict=True, ge=0.0, le=1.0, allow_inf_nan=False),
]
Score: TypeAlias = Annotated[
    float,
    Field(strict=True, ge=-1.0, le=1.0, allow_inf_nan=False),
]
Magnitude: TypeAlias = Annotated[
    float,
    Field(strict=True, ge=0.0, allow_inf_nan=False),
]


__all__ = [
    "ExType",
    "Direction",
    "Severity",
    "Zone",
    "HeartbeatStatus",
    "EntityId",
    "SubsystemId",
    "CycleId",
    "FactId",
    "SignalId",
    "DeltaId",
    "NodeId",
    "EvidenceRef",
    "VersionString",
    "SectorId",
    "AwareDatetime",
    "Confidence",
    "Score",
    "Magnitude",
]
