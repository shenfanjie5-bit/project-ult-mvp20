#!/usr/bin/env python3
"""Generate a per-overlay codex CLI prompt.

Given an industry_id (and optional ts_code), inspects the overlay YAML +
current realtime_current state and emits a self-contained markdown prompt
that codex can ingest to fill in LLM-derived fields.

Z1d (governance allowlist + write_policy):
    Filtering now reads ``config/llm_field_governance.yaml`` so only dp_ids
    with ``route ∈ {llm_close, llm_web}`` are surfaced to codex. Fields
    routed to ``skip`` / ``derive`` / unregistered fields are excluded.
    Optionality slots whose ``value`` is still empty are now also fillable
    (previously only ``data_status == Unknown`` was surfaced). Inactive
    nodes are skipped unless event-driven (EVENT_DRIVEN_DP_IDS) — for
    those, the next codex run is allowed to refresh in case a new event
    materialized. Each prompt also lists the model_tier + refresh_trigger
    so codex can scale effort, and prints an explicit "preserved" ban list.

Usage::

    # Industry-level overlay (L0 fields per industry)
    python scripts/codex_prompt_gen.py --industry AI_COMPUTE \
        --out /tmp/codex_AI_COMPUTE.md

    # Company-level overlay (L1-L5 fields per company)
    python scripts/codex_prompt_gen.py --industry STORAGE_GRID \
        --ts-code 300750.SZ --out /tmp/codex_300750_SZ.md

    # Dry-run list of dp_ids only (no full prompt body)
    python scripts/codex_prompt_gen.py --industry AI_COMPUTE --list-only

    # Filter by governance model_tier (e.g. only cheap_extract slots)
    python scripts/codex_prompt_gen.py --industry AI_COMPUTE \
        --ts-code 000063.SZ --model-tier cheap_extract --list-only
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mvp20.fingerprint import (  # noqa: E402
    compute_dependency_fingerprint,
    is_refresh_triggered,
)


GOVERNANCE_PATH = ROOT / "config" / "llm_field_governance.yaml"
HOT_DB_PATH = ROOT / "runtime" / "hot.sqlite"

MODEL_TIER_CHOICES = (
    "cheap_extract",
    "cheap_classify",
    "analysis",
    "web_analysis",
    "all",
)


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


# ---------------------------------------------------------------------------
# Governance loader
# ---------------------------------------------------------------------------


def load_governance(path: Path | None = None) -> dict:
    """Load ``llm_field_governance.yaml``. Returns empty dict if missing."""

    gov_path = path or GOVERNANCE_PATH
    if not gov_path.exists():
        return {}
    return yaml.safe_load(gov_path.read_text(encoding="utf-8")) or {}


def get_governance(dp_id: str, gov: dict) -> dict | None:
    """Look up the governance entry for ``dp_id``.

    Returns ``None`` if the dp_id is not registered in governance — this is
    the safe default: only fill LLM-allowlisted slots.
    """

    if not gov:
        return None
    return (gov.get("data_points") or {}).get(dp_id)


def _event_driven_dp_ids() -> frozenset[str]:
    try:
        from mvp20.overlays import EVENT_DRIVEN_DP_IDS  # type: ignore
    except ImportError:  # pragma: no cover — defensive
        return frozenset()
    return EVENT_DRIVEN_DP_IDS


# ---------------------------------------------------------------------------
# Filter logic
# ---------------------------------------------------------------------------


def _is_fillable(
    node: dict,
    governance_entry: dict | None,
    *,
    model_tier_filter: str = "all",
    event_driven_dp_ids: frozenset[str] | None = None,
    db_path: Path | None = None,
    ts_code: str | None = None,
) -> tuple[bool, str | None]:
    """Decide whether this node should be included in the codex prompt.

    Returns ``(fillable, skip_reason)`` so the caller can both filter and
    surface why something was dropped (used by ``--list-only`` for a
    transparent dry-run summary).

    Rules:
      1. Node not in governance → skip (default safe: only fill known LLM
         fields).
      2. ``governance.route`` ∉ ``{llm_close, llm_web}`` → skip
         (skip/derive routes are not LLM-fillable).
      3. ``data_status == Unknown`` → fillable.
      4. ``data_status == Optionality`` AND ``value`` is empty → fillable.
         Optionality with a populated current/future contribution is
         preserved by Z1a merge_preserve.
      5. ``data_status == Inactive`` AND dp_id is event-driven → fillable
         (transient state; allow refresh check next run).
      6. ``data_status == Known`` → Z2 refresh-trigger check: re-fill
         only if the source fingerprint rotated since the last fill.
         Backwards compatible: when ``db_path``/``ts_code`` are not
         supplied (e.g. unit tests, ``--list-only`` without DB) Known
         is preserved as before.
      7. ``data_status == N/A`` → preserved (Z1a).
      8. ``data_status == Optionality`` with non-empty value → skip
         (preserved by Z1a).
      9. Optional tier filter: governance.model_tier mismatch → skip.
    """

    dp_id = node.get("dp_id") or ""
    status = node.get("data_status")
    value = node.get("value")

    # Rule 1: governance allowlist
    if governance_entry is None:
        return False, "not_in_governance"

    # Rule 2: only route ∈ {llm_close, llm_web}
    route = governance_entry.get("route")
    if route not in ("llm_close", "llm_web"):
        return False, f"route={route}"

    # Rule 9: model_tier filter
    if model_tier_filter != "all":
        entry_tier = governance_entry.get("model_tier")
        if entry_tier != model_tier_filter:
            return False, f"tier_mismatch_{entry_tier}"

    # Rule 3: Unknown → fill
    if status == "Unknown":
        return True, None

    # Rule 4: Optionality with empty value → fill
    if status == "Optionality":
        if not isinstance(value, dict) or value is None:
            return True, None
        has_current = value.get("current_contribution") not in (None, "", {}, [])
        has_future = value.get("future_option_value") not in (None, "", {}, [])
        if not (has_current or has_future):
            return True, None
        return False, "optionality_already_filled"

    # Rule 5: Inactive event-driven → fingerprint-gated refresh (Z5 Fix 3).
    #
    # Pre-Z5 root cause: this branch returned True unconditionally for any
    # event-driven Inactive, so every cheap_classify pass re-prompted codex
    # on slots that had no new event signal. The fingerprint check (same
    # one used for Known) is the right gate — only re-fill when the source
    # dp_ids (governance.source_dependencies) actually changed.
    if status == "Inactive":
        # Prefer governance.refresh_trigger as the source of truth so the
        # check stays in sync with config/llm_field_governance.yaml even
        # when EVENT_DRIVEN_DP_IDS goes stale. Fall back to the legacy
        # set for nodes not yet declared in governance.
        is_event_driven = (
            governance_entry.get("refresh_trigger") == "event_driven"
            or dp_id in (event_driven_dp_ids or _event_driven_dp_ids())
        )
        if not is_event_driven:
            return False, "inactive_static"
        # Event-driven Inactive: only re-prompt when fingerprint rotates.
        if db_path is None or ts_code is None:
            # Backward-compat: no db context (unit tests / legacy callers)
            # → skip rather than spam codex with stale slots.
            return False, "inactive_event_no_db_context"
        need_refresh, reason = is_refresh_triggered(
            node, governance_entry, db_path, ts_code
        )
        if need_refresh:
            return True, f"refresh:{reason}"
        return False, f"inactive_event_no_change:{reason}"

    # Rule 6: Known → Z2 refresh-trigger check.
    if status == "Known":
        if db_path is None or ts_code is None:
            return False, "preserved_known"
        need_refresh, reason = is_refresh_triggered(
            node, governance_entry, db_path, ts_code
        )
        if need_refresh:
            return True, f"refresh:{reason}"
        return False, f"preserved_known:{reason}"

    # Rule 7: N/A → preserved
    if status == "N/A":
        return False, "preserved_n/a"

    return False, f"unknown_status_{status}"


def _filter_nodes(
    nodes: list[dict],
    governance: dict,
    *,
    layer_prefix: str | None = None,
    layer_exclude: tuple[str, ...] = (),
    model_tier_filter: str = "all",
    db_path: Path | None = None,
    ts_code: str | None = None,
) -> tuple[list[dict], list[tuple[str, str]]]:
    """Apply governance + status filter to a node list.

    Z2 additions: ``db_path`` + ``ts_code`` enable the refresh-trigger
    check for ``data_status=Known`` nodes. When omitted, Known is
    preserved unconditionally (legacy / unit-test behaviour).

    Returns ``(fillable_nodes, skipped_records)`` where ``skipped_records``
    is ``[(dp_id, reason), ...]`` for transparent dry-run reporting.
    """

    fillable: list[dict] = []
    skipped: list[tuple[str, str]] = []
    triggers = _event_driven_dp_ids()
    for node in nodes:
        dp_id = node.get("dp_id") or ""
        if layer_prefix and not dp_id.startswith(layer_prefix):
            continue
        if layer_exclude and any(dp_id.startswith(p) for p in layer_exclude):
            continue
        entry = get_governance(dp_id, governance)
        ok, reason = _is_fillable(
            node,
            entry,
            model_tier_filter=model_tier_filter,
            event_driven_dp_ids=triggers,
            db_path=db_path,
            ts_code=ts_code,
        )
        if ok:
            fillable.append(node)
        else:
            skipped.append((dp_id, reason or "no_reason"))
    return fillable, skipped


def _preserved_dp_ids(
    nodes: list[dict],
    governance: dict,
    *,
    layer_prefix: str | None = None,
    layer_exclude: tuple[str, ...] = (),
) -> list[tuple[str, str]]:
    """Collect dp_ids that should *not* be touched (Z1a-preserved).

    Only governance-registered dp_ids appear here — meta/non-LLM fields
    (e.g. the legacy ``company`` portrait slot) are excluded so the ban
    list stays focused on slots codex actually considers.

    These are surfaced in the prompt so codex sees an explicit ban list.
    Returns ``[(dp_id, status_or_reason), ...]``.
    """

    out: list[tuple[str, str]] = []
    for node in nodes:
        dp_id = node.get("dp_id") or ""
        if layer_prefix and not dp_id.startswith(layer_prefix):
            continue
        if layer_exclude and any(dp_id.startswith(p) for p in layer_exclude):
            continue
        # Only surface preserved dp_ids that are registered LLM slots.
        if get_governance(dp_id, governance) is None:
            continue
        status = node.get("data_status")
        value = node.get("value")
        if status == "Known":
            out.append((dp_id, "Known"))
        elif status == "N/A":
            out.append((dp_id, "N/A"))
        elif status == "Inactive" and dp_id not in _event_driven_dp_ids():
            out.append((dp_id, "Inactive(static)"))
        elif status == "Optionality" and isinstance(value, dict):
            has_current = value.get("current_contribution") not in (None, "", {}, [])
            has_future = value.get("future_option_value") not in (None, "", {}, [])
            if has_current or has_future:
                out.append((dp_id, "Optionality(filled)"))
    return out


# ---------------------------------------------------------------------------
# DB helper
# ---------------------------------------------------------------------------


def _read_realtime(db_path: Path, ts_code: str) -> dict[str, Any]:
    """Pull what's already in realtime_current for this stock (for codex context)."""

    if not db_path.exists():
        return {}
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT dp_id, value_json, source FROM realtime_current WHERE ts_code = ?",
            (ts_code,),
        ).fetchall()
    finally:
        conn.close()
    out = {}
    for dp_id, value_json, source in rows:
        try:
            out[dp_id] = {"value": json.loads(value_json), "source": source}
        except json.JSONDecodeError:
            out[dp_id] = {"value": value_json, "source": source}
    return out


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


CLOSED_LOOP_RULES = """## 严格闭环规则（X5 closed-loop — 必读 / 必遵守）

本任务**严格**禁止访问外部网络。codex 只能用以下 3 类信息：

1. **本地 SQLite dp_id** —— 由本 prompt 在下方 inline 注入（包括 X5 新增的 3 条文本披露：
   `L1.company.main_business` / `L9.disclosure.qa_recent` / `L8.gov.management_table`）。
2. **本地 overlay yaml** —— 本任务编辑文件 + 已填的行业/公司 overlay。
3. **行业框架推断** —— 行业级常识（如"半导体行业上行周期 24 个月"），但
   `confidence` 必须 ≤ 0.5 且 `evidence_quality: low`，标 `kind: industry_inference`。

**禁止行为**：
- 运行 `curl` / `wget` / `fetch` / `playwright` 或任何 HTTP 工具
- 凭训练记忆引用具体公司数字（如"NVDA Q3 营收 1234 亿美元"）
- 在 `evidence_sources` 写 http:// 或 https:// URL
- 引用 prompt 内没出现过的研报 / 年报 / 新闻

**evidence_sources schema**：仅允许 3 种 kind：
- `local_dp_id`：`{"kind": "local_dp_id", "dp_id": "...", "excerpt": "..."}`
- `local_overlay`：`{"kind": "local_overlay", "path": "config/...", "dp_id": "..."}`
- `industry_inference`：`{"kind": "industry_inference", "framework": "...", "confidence": 0.4}`

找不到本地证据 → `data_status: Unknown` + `missing_reason: "no_local_evidence"`，
**绝不 hallucinate URL**。

verify 脚本 `scripts/verify_overlay_closed_loop.py` 跑完会列出所有违规（含 http URL
/ 非白名单 kind）。**违规节点会被 auto-demote 回 Unknown** 并失去 confidence。

---

## Z2 — source fingerprint 写回（必读 / refresh trigger 闭环）

下方"待填字段"表的最后一列 `current_source_fingerprint` 是本 prompt 即时算出的
源指纹（`SHA256(dp_id + source + updated_at + normalized value_json)`，filing 类
还会折入 `period/end_date/ann_date`）。**填写每个节点时**，必须在 yaml node
内额外加 3 个字段：

```yaml
source_fingerprint_at_fill: <copy 表格中该 dp_id 的 current_source_fingerprint 列>
last_filled_period: <2026Q1 / 2025 / 当前 source 的报告期；不适用填 null>
last_event_id: <若 refresh_trigger=event_driven，填触发本次填充的 event 哈希 / 公告 id；否则 null>
```

下一轮跑 codex 时，`codex_prompt_gen` 会对比 `source_fingerprint_at_fill` 与
当前 SQLite 实际指纹：相同 → Known 字段被 preserve；不同 → 该 dp_id 会被重新
排队回 prompt（视作 source rotated）。

**绝不**把没列在表里的 dp_id 加进 `source_fingerprint_at_fill`。表里写 `-`
表示 governance 没声明 source_dependencies（如 D bucket pending Z3），此时
fingerprint 留空 `null` 即可。

---

"""


WEB_ANALYSIS_RULES = """## evidence_sources 规则（web_analysis 字段 — 允许 web）

本 prompt 含 `model_tier=web_analysis` 字段，**允许**引用外部 URL。每条 web
evidence 必须含完整审计字段：

| 字段 | 含义 |
|---|---|
| `kind` | `annual_report` / `research_report` / `investor_relations` / `external_url` / `industry_panel` |
| `url` | 完整可访问 URL（http 或 https） |
| `checksum` | `sha256(fetched_body)` 16-char hex prefix |
| `fetched_at` | ISO timestamp（拉取那一刻） |
| `excerpt` | 原文片段 ≤ 300 字符（让审计可定位原始证据） |

**未带 checksum → `evidence_quality=low` + `confidence ≤ 0.5`**（verify 脚本会
demote）。所有 URL 必须真实可访问；**不要 hallucinate URL**。

closed-loop 字段（`cheap_extract` / `cheap_classify` / `analysis`）依然只允
`local_dp_id` / `local_overlay` / `industry_inference`，**不要**把 web evidence
塞进 closed-loop 字段。

详见 `docs/codex/codex_fill_guide.md` §2a (web-enabled 字段)。

---

## Z2 — source fingerprint 写回（同 closed-loop 字段）

参考下方"待填字段"表的 `current_source_fingerprint` 列。即使 web_analysis
字段没有 SQLite 源依赖，也要在 yaml 节点写：

```yaml
source_fingerprint_at_fill: <表格列；governance 无 source_dependencies 时填 null>
last_filled_period: <报告期；不适用填 null>
last_event_id: null
```

---

"""


_CLOSED_LOOP_TIERS = frozenset({"cheap_extract", "cheap_classify", "analysis"})


def _render_evidence_rules(fillable: list[dict], governance: dict) -> str:
    """Pick the right evidence-rule block(s) based on the tier mix in this prompt.

    Z5 Fix 2 root cause: the previous code unconditionally inserted
    ``CLOSED_LOOP_RULES`` (which begins with "严格禁止访问外部网络") into
    every prompt — including ``--model-tier web_analysis`` prompts where
    codex_fill_guide.md §2a explicitly permits web URLs with checksum.
    The resulting contradiction either confused codex into refusing to
    use web evidence at all, or pushed it into hallucinating local-only
    evidence for web-tier slots.

    Returns:
        Markdown block. If the fillable set is all web_analysis →
        WEB_ANALYSIS_RULES alone. If all closed-loop → CLOSED_LOOP_RULES.
        Mixed → both, with the closed-loop block first so codex sees the
        stricter rule, then the relaxed web rule for the web-tier rows.
    """

    tiers: set[str] = set()
    for n in fillable:
        dp_id = n.get("dp_id") or ""
        entry = (governance.get("data_points") or {}).get(dp_id) or {}
        tier = entry.get("model_tier")
        if tier:
            tiers.add(tier)

    has_web = "web_analysis" in tiers
    has_closed = bool(tiers & _CLOSED_LOOP_TIERS)

    if has_web and has_closed:
        return CLOSED_LOOP_RULES + WEB_ANALYSIS_RULES
    if has_web:
        return WEB_ANALYSIS_RULES
    # Default — pure closed-loop (or empty fillable set, where preserving
    # the stricter rule is the safer default).
    return CLOSED_LOOP_RULES


def _format_fillable_table(
    nodes: list[dict],
    governance: dict,
    *,
    db_path: Path | None = None,
    ts_code: str | None = None,
) -> list[str]:
    """Render a markdown table with governance hints for each fillable node.

    Z2: when ``db_path`` + ``ts_code`` are supplied, also computes the
    *current_source_fingerprint* for each row and surfaces it so codex
    can copy it verbatim into ``source_fingerprint_at_fill`` on the
    yaml node. The verifier will then detect divergence next run.
    """

    lines: list[str] = []
    lines.append(
        "| dp_id | model_tier | refresh_trigger | source_deps | "
        "current_source_fingerprint |"
    )
    lines.append("|---|---|---|---|---|")
    for n in nodes:
        dp_id = n.get("dp_id") or ""
        entry = get_governance(dp_id, governance) or {}
        tier = entry.get("model_tier") or "-"
        trigger = entry.get("refresh_trigger") or "-"
        deps = entry.get("source_dependencies") or []
        deps_str = ", ".join(deps) if deps else "-"
        fp = "-"
        if db_path is not None and ts_code is not None and deps:
            current = compute_dependency_fingerprint(ts_code, deps, db_path)
            if current is not None:
                fp = current
        lines.append(
            f"| `{dp_id}` | {tier} | {trigger} | {deps_str} | `{fp}` |"
        )
    return lines


def _format_preserved_section(preserved: list[tuple[str, str]]) -> list[str]:
    """Render the explicit "do not touch" ban list."""

    parts: list[str] = []
    if not preserved:
        return parts
    parts.append("## 排除字段（已 preserved，不要重新填写）")
    parts.append("")
    parts.append(
        "以下字段 data_status 已是 Known/N/A/Inactive(static)/Optionality(filled)，"
    )
    parts.append("**不在本次填充范围**。Z1a merge_preserve 已保护它们：")
    parts.append("")
    for dp_id, reason in preserved:
        parts.append(f"- `{dp_id}` ({reason})")
    parts.append("")
    return parts


def build_industry_prompt(
    industry_id: str,
    *,
    root: Path = ROOT,
    model_tier_filter: str = "all",
    governance: dict | None = None,
) -> str:
    """Build a prompt for filling L0 fields in an industry_overlay file."""

    industry_path = root / "config" / "industry_overlays" / f"{industry_id}.yaml"
    industry_graph_path = root / "config" / "industry_graphs" / f"{industry_id}.yaml"
    if not industry_path.exists():
        sys.exit(f"industry_overlay not found: {industry_path}")
    overlay = _load_yaml(industry_path)
    graph = _load_yaml(industry_graph_path)
    governance = governance if governance is not None else load_governance()

    # Z2: industry-level fingerprint uses the INDUSTRY:<id> sentinel as
    # ts_code so source_dependencies are looked up in the macro/industry
    # rows of realtime_current.
    industry_ts_code = f"INDUSTRY:{industry_id}"
    db_path = root / "runtime" / "hot.sqlite"

    nodes = overlay.get("nodes") or []
    fillable_l0, _skipped = _filter_nodes(
        nodes,
        governance,
        layer_prefix="L0.",
        model_tier_filter=model_tier_filter,
        db_path=db_path,
        ts_code=industry_ts_code,
    )
    preserved_l0 = _preserved_dp_ids(nodes, governance, layer_prefix="L0.")

    industry_name = (
        overlay.get("industry_name")
        or overlay.get("industry_id")
        or industry_id
    )
    total_l0 = sum(1 for n in nodes if (n.get("dp_id") or "").startswith("L0."))

    parts: list[str] = []
    parts.append(
        f"# Codex 任务：填充 {industry_name}（{industry_id}）行业 overlay L0 字段"
    )
    parts.append("")
    parts.append(_render_evidence_rules(fillable_l0, governance).rstrip())
    parts.append("")
    parts.append("## 输入文件（必读）")
    parts.append("")
    parts.append(
        "1. **`docs/codex/codex_fill_guide.md`** — 总指南，字段语义 / 状态机 / 不要做的事"
    )
    parts.append("2. **`图谱设计.md`** — v2 spec 12 层")
    parts.append(
        "3. **`docs/data_sources/llm_derived_nodes.md`** Section 3 — 行业级 L0 字段的 prompt 模板 + output_schema"
    )
    parts.append(
        "4. **`config/industry_graphs/{0}.yaml`** — 该行业的因果图，含已填的行业层 priors（state_probabilities / valuation_mix / tail_risk）".format(
            industry_id
        )
    )
    parts.append(
        "5. **`config/industry_overlays/{0}.yaml`** — **你要编辑的文件**".format(
            industry_id
        )
    )
    parts.append(
        "6. **`config/llm_field_governance.yaml`** — governance（route / model_tier / refresh_trigger / source_dependencies）"
    )
    parts.append("")

    if not fillable_l0:
        parts.append("## ✅ 没有可填字段")
        parts.append("")
        parts.append(
            f"按 governance + 状态过滤后，无 L0 字段待填（"
            f"model_tier={model_tier_filter}）。若有 preserved 字段见下方列表。"
        )
        parts.append("")
        parts.extend(_format_preserved_section(preserved_l0))
        return "\n".join(parts)

    parts.append(
        f"## 当前状态：{len(fillable_l0)} / {total_l0} 条 L0 字段需要填充"
        f"（governance allowlist + model_tier={model_tier_filter}）"
    )
    parts.append("")
    parts.append("### 行业基本信息")
    parts.append(f"- 行业 ID：`{industry_id}`")
    parts.append(f"- 行业名称：{industry_name}")
    period = overlay.get("period")
    if period:
        parts.append(f"- 报告期：{period}")
    parts.append("")

    if graph.get("priors"):
        priors = graph["priors"]
        parts.append("### 行业图谱 priors（参考输入）")
        parts.append("")
        if priors.get("boundary"):
            b = priors["boundary"]
            parts.append(f"- 范围：{b.get('core_judgment', '')}")
        if priors.get("state_probabilities"):
            states = ", ".join(
                f"{s.get('name')}={s.get('probability'):.0%}"
                for s in priors["state_probabilities"]
            )
            parts.append(f"- 状态概率：{states}")
        if priors.get("tail_risk"):
            parts.append(
                f"- 尾部风险：{priors['tail_risk'].get('formula_note', '')}"
            )
        parts.append("")

    parts.append(f"### {len(fillable_l0)} 条待填字段")
    parts.append("")
    parts.extend(
        _format_fillable_table(
            fillable_l0, governance, db_path=db_path, ts_code=industry_ts_code
        )
    )
    parts.append("")
    parts.append("#### 节点元信息")
    parts.append("")
    for n in fillable_l0:
        parts.append(
            f"- `{n['dp_id']}` — {n.get('node_name', '')}  "
            f"（required_level={n.get('required_level', 'optional')}，"
            f"materiality={n.get('materiality')}，"
            f"data_status={n.get('data_status')}）"
        )
    parts.append("")

    parts.extend(_format_preserved_section(preserved_l0))

    parts.append("## 任务")
    parts.append("")
    parts.append(f"编辑 `config/industry_overlays/{industry_id}.yaml`：")
    parts.append("")
    parts.append(
        "对上面待填节点（在 YAML `nodes:` 数组中），按 "
        "`docs/data_sources/llm_derived_nodes.md` Section 3 的 output_schema "
        "输出 `value` 字段，并："
    )
    parts.append("")
    parts.append(
        "- `data_status: Known` 找到证据时（或 `Inactive` 若节点是事件型且当前无事件，如价格战）"
    )
    parts.append(
        "- `data_status: Unknown` 找不到一手证据时（保留，**不要瞎编**）"
    )
    parts.append(
        "- `value` 用 JSON dict 含 `yoy_pct` / `trend` / `magnitude` 等结构化字段（按各 dp_id schema）"
    )
    parts.append("- `confidence` 0-1，evidence 一手为 medium ≈ 0.7，二手 ≈ 0.5")
    parts.append("- `evidence_quality` low / medium / high")
    parts.append(
        "- `evidence_sources` 列表，每项 `{kind, title, source, published_at, excerpt}`，必须真实可查"
    )
    parts.append("- `last_updated` ISO 时间戳")
    parts.append("")
    parts.append(
        "不动 `node_id` / `dp_id` / `child_nodes` / `parent_node` / `materiality` / `required_level` 等结构字段。"
    )
    parts.append("")
    parts.append("## 数据源建议")
    parts.append("")
    parts.append(
        "- **优先**：本行业最新年度/季度产销数据（如电池行业 → 高工锂电 GGII；汽车 → 中汽协）"
    )
    parts.append(
        "- **次之**：龙头公司业绩说明会纪要（提到行业 demand/supply 现状）"
    )
    parts.append(
        "- **再次**：券商行业深度研报（中信/中金/华泰本行业研报）"
    )
    parts.append("- **最后**：财经媒体（财新/界面新闻/澎湃）")
    parts.append("")
    parts.append(
        '找不到任何证据 → `data_status: Unknown` + `missing_reason: "行业数据未公开披露"`，不要 hallucinate。'
    )
    parts.append("")

    return "\n".join(parts)


def build_company_prompt(
    industry_id: str,
    ts_code: str,
    *,
    root: Path = ROOT,
    model_tier_filter: str = "all",
    governance: dict | None = None,
) -> str:
    """Build a prompt for filling L1-L5 fields in a company stock_overlay."""

    stock_path = (
        root / "config" / "stock_overlays" / industry_id / f"{ts_code}.yaml"
    )
    industry_overlay_path = (
        root / "config" / "industry_overlays" / f"{industry_id}.yaml"
    )
    db_path = root / "runtime" / "hot.sqlite"

    if not stock_path.exists():
        sys.exit(f"stock_overlay not found: {stock_path}")
    overlay = _load_yaml(stock_path)
    industry_overlay = _load_yaml(industry_overlay_path)
    governance = governance if governance is not None else load_governance()

    nodes = overlay.get("nodes") or []
    fillable_company, _skipped = _filter_nodes(
        nodes,
        governance,
        layer_exclude=("L0.",),
        model_tier_filter=model_tier_filter,
        db_path=db_path,
        ts_code=ts_code,
    )
    preserved_company = _preserved_dp_ids(
        nodes, governance, layer_exclude=("L0.",)
    )

    name = overlay.get("name") or ts_code
    role = overlay.get("role", "target")

    parts: list[str] = []
    parts.append(
        f"# Codex 任务：填充 {name}（{ts_code} · {industry_id}）公司 overlay L1-L5 字段"
    )
    parts.append("")
    parts.append(_render_evidence_rules(fillable_company, governance).rstrip())
    parts.append("")
    parts.append("## 输入文件（必读）")
    parts.append("")
    parts.append("1. **`docs/codex/codex_fill_guide.md`** — 总指南")
    parts.append("2. **`图谱设计.md`** — v2 spec")
    parts.append(
        "3. **`docs/data_sources/llm_derived_nodes.md`** Section 4 — 公司级字段 prompt + output_schema"
    )
    parts.append(
        f"4. **`config/industry_overlays/{industry_id}.yaml`** — 该行业 overlay 已填的 L0 上下文（作为公司判断的输入参考）"
    )
    parts.append(
        f"5. **`config/stock_overlays/{industry_id}/{ts_code}.yaml`** — **你要编辑的文件**"
    )
    parts.append(
        "6. **`config/llm_field_governance.yaml`** — governance（route / model_tier / refresh_trigger / source_dependencies）"
    )
    parts.append("")

    if not fillable_company:
        parts.append("## ✅ 没有可填字段")
        parts.append("")
        parts.append(
            f"按 governance + 状态过滤后，无 L1-L5 字段待填（"
            f"model_tier={model_tier_filter}）。若有 preserved 字段见下方列表。"
        )
        parts.append("")
        parts.extend(_format_preserved_section(preserved_company))
        return "\n".join(parts)

    parts.append(
        f"## 当前状态：{len(fillable_company)} 条 L1-L5 字段需要填充"
        f"（governance allowlist + model_tier={model_tier_filter}）"
    )
    parts.append("")
    parts.append("### 公司基本信息")
    parts.append(f"- ts_code：`{ts_code}` 名称：{name} 角色：{role}")
    parts.append(f"- 主行业：{industry_id}")
    market = (
        "A股"
        if ts_code.endswith((".SH", ".SZ", ".BJ"))
        else "HK"
        if ts_code.endswith(".HK")
        else "US"
        if ts_code.endswith(".US")
        else "?"
    )
    parts.append(f"- 市场：{market}")
    period = overlay.get("period")
    if period:
        parts.append(f"- 报告期：{period}")
    parts.append("")

    # Pull realtime data so codex knows what's already known about the company
    realtime = _read_realtime(db_path, ts_code)
    if realtime:
        parts.append(
            f"### 已注入的财务/估值/资金数据（共 {len(realtime)} 字段，作为 codex 判断的事实背景）"
        )
        parts.append("")
        # X5 highlight: surface the three text-disclosure dp_ids first so
        # codex *sees* them and uses them as primary evidence for Group A
        # company-portrait slots. They give codex concrete inline facts
        # rather than forcing it to lean on training-set memory.
        x5_text_dp_ids = (
            "L1.company.main_business",
            "L9.disclosure.qa_recent",
            "L8.gov.management_table",
        )
        x5_present = [d for d in x5_text_dp_ids if d in realtime]
        if x5_present:
            parts.append("#### X5 文本披露（codex 必须优先引用作为 local_dp_id 证据）")
            parts.append("")
            for dp_id in x5_present:
                entry = realtime[dp_id]
                val = entry.get("value")
                src = entry.get("source", "")
                # For text disclosures we want a longer excerpt — codex needs the
                # actual text to quote / paraphrase, not just the keys.
                val_str = json.dumps(val, ensure_ascii=False)[:600]
                parts.append(f"- `{dp_id}` ({src}): {val_str}")
            parts.append("")
        parts.append("#### 其他财务/估值/资金事实")
        parts.append("")
        for dp_id in sorted(realtime.keys()):
            if dp_id in x5_text_dp_ids:
                continue
            entry = realtime[dp_id]
            val = entry.get("value")
            src = entry.get("source", "")
            # Compact value display
            if isinstance(val, dict):
                val_str = "; ".join(
                    f"{k}={v}" for k, v in val.items() if v is not None
                )[:120]
            else:
                val_str = str(val)[:120]
            parts.append(f"- `{dp_id}` ({src}): {val_str}")
        parts.append("")

    # Industry overlay context: list filled L0 fields if any
    industry_filled_nodes = [
        n
        for n in (industry_overlay.get("nodes") or [])
        if n.get("data_status") == "Known"
        and (n.get("dp_id") or "").startswith("L0.")
    ]
    if industry_filled_nodes:
        parts.append(
            f"### 行业 overlay 已填的 L0 上下文（{len(industry_filled_nodes)} 条）"
        )
        parts.append("")
        for n in industry_filled_nodes:
            val = n.get("value")
            val_str = (
                json.dumps(val, ensure_ascii=False)[:140] if val else "(空)"
            )
            parts.append(
                f"- `{n['dp_id']}` — {n.get('node_name', '')}: {val_str}"
            )
        parts.append("")
    else:
        parts.append(f"### 行业 overlay 上下文")
        parts.append("")
        parts.append(
            f"⚠️ `industry_overlays/{industry_id}.yaml` 暂未填 L0 字段。"
            f"建议先跑 `--industry {industry_id}` 把行业级填上，"
            f"再回来填公司级。或者公司级的判断会缺行业上下文支撑。"
        )
        parts.append("")

    parts.append(f"### {len(fillable_company)} 条待填字段（含 governance 元信息）")
    parts.append("")
    parts.extend(
        _format_fillable_table(
            fillable_company, governance, db_path=db_path, ts_code=ts_code
        )
    )
    parts.append("")
    parts.append("#### 按层分组")
    parts.append("")
    by_layer: dict[str, list[dict]] = {}
    for n in fillable_company:
        layer = (n.get("dp_id") or "").split(".")[0]
        by_layer.setdefault(layer, []).append(n)
    for layer in sorted(by_layer.keys()):
        items = by_layer[layer]
        parts.append(f"#### {layer}（{len(items)} 条）")
        parts.append("")
        for n in items:
            parts.append(
                f"- `{n['dp_id']}` — {n.get('node_name', '')}  "
                f"（required_level={n.get('required_level', 'optional')}，"
                f"materiality={n.get('materiality')}，"
                f"data_status={n.get('data_status')}）"
            )
        parts.append("")

    parts.extend(_format_preserved_section(preserved_company))

    parts.append("## 任务")
    parts.append("")
    parts.append(f"编辑 `config/stock_overlays/{industry_id}/{ts_code}.yaml`：")
    parts.append("")
    parts.append(
        "对上面 N 条节点，按 `llm_derived_nodes.md` Section 4 各 dp_id 的 "
        "`output_schema` 输出 `value` 字段。判断时要参考："
    )
    parts.append("")
    parts.append("1. 已注入的财务/估值数据（事实背景）")
    parts.append("2. 行业 overlay L0 上下文（行业级判断的参照系）")
    parts.append("3. 公司年报 / 业绩说明会 / 调研纪要 / 三方研报")
    parts.append("")
    parts.append("**关键规则**：")
    parts.append("")
    parts.append(
        f"- 公司天然不适用的 → `data_status: N/A` + `missing_reason` 说明（例：{name} "
        f"是 B2B 制造商，则 `L4.volume.foot_traffic` / `L4.price.subscription` 多半 N/A）"
    )
    parts.append(
        '- 适用但拿不到信息 → `data_status: Unknown` + `missing_reason: "公司未披露此项"`'
    )
    parts.append(
        "- 适用且有证据 → `data_status: Known` + `value` 结构化 + `evidence_sources` 真实"
    )
    parts.append(
        "- Optionality 字段（如 L2.newbiz.*）→ 填 `value.current_contribution` 或 "
        "`value.future_option_value`，保留 `data_status: Optionality`"
    )
    parts.append("- **不要 hallucinate** — 数字必须有出处")
    parts.append("")
    parts.append(
        "不动结构字段（node_id / dp_id / child_nodes / parent_node / materiality / "
        "required_level / missing_policy / aggregation_policy / calculation_type）。"
    )
    parts.append("")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# list-only helper (dry-run report)
# ---------------------------------------------------------------------------


def build_list_only_report(
    industry_id: str,
    ts_code: str | None,
    *,
    root: Path = ROOT,
    model_tier_filter: str = "all",
    governance: dict | None = None,
) -> str:
    """Return a compact dry-run summary of which dp_ids would be filled."""

    governance = governance if governance is not None else load_governance()
    db_path = root / "runtime" / "hot.sqlite"
    if ts_code:
        path = (
            root / "config" / "stock_overlays" / industry_id / f"{ts_code}.yaml"
        )
        layer_exclude = ("L0.",)
        layer_prefix = None
        scope = f"stock {industry_id}/{ts_code}"
        scope_ts_code = ts_code
    else:
        path = root / "config" / "industry_overlays" / f"{industry_id}.yaml"
        layer_exclude = ()
        layer_prefix = "L0."
        scope = f"industry {industry_id}"
        scope_ts_code = f"INDUSTRY:{industry_id}"

    if not path.exists():
        sys.exit(f"overlay not found: {path}")
    overlay = _load_yaml(path)
    nodes = overlay.get("nodes") or []
    fillable, skipped = _filter_nodes(
        nodes,
        governance,
        layer_prefix=layer_prefix,
        layer_exclude=layer_exclude,
        model_tier_filter=model_tier_filter,
        db_path=db_path,
        ts_code=scope_ts_code,
    )

    lines: list[str] = []
    lines.append(f"# list-only · {scope} · model_tier={model_tier_filter}")
    lines.append("")
    lines.append(f"## Fillable: {len(fillable)}")
    lines.append("")
    tier_counts: dict[str, int] = {}
    for n in fillable:
        entry = get_governance(n.get("dp_id") or "", governance) or {}
        tier = entry.get("model_tier") or "-"
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        lines.append(
            f"- `{n.get('dp_id')}` "
            f"[tier={tier}, "
            f"trigger={entry.get('refresh_trigger') or '-'}, "
            f"status={n.get('data_status')}]"
        )
    if tier_counts:
        lines.append("")
        lines.append("### Tier distribution")
        for tier, ct in sorted(tier_counts.items()):
            lines.append(f"- {tier}: {ct}")
    lines.append("")
    lines.append(f"## Skipped: {len(skipped)}")
    lines.append("")
    reason_counts: dict[str, int] = {}
    for _, r in skipped:
        reason_counts[r] = reason_counts.get(r, 0) + 1
    for reason, ct in sorted(reason_counts.items()):
        lines.append(f"- {reason}: {ct}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--industry", required=True, help="industry_id, e.g. AI_COMPUTE"
    )
    parser.add_argument(
        "--ts-code",
        default=None,
        help=(
            "If given, build company-level prompt for this ts_code under "
            "--industry; otherwise build industry-level prompt for --industry."
        ),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path (default: stdout).",
    )
    parser.add_argument(
        "--model-tier",
        choices=MODEL_TIER_CHOICES,
        default="all",
        help=(
            "Only generate prompts for fields of this model_tier "
            "(default: all). Use to batch-dispatch by cost tier."
        ),
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help=(
            "Just list filtered dp_ids + tier distribution + skip reasons "
            "without writing the full prompt body. Useful as a dry-run."
        ),
    )
    args = parser.parse_args()

    if args.list_only:
        prompt = build_list_only_report(
            args.industry,
            args.ts_code,
            model_tier_filter=args.model_tier,
        )
    elif args.ts_code:
        prompt = build_company_prompt(
            args.industry,
            args.ts_code,
            model_tier_filter=args.model_tier,
        )
    else:
        prompt = build_industry_prompt(
            args.industry,
            model_tier_filter=args.model_tier,
        )

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(prompt, encoding="utf-8")
        print(f"wrote {args.out} ({len(prompt)} chars)", file=sys.stderr)
    else:
        sys.stdout.write(prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
