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
from mvp20.storage import read_hot_snapshot  # noqa: E402
from mvp20.schema_validator import DP_SCHEMA, _type_name  # noqa: E402


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
    refresh_baseline_missing: bool = True,
    preserve_unknown_no_local_evidence: bool = False,
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
      10. If ``refresh_baseline_missing`` is false, legacy Known/Inactive
          nodes that lack ``source_fingerprint_at_fill`` are preserved for
          audit instead of being re-prompted just to establish a baseline.
      11. If ``preserve_unknown_no_local_evidence`` is true, an Unknown node
          previously filled as ``missing_reason: no_local_evidence`` is also
          fingerprint-gated so unchanged local evidence is not sent back to
          the LLM repeatedly.
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

    # Rule 3: Unknown → fill, unless a previous no-evidence fill already
    # established a current source fingerprint for this exact source state.
    if status == "Unknown":
        if (
            preserve_unknown_no_local_evidence
            and node.get("missing_reason") == "no_local_evidence"
        ):
            if db_path is None or ts_code is None:
                return False, "preserved_unknown_no_local_evidence:no_db_context"
            need_refresh, reason = is_refresh_triggered(
                node, governance_entry, db_path, ts_code
            )
            if need_refresh:
                return True, f"refresh:{reason}"
            return False, f"preserved_unknown_no_local_evidence:{reason}"
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
            if reason == "fingerprint_baseline_missing" and not refresh_baseline_missing:
                return False, "inactive_event_baseline_missing_preserved"
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
            if reason == "fingerprint_baseline_missing" and not refresh_baseline_missing:
                return False, "preserved_known:fingerprint_baseline_missing"
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
    refresh_baseline_missing: bool = True,
    preserve_unknown_no_local_evidence: bool = False,
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
            refresh_baseline_missing=refresh_baseline_missing,
            preserve_unknown_no_local_evidence=preserve_unknown_no_local_evidence,
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

1. **本地 SQLite dp_id** —— 由本 prompt 在下方 inline 注入（包括 Tushare
   本地事实：`L1.company.main_business` / `L9.disclosure.qa_recent` /
   `L8.gov.management_table`，以及已落库的 `L9.disclosure.annual_report`
   章节摘录、公告/问答/主营/管理层等 `tushare:*` source 行）。
2. **本地 overlay yaml** —— 本任务编辑文件 + 已填的行业/公司 overlay。
3. **行业框架推断** —— 行业级常识（如"半导体行业上行周期 24 个月"），但
   `confidence` 必须 ≤ 0.5 且 `evidence_quality: low`，标 `kind: industry_inference`。

**禁止行为**：
- 运行 `curl` / `wget` / `fetch` / `playwright` 或任何 HTTP 工具
- 凭训练记忆引用具体公司数字（如"NVDA Q3 营收 1234 亿美元"）
- 在 `evidence_sources` 写 http:// 或 https:// URL
- 引用 prompt 内没出现过的研报 / 年报 / 新闻

**evidence_sources schema**：仅允许 3 种 kind：
- `local_dp_id`：`{"kind": "local_dp_id", "dp_id": "...", "source": "tushare:* 或本地派生源", "excerpt": "..."}`
- `local_overlay`：`{"kind": "local_overlay", "path": "config/...", "dp_id": "..."}`
- `industry_inference`：`{"kind": "industry_inference", "framework": "...", "confidence": 0.4}`

`local_dp_id` 可以引用 Tushare/AKShare/FMP 已经写入 `runtime/hot.sqlite` 的本地
事实，但不能写 `url` 字段；即使原始公告 URL 存在于本地 value 中，也只引用本地
dp_id、source 和 verbatim excerpt。

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


# ---------------------------------------------------------------------------
# Strict output_schema block (C1 hardening). Low-effort codex frequently
# invented field names / wrong types (101 schema_drift across 8/10 AI_COMPUTE
# A-shares). Referencing llm_derived_nodes.md by name was not enough — we now
# inline each fillable dp_id's exact ``DP_SCHEMA`` shape (the same registry the
# verifier's --check-schema validates against) so the model sees the allowed
# fields + types right next to the field list.
# ---------------------------------------------------------------------------

_PROMPT_SCHEMA_GUIDANCE: dict[str, tuple[str, ...]] = {
    "L1.role.tag": (
        "标签只写 `value.tags` 列表；不要写 `role` / `category` / `summary` 等额外字段。",
        "`last_filled_period` 用最近本地事实源期间；只有主营/问答文本时可用 `2026Q1`。",
    ),
    "L1.model.tag": (
        "标签只写 `value.tags` 列表；不要写 `model` / `business_model` / `summary` 等额外字段。",
        "`last_filled_period` 用最近本地事实源期间；只有主营/问答文本时可用 `2026Q1`。",
    ),
    "L1.moat.tags": (
        "标签只写 `value.tags`，可选 `notes`；护城河弱也填保守标签，不要编造强护城河。",
        "证据不足时降低 `confidence`，不要用行业常识替代本地公司证据。",
    ),
    "L1.stock_attr.tags": (
        "标签只写 `value.tags`，可选 `notes`；可引用 `L6.path.tag`、收入增速、主营文本。",
        "只能把 `L6.path.tag` 的文字标签作为证据；不要把 PE/PB 分位、估值倍数、百分位数字写成标签或挂在 `L6.path.tag` 证据下。",
        "自然语言说明也不要写“未把估值倍数/分位数/百分位写入标签”这类治理提示词；改写为“未使用具体估值数值或相对位置作为标签”。",
        "不要把估值/主题标签写成顶层字段。",
    ),
    "L1.position.growth_rank": (
        "禁止旧字段：`growth_pct` / `rank_bucket` / `growth_metric` / `value_pct` / `growth_tier` / `rank_label`。",
        "`rank` 和 `share_pct` 只有本地证据直接披露行业排名/份额时才可填数字；否则必须为 `null`。",
        "`trend` 只允许 `modest_growth` / `decline` / `mixed`：收入同比正增长写 `modest_growth`，负增长写 `decline`，口径冲突或缺失写 `mixed`。",
        "无排名/份额直接证据时 `confidence <= 0.52` 且 `evidence_quality: low`；优先引用 `L5.is.revenue_growth` 与 `L5.fina.revenue_yoy`，不要用 `local_overlay` 伪造排名证据。",
    ),
    "L3.channel.mix": (
        "只有年报/本地文本直接披露直销、经销/分销、电商、其他渠道占比，或同一张销售模式表披露可直接映射的收入金额时，才填 `Known`。",
        "若同表披露直销、经销/分销、电商、其他等销售模式收入金额和可核对合计，可用金额做确定性占比计算；工业模式、其他模式等非标准销售模式归入 `others_pct`，内部抵消不当作渠道模式。",
        "若披露“销售模式均为直销”或等价表述，可填 direct_pct=100，其余为 0；否则 Unknown/no_local_evidence，四个占比都写 null。",
        "业务线、客户类型、区域、收入结构不等于渠道结构，不能据此推算渠道占比。",
        "线上/线下、境内/境外、产品/服务类型也不能映射为 ecommerce/others；除非文本直接披露“电商渠道”或 direct/distributor/ecommerce/other 口径，否则保持 Unknown。",
        "`value.trend` 不写中文自由文本；仅用短枚举式字符串，例如 `direct_sales_dominant`、`direct_share_up`、`direct_share_slightly_down`、`flat`、`mixed`，无趋势证据写 `null`。",
        "若 `direct_pct`、`distributor_pct`、`ecommerce_pct`、`others_pct` 全部为 `null`，或节点仍是 Unknown，则 `value.trend` 也必须写 `null`；定性“直销为主/经销为辅”只写在 notes。",
    ),
}


def _schema_one_line(node: dict) -> str | None:
    """Compact one-line schema spec for a fillable node, or None.

    Optionality-status nodes are special-cased: the compiler requires the
    ``value`` to split into ``current_contribution`` + ``future_option_value``
    (two objects), regardless of what the flat DP_SCHEMA field list says — so
    we render that contract instead of the flat fields to avoid steering the
    model into the shape that fails compile.
    """

    dp_id = node.get("dp_id") or ""
    if str(node.get("data_status")) == "Optionality":
        return (
            "required{current_contribution:dict, future_option_value:dict} "
            "（Optionality：两个键都必须是对象；当前贡献放 current_contribution，"
            "催化后期权价值放 future_option_value，各对象内可含 level/factors/"
            "catalyst_required 等说明字段）"
        )
    sch = DP_SCHEMA.get(dp_id)
    if not sch:
        return None
    parts: list[str] = []
    req = sch.get("required") or {}
    opt = sch.get("optional") or {}
    parts.append(
        "required{" + ", ".join(f"{k}:{_type_name(v)}" for k, v in req.items()) + "}"
    )
    if opt:
        parts.append(
            "optional{" + ", ".join(f"{k}:{_type_name(v)}" for k, v in opt.items()) + "}"
        )
    # Nested list element schemas: keys named "<field>_item_schema".
    for key, val in sch.items():
        if key.endswith("_item_schema") and isinstance(val, dict):
            base = key[: -len("_item_schema")]
            parts.append(
                f"{base}[]=每元素{{"
                + ", ".join(f"{k}:{_type_name(v)}" for k, v in val.items())
                + "}"
            )
    return "; ".join(parts)


def _format_schema_block(nodes: list[dict]) -> list[str]:
    """Render the strict per-dp_id output_schema enforcement block."""

    rows: list[str] = []
    for n in nodes:
        dp_id = n.get("dp_id") or ""
        spec = _schema_one_line(n)
        if spec:
            rows.append(f"- `{dp_id}`: {spec}")
            for guidance in _PROMPT_SCHEMA_GUIDANCE.get(dp_id, ()):
                rows.append(f"  - {guidance}")
    if not rows:
        return []
    return [
        "### 各待填字段 output_schema（强约束 — value 必须严格匹配）",
        "",
        "**铁律**：每个 dp_id 的 `value` **只能包含下列字段名**，类型必须匹配。"
        "**禁止新增 schema 之外的任何字段，禁止改字段类型** —— 额外字段 / 错类型会被 "
        "`schema_validator` 拒绝、导致节点编译失败。`required` 字段必须出现"
        "（无数据填 `null`，不要省略也不要换名）；`optional` 字段可省略。",
        "类型记号：`float|int` = 数字，`str` = 字符串，`null` = JSON null，"
        "`dict` = JSON 对象，`list` = JSON 数组，`bool` = 布尔。",
        "自然语言说明（如 `evidence_summary`、`notes`、`missing_reason`）必须使用中文；"
        "不要输出英文句子。枚举值、dp_id、source 名称、`no_local_evidence` 可保持原格式。",
        "自然语言说明不要复述 schema 字段名或枚举 key，例如 `rank`、`share_pct`、`trend`、"
        "`path.tag`、`decline`、`modest_growth`；应改写成中文“排名、份额、趋势、路径标签、下降、温和增长”。",
        "Optionality 节点（schema 含 `current_contribution` + `future_option_value`）"
        "的 `value` 必须同时含这两个键、各为对象，**不要写成扁平结构**。",
        "",
        *rows,
        "",
    ]


# ---------------------------------------------------------------------------
# Fix B (B1) — inline source dp_id values into the prompt so the LLM
# can quote them verbatim instead of paraphrasing. The A/B test showed
# codex_low produced ``evidence_sources[kind=local_dp_id]`` with
# excerpts that didn't appear anywhere in the source value, because the
# model never actually saw the source value — only its dp_id reference.
# Inlining the full SQLite value text fixes the citation provenance.
# ---------------------------------------------------------------------------


# Cap each inlined value at this many chars to keep prompt size bounded.
# 600 is enough to show a JSON dict with ~5-10 keys; we already use the
# same cap for X5 text disclosures.
_INLINE_VALUE_MAXLEN = 600


# ---------------------------------------------------------------------------
# Industry-level source aggregation (P-fix: industry L0 prompt evidence).
#
# Root cause this block addresses
# --------------------------------
# An industry-level L0 prompt looks up its ``source_dependencies`` against the
# ``INDUSTRY:<id>`` sentinel ts_code. But the realtime collectors store those
# deps in TWO other places, never under ``INDUSTRY:<id>``:
#
#   * Per-stock fundamentals/text (``L5.is.*`` / ``L5.bs.*`` / ``L5.cf.*`` /
#     ``L4.*`` / ``L9.disclosure.qa_recent`` / ``L9.media.social_buzz`` /
#     ``L1.company.main_business``) are keyed by the constituent ts_code
#     (``000063.SZ`` …) — 221-328 rows each.
#   * Market-wide catalyst/macro feeds (``L9.media.report`` /
#     ``L9.industry.compete_risk`` / ``L9.industry.policy_change`` /
#     ``L9.macro.*``) are keyed by the ``MARKET:CN`` sentinel — exactly 1 row
#     each (the shared 财联社 telegraph stream).
#
# ``read_hot_snapshot('INDUSTRY:AI_COMPUTE')`` resolves NEITHER (the sentinel
# fan-out only adds ``MARKET:<market>`` for *real* stock ts_codes via
# ``_ts_code_to_market``, which returns ``None`` for an ``INDUSTRY:`` key), so
# every L0 dep rendered as "(missing in SQLite)" and codex correctly refused
# to fabricate → 27 Unknown / no_local_evidence nodes.
#
# The fix: for the industry path, resolve each dep through a tier ladder:
#   1. industry-sentinel direct hit (already industry-level, e.g.
#      ``L0.cost.raw_material`` from the akshare commodity fetch),
#   2. AGGREGATE across the industry's constituents (mean/median + per-member
#      sample for numeric scalars; per-member latest text for dict/text deps),
#   3. fall back to the ``MARKET:CN`` sentinel row (market-wide feeds).
# ---------------------------------------------------------------------------


# Deps that are inherently market-wide (single MARKET:<market> sentinel row,
# no per-constituent fan-out). For an industry prompt these resolve via the
# MARKET:CN fallback rather than constituent aggregation.
_MARKET_LEVEL_DEP_PREFIXES = (
    "L9.media.report",
    "L9.industry.",
    "L9.macro.",
)

# How many constituents to surface verbatim in a per-member sample (keeps the
# prompt bounded — the aggregate stats already summarise the whole set).
_INDUSTRY_SAMPLE_N = 6


def _load_industry_constituents(industry_id: str, root: Path) -> list[str]:
    """Return the constituent ts_codes whose ``industry_ids`` include
    ``industry_id`` (read from ``config/mvp20.universe.yaml``).

    Mirrors the universe-read pattern used in ``mvp20.audit`` /
    ``mvp20.onboard``. Returns ``[]`` on missing / unparseable universe so
    the caller degrades gracefully (deps just render "(missing …)" as before).
    """

    universe_path = root / "config" / "mvp20.universe.yaml"
    if not universe_path.exists():
        return []
    try:
        data = yaml.safe_load(universe_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return []
    out: list[str] = []
    for c in data.get("constituents") or []:
        ts = c.get("ts_code")
        if not ts:
            continue
        ids = c.get("industry_ids") or []
        if isinstance(ids, list) and industry_id in [str(i) for i in ids]:
            out.append(str(ts))
    return out


def _is_market_level_dep(dep: str) -> bool:
    return any(
        dep == p or dep.startswith(p) for p in _MARKET_LEVEL_DEP_PREFIXES
    )


def _primary_numeric(value: Any) -> tuple[float, str] | None:
    """Extract the headline numeric from a source value dict, if any.

    Returns ``(number, field_name)`` or ``None``. Recognises the value
    shapes the fundamentals collectors emit:
      * ``{"scalar": N, "unit": ...}``   → most L5.is.* / L5.cf.* / L5.bs.*
      * ``{"yoy_pct": N, ...}``          → L5.is.revenue_growth
      * ``{"sga_rd_ratio_revenue": N}``  → L5.is.sga_rd
    Falls back to the first finite numeric leaf so unknown-but-numeric deps
    still aggregate instead of silently degrading to a text list.
    """

    if not isinstance(value, dict):
        return None
    for key in ("scalar", "yoy_pct", "sga_rd_ratio_revenue", "ratio", "value"):
        v = value.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            f = float(v)
            if f == f:  # not NaN
                return f, key
    for k, v in value.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            f = float(v)
            if f == f:
                return f, k
    return None


def _fmt_num(n: float) -> str:
    """Compact human number: keep ratios precise, abbreviate large counts."""

    if abs(n) >= 1e8:
        return f"{n / 1e8:.2f}亿"
    if abs(n) >= 1e4:
        return f"{n / 1e4:.2f}万"
    if abs(n) < 1 and n != 0:
        return f"{n:.4f}"
    return f"{n:.2f}"


def _aggregate_industry_dep_value(
    dep: str,
    constituents: list[str],
    db_path: Path,
    *,
    snapshot_cache: dict[str, dict] | None = None,
) -> str | None:
    """Aggregate one source dep across an industry's constituents.

    Reads each constituent's per-stock value (via ``read_hot_snapshot`` so
    sentinel fan-out still applies per member) and produces an inline-able
    summary string:

      * Numeric deps → ``n=K members; mean=…; median=…; latest_period=…;
        members[ts=val,…]`` so the LLM sees the cross-constituent
        distribution AND can quote an individual member's exact figure.
      * Text/dict deps → ``n=K members; <ts>: <compact value>; …`` for the
        first ``_INDUSTRY_SAMPLE_N`` members that have the dep.

    ``snapshot_cache`` memoises ``read_hot_snapshot`` per ts_code so a whole
    prompt (many deps × the same constituents) reads each member once.

    Returns ``None`` when no constituent has the dep (caller then falls back
    to the MARKET sentinel / "(missing …)").
    """

    if not constituents:
        return None

    # (ts_code, value) for every member that actually has this dep.
    present: list[tuple[str, Any]] = []
    for ts in constituents:
        if snapshot_cache is not None:
            snap = snapshot_cache.get(ts)
            if snap is None:
                snap = read_hot_snapshot(db_path, ts)
                snapshot_cache[ts] = snap
        else:
            snap = read_hot_snapshot(db_path, ts)
        entry = snap.get(dep)
        if entry is None:
            continue
        present.append((ts, entry.get("value")))
    if not present:
        return None

    # Numeric path: aggregate when a majority of members expose a headline
    # number (defends against a stray numeric leaf in an otherwise-text dep).
    numerics: list[tuple[str, float, str]] = []
    periods: set[str] = set()
    for ts, val in present:
        pn = _primary_numeric(val)
        if pn is not None:
            numerics.append((ts, pn[0], pn[1]))
        if isinstance(val, dict):
            p = val.get("period") or val.get("current_period") or val.get(
                "end_date"
            )
            if p:
                periods.add(str(p))

    if numerics and len(numerics) >= max(2, len(present) // 2):
        field = numerics[0][2]
        vals = sorted(v for _, v, _ in numerics)
        k = len(vals)
        mean = sum(vals) / k
        mid = k // 2
        median = vals[mid] if k % 2 else (vals[mid - 1] + vals[mid]) / 2
        sample = "; ".join(
            f"{ts}={_fmt_num(v)}" for ts, v, _ in numerics[:_INDUSTRY_SAMPLE_N]
        )
        period_note = (
            f"; latest_period={sorted(periods)[-1]}" if periods else ""
        )
        more = (
            f"; (+{len(numerics) - _INDUSTRY_SAMPLE_N} more)"
            if len(numerics) > _INDUSTRY_SAMPLE_N
            else ""
        )
        return (
            f"[industry-aggregate over {k} constituents] field={field}; "
            f"mean={_fmt_num(mean)}; median={_fmt_num(median)}; "
            f"min={_fmt_num(vals[0])}; max={_fmt_num(vals[-1])}{period_note}; "
            f"members[{sample}{more}]"
        )

    # Text / dict path: list each member's compact value (capped).
    parts: list[str] = [
        f"[industry-aggregate over {len(present)} constituents (text)]"
    ]
    for ts, val in present[:_INDUSTRY_SAMPLE_N]:
        try:
            vs = json.dumps(val, ensure_ascii=False)
        except (TypeError, ValueError):
            vs = str(val)
        if len(vs) > 180:
            vs = vs[:180] + "…"
        parts.append(f"{ts}: {vs}")
    if len(present) > _INDUSTRY_SAMPLE_N:
        parts.append(f"(+{len(present) - _INDUSTRY_SAMPLE_N} more constituents)")
    return " ｜ ".join(parts)


def _resolve_dep_value_text(
    dep: str,
    snapshot: dict,
    *,
    industry_constituents: list[str] | None,
    db_path: Path,
    snapshot_cache: dict[str, dict] | None = None,
) -> str:
    """Resolve one source dep to an inline value string.

    Company path (``industry_constituents is None``): legacy behaviour —
    direct snapshot lookup, "(missing in SQLite)" when absent.

    Industry path: tier ladder — industry-sentinel direct hit → constituent
    aggregate → MARKET:CN sentinel fallback → "(missing …)".
    """

    entry = snapshot.get(dep)
    if entry is not None:
        v = entry.get("value")
        try:
            value_str = json.dumps(v, ensure_ascii=False)
        except (TypeError, ValueError):
            value_str = str(v)
        if len(value_str) > _INLINE_VALUE_MAXLEN:
            value_str = value_str[: _INLINE_VALUE_MAXLEN] + "...(truncated)"
        return value_str

    # Company prompt: no aggregation, preserve original semantics.
    if industry_constituents is None:
        return "(missing in SQLite)"

    # Industry prompt — market-wide feeds resolve via MARKET:CN; everything
    # else aggregates across constituents.
    if not _is_market_level_dep(dep):
        agg = _aggregate_industry_dep_value(
            dep, industry_constituents, db_path, snapshot_cache=snapshot_cache
        )
        if agg is not None:
            value_str = agg
            if len(value_str) > _INLINE_VALUE_MAXLEN:
                value_str = value_str[: _INLINE_VALUE_MAXLEN] + "...(truncated)"
            return value_str

    # MARKET:CN sentinel fallback (market-wide catalyst / macro deps, or a
    # per-stock dep that no constituent happened to carry).
    market_snap = read_hot_snapshot(db_path, "MARKET:CN", include_sentinels=False)
    m_entry = market_snap.get(dep)
    if m_entry is not None:
        v = m_entry.get("value")
        try:
            value_str = json.dumps(v, ensure_ascii=False)
        except (TypeError, ValueError):
            value_str = str(v)
        status = m_entry.get("data_status")
        prefix = f"[MARKET:CN, status={status}] " if status else "[MARKET:CN] "
        value_str = prefix + value_str
        if len(value_str) > _INLINE_VALUE_MAXLEN:
            value_str = value_str[: _INLINE_VALUE_MAXLEN] + "...(truncated)"
        return value_str

    return "(missing in SQLite)"


def _build_source_value_table(
    fillable_nodes: list[dict],
    governance: dict,
    ts_code: str,
    db_path: Path,
    *,
    industry_constituents: list[str] | None = None,
) -> list[tuple[str, str, str]]:
    """For each (fillable dp_id, source_dependency) pair, look up the
    current SQLite value and format it for inlining into the prompt.

    Uses ``storage.read_hot_snapshot`` so the sentinel fan-out
    (``INDUSTRY:<id>`` / ``MARKET:<x>``) already in place naturally
    resolves industry/macro-level dependencies for company dp_ids.

    When ``industry_constituents`` is supplied (industry-level prompt), each
    dep is resolved through the tier ladder in ``_resolve_dep_value_text``:
    industry-sentinel direct hit → aggregate across constituents → MARKET:CN
    fallback. This surfaces REAL evidence for industry L0 fields whose deps
    are only ever stored per-stock or under MARKET:CN, not under the
    ``INDUSTRY:<id>`` key the snapshot is read against.

    Returns a list of ``(dp_id, source_dp_id, value_text)`` rows. Missing
    rows surface ``"(missing in SQLite)"`` so codex sees explicitly that no
    local evidence exists for that dependency — better than silently dropping
    the row, which would invite hallucination.
    """

    snapshot = read_hot_snapshot(db_path, ts_code) if db_path.exists() else {}
    # Memoise per-constituent snapshots so a whole industry prompt reads each
    # member once across all (dep × constituent) aggregations.
    snapshot_cache: dict[str, dict] = {}
    rows: list[tuple[str, str, str]] = []
    for node in fillable_nodes:
        dp_id = node.get("dp_id") or ""
        gov_entry = (governance.get("data_points") or {}).get(dp_id) or {}
        deps = gov_entry.get("source_dependencies") or []
        for dep in deps:
            value_str = _resolve_dep_value_text(
                dep,
                snapshot,
                industry_constituents=industry_constituents,
                db_path=db_path,
                snapshot_cache=snapshot_cache,
            )
            rows.append((dp_id, dep, value_str))
    return rows


# A1 Phase: which annual-report sections each fillable dp_id should see.
# Conservative — only fields where the AR章节 actually adds signal beyond
# what L9.disclosure.qa_recent / L1.company.main_business already gives.
_AR_SECTION_BY_DP_ID: dict[str, tuple[str, ...]] = {
    "L3.customer.segment_mix": ("customer_segment", "revenue_structure"),
    "L3.channel.mix": ("revenue_structure", "customer_segment"),
    "L3.region.tier_mix": ("region_distribution", "revenue_structure"),
    "L3.product.lifecycle": ("business_overview", "revenue_structure"),
    "L2.segment.industry_exposure": ("revenue_structure", "customer_segment"),
    "L2.segment.compete_landscape": ("business_overview", "risk_disclosure"),
    "L2.segment.business_risk": ("risk_disclosure",),
    "L4.eff.conversion_retention": ("customer_segment",),
    "L4.share.customer_channel": ("customer_segment", "revenue_structure"),
    "L1.position.channel_edge": ("revenue_structure", "business_overview"),
    "L1.position.market_share": ("business_overview", "revenue_structure"),
    "L1.position.brand": ("business_overview",),
    "L1.position.tech_barrier": ("business_overview", "risk_disclosure"),
    "L3.customer.solvency": ("customer_segment",),
    "L3.channel.overseas": ("region_distribution", "revenue_structure"),
    "L3.region.domestic_overseas": ("region_distribution", "revenue_structure"),
    "L3.region.fx_geo": ("region_distribution", "risk_disclosure"),
    "L3.region.key_risk": ("region_distribution", "risk_disclosure"),
    "L4.cost.rent_energy_logistics": ("business_overview", "risk_disclosure"),
    "L4.eff.store_labor": ("business_overview", "revenue_structure"),
    "L4.price.asp_aov_arpu": ("revenue_structure",),
    "L4.price.subscription": ("business_overview", "revenue_structure"),
    "L4.share.market": ("business_overview", "revenue_structure"),
    "L4.volume.orders": ("customer_segment", "revenue_structure"),
    "L4.volume.users": ("customer_segment", "revenue_structure"),
}


def _build_annual_report_block(
    fillable_nodes: list[dict],
    realtime: dict,
) -> list[str]:
    """A1 Phase: when ``L9.disclosure.annual_report`` exists in the snapshot
    AND at least one fillable dp_id maps to AR sections, surface the relevant
    section excerpts so codex can quote them verbatim.

    Returns markdown lines (possibly empty). Lives between the source-value
    table and the preserved list so codex sees AR excerpts as the strongest
    text-evidence channel.
    """

    ar_entry = realtime.get("L9.disclosure.annual_report")
    if not ar_entry:
        return []

    ar_value = ar_entry.get("value") or {}
    sections = ar_value.get("sections") or {}
    if not isinstance(sections, dict) or not sections:
        return []

    # Which dp_ids will actually use AR sections? Only emit those rows.
    relevant: dict[str, set[str]] = {}
    for n in fillable_nodes:
        dp_id = n.get("dp_id") or ""
        wanted = _AR_SECTION_BY_DP_ID.get(dp_id)
        if not wanted:
            continue
        relevant[dp_id] = set(wanted)
    if not relevant:
        return []

    used_sections: set[str] = set()
    for s in relevant.values():
        used_sections.update(s)

    ar_year = ar_value.get("ar_year")
    src = ar_entry.get("source", "")

    parts: list[str] = []
    parts.append(
        f"### 年报章节摘录（{ar_year} 年报）— A1 inline 文本证据"
    )
    parts.append("")
    parts.append(
        f"以下章节来自本地 SQLite dp_id `L9.disclosure.annual_report` (source={src})。"
        "这些章节包含具体客户结构 / 收入构成 / 区域分布 / 业务概览 / 风险因素披露 — "
        "**填充以下 D bucket / 公司画像字段时，必须从对应章节抽取证据**：（详见下表）。"
    )
    parts.append("")
    parts.append("| dp_id | 应引用的年报章节 |")
    parts.append("|---|---|")
    for dp_id in sorted(relevant.keys()):
        section_names = ", ".join(sorted(relevant[dp_id]))
        parts.append(f"| `{dp_id}` | {section_names} |")
    parts.append("")

    # Render each used section's text verbatim
    for sec_name in sorted(used_sections):
        text = (sections.get(sec_name) or "").strip()
        if not text:
            continue
        parts.append(f"#### 章节：`{sec_name}`（{len(text)} 字符）")
        parts.append("")
        parts.append("```")
        parts.append(text)
        parts.append("```")
        parts.append("")

    parts.append(
        "**写入 `evidence_sources` 时**：使用 `kind=local_dp_id`，"
        "`dp_id=L9.disclosure.annual_report`，`source=annual_report:cninfo:*`，"
        "`excerpt` 从上面章节文本里 verbatim 复制对应数字 / 描述。"
        "**不要写 `url` 字段**；closed-loop verifier 会把任何 http(s) 字段当作 web evidence。"
    )
    parts.append("")
    return parts


def _format_source_value_section(
    rows: list[tuple[str, str, str]],
) -> list[str]:
    """Render the inline-source-value table into the prompt's markdown.

    The block sits between the "待填字段" table and the "任务" section so
    codex sees the fillable list, then the verbatim source values it
    must cite from, before reading the task description.

    Empty input ⇒ empty output (no header), so prompts where no fillable
    dp_id has source_dependencies don't get a useless empty section.
    """

    if not rows:
        return []
    parts: list[str] = []
    parts.append(
        "### 上游 source 完整 value 列表（B1 inline — 引用必须从这里抽）"
    )
    parts.append("")
    parts.append(
        "下表列出每个待填 dp_id 在 governance 声明的 source_dependencies，"
        "以及对应字段当前在 SQLite 的完整 value 文本。"
        "**强制规则**：你写 `evidence_sources` 时，"
        "`kind=local_dp_id` 的 `excerpt` 字段必须从对应 source 的 value 文本里"
        " **verbatim 复制语义值片段**（保留数字格式 / 单位）。"
        "不要复制 JSON key 名、外层引号、冒号或 `\\n` 转义符；"
        "多行文本请写成真实换行。禁止 paraphrase，禁止改数字格式。"
    )
    parts.append("")
    parts.append(
        "| dp_id | source_dependency | current SQLite value (verbatim) |"
    )
    parts.append("|---|---|---|")
    for dp_id, dep, value_str in rows:
        # Escape pipes so they don't break the markdown table.
        safe_value = value_str.replace("|", "\\|")
        # Wrap in backticks for monospace rendering; if value contains
        # a backtick the formatting breaks but it's still readable.
        parts.append(f"| `{dp_id}` | `{dep}` | `{safe_value}` |")
    parts.append("")
    return parts


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


def _format_company_verification_boundary(industry_id: str, ts_code: str) -> list[str]:
    """Render self-check limits for company-level LLM subprocesses."""

    overlay_path = f"config/stock_overlays/{industry_id}/{ts_code}.yaml"
    return [
        "**自检边界（节省时间 / 降低噪音）**：",
        "",
        "- 不要运行 `scripts/verify_overlay_closed_loop.py` 的默认全量扫描，也不要对整个行业目录扫描；外层 batch runner 会统一跑全量 verifier、`validate-overlays` 和 pytest。",
        f"- 如需在子流程内自检，只检查当前目标文件 `{overlay_path}`：把它复制到 `/tmp` 下只含这一只股票的临时 `stock_overlays/{industry_id}/` 目录，再用 `--stock-overlays-dir` 指向该临时单文件目录。",
        "- 子流程自检必须保持只读；不要因为历史 soft warning 修改 preserved/排除字段。",
        "",
    ]


def build_industry_prompt(
    industry_id: str,
    *,
    root: Path = ROOT,
    model_tier_filter: str = "all",
    governance: dict | None = None,
    include_source_values: bool = True,
    refresh_baseline_missing: bool = True,
    preserve_unknown_no_local_evidence: bool = False,
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
        refresh_baseline_missing=refresh_baseline_missing,
        preserve_unknown_no_local_evidence=preserve_unknown_no_local_evidence,
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
    parts.append("## 本地上下文（已内联优先，必要时才打开文件）")
    parts.append("")
    parts.append(
        "1. **本 prompt 已内联的 output_schema / source value / 指纹表** — 最高优先级"
    )
    parts.append("2. **`config/industry_overlays/{0}.yaml`** — 该行业 overlay，也是你要编辑的文件".format(industry_id))
    parts.append(
        "3. **`config/industry_graphs/{0}.yaml`** — 该行业的因果图，仅作行业层上下文".format(
            industry_id
        )
    )
    parts.append(
        "4. **`config/llm_field_governance.yaml`** — governance；prompt 已摘取本次相关字段"
    )
    parts.append(
        "不要为了找 schema 再读旧 docs 或历史 overlay 样本；如需打开文件，只打开本任务列出的本地文件。"
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
    parts.extend(_format_schema_block(fillable_l0))
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

    # Fix B (B1): inline upstream SQLite values so codex can quote them
    # verbatim. Industry-level ts_code is the INDUSTRY:<id> sentinel; the
    # L0 deps are stored per-constituent (L5.*/L9.disclosure.*/…) or under
    # MARKET:CN (L9.media.report/L9.industry.*), never under INDUSTRY:<id>.
    # Passing the universe constituents lets _build_source_value_table
    # AGGREGATE per-constituent evidence + fall back to MARKET:CN.
    if include_source_values:
        constituents = _load_industry_constituents(industry_id, root)
        source_rows = _build_source_value_table(
            fillable_l0, governance, industry_ts_code, db_path,
            industry_constituents=constituents,
        )
        parts.extend(_format_source_value_section(source_rows))

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
    include_source_values: bool = True,
    refresh_baseline_missing: bool = True,
    preserve_unknown_no_local_evidence: bool = False,
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
        refresh_baseline_missing=refresh_baseline_missing,
        preserve_unknown_no_local_evidence=preserve_unknown_no_local_evidence,
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
    parts.append("## 本地上下文（已内联优先，必要时才打开文件）")
    parts.append("")
    parts.append("1. **本 prompt 已内联的 output_schema / source value / 年报摘录 / 指纹表** — 最高优先级")
    parts.append(
        f"2. **`config/stock_overlays/{industry_id}/{ts_code}.yaml`** — **你要编辑的文件**"
    )
    parts.append(
        f"3. **`config/industry_overlays/{industry_id}.yaml`** — 行业 overlay L0 上下文"
    )
    parts.append(
        "4. **`config/llm_field_governance.yaml`** — governance；prompt 已摘取本次相关字段"
    )
    parts.append(
        "不要为了找 schema 再读旧 docs 或历史 overlay 样本；如需打开文件，只打开本任务列出的本地文件。"
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
    parts.extend(_format_schema_block(fillable_company))
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

    # Fix B (B1): inline upstream SQLite values so codex can quote them
    # verbatim. Read against the company's ts_code so sentinel fan-out
    # naturally pulls industry/macro deps too (read_hot_snapshot does
    # that via overlay_manifest).
    if include_source_values:
        source_rows = _build_source_value_table(
            fillable_company, governance, ts_code, db_path,
        )
        parts.extend(_format_source_value_section(source_rows))

    # A1 Phase: when L9.disclosure.annual_report exists in realtime,
    # inline the relevant section excerpts for D-bucket / company-portrait
    # fields so codex has real text evidence (not just qa_recent snippets).
    parts.extend(_build_annual_report_block(fillable_company, realtime))

    parts.extend(_format_preserved_section(preserved_company))

    parts.append("## 任务")
    parts.append("")
    parts.append(f"编辑 `config/stock_overlays/{industry_id}/{ts_code}.yaml`：")
    parts.append("")
    parts.append("**操作边界（防 schema drift）**：")
    parts.append("")
    parts.append(
        "- 不要用 `rg` / `grep` 搜索其它 overlay 样本来模仿字段形状；历史 overlay "
        "可能包含旧 schema，本 prompt 下方的 output_schema 才是最高优先级。"
    )
    parts.append(
        "- 除非本 prompt 明确缺证据，不要再阅读 `docs/data_sources/llm_derived_nodes.md` "
        "或旧审计/旧 patch；这里已经内联了本次需要的 schema、source value 和年报摘录。"
    )
    parts.append(
        "- 只生成并应用本次待填 dp_id 的 patch；不要改 preserved/排除字段，也不要顺手修其它股票。"
    )
    parts.append("")
    parts.append(
        "**强制编辑方式**：不要用宽上下文 `apply_patch` 直接改 overlay。"
        "同一文件中很多 node 块字段布局相同，容易误命中相邻 dp_id。"
        "请先生成只含本次待填 dp_id 的 YAML patch（顶层 `nodes:`，每项含 `dp_id`），"
        "再运行 `scripts/apply_yaml_patch.py --strict-schema config/stock_overlays/"
        f"{industry_id}/{ts_code}.yaml <patch-file>` 按 dp_id 合并。"
        "应用后必须用结构 diff 确认只改了本 prompt 列出的 dp_id。"
    )
    parts.append("")
    parts.extend(_format_company_verification_boundary(industry_id, ts_code))
    parts.append(
        "对上面 N 条节点，按本 prompt 已内联的 output_schema 输出 `value` 字段。"
        "判断时要参考："
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
    parts.append(
        "- `evidence_quality` 是顶层字符串枚举，只能写 `low` / `medium` / `high`；"
        "禁止写 0.7、0.55 等数字。`confidence` 才是 0-1 数值。"
    )
    parts.append(
        "- `value.evidence_summary`、`value.notes`、`missing_reason` 等自然语言说明必须使用中文；"
        "不要输出英文句子。枚举值、dp_id、source 名称、`no_local_evidence` 可保持原格式。"
    )
    parts.append(
        "- 自然语言说明不要复述 schema 字段名或枚举 key，例如 `rank`、`share_pct`、`trend`、"
        "`path.tag`、`decline`、`modest_growth`；应改写成中文“排名、份额、趋势、路径标签、下降、温和增长”。"
    )
    parts.append(
        "- `L3.channel.mix` 必须有直接披露的直销/经销/电商/其他渠道占比才可填 "
        "`Known`；如果同一张年报销售模式表披露直销、经销/分销、电商、其他等"
        "可直接映射模式的收入金额和可核对合计，可用金额做确定性占比计算；"
        "工业模式、其他模式等非标准销售模式归入 `others_pct`，内部抵消不当作渠道模式。"
        "如果只有业务线、客户结构、区域或收入结构，而没有这些渠道占比或销售模式金额，"
        "或仅有线上/线下、境内/境外、产品/服务类型结构，"
        "保持 `status/data_status: Unknown`、`missing_reason: no_local_evidence`、"
        "`evidence_sources: []`，并按 schema 写四个占比 `null`。"
    )
    parts.append(
        "- `L1.stock_attr.tags` 可引用 `L6.path.tag` 的文字标签（如估值扩张/估值修复），"
        "但不要把 PE/PB 分位、估值倍数、百分位数字写成 `value.tags`，也不要把这些数字"
        "挂在 `L6.path.tag` evidence excerpt 下。"
    )
    parts.append(
        "- `L1.stock_attr.tags.value.evidence_summary/notes` 也不要写“未把估值倍数/"
        "分位数/百分位写入标签”这类治理提示词；改写为“未使用具体估值数值或相对位置作为标签”。"
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
    refresh_baseline_missing: bool = True,
    preserve_unknown_no_local_evidence: bool = False,
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
        refresh_baseline_missing=refresh_baseline_missing,
        preserve_unknown_no_local_evidence=preserve_unknown_no_local_evidence,
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
    # Fix B (B1): inline source values default ON. Flag exists so the
    # regression test suite can build prompts without DB-dependent
    # value injection.
    parser.add_argument(
        "--include-source-values",
        dest="include_source_values",
        action="store_true",
        default=True,
        help=(
            "Inline the SQLite value of every (fillable dp_id × "
            "source_dependency) pair into the prompt so the LLM can "
            "quote it verbatim. Default ON."
        ),
    )
    parser.add_argument(
        "--no-include-source-values",
        dest="include_source_values",
        action="store_false",
        help=(
            "Disable inline source value injection (regression-test / "
            "legacy path; use only when comparing prompt sizes)."
        ),
    )
    parser.add_argument(
        "--preserve-known-baseline-missing",
        dest="refresh_baseline_missing",
        action="store_false",
        default=True,
        help=(
            "Preserve Known / event-driven Inactive nodes whose only refresh "
            "reason is missing source_fingerprint_at_fill. This avoids "
            "re-prompting legacy LLM content just to establish a fingerprint "
            "baseline; true source_changed refreshes still enter the prompt."
        ),
    )
    parser.add_argument(
        "--preserve-unknown-no-local-evidence",
        action="store_true",
        help=(
            "Preserve Unknown nodes previously filled as "
            "missing_reason=no_local_evidence when their source fingerprint "
            "is unchanged. This prevents repeated LLM calls for already "
            "audited no-evidence cases; true source_changed refreshes still "
            "enter the prompt."
        ),
    )
    args = parser.parse_args()

    if args.list_only:
        prompt = build_list_only_report(
            args.industry,
            args.ts_code,
            model_tier_filter=args.model_tier,
            refresh_baseline_missing=args.refresh_baseline_missing,
            preserve_unknown_no_local_evidence=args.preserve_unknown_no_local_evidence,
        )
    elif args.ts_code:
        prompt = build_company_prompt(
            args.industry,
            args.ts_code,
            model_tier_filter=args.model_tier,
            include_source_values=args.include_source_values,
            refresh_baseline_missing=args.refresh_baseline_missing,
            preserve_unknown_no_local_evidence=args.preserve_unknown_no_local_evidence,
        )
    else:
        prompt = build_industry_prompt(
            args.industry,
            model_tier_filter=args.model_tier,
            include_source_values=args.include_source_values,
            refresh_baseline_missing=args.refresh_baseline_missing,
            preserve_unknown_no_local_evidence=args.preserve_unknown_no_local_evidence,
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
