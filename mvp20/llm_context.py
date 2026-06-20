"""Frozen single-stock decision context and evidence normalization."""

from __future__ import annotations

import math
import re
import time
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Literal, Mapping

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from mvp20 import providers as providers_mod
from mvp20 import signal_5d, signal_up_5d
from mvp20.llm_storage import canonical_json, sha256_payload, short_hash
from mvp20.storage import read_hot_snapshot

SCHEMA_VERSION = "single_stock_decision_context.v1"
DEFAULT_CYCLE_PREFIX = "mvp20-llm"
ASIA_SHANGHAI = timezone(timedelta(hours=8))

SUPPORTED_HORIZONS: dict[str, int] = {
    "5d": 5,
    "10d": 10,
    "30d": 30,
    "3m": 90,
    "6m": 180,
    "180d": 180,
    "1y": 365,
    "2y": 730,
}

PRIMARY_HORIZONS = {"5d", "180d", "1y"}
PROBABILITY_BLOCKED_SOURCES = {
    "train_base_rate_unvalidated",
    "score_pct_logistic_shadow",
}


def _stable_json(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _stable_json(value.model_dump(mode="json", by_alias=True))
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        rounded = round(value, 6)
        return 0.0 if rounded == -0.0 else rounded
    if isinstance(value, Mapping):
        return {str(k): _stable_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_stable_json(v) for v in value]
    return value


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourcePacket(FrozenModel):
    packet_id: str
    kind: str
    source_ref: str
    as_of: str | None = None
    observed_at: str | None = None
    fetched_at: str | None = None
    checksum: str
    available: bool
    stale: bool | None = None
    error: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)


class EvidenceItem(FrozenModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    evidence_ref: str
    kind: str
    source_system: str
    source_ref: str
    snapshot_id: str | None = None
    row_id: str | None = None
    ts_code: str
    origin_ts_code: str | None = Field(default=None, alias="_origin_ts_code")
    as_of: str | None = None
    observed_at: str | None = None
    fetched_at: str | None = None
    extracted_at: str | None = None
    updated_at: str | int | None = None
    age_seconds: int | None = None
    checksum: str
    excerpt: str | None = None
    value_json: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = None
    data_status: str
    freshness_status: Literal["fresh", "stale", "expired", "unknown"]
    verification_status: Literal[
        "verified",
        "review_required",
        "unverified",
        "rejected",
        "unavailable",
    ]
    availability_status: Literal[
        "available",
        "missing",
        "not_applicable",
        "permission_denied",
        "fetch_failed",
    ]
    llm_usable: bool
    use_scope: Literal[
        "primary_signal",
        "supporting_signal",
        "context_only",
        "negative_evidence",
        "blocked",
        "diagnostic_only",
    ]
    block_reason: str | None = None

    @model_validator(mode="after")
    def validate_blocked_evidence(self) -> "EvidenceItem":
        if not self.llm_usable and self.use_scope in {
            "primary_signal",
            "supporting_signal",
            "negative_evidence",
        }:
            raise ValueError("llm_usable=false cannot use signal evidence scope")
        if self.llm_usable and self.block_reason:
            raise ValueError("llm_usable=true cannot carry block_reason")
        return self


class ProbabilityEstimate(FrozenModel):
    evidence_ref: str
    probability: float | None
    target_kind: str
    probability_semantics: str
    horizon_days: int
    base_rate: float | None = None
    model_method: str | None = None
    probability_source: str | None = None
    feature_coverage: float | None = None
    validated: bool
    stale: bool
    asof: str | None = None
    backtest_evidence: dict[str, Any] = Field(default_factory=dict)
    fallback: bool = False
    shadow: bool = False
    use_scope: Literal["primary_signal", "diagnostic_only", "blocked"]
    block_reason: str | None = None

    @model_validator(mode="after")
    def validate_probability(self) -> "ProbabilityEstimate":
        if self.probability is not None:
            if not math.isfinite(self.probability):
                raise ValueError("probability must be finite")
            if self.probability < 0 or self.probability > 1:
                raise ValueError("probability must be in [0,1]")
        if self.use_scope == "primary_signal" and (
            not self.validated or self.stale or self.fallback or self.shadow
        ):
            raise ValueError("primary probability must be fresh validated non-fallback")
        return self


class SingleStockDecisionContext(FrozenModel):
    schema_version: Literal["single_stock_decision_context.v1"]
    context_id: str
    cycle_id: str
    ts_code: str
    name: str | None = None
    market: Literal["A_share"]
    industry_id: str | None = None
    industry_ids: list[str] = Field(default_factory=list)
    as_of: str
    horizon: str
    horizon_days: int
    decision_task: dict[str, Any]
    source_packets: dict[str, SourcePacket]
    normalized_decision_inputs: dict[str, Any]
    model_probabilities: list[ProbabilityEstimate]
    evidence_pack: list[EvidenceItem]
    evidence_counts: dict[str, int] = Field(default_factory=dict)
    unavailable_evidence: list[dict[str, Any]] = Field(default_factory=list)
    contradictions: list[dict[str, Any]] = Field(default_factory=list)
    coverage_and_confidence: dict[str, Any]
    freshness: dict[str, Any]
    backtest_evidence: list[dict[str, Any]] = Field(default_factory=list)
    llm_boundaries: dict[str, Any]
    audit_refs: dict[str, Any]
    input_hash: str

    @model_validator(mode="after")
    def validate_context_hash(self) -> "SingleStockDecisionContext":
        if self.horizon not in SUPPORTED_HORIZONS:
            raise ValueError(f"unsupported horizon: {self.horizon}")
        if self.horizon_days != SUPPORTED_HORIZONS[self.horizon]:
            raise ValueError("horizon_days does not match horizon")
        recomputed = context_input_hash(self.model_dump(mode="json", by_alias=True))
        if self.input_hash != recomputed:
            raise ValueError("input_hash does not match canonical context payload")
        return self


def now_shanghai() -> datetime:
    return datetime.now(ASIA_SHANGHAI).replace(microsecond=0)


def normalize_horizon(raw: str | None) -> str:
    value = (raw or "5d").strip().lower()
    aliases = {"5": "5d", "180": "180d", "365": "1y", "1yr": "1y"}
    value = aliases.get(value, value)
    if value not in SUPPORTED_HORIZONS:
        raise ValueError(
            "horizon must be one of "
            + "|".join(sorted(SUPPORTED_HORIZONS, key=lambda k: SUPPORTED_HORIZONS[k]))
        )
    return value


def market_for_ts_code(ts_code: str) -> str:
    if ts_code.endswith((".SH", ".SZ", ".BJ")):
        return "A_share"
    if ts_code.endswith(".HK"):
        return "HK"
    if ts_code.endswith(".US"):
        return "US"
    return "UNKNOWN"


def normalize_market(raw: str | None, ts_code: str | None = None) -> tuple[str, bool, str | None]:
    inferred = market_for_ts_code(ts_code or "")
    value = (raw or inferred or "A_share").strip()
    if value in {"A", "A_share", "CN"}:
        value = "A_share"
    if inferred in {"HK", "US"} and value == "A_share":
        value = inferred
    if value != "A_share":
        return value, False, "single-stock LLM decision context is currently implemented for A-share only"
    if ts_code and inferred != "A_share":
        return inferred, False, "ts_code is not an A-share instrument"
    return "A_share", True, None


def unsupported_context_payload(
    *,
    ts_code: str,
    market: str,
    horizon: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "status": "unsupported",
        "schema_version": SCHEMA_VERSION,
        "ts_code": ts_code,
        "market": market,
        "horizon": horizon,
        "horizon_days": SUPPORTED_HORIZONS.get(horizon),
        "reason": reason,
        "context": None,
        "llm_boundaries": _llm_boundaries(),
    }


def _freeze_snapshot_ages(snapshot: Mapping[str, Any], now_dt: datetime) -> dict[str, Any]:
    now_ts = int(now_dt.timestamp())
    out: dict[str, Any] = {}
    for key, value in snapshot.items():
        if not isinstance(value, Mapping):
            out[str(key)] = value
            continue
        row = dict(value)
        updated_at = row.get("updated_at")
        if isinstance(updated_at, (int, float)) and updated_at > 0:
            row["age_seconds"] = max(0, now_ts - int(updated_at))
        out[str(key)] = row
    return out


def context_input_hash(payload: Mapping[str, Any]) -> str:
    material = dict(payload)
    material.pop("input_hash", None)
    material.pop("context_id", None)
    return sha256_payload(material)


def finalize_context(payload: dict[str, Any]) -> SingleStockDecisionContext:
    payload = _stable_json(dict(payload))
    payload["input_hash"] = context_input_hash(payload)
    payload["context_id"] = "ctx_" + short_hash(payload)
    payload["input_hash"] = context_input_hash(payload)
    return SingleStockDecisionContext.model_validate(payload)


def _packet(
    *,
    packet_id: str,
    kind: str,
    source_ref: str,
    payload: Mapping[str, Any] | None,
    now_iso: str,
    available: bool = True,
    stale: bool | None = None,
    error: str | None = None,
    as_of: str | None = None,
) -> SourcePacket:
    body = _stable_json(dict(payload or {}))
    return SourcePacket(
        packet_id=packet_id,
        kind=kind,
        source_ref=source_ref,
        as_of=as_of or _extract_as_of(body),
        fetched_at=now_iso,
        checksum=sha256_payload(body),
        available=available,
        stale=stale,
        error=error,
        payload_json=body,
    )


def _excerpt(value: Any, limit: int = 420) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        text = canonical_json(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _extract_as_of(value: Mapping[str, Any]) -> str | None:
    for key in ("as_of", "asof", "trade_date", "ann_date", "end_date", "period", "date"):
        candidate = value.get(key)
        if candidate is not None:
            return str(candidate)
    nested = value.get("value")
    if isinstance(nested, Mapping):
        return _extract_as_of(nested)
    return None


def _status_from_row(data_status: str | None, source: str | None) -> str:
    source_s = str(source or "")
    if source_s.startswith("mock:"):
        return "Mock"
    raw = str(data_status or "Unknown")
    if raw in {"N/A", "NotApplicable", "not_applicable"}:
        return "N/A"
    if raw in {"Known", "Mock", "Proxy", "Unknown", "Inactive", "Optionality"}:
        return raw
    return raw or "Unknown"


def _freshness_status(age_seconds: int | None, *, stale_after_seconds: int) -> str:
    if age_seconds is None:
        return "unknown"
    if age_seconds > stale_after_seconds * 3:
        return "expired"
    if age_seconds > stale_after_seconds:
        return "stale"
    return "fresh"


def normalize_evidence_item(
    *,
    evidence_ref: str,
    kind: str,
    source_system: str,
    source_ref: str,
    ts_code: str,
    value_json: Mapping[str, Any] | None,
    data_status: str | None = "Known",
    confidence: float | None = None,
    age_seconds: int | None = None,
    updated_at: str | int | None = None,
    origin_ts_code: str | None = None,
    as_of: str | None = None,
    row_id: str | None = None,
    stale_after_seconds: int = 26 * 3600,
    verification_status: str | None = None,
    availability_status: str | None = None,
    use_scope: str | None = None,
) -> EvidenceItem:
    payload = _stable_json(dict(value_json or {}))
    status = _status_from_row(data_status, source_ref or source_system)
    freshness = _freshness_status(age_seconds, stale_after_seconds=stale_after_seconds)
    availability = availability_status or (
        "not_applicable" if status == "N/A" else "available"
    )
    verification = verification_status or ("verified" if status == "Known" else "unverified")
    block_reason = None
    usable = True
    scope = use_scope or "supporting_signal"

    if status == "Mock":
        usable = False
        scope = "blocked"
        verification = "rejected"
        block_reason = "mock data cannot enter effective LLM conclusion"
    elif status in {"Unknown", "Proxy"}:
        usable = False
        scope = "diagnostic_only" if status == "Proxy" else "blocked"
        block_reason = f"{status} evidence cannot be used as a decision fact"
    elif status in {"N/A", "Inactive"}:
        usable = False
        scope = "context_only"
        block_reason = f"{status} is neutral availability context, not negative evidence"
    elif freshness != "fresh":
        usable = False
        scope = "diagnostic_only"
        block_reason = f"evidence freshness is {freshness}"
    elif verification != "verified":
        usable = False
        scope = "diagnostic_only"
        block_reason = f"verification_status={verification}"

    return EvidenceItem(
        evidence_ref=evidence_ref,
        kind=kind,
        source_system=source_system,
        source_ref=source_ref,
        row_id=row_id,
        ts_code=ts_code,
        origin_ts_code=origin_ts_code,
        as_of=as_of or _extract_as_of(payload),
        observed_at=as_of or _extract_as_of(payload),
        updated_at=updated_at,
        age_seconds=age_seconds,
        checksum=sha256_payload(payload),
        excerpt=_excerpt(payload),
        value_json=payload,
        confidence=confidence,
        data_status=status,
        freshness_status=freshness,
        verification_status=verification,  # type: ignore[arg-type]
        availability_status=availability,  # type: ignore[arg-type]
        llm_usable=usable,
        use_scope=scope,  # type: ignore[arg-type]
        block_reason=block_reason,
    )


def evidence_counts(evidence: list[EvidenceItem], unavailable: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    counts["total"] = len(evidence)
    counts["usable"] = sum(1 for item in evidence if item.llm_usable)
    counts["missing"] = len(unavailable)
    for item in evidence:
        counts[item.freshness_status] += 1
        counts[item.verification_status] += 1
        counts[item.availability_status] += 1
        if item.data_status == "Mock":
            counts["mock"] += 1
        if item.data_status == "Proxy":
            counts["proxy"] += 1
        if item.data_status == "Unknown":
            counts["unknown"] += 1
        if item.data_status == "N/A":
            counts["not_applicable"] += 1
        if item.data_status == "Inactive":
            counts["inactive"] += 1
        if not item.llm_usable:
            counts["unusable"] += 1
    return dict(counts)


def build_single_stock_context(  # noqa: PLR0913, PLR0915
    *,
    repo_root: Path,
    ts_code: str,
    horizon: str = "5d",
    market: str | None = None,
    industry_id: str | None = None,
    as_of: str | None = None,
    include_raw: bool = False,
    include_unusable: bool = False,
    max_evidence: int | None = None,
    now: datetime | None = None,
) -> SingleStockDecisionContext | dict[str, Any]:
    horizon = normalize_horizon(horizon)
    market_value, supported, reason = normalize_market(market, ts_code)
    if not supported:
        return unsupported_context_payload(
            ts_code=ts_code,
            market=market_value,
            horizon=horizon,
            reason=reason or "unsupported market",
        )

    now_dt = now or now_shanghai()
    now_iso = as_of or now_dt.isoformat()
    config_dir = repo_root / "config"
    runtime_dir = repo_root / "runtime"
    hot_db_path = runtime_dir / "hot.sqlite"
    universe = _load_yaml(config_dir / "mvp20.universe.yaml")
    profile = _profile_for(universe, ts_code)
    industry_ids = list(profile.get("industry_ids") or [])
    selected_industry = industry_id or (industry_ids[0] if industry_ids else None)
    overlay = _load_overlay(config_dir, ts_code, selected_industry)
    industry_overlay = _load_industry_overlay(config_dir, selected_industry)
    realtime = (
        _freeze_snapshot_ages(read_hot_snapshot(hot_db_path, ts_code), now_dt)
        if hot_db_path.exists()
        else {}
    )

    packets: dict[str, SourcePacket] = {}
    unavailable: list[dict[str, Any]] = []
    evidence: list[EvidenceItem] = []

    score_payload, aggregate_payload, coverage_payload = _derived_score_packets(
        overlay=overlay,
        industry_overlay=industry_overlay,
        realtime=realtime,
        ts_code=ts_code,
        industry_id=selected_industry,
    )
    packets["score"] = _packet(
        packet_id="score",
        kind="score",
        source_ref="mvp20.scoring.score_company",
        payload=_trim_packet(score_payload, include_raw=include_raw),
        now_iso=now_iso,
        available=bool(score_payload),
        stale=bool((score_payload.get("freshness") or {}).get("stale")) if score_payload else None,
    )
    packets["aggregate"] = _packet(
        packet_id="aggregate",
        kind="aggregate",
        source_ref="mvp20.aggregator.aggregate_company_graph",
        payload=_trim_packet(aggregate_payload, include_raw=include_raw),
        now_iso=now_iso,
        available=bool(aggregate_payload),
    )
    packets["coverage"] = _packet(
        packet_id="coverage",
        kind="coverage",
        source_ref="mvp20.coverage.combined_coverage_summary",
        payload=_trim_packet(coverage_payload, include_raw=include_raw),
        now_iso=now_iso,
        available=bool(coverage_payload),
    )
    if not overlay:
        unavailable.append(_unavailable("stock_overlay", "missing", "stock overlay not found"))
    packets["stock_overlay"] = _packet(
        packet_id="stock_overlay",
        kind="stock_overlay",
        source_ref=f"config/stock_overlays/{selected_industry or '*'}/{ts_code}.yaml",
        payload=_stock_overlay_packet(overlay, industry_overlay, realtime, include_raw=include_raw),
        now_iso=now_iso,
        available=bool(overlay),
    )

    signal5 = signal_5d.lookup(ts_code)
    signal_up = signal_up_5d.lookup(ts_code)
    packets["signal_5d"] = _packet(
        packet_id="signal_5d",
        kind="signal_5d",
        source_ref="runtime/signal_5d/A_share.json",
        payload=signal5,
        now_iso=now_iso,
        available=bool(signal5.get("available")),
        stale=bool(signal5.get("stale")),
        as_of=signal5.get("asof"),
    )
    packets["signal_up_5d"] = _packet(
        packet_id="signal_up_5d",
        kind="signal_up_5d",
        source_ref="runtime/signal_up_5d/A_share.json",
        payload=signal_up,
        now_iso=now_iso,
        available=bool(signal_up.get("available")),
        stale=bool(signal_up.get("stale")),
        as_of=signal_up.get("asof"),
    )

    technicals_packet, technical_evidence = _technicals_packet(realtime, ts_code, now_iso)
    packets["technicals"] = technicals_packet
    evidence.extend(technical_evidence)
    market_packet, market_evidence = _market_events_packet(realtime, ts_code, now_iso)
    packets["market_events"] = market_packet
    evidence.extend(market_evidence)
    annual_packet, annual_evidence = _annual_report_packet(repo_root, realtime, ts_code, now_iso)
    packets["annual_report_summary"] = annual_packet
    evidence.extend(annual_evidence)
    ranking_payload = _ranking_packet(repo_root, ts_code)
    packets["ranking"] = _packet(
        packet_id="ranking",
        kind="ranking",
        source_ref="runtime/backtest/pnl.sqlite + runtime/quant_score/A_share.json",
        payload=ranking_payload,
        now_iso=now_iso,
        available=bool(ranking_payload.get("available")),
        stale=bool(ranking_payload.get("stale")) if "stale" in ranking_payload else None,
    )
    provider_payload = _provider_packet(config_dir)
    packets["provider_capabilities"] = _packet(
        packet_id="provider_capabilities",
        kind="provider_capabilities",
        source_ref="config/data_providers.yaml",
        payload=provider_payload,
        now_iso=now_iso,
        available=bool(provider_payload.get("available")),
    )

    evidence.append(_score_evidence(score_payload, ts_code))
    evidence.append(_coverage_evidence(coverage_payload, ts_code))
    signal_evidence, probabilities = _probability_evidence(signal5, signal_up, ts_code, horizon)
    evidence.extend(signal_evidence)
    evidence.extend(_hot_row_evidence(realtime, ts_code, include_unusable=include_unusable))

    unavailable.extend(_unavailable_from_packets(packets))
    if horizon not in {"5d"}:
        unavailable.append(_unavailable(
            f"validated_probability_{horizon}",
            "missing",
            f"no validated {horizon} stock-specific probability model is available",
        ))

    evidence = _dedupe_evidence(evidence)
    if not include_unusable:
        protected = {p.evidence_ref for p in signal_evidence}
        evidence = [
            item for item in evidence
            if item.llm_usable or item.evidence_ref in protected
        ]
    if max_evidence is not None and max_evidence > 0:
        protected = {p.evidence_ref for p in probabilities}
        kept = [item for item in evidence if item.evidence_ref in protected]
        room = max(0, max_evidence - len(kept))
        kept_refs = {item.evidence_ref for item in kept}
        kept.extend(
            [item for item in evidence if item.evidence_ref not in kept_refs][:room]
        )
        evidence = _dedupe_evidence(kept)

    normalized_inputs = _normalized_inputs(score_payload, horizon)
    counts = evidence_counts(evidence, unavailable)
    coverage_confidence = _coverage_confidence(coverage_payload, evidence, unavailable)
    freshness = _freshness_summary(evidence, packets)
    contradictions = _contradictions(normalized_inputs, probabilities, evidence)

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "context_id": "pending",
        "cycle_id": f"{DEFAULT_CYCLE_PREFIX}-{now_dt.strftime('%Y%m%d')}",
        "ts_code": ts_code,
        "name": profile.get("name") or ts_code,
        "market": "A_share",
        "industry_id": selected_industry,
        "industry_ids": industry_ids,
        "as_of": now_iso,
        "horizon": horizon,
        "horizon_days": SUPPORTED_HORIZONS[horizon],
        "decision_task": _decision_task(horizon),
        "source_packets": packets,
        "normalized_decision_inputs": normalized_inputs,
        "model_probabilities": probabilities,
        "evidence_pack": evidence,
        "evidence_counts": counts,
        "unavailable_evidence": unavailable,
        "contradictions": contradictions,
        "coverage_and_confidence": {
            **coverage_confidence,
            "evidence_counts": counts,
        },
        "freshness": freshness,
        "backtest_evidence": _backtest_evidence(signal5, signal_up, ranking_payload),
        "llm_boundaries": _llm_boundaries(),
        "audit_refs": {
            "runtime_context_path_pattern": (
                "runtime/llm_contexts/{market}/{ts_code}/{horizon}/{context_id}.json"
            ),
            "source_docs": [
                "docs/llm_stock_decision_architecture.md",
                "docs/llm_evidence_contract.md",
            ],
        },
        "input_hash": "pending",
    }
    return finalize_context(payload)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _profile_for(universe: Mapping[str, Any], ts_code: str) -> dict[str, Any]:
    for row in universe.get("constituents") or []:
        if isinstance(row, Mapping) and row.get("ts_code") == ts_code:
            return dict(row)
    return {"ts_code": ts_code, "name": ts_code, "industry_ids": []}


def _load_overlay(config_dir: Path, ts_code: str, industry_id: str | None) -> dict[str, Any]:
    paths: list[Path] = []
    if industry_id:
        paths.append(config_dir / "stock_overlays" / industry_id / f"{ts_code}.yaml")
    paths.extend(sorted((config_dir / "stock_overlays").glob(f"*/{ts_code}.yaml")))
    for path in paths:
        if path.exists():
            return _load_yaml(path)
    return {}


def _load_industry_overlay(config_dir: Path, industry_id: str | None) -> dict[str, Any]:
    if not industry_id:
        return {}
    return _load_yaml(config_dir / "industry_overlays" / f"{industry_id}.yaml")


def _derived_score_packets(
    *,
    overlay: Mapping[str, Any],
    industry_overlay: Mapping[str, Any],
    realtime: Mapping[str, Any],
    ts_code: str,
    industry_id: str | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if not overlay:
        return {}, {}, {}
    try:
        from mvp20.aggregator import aggregate_company_graph
        aggregate = aggregate_company_graph(
            overlay,
            industry_overlay or None,
            realtime_snapshot=realtime or None,
        ) or {}
    except Exception as exc:  # noqa: BLE001
        aggregate = {"available": False, "error": str(exc)}
    try:
        from mvp20.coverage import combined_coverage_summary, coverage_summary_for_overlay
        coverage = combined_coverage_summary(overlay, ts_code=ts_code) or {}
        coverage_for_score = coverage_summary_for_overlay(overlay) or {}
    except Exception as exc:  # noqa: BLE001
        coverage = {"available": False, "error": str(exc)}
        coverage_for_score = {}
    try:
        from mvp20.scoring import score_company
        score = score_company(
            stock_overlay=overlay,
            aggregated_nodes=aggregate,
            coverage_report=coverage_for_score,
            realtime_data=realtime,
        ) or {}
    except Exception as exc:  # noqa: BLE001
        score = {"available": False, "error": str(exc)}
    final_score = score.get("final_score") if isinstance(score, Mapping) else None
    score_payload = {
        "ts_code": score.get("ts_code") or ts_code,
        "industry_id": score.get("industry_id") or industry_id,
        "mode": score.get("mode_display") or score.get("mode"),
        "mode_code": score.get("mode"),
        "mode_confidence": score.get("mode_confidence"),
        "mode_rationale": score.get("mode_rationale"),
        "primary_drivers": score.get("mode_drivers") or [],
        "short_total": score.get("short_total"),
        "medium_total": score.get("medium_total"),
        "long_total": score.get("long_total"),
        "trading_signal": score.get("trading_signal"),
        "trading_signal_v2": score.get("trading_signal_v2"),
        "merit": score.get("merit"),
        "timing": score.get("timing"),
        "company_score": score.get("company_score") or {},
        "final_score": final_score or {},
        "top_paths": score.get("top_paths") or {"positive": [], "negative": []},
        "signals": score.get("signals") or {},
    }
    return score_payload, {"nodes": aggregate, "node_count": len(aggregate)}, coverage


def _trim_packet(payload: Mapping[str, Any], *, include_raw: bool) -> dict[str, Any]:
    if include_raw:
        return dict(payload)
    out = dict(payload)
    if "nodes" in out and isinstance(out["nodes"], Mapping):
        nodes = out["nodes"]
        out["node_count"] = len(nodes)
        out["nodes_sample"] = list(nodes.items())[:20]
        out.pop("nodes", None)
    if "per_node" in out and isinstance(out["per_node"], list):
        out["per_node_count"] = len(out["per_node"])
        out["per_node_sample"] = out["per_node"][:20]
        out.pop("per_node", None)
    return out


def _stock_overlay_packet(
    overlay: Mapping[str, Any],
    industry_overlay: Mapping[str, Any],
    realtime: Mapping[str, Any],
    *,
    include_raw: bool,
) -> dict[str, Any]:
    payload = {
        "available": bool(overlay),
        "industry_id": overlay.get("industry_id"),
        "primary_industry": overlay.get("primary_industry"),
        "node_count": len(overlay.get("nodes") or []),
        "causal_edge_count": len(overlay.get("causal_edges") or []),
        "industry_context_available": bool(industry_overlay),
        "realtime_node_count": len(realtime),
    }
    if include_raw:
        payload["overlay"] = dict(overlay)
        payload["industry_overlay"] = dict(industry_overlay)
    return payload


def _technicals_packet(
    realtime: Mapping[str, Any],
    ts_code: str,
    now_iso: str,
) -> tuple[SourcePacket, list[EvidenceItem]]:
    technicals = {}
    evidence: list[EvidenceItem] = []
    for dp_id, row in realtime.items():
        if not str(dp_id).startswith("L11.tech."):
            continue
        value = row.get("value") if isinstance(row, Mapping) else None
        technicals[str(dp_id)] = value
        evidence.append(normalize_evidence_item(
            evidence_ref=f"ev_hot_{_safe_ref(ts_code)}_{_safe_ref(str(dp_id))}",
            kind="technical",
            source_system="hot.sqlite:realtime_current",
            source_ref=str(row.get("source") or "unknown"),
            ts_code=ts_code,
            value_json={"dp_id": dp_id, "value": value},
            data_status=row.get("data_status"),
            confidence=row.get("confidence"),
            age_seconds=row.get("age_seconds"),
            updated_at=row.get("updated_at"),
            origin_ts_code=row.get("_origin_ts_code"),
            row_id=f"{row.get('_origin_ts_code') or ts_code}:{dp_id}",
            stale_after_seconds=26 * 3600,
            use_scope="supporting_signal",
        ))
    packet = _packet(
        packet_id="technicals",
        kind="technicals",
        source_ref="hot.sqlite:L11.tech.*",
        payload={"available": bool(technicals), "indicators": technicals},
        now_iso=now_iso,
        available=bool(technicals),
        stale=any(item.freshness_status != "fresh" for item in evidence) if evidence else None,
    )
    return packet, evidence


def _market_events_packet(
    realtime: Mapping[str, Any],
    ts_code: str,
    now_iso: str,
) -> tuple[SourcePacket, list[EvidenceItem]]:
    event_dp_ids = {
        "L9.media.report",
        "L9.event.intraday_news",
        "L9.company.earnings_guidance",
    }
    events: dict[str, Any] = {}
    evidence: list[EvidenceItem] = []
    for dp_id, row in realtime.items():
        if dp_id not in event_dp_ids:
            continue
        value = row.get("value") if isinstance(row, Mapping) else None
        events[str(dp_id)] = value
        verification = (
            "verified"
            if dp_id == "L9.company.earnings_guidance"
            else "review_required"
        )
        evidence.append(normalize_evidence_item(
            evidence_ref=f"ev_event_{_safe_ref(ts_code)}_{_safe_ref(str(dp_id))}",
            kind="event",
            source_system="hot.sqlite:realtime_current",
            source_ref=str(row.get("source") or "unknown"),
            ts_code=ts_code,
            value_json={"dp_id": dp_id, "value": value},
            data_status=row.get("data_status"),
            confidence=row.get("confidence"),
            age_seconds=row.get("age_seconds"),
            updated_at=row.get("updated_at"),
            origin_ts_code=row.get("_origin_ts_code"),
            row_id=f"{row.get('_origin_ts_code') or ts_code}:{dp_id}",
            verification_status=verification,
            stale_after_seconds=7 * 86400,
            use_scope="supporting_signal",
        ))
    packet = _packet(
        packet_id="market_events",
        kind="market_events",
        source_ref="hot.sqlite:L9.media/event/guidance",
        payload={"available": bool(events), "events": events},
        now_iso=now_iso,
        available=bool(events),
        stale=any(item.freshness_status != "fresh" for item in evidence) if evidence else None,
    )
    return packet, evidence


def _annual_report_packet(
    repo_root: Path,
    realtime: Mapping[str, Any],
    ts_code: str,
    now_iso: str,
) -> tuple[SourcePacket, list[EvidenceItem]]:
    row = realtime.get("L9.disclosure.annual_report")
    payload = row.get("value") if isinstance(row, Mapping) else None
    if not isinstance(payload, Mapping):
        txts = sorted((repo_root / "runtime" / "annual_reports" / ts_code).glob("*.txt"))
        if txts:
            text = txts[-1].read_text(encoding="utf-8", errors="ignore")
            payload = {
                "local_text_path": str(txts[-1].relative_to(repo_root)),
                "excerpt": text[:1800],
                "total_text_chars": len(text),
            }
    evidence: list[EvidenceItem] = []
    if isinstance(payload, Mapping):
        sections = payload.get("sections")
        excerpt_value = sections if isinstance(sections, Mapping) else payload
        evidence.append(normalize_evidence_item(
            evidence_ref=f"ev_annual_report_{_safe_ref(ts_code)}",
            kind="annual_report_summary",
            source_system="annual_report:cninfo",
            source_ref=str(payload.get("ar_url") or payload.get("local_text_path") or "runtime/annual_reports"),
            ts_code=ts_code,
            value_json=dict(payload),
            data_status=row.get("data_status") if isinstance(row, Mapping) else "Known",
            confidence=row.get("confidence") if isinstance(row, Mapping) else 0.7,
            age_seconds=row.get("age_seconds") if isinstance(row, Mapping) else None,
            updated_at=row.get("updated_at") if isinstance(row, Mapping) else None,
            origin_ts_code=row.get("_origin_ts_code") if isinstance(row, Mapping) else ts_code,
            row_id=f"{ts_code}:L9.disclosure.annual_report",
            stale_after_seconds=540 * 86400,
            verification_status="verified",
            use_scope="supporting_signal",
        ))
        packet_payload = dict(payload)
        if isinstance(excerpt_value, Mapping):
            packet_payload["section_keys"] = list(excerpt_value.keys())[:20]
            packet_payload["sections"] = {
                k: _excerpt(v, 600)
                for k, v in list(excerpt_value.items())[:6]
            }
    else:
        packet_payload = {"available": False}
    packet = _packet(
        packet_id="annual_report_summary",
        kind="annual_report_summary",
        source_ref="runtime/annual_reports + hot.sqlite:L9.disclosure.annual_report",
        payload=packet_payload,
        now_iso=now_iso,
        available=bool(evidence),
        stale=False if evidence else None,
    )
    return packet, evidence


def _ranking_packet(repo_root: Path, ts_code: str) -> dict[str, Any]:
    try:
        from mvp20 import pnl_loop, quant_score
        base_date, snap = pnl_loop.latest_snapshot()
        artifact = quant_score.load_artifact()
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": str(exc)}
    score_row = (snap or {}).get(ts_code)
    quant_row = ((artifact or {}).get("rows") or {}).get(ts_code)
    return {
        "available": bool(score_row or quant_row),
        "asof_snapshot": base_date,
        "asof_quant": (artifact or {}).get("asof"),
        "score_snapshot": score_row,
        "quant_row": quant_row,
        "stale": True,
        "note": "ranking and quant artifacts are cross-sectional context, not absolute probabilities",
    }


def _provider_packet(config_dir: Path) -> dict[str, Any]:
    path = config_dir / "data_providers.yaml"
    if not path.exists():
        return {"available": False, "reason": "config/data_providers.yaml missing"}
    payload = _load_yaml(path)
    try:
        validation = providers_mod.validate_provider_catalog(
            path,
            required_markets={"A", "HK", "US"},
        )
        validation_payload = {
            "ok": validation.ok,
            "active_providers": list(validation.active_providers),
            "market_coverage": validation.market_coverage,
            "capability_coverage": validation.capability_coverage,
            "warnings": list(validation.warnings),
            "errors": list(validation.errors),
        }
    except Exception as exc:  # noqa: BLE001
        validation_payload = {"ok": False, "errors": [str(exc)]}
    return {
        "available": True,
        "catalog": payload,
        "validation": validation_payload,
        "use_scope": "context_only",
        "note": "provider catalog is capability metadata, not decision evidence",
    }


def _score_evidence(score_payload: Mapping[str, Any], ts_code: str) -> EvidenceItem:
    stale = bool((score_payload.get("freshness") or {}).get("stale"))
    return normalize_evidence_item(
        evidence_ref=f"ev_score_{_safe_ref(ts_code)}",
        kind="score_summary",
        source_system="mvp20.scoring",
        source_ref="mvp20.scoring.score_company",
        ts_code=ts_code,
        value_json=dict(score_payload or {}),
        data_status="Known" if score_payload else "Unknown",
        confidence=score_payload.get("mode_confidence") if isinstance(score_payload, Mapping) else None,
        age_seconds=(27 * 3600 if stale else 0),
        row_id=f"{ts_code}:score",
        stale_after_seconds=26 * 3600,
        verification_status="verified" if score_payload else "unavailable",
        use_scope="supporting_signal",
    )


def _coverage_evidence(coverage_payload: Mapping[str, Any], ts_code: str) -> EvidenceItem:
    return normalize_evidence_item(
        evidence_ref=f"ev_coverage_{_safe_ref(ts_code)}",
        kind="coverage_summary",
        source_system="mvp20.coverage",
        source_ref="mvp20.coverage.combined_coverage_summary",
        ts_code=ts_code,
        value_json=dict(coverage_payload or {}),
        data_status="Known" if coverage_payload else "Unknown",
        confidence=None,
        age_seconds=0 if coverage_payload else None,
        row_id=f"{ts_code}:coverage",
        stale_after_seconds=30 * 86400,
        verification_status="verified" if coverage_payload else "unavailable",
        use_scope="context_only",
    )


def _probability_evidence(
    signal5: Mapping[str, Any],
    signal_up: Mapping[str, Any],
    ts_code: str,
    horizon: str,
) -> tuple[list[EvidenceItem], list[ProbabilityEstimate]]:
    evidence: list[EvidenceItem] = []
    probs: list[ProbabilityEstimate] = []
    if signal5:
        ev_ref = f"ev_signal_5d_{_safe_ref(ts_code)}"
        stale = bool(signal5.get("stale"))
        validated = bool(signal5.get("validated"))
        block_reason = _probability_block_reason(signal5, requires_absolute=False)
        use_scope = "primary_signal" if not block_reason and horizon == "5d" else "diagnostic_only"
        evidence.append(normalize_evidence_item(
            evidence_ref=ev_ref,
            kind="probability_signal",
            source_system="mvp20.signal_5d",
            source_ref=str(signal5.get("source_artifact") or "runtime/signal_5d/A_share.json"),
            ts_code=ts_code,
            value_json=dict(signal5),
            data_status="Known" if signal5.get("available") else "Unknown",
            confidence=signal5.get("feature_coverage"),
            age_seconds=11 * 86400 if stale else 0,
            as_of=signal5.get("asof"),
            row_id=f"{ts_code}:signal_5d",
            stale_after_seconds=10 * 86400,
            verification_status="verified" if validated and not stale else "review_required",
            use_scope=use_scope,
        ))
        probs.append(ProbabilityEstimate(
            evidence_ref=ev_ref,
            probability=signal5.get("probability"),
            target_kind=str(signal5.get("target_kind") or "relative_cross_section_median"),
            probability_semantics=str(
                signal5.get("probability_semantics")
                or "P(5d return beats same-day liquid-universe median); not absolute P(up)"
            ),
            horizon_days=int(signal5.get("horizon_days") or 5),
            base_rate=signal5.get("base_rate"),
            model_method=signal5.get("model_method"),
            probability_source=signal5.get("probability_source"),
            feature_coverage=signal5.get("feature_coverage"),
            validated=validated,
            stale=stale,
            asof=signal5.get("asof"),
            backtest_evidence={
                "params_version": signal5.get("params_version"),
                "params_built_at": signal5.get("params_built_at"),
            },
            fallback=str(signal5.get("probability_source") or "").endswith("bin10"),
            shadow=signal5.get("model_probability_shadow") is not None,
            use_scope=use_scope,
            block_reason=block_reason,
        ))
    if signal_up:
        ev_ref = f"ev_signal_up_5d_{_safe_ref(ts_code)}"
        stale = bool(signal_up.get("stale"))
        validated = bool(signal_up.get("validated"))
        block_reason = _probability_block_reason(signal_up, requires_absolute=True)
        use_scope = "primary_signal" if not block_reason and horizon == "5d" else "diagnostic_only"
        evidence.append(normalize_evidence_item(
            evidence_ref=ev_ref,
            kind="probability_signal",
            source_system="mvp20.signal_up_5d",
            source_ref=str(signal_up.get("source_artifact") or "runtime/signal_up_5d/A_share.json"),
            ts_code=ts_code,
            value_json=dict(signal_up),
            data_status="Known" if signal_up.get("available") else "Unknown",
            confidence=signal_up.get("feature_coverage"),
            age_seconds=11 * 86400 if stale else 0,
            as_of=signal_up.get("asof"),
            row_id=f"{ts_code}:signal_up_5d",
            stale_after_seconds=10 * 86400,
            verification_status="verified" if validated and not stale else "review_required",
            use_scope=use_scope,
        ))
        probs.append(ProbabilityEstimate(
            evidence_ref=ev_ref,
            probability=signal_up.get("probability"),
            target_kind=str(signal_up.get("target_kind") or "absolute_up_5d"),
            probability_semantics=str(
                signal_up.get("probability_semantics")
                or signal_up_5d.PROBABILITY_SEMANTICS
            ),
            horizon_days=int(signal_up.get("horizon_days") or 5),
            base_rate=signal_up.get("base_rate"),
            model_method=signal_up.get("model_method"),
            probability_source=signal_up.get("probability_source"),
            feature_coverage=signal_up.get("feature_coverage"),
            validated=validated,
            stale=stale,
            asof=signal_up.get("asof"),
            backtest_evidence={
                "params_version": signal_up.get("params_version"),
                "params_built_at": signal_up.get("params_built_at"),
            },
            fallback=str(signal_up.get("probability_source") or "") in PROBABILITY_BLOCKED_SOURCES
            or "fallback" in str(signal_up.get("probability_source") or ""),
            shadow=signal_up.get("model_probability_shadow") is not None,
            use_scope=use_scope,
            block_reason=block_reason,
        ))
    return evidence, probs


def _probability_block_reason(block: Mapping[str, Any], *, requires_absolute: bool) -> str | None:
    if not block.get("available"):
        return str(block.get("reason") or "probability unavailable")
    if block.get("stale"):
        return "probability artifact is stale"
    if not block.get("validated"):
        return "probability is not validated"
    source = str(block.get("probability_source") or "")
    if "fallback" in source or source in PROBABILITY_BLOCKED_SOURCES:
        return f"probability_source={source} is fallback/shadow"
    semantics = str(block.get("probability_semantics") or "")
    if requires_absolute and "return > 0" not in semantics:
        return "absolute probability semantics missing"
    if not requires_absolute and "not absolute" not in semantics:
        return "relative signal must explicitly state not absolute P(up)"
    return None


def _hot_row_evidence(
    realtime: Mapping[str, Any],
    ts_code: str,
    *,
    include_unusable: bool,
) -> list[EvidenceItem]:
    preferred_prefixes = (
        "L5.",
        "L6.",
        "L7.",
        "L8.",
        "L9.",
        "L10.",
        "L11.short",
        "L11.medium",
        "L11.long",
    )
    rows: list[EvidenceItem] = []
    for dp_id, row in sorted(realtime.items()):
        if str(dp_id).startswith("L11.tech."):
            continue
        if dp_id in {
            "L9.media.report",
            "L9.event.intraday_news",
            "L9.company.earnings_guidance",
            "L9.disclosure.annual_report",
        }:
            continue
        if not include_unusable and not str(dp_id).startswith(preferred_prefixes):
            continue
        if not isinstance(row, Mapping):
            continue
        value = row.get("value")
        item = normalize_evidence_item(
            evidence_ref=f"ev_hot_{_safe_ref(ts_code)}_{_safe_ref(str(dp_id))}",
            kind="hot_realtime",
            source_system="hot.sqlite:realtime_current",
            source_ref=str(row.get("source") or "unknown"),
            ts_code=ts_code,
            value_json={"dp_id": dp_id, "value": value},
            data_status=row.get("data_status"),
            confidence=row.get("confidence"),
            age_seconds=row.get("age_seconds"),
            updated_at=row.get("updated_at"),
            origin_ts_code=row.get("_origin_ts_code"),
            row_id=f"{row.get('_origin_ts_code') or ts_code}:{dp_id}",
            stale_after_seconds=_stale_window_for_dp(str(dp_id)),
            use_scope="supporting_signal",
        )
        rows.append(item)
    rows.sort(key=lambda item: (
        0 if item.llm_usable else 1,
        item.age_seconds if item.age_seconds is not None else 10**12,
        item.evidence_ref,
    ))
    return rows


def _stale_window_for_dp(dp_id: str) -> int:
    if dp_id.startswith("L11.") or dp_id.startswith("L7.trade"):
        return 26 * 3600
    if dp_id.startswith("L9."):
        return 14 * 86400
    if dp_id.startswith("L5.") or dp_id.startswith("L8.gov"):
        return 540 * 86400
    return 120 * 86400


def _dedupe_evidence(items: list[EvidenceItem]) -> list[EvidenceItem]:
    out: dict[str, EvidenceItem] = {}
    for item in items:
        out.setdefault(item.evidence_ref, item)
    return [out[key] for key in sorted(out)]


def _normalized_inputs(score: Mapping[str, Any], horizon: str) -> dict[str, Any]:
    final_score = score.get("final_score") or {}
    return {
        "final_score": final_score,
        "company_score": score.get("company_score") or {},
        "short_total": score.get("short_total"),
        "medium_total": score.get("medium_total"),
        "long_total": score.get("long_total"),
        "merit": score.get("merit"),
        "timing": score.get("timing"),
        "mode": score.get("mode"),
        "mode_confidence": score.get("mode_confidence"),
        "trading_signal": score.get("trading_signal"),
        "trading_signal_v2": score.get("trading_signal_v2"),
        "top_paths": score.get("top_paths") or {"positive": [], "negative": []},
        "primary_drivers": score.get("primary_drivers") or [],
        "positive_evidence": (score.get("top_paths") or {}).get("positive") or [],
        "negative_evidence": (score.get("top_paths") or {}).get("negative") or [],
        "risks": (score.get("top_paths") or {}).get("negative") or [],
        "contradictions": [],
        "horizon_focus": _decision_task(horizon)["focus"],
        "probability_boundary": (
            "final_score, base_score, trading signals, grades, direction, RSI, "
            "MACD, and industry heat are not probabilities"
        ),
    }


def _coverage_confidence(
    coverage: Mapping[str, Any],
    evidence: list[EvidenceItem],
    unavailable: list[dict[str, Any]],
) -> dict[str, Any]:
    overall = coverage.get("overall") if isinstance(coverage.get("overall"), Mapping) else {}
    cov = (
        overall.get("combined_coverage_pct")
        or overall.get("data_coverage")
        or coverage.get("overall_data_coverage")
        or 0.0
    )
    try:
        cov_f = float(cov)
        if cov_f > 1:
            cov_f = cov_f / 100.0
    except (TypeError, ValueError):
        cov_f = 0.0
    usable = [item.confidence for item in evidence if item.llm_usable and item.confidence is not None]
    return {
        "coverage": round(cov_f, 4),
        "usable_evidence_ratio": round(
            sum(1 for item in evidence if item.llm_usable) / max(len(evidence), 1),
            4,
        ),
        "mean_usable_confidence": round(sum(usable) / len(usable), 4) if usable else None,
        "unavailable_count": len(unavailable),
        "confidence_caps": {
            "coverage_lt_0_3": 0.3,
            "coverage_lt_0_5": 0.55,
            "stale_primary_signal": 0.45,
        },
    }


def _freshness_summary(
    evidence: list[EvidenceItem],
    packets: Mapping[str, SourcePacket],
) -> dict[str, Any]:
    counts = Counter(item.freshness_status for item in evidence)
    ages = [item.age_seconds for item in evidence if item.age_seconds is not None]
    return {
        "counts": dict(counts),
        "max_age_seconds": max(ages) if ages else None,
        "primary_packets_stale": [
            key for key, packet in packets.items() if packet.stale is True
        ],
        "stale_primary_signal": any(
            packets.get(key) and packets[key].stale is True
            for key in ("signal_5d", "signal_up_5d")
        ),
    }


def _contradictions(
    normalized_inputs: Mapping[str, Any],
    probabilities: list[ProbabilityEstimate],
    evidence: list[EvidenceItem],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    trading_signal = normalized_inputs.get("trading_signal")
    if trading_signal in {"BUY", "AVOID"} and any(p.stale for p in probabilities):
        rows.append({
            "kind": "signal_freshness_vs_score",
            "summary": "headline score exists but primary 5d probability artifacts are stale/unvalidated",
            "severity": "medium",
        })
    if not any(item.llm_usable for item in evidence):
        rows.append({
            "kind": "no_usable_evidence",
            "summary": "no fresh verified evidence is usable by the LLM",
            "severity": "high",
        })
    return rows


def _backtest_evidence(
    signal5: Mapping[str, Any],
    signal_up: Mapping[str, Any],
    ranking: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows = []
    for name, block in (("signal_5d", signal5), ("signal_up_5d", signal_up)):
        if not block:
            continue
        rows.append({
            "source": name,
            "params_version": block.get("params_version"),
            "params_built_at": block.get("params_built_at"),
            "validated": block.get("validated"),
            "stale": block.get("stale"),
            "probability_source": block.get("probability_source"),
            "reason": block.get("reason"),
        })
    if ranking:
        rows.append({
            "source": "ranking",
            "available": ranking.get("available"),
            "asof_snapshot": ranking.get("asof_snapshot"),
            "asof_quant": ranking.get("asof_quant"),
            "stale": ranking.get("stale"),
        })
    return rows


def _decision_task(horizon: str) -> dict[str, Any]:
    focus_map = {
        "5d": [
            "relative 5d signal semantics",
            "absolute up-5d only if validated",
            "technicals",
            "market regime",
            "events/news",
            "flows/sentiment",
            "short_total",
            "timing",
            "freshness",
        ],
        "180d": [
            "medium_total",
            "fundamental score",
            "earnings trend",
            "valuation",
            "expectation gap",
            "industry cycle",
            "policy/supply/demand",
            "financial reports",
            "coverage",
        ],
        "1y": [
            "long_total",
            "moat",
            "industry structure",
            "growth runway",
            "governance",
            "capital allocation",
            "valuation rerating",
            "structural risks",
            "long-cycle industry graph",
        ],
    }
    focus = focus_map.get(horizon, focus_map["180d"])
    return {
        "task": "single_stock_llm_decision",
        "horizon": horizon,
        "focus": focus,
        "output_actions": ["buy", "hold", "reduce", "inconclusive"],
        "unknown_policy": "unknown must produce inconclusive, never hold",
    }


def _llm_boundaries() -> dict[str, Any]:
    return {
        "closed_loop": True,
        "input_contract": "LLM may only read SingleStockDecisionContext",
        "external_provider_calls_allowed": False,
        "external_web_allowed": False,
        "probability_rules": [
            "signal_5d is relative P(beat same-day liquid median), not P(up)",
            "signal_up_5d is absolute P(up) only when fresh and validated",
            "final_score/base_score/trading_signal/technicals are not probabilities",
            "stale/unverified/validated=false evidence cannot be decisive",
        ],
        "missing_data_rules": [
            "Unknown is not zero",
            "N/A is not bad news",
            "Inactive is not negative unless event-specific scan semantics prove absence",
            "Mock cannot enter effective conclusions",
        ],
    }


def _unavailable(kind: str, status: str, reason: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "availability_status": status,
        "reason": reason,
        "llm_usable": False,
    }


def _unavailable_from_packets(packets: Mapping[str, SourcePacket]) -> list[dict[str, Any]]:
    rows = []
    for key, packet in packets.items():
        if not packet.available:
            rows.append(_unavailable(key, "missing", packet.error or "source packet unavailable"))
    return rows


def _safe_ref(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")
