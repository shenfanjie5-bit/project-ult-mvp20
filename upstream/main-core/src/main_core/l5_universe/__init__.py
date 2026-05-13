"""L5 package — observation and core pool work; see §14 of main-core.project-doc.md."""

from main_core.l5_universe.mvp20 import select_mvp20_decision_pool
from main_core.l5_universe.rules import rank_candidates, score_candidate
from main_core.l5_universe.service import select_official_alpha_pool
from main_core.l5_universe.types import (
    MVP20_DECISION_POOL_CAPACITY,
    MVP20_MANIFEST_TARGET_FREEZE_REASON,
    MVP20DecisionPoolSpec,
    PoolSelectionConfig,
)

__all__ = [
    "MVP20_DECISION_POOL_CAPACITY",
    "MVP20_MANIFEST_TARGET_FREEZE_REASON",
    "MVP20DecisionPoolSpec",
    "PoolSelectionConfig",
    "rank_candidates",
    "score_candidate",
    "select_official_alpha_pool",
    "select_mvp20_decision_pool",
]
