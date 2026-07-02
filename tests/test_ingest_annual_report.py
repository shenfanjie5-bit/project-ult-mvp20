"""Tests for ``scripts/ingest_annual_report`` section extraction.

Locks the risk-section finder so it lands on the enumerated MD&A
"可能面临的风险" block rather than a front-matter "注意投资风险" reference or
the IFRS financial-instruments risk note (the bug that fed codex 董事会
boilerplate as "risk" evidence).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.ingest_annual_report as ing  # noqa: E402


# A synthetic report: front-matter reference + 董事会 boilerplate + an IFRS
# financial-risk note (风险-dense but not enumerated business risks) + the real
# enumerated MD&A risk section last.
_FRONT = "重要提示：请投资者注意公司可能面临的风险因素，详见管理层讨论与分析。"
_BOARD = "四、公司全体董事出席董事会会议。五、会计师事务所出具标准无保留意见的审计报告。" * 4
_FIN_NOTE = (
    "金融工具风险：本公司面临的风险包括市场风险、信用风险和流动性风险。"
    "市场风险、信用风险、流动性风险的管理政策如下。" * 6
)
_REAL = (
    "（四）可能面临的风险和应对措施\n"
    "1、宏观经济波动带来的风险：宏观经济波动可能影响需求，构成风险。\n"
    "2、市场竞争风险：行业竞争加剧构成市场竞争风险。\n"
    "3、汇率波动风险：公司存在进出口业务，汇率大幅波动对经营构成风险。\n"
)


def test_risk_section_pos_picks_enumerated_over_reference_and_finance_note() -> None:
    text = _FRONT + _BOARD + _FIN_NOTE + _REAL
    pos = ing._risk_section_pos(
        text, ["可能面临的风险", "公司可能面临的风险", "风险因素", "面临的风险"], 600
    )
    assert pos, "should locate a risk section"
    seg = ing._slice(text, pos, 600)
    assert "可能面临的风险和应对措施" in seg
    assert "汇率波动风险" in seg  # reached the enumerated body
    assert not seg.startswith("重要提示")  # not the front-matter reference


def test_extract_sections_risk_is_enumerated_business_risk() -> None:
    text = (
        "一、报告期内公司从事的主要业务：示例业务。" + "A" * 300
        + _FRONT + _BOARD + _FIN_NOTE + _REAL
    )
    secs = ing.extract_sections(text)
    risk = secs["risk_disclosure"]
    assert "1、宏观经济波动带来的风险" in risk
    assert "市场竞争风险" in risk


def test_best_section_pos_density_tiebreak() -> None:
    # Two "锚" occurrences; only the second's window holds 地区 → chosen.
    text = "锚" + ("x" * 40) + "锚地区地区地区"
    second = text.index("锚", 1)
    pos = ing._best_section_pos(text, ["锚"], 12, "地区")
    assert pos and pos[0] == second
