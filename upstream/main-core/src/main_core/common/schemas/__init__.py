"""Pydantic schema objects shared across main-core layers."""

from types import MappingProxyType
from typing import Final

from main_core.common.schemas.alpha import (
    AlphaResultSnapshot,
    AlphaStatus,
    AnalyzerType,
    single_prompt_result,
)
from main_core.common.schemas.base import FormalObjectBase
from main_core.common.schemas.dashboard import DashboardSnapshot
from main_core.common.schemas.feature_bundle import FeatureSignalBundle
from main_core.common.schemas.override import OverrideRecord
from main_core.common.schemas.pool import OfficialAlphaPool
from main_core.common.schemas.publish import PublishBundle
from main_core.common.schemas.recommendation import (
    ActionType,
    RecommendationSnapshot,
    TriggerSource,
)
from main_core.common.schemas.report import FormalReport
from main_core.common.schemas.world_state import WorldStateSnapshot

SCHEMA_COMMON_EXPORTS: Final = frozenset({"FormalObjectBase"})
SCHEMA_COMMON_MODULES: Final = frozenset({"base"})

_SCHEMA_LAYER_SEQUENCE: Final = (
    "l1_l2_basis",
    "l3_features",
    "l4_world_state",
    "l5_universe",
    "l6_alpha",
    "l7_recommendation",
    "l8_publish",
)
_SCHEMA_LAYER_ORDER: Final = {
    layer_name: layer_index
    for layer_index, layer_name in enumerate(_SCHEMA_LAYER_SEQUENCE)
}

SCHEMA_CONTRACT_LAYER: Final = MappingProxyType(
    {
        "FeatureSignalBundle": "l3_features",
        "WorldStateSnapshot": "l4_world_state",
        "OfficialAlphaPool": "l5_universe",
        "AlphaResultSnapshot": "l6_alpha",
        "AlphaStatus": "l6_alpha",
        "AnalyzerType": "l6_alpha",
        "single_prompt_result": "l6_alpha",
        "ActionType": "l7_recommendation",
        "OverrideRecord": "l7_recommendation",
        "RecommendationSnapshot": "l7_recommendation",
        "TriggerSource": "l7_recommendation",
        "DashboardSnapshot": "l8_publish",
        "FormalReport": "l8_publish",
        "PublishBundle": "l8_publish",
    }
)

SCHEMA_MODULE_LAYER: Final = MappingProxyType(
    {
        "alpha": "l6_alpha",
        "dashboard": "l8_publish",
        "feature_bundle": "l3_features",
        "override": "l7_recommendation",
        "pool": "l5_universe",
        "publish": "l8_publish",
        "recommendation": "l7_recommendation",
        "report": "l8_publish",
        "world_state": "l4_world_state",
    }
)

LAYER_SCHEMA_IMPORT_POLICY: Final = MappingProxyType(
    {
        consumer_layer: frozenset(
            SCHEMA_COMMON_EXPORTS
            | {
                schema_name
                for schema_name, owner_layer in SCHEMA_CONTRACT_LAYER.items()
                if _SCHEMA_LAYER_ORDER[owner_layer] <= _SCHEMA_LAYER_ORDER[consumer_layer]
            }
        )
        for consumer_layer in _SCHEMA_LAYER_SEQUENCE
    }
)

__all__ = [
    "ActionType",
    "AlphaResultSnapshot",
    "AlphaStatus",
    "AnalyzerType",
    "DashboardSnapshot",
    "FeatureSignalBundle",
    "FormalObjectBase",
    "FormalReport",
    "LAYER_SCHEMA_IMPORT_POLICY",
    "OfficialAlphaPool",
    "OverrideRecord",
    "PublishBundle",
    "RecommendationSnapshot",
    "SCHEMA_COMMON_EXPORTS",
    "SCHEMA_COMMON_MODULES",
    "SCHEMA_CONTRACT_LAYER",
    "SCHEMA_MODULE_LAYER",
    "TriggerSource",
    "WorldStateSnapshot",
    "single_prompt_result",
]
