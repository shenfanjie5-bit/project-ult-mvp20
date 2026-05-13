"""L6 package: single-stock alpha analysis."""

from main_core.l6_alpha.ab_runner import run_ab_evaluation, write_ab_report
from main_core.l6_alpha.fallback import build_inconclusive_result
from main_core.l6_alpha.multi_agent_analyzer import (
    AgentRoleConfig,
    MultiAgentAnalyzer,
    MultiAgentReasonerPort,
    MultiAgentRoleResult,
    StaticMultiAgentReasonerPort,
)
from main_core.l6_alpha.reasoner_port import (
    AlphaReasonerPort,
    AlphaReasonerResponse,
    StaticAlphaReasonerPort,
)
from main_core.l6_alpha.service import analyze_stock
from main_core.l6_alpha.single_prompt_analyzer import SinglePromptAnalyzer

__all__ = [
    "AgentRoleConfig",
    "AlphaReasonerPort",
    "AlphaReasonerResponse",
    "MultiAgentAnalyzer",
    "MultiAgentReasonerPort",
    "MultiAgentRoleResult",
    "SinglePromptAnalyzer",
    "StaticAlphaReasonerPort",
    "StaticMultiAgentReasonerPort",
    "analyze_stock",
    "build_inconclusive_result",
    "run_ab_evaluation",
    "write_ab_report",
]
