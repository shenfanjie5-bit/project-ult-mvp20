"""Core entity models and canonical ID rules."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

from entity_registry.contracts import current_canonical_id_rule_version


class EntityType(str, Enum):
    """Supported canonical entity categories."""

    STOCK = "stock"
    CORP = "corp"
    PERSON = "person"
    ORG = "org"
    INDEX = "index"
    EVENT = "event"


class EntityStatus(str, Enum):
    """Lifecycle status for canonical entities."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    MERGED = "merged"


class AliasType(str, Enum):
    """Supported alias categories."""

    FULL_NAME = "full_name"
    SHORT_NAME = "short_name"
    CODE = "code"
    ENGLISH = "english"
    FORMER_NAME = "former_name"
    CNSPELL = "cnspell"


class ResolutionMethod(str, Enum):
    """Resolution paths recorded for entity references."""

    DETERMINISTIC = "deterministic"
    FUZZY = "fuzzy"
    LLM = "llm"
    MANUAL = "manual"
    UNRESOLVED = "unresolved"


class DecisionType(str, Enum):
    """Decision sources for resolution audit cases."""

    AUTO = "auto"
    LLM_ASSISTED = "llm_assisted"
    MANUAL_REVIEW = "manual_review"


class FinalStatus(str, Enum):
    """Final runtime status for a mention candidate set."""

    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    MANUAL_REVIEW = "manual_review"


_ENTITY_ID_PATTERN = re.compile(r"^ENT_[A-Z][A-Z0-9]*_[A-Za-z0-9][A-Za-z0-9._-]*$")
_TS_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def generate_stock_entity_id(ts_code: str) -> str:
    """Generate the canonical ID for a listed stock from its exchange code."""

    if not isinstance(ts_code, str):
        raise ValueError("ts_code must be a string")

    normalized_ts_code = ts_code.strip()
    if not normalized_ts_code:
        raise ValueError("ts_code must not be empty")
    if not _TS_CODE_PATTERN.fullmatch(normalized_ts_code):
        raise ValueError("ts_code contains unsupported characters")

    return f"ENT_STOCK_{normalized_ts_code}"


def generate_event_entity_id(namespace: str, event_key: str) -> str:
    """Generate a deterministic canonical ID for an anchored event node."""

    normalized_namespace = _normalize_event_id_part(namespace, field_name="namespace")
    normalized_event_key = _normalize_event_anchor_part(event_key, field_name="event_key")
    digest = hashlib.sha256(
        f"{normalized_namespace}\x1f{normalized_event_key}".encode("utf-8")
    ).hexdigest()[:16].upper()
    return f"ENT_EVENT_{normalized_namespace}_{digest}"


def _normalize_event_id_part(value: str, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", value.strip().upper()).strip("_")
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _normalize_event_anchor_part(value: str, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def validate_entity_id(entity_id: str) -> bool:
    """Return whether a canonical entity ID follows the ENT_* namespace format."""

    if not isinstance(entity_id, str):
        return False

    normalized_entity_id = entity_id.strip()
    if normalized_entity_id != entity_id:
        return False

    return bool(_ENTITY_ID_PATTERN.fullmatch(entity_id))


class CanonicalEntity(BaseModel):
    """System-level canonical entity record."""

    canonical_entity_id: str
    entity_type: EntityType
    display_name: str
    status: EntityStatus
    anchor_code: str | None = None
    cross_listing_group: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    canonical_id_rule_version: str = Field(
        default_factory=current_canonical_id_rule_version,
        exclude=True,
    )

    @model_validator(mode="after")
    def validate_canonical_entity(self) -> CanonicalEntity:
        if not validate_entity_id(self.canonical_entity_id):
            raise ValueError("canonical_entity_id must use the ENT_* namespace")

        if self.entity_type is EntityType.STOCK and self.anchor_code is None:
            raise ValueError("anchor_code is required for stock entities")

        if self.canonical_entity_id.startswith("ENT_STOCK_") and self.anchor_code is None:
            raise ValueError("anchor_code is required for ENT_STOCK_* IDs")

        if self.entity_type is EntityType.EVENT and self.anchor_code is None:
            raise ValueError("anchor_code is required for event entities")

        if self.canonical_entity_id.startswith("ENT_EVENT_") and self.anchor_code is None:
            raise ValueError("anchor_code is required for ENT_EVENT_* IDs")

        return self


class EntityAlias(BaseModel):
    """Alias mapping from raw text to a canonical entity."""

    canonical_entity_id: str
    alias_text: str
    alias_type: AliasType
    confidence: float
    source: str
    is_primary: bool
    created_at: datetime = Field(default_factory=_utcnow)
    canonical_id_rule_version: str = Field(
        default_factory=current_canonical_id_rule_version,
        exclude=True,
    )

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        if value < 0.0 or value > 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        return value
