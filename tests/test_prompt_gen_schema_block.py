"""Tests for the C1 strict output_schema block in ``codex_prompt_gen``.

Locks the behaviour that hardens low-effort codex against schema drift
(101 drifts across 8/10 AI_COMPUTE A-shares in the first C1 pass): each
fillable dp_id's exact DP_SCHEMA shape is inlined, and Optionality nodes
render the current_contribution/future_option_value split the compiler
requires (rather than the flat DP_SCHEMA field list).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import codex_prompt_gen as cpg  # noqa: E402


def test_schema_one_line_normal_field_lists_required() -> None:
    spec = cpg._schema_one_line({"dp_id": "L3.channel.mix", "data_status": "Unknown"})
    assert spec is not None
    assert spec.startswith("required{")
    # canonical numeric channel fields are present
    assert "direct_pct" in spec and "distributor_pct" in spec


def test_schema_one_line_optionality_renders_split_not_flat() -> None:
    # L2.newbiz.uncertainty's flat DP_SCHEMA is {level:str,...}, but as an
    # Optionality node the compiler demands the split — the block must steer
    # the model to the split, not the flat shape that fails compile.
    spec = cpg._schema_one_line(
        {"dp_id": "L2.newbiz.uncertainty", "data_status": "Optionality"}
    )
    assert spec is not None
    assert "current_contribution" in spec and "future_option_value" in spec
    # must NOT present the flat {level:str} as the value shape
    assert not spec.startswith("required{level")


def test_schema_one_line_list_item_schema_rendered() -> None:
    spec = cpg._schema_one_line(
        {"dp_id": "L3.product.portfolio", "data_status": "Unknown"}
    )
    assert spec is not None
    # products list element schema must be spelled out (the [str] vs [dict] trap)
    assert "products[]=每元素" in spec
    assert "name" in spec and "revenue_pct" in spec


def test_schema_one_line_unknown_dp_returns_none() -> None:
    assert cpg._schema_one_line({"dp_id": "L99.fake.field", "data_status": "Unknown"}) is None


def test_format_schema_block_has_rules_and_rows() -> None:
    block = cpg._format_schema_block(
        [{"dp_id": "L3.channel.mix", "data_status": "Unknown"}]
    )
    text = "\n".join(block)
    assert "铁律" in text
    assert "禁止新增" in text
    assert "`L3.channel.mix`" in text


def test_format_schema_block_empty_when_no_known_schema() -> None:
    assert cpg._format_schema_block(
        [{"dp_id": "L99.fake.field", "data_status": "Unknown"}]
    ) == []
