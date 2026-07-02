"""Structured single-stock LLM decision contract and validator."""

from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mvp20.llm_context import SCHEMA_VERSION as CONTEXT_SCHEMA_VERSION
from mvp20.llm_context import context_input_hash, evidence_counts, now_shanghai
from mvp20.llm_storage import canonical_json, sha256_payload, sha256_text, short_hash

OUTPUT_SCHEMA_VERSION = "single_stock_decision_output.v1"

ActionType = Literal["buy", "hold", "reduce", "inconclusive"]
DecisionStatus = Literal["ok", "inconclusive", "blocked", "invalid"]
ClaimUse = Literal["supporting", "risk", "uncertainty", "data_quality"]
ProbabilityUse = Literal["primary", "diagnostic", "rejected"]

_URL_RE = re.compile(r"https?://[^\s)>\"]+")
_PROBABILITY_BLOCKED_NAMES = {
    "final_score",
    "base_score",
    "market_adjusted_final_score",
    "short",
    "medium",
    "long",
    "company_score",
    "merit",
    "timing",
    "trading_signal",
    "trading_signal_v2",
    "mode_confidence",
    "direction",
    "strength",
    "grade",
    "rsi",
    "macd",
    "technical",
    "heat",
}


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DecisionClaim(FrozenModel):
    claim_id: str
    claim_use: ClaimUse
    text: str
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float | None = None

    @model_validator(mode="after")
    def validate_claim(self) -> "DecisionClaim":
        if self.claim_use in {"supporting", "risk"} and not self.evidence_refs:
            raise ValueError("supporting/risk claims require evidence_refs")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("claim confidence must be in [0,1]")
        return self


class DecisionProbability(FrozenModel):
    evidence_ref: str
    probability: float | None
    target_kind: str
    probability_semantics: str
    horizon_days: int
    use_scope: ProbabilityUse
    explanation: str | None = None

    @model_validator(mode="after")
    def validate_probability_range(self) -> "DecisionProbability":
        if self.probability is not None:
            if not math.isfinite(self.probability):
                raise ValueError("probability must be finite")
            if self.probability < 0 or self.probability > 1:
                raise ValueError("probability must be in [0,1]")
        return self


class SingleStockDecisionOutput(FrozenModel):
    schema_version: Literal["single_stock_decision_output.v1"]
    decision_id: str
    context_ref: dict[str, Any]
    cycle_id: str
    ts_code: str
    market: str
    horizon: str
    horizon_days: int | None = None
    as_of: str
    status: DecisionStatus
    action_type: ActionType
    rating: str | None = None
    confidence: float | None = None
    thesis: str
    positive_driver_claims: list[DecisionClaim] = Field(default_factory=list)
    negative_driver_claims: list[DecisionClaim] = Field(default_factory=list)
    uncertainty_claims: list[DecisionClaim] = Field(default_factory=list)
    probability_estimates: list[DecisionProbability] = Field(default_factory=list)
    data_quality_summary: dict[str, Any] = Field(default_factory=dict)
    constraints_applied: dict[str, Any] = Field(default_factory=dict)
    degradation_flags: list[str] = Field(default_factory=list)
    audit_record: dict[str, Any]
    validation_result: dict[str, Any] = Field(default_factory=dict)
    decision_hash: str

    @model_validator(mode="after")
    def validate_status_action_invariants(self) -> "SingleStockDecisionOutput":
        if self.status != "ok":
            if self.action_type != "inconclusive":
                raise ValueError("status!=ok requires action_type=inconclusive")
            if self.confidence is not None:
                raise ValueError("status!=ok requires confidence=None")
        if self.action_type == "inconclusive" and self.confidence is not None:
            raise ValueError("inconclusive action requires confidence=None")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be in [0,1]")
        return self


def normalize_context_payload(context: Mapping[str, Any] | Any) -> dict[str, Any]:
    if hasattr(context, "model_dump"):
        return context.model_dump(mode="json", by_alias=True)
    return dict(context)


def decision_hash_payload(payload: Mapping[str, Any]) -> str:
    material = dict(payload)
    material.pop("decision_hash", None)
    return sha256_payload(material)


def confidence_cap(context_payload: Mapping[str, Any]) -> dict[str, Any]:
    counts = _context_evidence_counts(context_payload)
    total = int(counts.get("total") or 0)
    usable = int(counts.get("usable") or 0)
    usable_ratio = usable / total if total else 0.0
    cap = 0.75
    reasons: list[str] = []
    if usable_ratio < 0.3:
        cap = min(cap, 0.3)
        reasons.append("usable evidence coverage below 30%")
    elif usable_ratio < 0.5:
        cap = min(cap, 0.55)
        reasons.append("usable evidence coverage below 50%")
    if int(counts.get("stale") or 0) > 0:
        cap = min(cap, 0.65)
        reasons.append("stale evidence present")
    primary_probabilities = [
        p
        for p in context_payload.get("model_probabilities") or []
        if isinstance(p, Mapping) and p.get("use_scope") == "primary_signal"
    ]
    if not primary_probabilities:
        cap = min(cap, 0.45)
        reasons.append("no fresh validated primary probability estimate")
    if context_payload.get("contradictions"):
        cap = min(cap, 0.6)
        reasons.append("context carries unresolved contradictions")
    return {
        "confidence_cap": round(cap, 4),
        "usable_evidence_ratio": round(usable_ratio, 4),
        "reasons": reasons,
    }


def validate_decision_output(
    context: Mapping[str, Any] | Any,
    output: Mapping[str, Any] | Any,
    *,
    closed_loop: bool = True,
) -> dict[str, Any]:
    context_payload = normalize_context_payload(context)
    output_payload = (
        output.model_dump(mode="json") if hasattr(output, "model_dump") else dict(output)
    )
    errors: list[str] = []
    warnings: list[str] = []
    rejected_claims: list[dict[str, Any]] = []

    try:
        decision = SingleStockDecisionOutput.model_validate(output_payload)
    except Exception as exc:  # pydantic reports detailed locations in str(exc)
        return {
            "passed": False,
            "evidence_gate_passed": False,
            "closed_loop_passed": not closed_loop,
            "probability_semantics_passed": False,
            "errors": [str(exc)],
            "warnings": warnings,
            "rejected_claims": rejected_claims,
            "confidence_policy": confidence_cap(context_payload)
            if context_payload.get("context_id")
            else {},
        }

    context_ref = decision.context_ref
    expected_context_id = context_payload.get("context_id")
    expected_hash = _context_hash(context_payload)
    if expected_context_id and context_ref.get("context_id") != expected_context_id:
        errors.append("decision.context_ref.context_id does not match context")
    if expected_hash and context_ref.get("context_hash") != expected_hash:
        errors.append("decision.context_ref.context_hash does not match context")
    if context_payload.get("schema_version") != CONTEXT_SCHEMA_VERSION:
        errors.append("unsupported or missing context schema_version")
    if decision.ts_code != context_payload.get("ts_code"):
        errors.append("decision ts_code does not match context")
    if decision.horizon != context_payload.get("horizon"):
        errors.append("decision horizon does not match context")

    evidence_by_ref = {
        str(item.get("evidence_ref")): item
        for item in context_payload.get("evidence_pack") or []
        if isinstance(item, Mapping) and item.get("evidence_ref")
    }
    allowed_urls = _allowed_urls(context_payload)
    for claim in (
        list(decision.positive_driver_claims)
        + list(decision.negative_driver_claims)
        + list(decision.uncertainty_claims)
    ):
        claim_errors = _validate_claim_evidence(claim, evidence_by_ref)
        if claim_errors:
            rejected_claims.append(
                {
                    "claim_id": claim.claim_id,
                    "claim_use": claim.claim_use,
                    "errors": claim_errors,
                }
            )
            errors.extend(f"{claim.claim_id}: {error}" for error in claim_errors)
        if closed_loop:
            external_urls = [
                url for url in _URL_RE.findall(claim.text) if url not in allowed_urls
            ]
            if external_urls:
                errors.append(
                    f"{claim.claim_id}: claim contains URL outside frozen context"
                )
    if closed_loop:
        thesis_urls = [
            url for url in _URL_RE.findall(decision.thesis) if url not in allowed_urls
        ]
        if thesis_urls:
            errors.append("thesis contains URL outside frozen context")

    probability_errors = _validate_probability_semantics(
        decision.probability_estimates,
        context_payload,
        evidence_by_ref,
    )
    errors.extend(probability_errors)

    cap_policy = confidence_cap(context_payload) if expected_context_id else {}
    cap_value = cap_policy.get("confidence_cap")
    if (
        decision.status == "ok"
        and decision.confidence is not None
        and isinstance(cap_value, (int, float))
        and decision.confidence > float(cap_value)
    ):
        errors.append(
            f"confidence {decision.confidence} exceeds policy cap {cap_value}"
        )
    if decision.status == "ok" and not decision.positive_driver_claims and not decision.negative_driver_claims:
        warnings.append("ok decision has no directional driver claims")

    formal_audit_errors = _validate_embedded_audit_record(decision.audit_record)
    errors.extend(formal_audit_errors)

    recomputed_decision_hash = decision_hash_payload(output_payload)
    if decision.decision_hash != recomputed_decision_hash:
        errors.append("decision_hash does not match canonical decision payload")

    evidence_gate_passed = not rejected_claims and not any(
        "evidence" in error.lower() for error in errors
    )
    probability_passed = not probability_errors
    closed_loop_passed = not any("outside frozen context" in error for error in errors)
    return {
        "passed": not errors,
        "evidence_gate_passed": evidence_gate_passed,
        "closed_loop_passed": closed_loop_passed,
        "probability_semantics_passed": probability_passed,
        "errors": errors,
        "warnings": warnings,
        "rejected_claims": rejected_claims,
        "confidence_policy": cap_policy,
        "recomputed_decision_hash": recomputed_decision_hash,
    }


def build_dry_run_decision(context: Mapping[str, Any] | Any) -> dict[str, Any]:
    context_payload = normalize_context_payload(context)
    if context_payload.get("status") == "unsupported":
        return _finalize_decision(
            _unsupported_decision_payload(context_payload),
            context_payload,
        )

    counts = _context_evidence_counts(context_payload)
    cap_policy = confidence_cap(context_payload)
    primary_probabilities = [
        p
        for p in context_payload.get("model_probabilities") or []
        if isinstance(p, Mapping) and p.get("use_scope") == "primary_signal"
    ]
    usable_probability = primary_probabilities[0] if primary_probabilities else None
    probability_estimates = [
        _decision_probability_from_context_probability(p)
        for p in context_payload.get("model_probabilities") or []
        if isinstance(p, Mapping)
    ]
    degradation_flags = _degradation_flags(context_payload, counts)

    if usable_probability is None:
        payload = {
            **_decision_base(context_payload),
            "status": "inconclusive",
            "action_type": "inconclusive",
            "rating": None,
            "confidence": None,
            "thesis": (
                "No buy/hold/reduce conclusion is emitted because the frozen "
                "context lacks a fresh validated primary probability estimate."
            ),
            "positive_driver_claims": [],
            "negative_driver_claims": [],
            "uncertainty_claims": _uncertainty_claims(context_payload),
            "probability_estimates": probability_estimates,
            "data_quality_summary": _data_quality_summary(
                context_payload,
                counts,
                cap_policy,
            ),
            "constraints_applied": {
                "closed_loop_context_only": True,
                "primary_probability_required": True,
                "stale_unverified_unavailable_not_supporting": True,
                "final_score_not_probability": True,
            },
            "degradation_flags": degradation_flags
            or ["primary_probability_unavailable"],
        }
        return _finalize_decision(payload, context_payload)

    probability = usable_probability.get("probability")
    action = _action_from_probability(probability)
    confidence = _confidence_from_probability(probability, cap_policy)
    status: DecisionStatus = "ok" if action != "inconclusive" else "inconclusive"
    payload = {
        **_decision_base(context_payload),
        "status": status,
        "action_type": action,
        "rating": action if action != "inconclusive" else None,
        "confidence": confidence if status == "ok" else None,
        "thesis": _thesis_for_probability(action, usable_probability),
        "positive_driver_claims": _directional_claims(
            context_payload,
            positive=True,
            action=action,
        ),
        "negative_driver_claims": _directional_claims(
            context_payload,
            positive=False,
            action=action,
        ),
        "uncertainty_claims": _uncertainty_claims(context_payload),
        "probability_estimates": probability_estimates,
        "data_quality_summary": _data_quality_summary(
            context_payload,
            counts,
            cap_policy,
        ),
        "constraints_applied": {
            "closed_loop_context_only": True,
            "primary_probability_required": True,
            "stale_unverified_unavailable_not_supporting": True,
            "final_score_not_probability": True,
        },
        "degradation_flags": degradation_flags,
    }
    return _finalize_decision(payload, context_payload)


def prepare_decision_snapshot(
    context: Mapping[str, Any] | Any,
    output: Mapping[str, Any] | None = None,
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    context_payload = normalize_context_payload(context)
    if output is None:
        snapshot = build_dry_run_decision(context_payload)
    else:
        snapshot = dict(output)
        snapshot.setdefault("audit_record", _audit_record(snapshot, context_payload, dry_run=dry_run))
        snapshot = _finalize_decision(snapshot, context_payload, dry_run=dry_run)
    return snapshot


def _context_hash(context_payload: Mapping[str, Any]) -> str | None:
    if not context_payload.get("context_id"):
        return None
    return context_payload.get("input_hash") or context_input_hash(context_payload)


def _context_evidence_counts(context_payload: Mapping[str, Any]) -> dict[str, int]:
    counts = context_payload.get("evidence_counts")
    if isinstance(counts, Mapping):
        return {str(k): int(v) for k, v in counts.items() if isinstance(v, int)}
    nested = context_payload.get("coverage_and_confidence", {}).get("evidence_counts")
    if isinstance(nested, Mapping):
        return {str(k): int(v) for k, v in nested.items() if isinstance(v, int)}
    try:
        return evidence_counts(
            list(context_payload.get("evidence_pack") or []),
            list(context_payload.get("unavailable_evidence") or []),
        )
    except Exception:
        return {}


def _decision_base(context_payload: Mapping[str, Any]) -> dict[str, Any]:
    as_of = str(context_payload.get("as_of") or now_shanghai().isoformat())
    return {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "decision_id": "pending",
        "context_ref": {
            "schema_version": context_payload.get("schema_version"),
            "context_id": context_payload.get("context_id"),
            "context_hash": _context_hash(context_payload),
        },
        "cycle_id": str(context_payload.get("cycle_id") or "unknown"),
        "ts_code": str(context_payload.get("ts_code") or ""),
        "market": str(context_payload.get("market") or "UNKNOWN"),
        "horizon": str(context_payload.get("horizon") or "5d"),
        "horizon_days": context_payload.get("horizon_days"),
        "as_of": as_of,
        "audit_record": {},
        "validation_result": {},
        "decision_hash": "pending",
    }


def _unsupported_decision_payload(context_payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **_decision_base(context_payload),
        "status": "blocked",
        "action_type": "inconclusive",
        "rating": None,
        "confidence": None,
        "thesis": str(context_payload.get("reason") or "unsupported market/context"),
        "positive_driver_claims": [],
        "negative_driver_claims": [],
        "uncertainty_claims": [
            {
                "claim_id": "uq_unsupported_context",
                "claim_use": "data_quality",
                "text": str(context_payload.get("reason") or "unsupported context"),
                "evidence_refs": [],
                "confidence": None,
            }
        ],
        "probability_estimates": [],
        "data_quality_summary": {
            "status": "unsupported",
            "reason": context_payload.get("reason"),
            "evidence_counts": {},
        },
        "constraints_applied": {
            "a_share_only": True,
            "closed_loop_context_only": True,
        },
        "degradation_flags": ["unsupported_context"],
    }


def _decision_probability_from_context_probability(p: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "evidence_ref": str(p.get("evidence_ref") or ""),
        "probability": p.get("probability"),
        "target_kind": str(p.get("target_kind") or ""),
        "probability_semantics": str(p.get("probability_semantics") or ""),
        "horizon_days": int(p.get("horizon_days") or 0),
        "use_scope": "primary" if p.get("use_scope") == "primary_signal" else "diagnostic",
        "explanation": p.get("block_reason") or p.get("probability_source"),
    }


def _degradation_flags(
    context_payload: Mapping[str, Any],
    counts: Mapping[str, int],
) -> list[str]:
    flags: list[str] = []
    if int(counts.get("stale") or 0) > 0:
        flags.append("stale_evidence_present")
    if int(counts.get("unusable") or 0) > 0:
        flags.append("unusable_evidence_present")
    if not [
        p
        for p in context_payload.get("model_probabilities") or []
        if isinstance(p, Mapping) and p.get("use_scope") == "primary_signal"
    ]:
        flags.append("primary_probability_unavailable")
    if context_payload.get("contradictions"):
        flags.append("context_contradictions_present")
    return sorted(set(flags))


def _uncertainty_claims(context_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    diagnostic_refs = [
        str(p.get("evidence_ref"))
        for p in context_payload.get("model_probabilities") or []
        if isinstance(p, Mapping) and p.get("evidence_ref")
    ]
    if diagnostic_refs:
        claims.append(
            {
                "claim_id": "uq_probability_gate",
                "claim_use": "data_quality",
                "text": (
                    "Probability-shaped artifacts are retained as diagnostics "
                    "unless they are fresh, validated, and non-fallback."
                ),
                "evidence_refs": diagnostic_refs,
                "confidence": None,
            }
        )
    unavailable = context_payload.get("unavailable_evidence") or []
    if unavailable:
        claims.append(
            {
                "claim_id": "uq_unavailable_evidence",
                "claim_use": "data_quality",
                "text": "Some requested evidence was unavailable in the frozen context.",
                "evidence_refs": [],
                "confidence": None,
            }
        )
    return claims


def _directional_claims(
    context_payload: Mapping[str, Any],
    *,
    positive: bool,
    action: str,
) -> list[dict[str, Any]]:
    if action == "inconclusive":
        return []
    refs = [
        str(item.get("evidence_ref"))
        for item in context_payload.get("evidence_pack") or []
        if isinstance(item, Mapping)
        and item.get("llm_usable") is True
        and item.get("use_scope") in {"primary_signal", "supporting_signal"}
    ][:2]
    if not refs:
        return []
    if positive and action in {"buy", "hold"}:
        return [
            {
                "claim_id": "pos_probability_supported",
                "claim_use": "supporting",
                "text": "The action is supported only by fresh usable evidence in the frozen context.",
                "evidence_refs": refs,
                "confidence": 0.55,
            }
        ]
    if (not positive) and action == "reduce":
        return [
            {
                "claim_id": "neg_probability_supported",
                "claim_use": "risk",
                "text": "The action is constrained by fresh usable evidence in the frozen context.",
                "evidence_refs": refs,
                "confidence": 0.55,
            }
        ]
    return []


def _data_quality_summary(
    context_payload: Mapping[str, Any],
    counts: Mapping[str, int],
    cap_policy: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "context_id": context_payload.get("context_id"),
        "context_hash": _context_hash(context_payload),
        "evidence_counts": dict(counts),
        "freshness": context_payload.get("freshness") or {},
        "coverage_and_confidence": context_payload.get("coverage_and_confidence") or {},
        "confidence_policy": dict(cap_policy),
        "model_probability_count": len(context_payload.get("model_probabilities") or []),
    }


def _action_from_probability(probability: Any) -> ActionType:
    if not isinstance(probability, (int, float)) or not math.isfinite(float(probability)):
        return "inconclusive"
    p = float(probability)
    if p >= 0.57:
        return "buy"
    if p <= 0.43:
        return "reduce"
    return "hold"


def _confidence_from_probability(
    probability: Any,
    cap_policy: Mapping[str, Any],
) -> float | None:
    if not isinstance(probability, (int, float)) or not math.isfinite(float(probability)):
        return None
    edge = abs(float(probability) - 0.5) * 2
    raw = min(0.75, 0.45 + edge)
    cap = float(cap_policy.get("confidence_cap") or 0.45)
    return round(min(raw, cap), 4)


def _thesis_for_probability(action: str, probability: Mapping[str, Any]) -> str:
    semantics = probability.get("probability_semantics") or probability.get("target_kind")
    return (
        f"Action {action} is based on the primary probability estimate "
        f"with semantics: {semantics}."
    )


def _finalize_decision(
    payload: Mapping[str, Any],
    context_payload: Mapping[str, Any],
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    draft = dict(payload)
    draft["decision_id"] = "dec_" + short_hash(
        {
            "schema_version": OUTPUT_SCHEMA_VERSION,
            "context_id": draft.get("context_ref", {}).get("context_id"),
            "ts_code": draft.get("ts_code"),
            "horizon": draft.get("horizon"),
            "status": draft.get("status"),
            "action_type": draft.get("action_type"),
            "as_of": draft.get("as_of"),
        }
    )
    draft["audit_record"] = _audit_record(draft, context_payload, dry_run=dry_run)
    draft["validation_result"] = {}
    draft["decision_hash"] = decision_hash_payload(draft)
    validation = validate_decision_output(context_payload, draft)
    draft["validation_result"] = {
        key: value
        for key, value in validation.items()
        if key != "recomputed_decision_hash"
    }
    draft["decision_hash"] = decision_hash_payload(draft)
    validation = validate_decision_output(context_payload, draft)
    draft["validation_result"] = {
        key: value
        for key, value in validation.items()
        if key != "recomputed_decision_hash"
    }
    draft["decision_hash"] = decision_hash_payload(draft)
    return SingleStockDecisionOutput.model_validate(draft).model_dump(mode="json")


def _audit_record(
    decision_payload: Mapping[str, Any],
    context_payload: Mapping[str, Any],
    *,
    dry_run: bool,
) -> dict[str, Any]:
    decision_id = str(decision_payload.get("decision_id") or "pending")
    created_at = str(decision_payload.get("as_of") or now_shanghai().isoformat())
    # The local runtime path is deterministic and does not call an LLM provider.
    return {
        "record_id": f"AUD_{decision_id}",
        "cycle_id": str(context_payload.get("cycle_id") or decision_payload.get("cycle_id") or "unknown"),
        "layer": "L7",
        "object_ref": (
            f"{decision_payload.get('ts_code')}:"
            f"{decision_payload.get('horizon')}:llm_decision"
        ),
        "params_snapshot": {
            "dry_run": bool(dry_run),
            "context_schema_version": context_payload.get("schema_version"),
            "decision_schema_version": OUTPUT_SCHEMA_VERSION,
            "context_id": context_payload.get("context_id"),
            "context_hash": _context_hash(context_payload),
        },
        "llm_lineage": {
            "called": False,
            "reason": "deterministic dry-run or client-supplied validation path",
        },
        "llm_cost": {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0},
        "sanitized_input": None,
        "input_hash": None,
        "raw_output": None,
        "parsed_result": None,
        "output_hash": None,
        "degradation_flags": {
            "flags": list(decision_payload.get("degradation_flags") or []),
        },
        "created_at": created_at,
    }


def _validate_claim_evidence(
    claim: DecisionClaim,
    evidence_by_ref: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    errors: list[str] = []
    for ref in claim.evidence_refs:
        item = evidence_by_ref.get(ref)
        if item is None:
            errors.append(f"unknown evidence_ref {ref}")
            continue
        if claim.claim_use in {"supporting", "risk"}:
            if item.get("llm_usable") is not True:
                errors.append(f"evidence_ref {ref} is not LLM-usable")
            if item.get("freshness_status") not in {"fresh", "unknown"}:
                errors.append(f"evidence_ref {ref} is stale/expired")
            if item.get("verification_status") != "verified":
                errors.append(f"evidence_ref {ref} is not verified")
            if item.get("availability_status") != "available":
                errors.append(f"evidence_ref {ref} is unavailable")
            if item.get("use_scope") in {"diagnostic_only", "blocked", "context_only"}:
                errors.append(f"evidence_ref {ref} is not supporting evidence")
    return errors


def _validate_probability_semantics(
    estimates: list[DecisionProbability],
    context_payload: Mapping[str, Any],
    evidence_by_ref: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    errors: list[str] = []
    context_probs = {
        str(p.get("evidence_ref")): p
        for p in context_payload.get("model_probabilities") or []
        if isinstance(p, Mapping) and p.get("evidence_ref")
    }
    for estimate in estimates:
        if estimate.evidence_ref not in evidence_by_ref:
            errors.append(
                f"probability estimate references unknown evidence_ref {estimate.evidence_ref}"
            )
            continue
        ctx_prob = context_probs.get(estimate.evidence_ref)
        if not ctx_prob:
            errors.append(
                f"probability estimate {estimate.evidence_ref} is not declared in context.model_probabilities"
            )
            continue
        source_text = canonical_json(ctx_prob).lower()
        if any(name in source_text for name in _PROBABILITY_BLOCKED_NAMES):
            if estimate.use_scope == "primary":
                errors.append(
                    f"probability estimate {estimate.evidence_ref} uses score/technical fields as probability"
                )
        if estimate.target_kind != ctx_prob.get("target_kind"):
            errors.append(
                f"probability target_kind mismatch for {estimate.evidence_ref}"
            )
        if estimate.probability_semantics != ctx_prob.get("probability_semantics"):
            errors.append(
                f"probability semantics mismatch for {estimate.evidence_ref}"
            )
        if (
            estimate.target_kind == "absolute_up_5d"
            and "signal_5d" in estimate.evidence_ref
            and "signal_up_5d" not in estimate.evidence_ref
        ):
            errors.append("signal_5d relative artifact cannot be used as absolute_up_5d")
        if estimate.use_scope == "primary":
            if ctx_prob.get("use_scope") != "primary_signal":
                errors.append(
                    f"probability estimate {estimate.evidence_ref} is not primary in context"
                )
            if (
                ctx_prob.get("validated") is not True
                or ctx_prob.get("stale") is True
                or ctx_prob.get("fallback") is True
                or ctx_prob.get("shadow") is True
            ):
                errors.append(
                    f"probability estimate {estimate.evidence_ref} fails validation/freshness/fallback gates"
                )
    return errors


def _allowed_urls(context_payload: Mapping[str, Any]) -> set[str]:
    urls: set[str] = set()
    for packet in (context_payload.get("source_packets") or {}).values():
        if isinstance(packet, Mapping):
            _collect_urls(packet, urls)
    for item in context_payload.get("evidence_pack") or []:
        if isinstance(item, Mapping):
            _collect_urls(item, urls)
    return urls


def _collect_urls(value: Any, urls: set[str]) -> None:
    if isinstance(value, str):
        urls.update(_URL_RE.findall(value))
    elif isinstance(value, Mapping):
        for child in value.values():
            _collect_urls(child, urls)
    elif isinstance(value, list):
        for child in value:
            _collect_urls(child, urls)


def _validate_embedded_audit_record(audit_record: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    required = {
        "record_id",
        "cycle_id",
        "layer",
        "object_ref",
        "params_snapshot",
        "llm_lineage",
        "llm_cost",
        "sanitized_input",
        "input_hash",
        "raw_output",
        "parsed_result",
        "output_hash",
        "degradation_flags",
        "created_at",
    }
    missing = sorted(required - set(audit_record.keys()))
    if missing:
        return [f"audit_record missing required fields: {', '.join(missing)}"]
    if audit_record.get("layer") != "L7":
        errors.append("audit_record.layer must be L7")
    lineage = audit_record.get("llm_lineage")
    if not isinstance(lineage, Mapping) or "called" not in lineage:
        errors.append("audit_record.llm_lineage.called must be present")
    elif not isinstance(lineage.get("called"), bool):
        errors.append("audit_record.llm_lineage.called must be boolean")
    elif lineage.get("called") is True:
        for field_name in (
            "sanitized_input",
            "input_hash",
            "raw_output",
            "parsed_result",
            "output_hash",
        ):
            if audit_record.get(field_name) is None:
                errors.append(
                    f"LLM-called audit records require replay field {field_name}"
                )
        sanitized_input = audit_record.get("sanitized_input")
        input_hash = audit_record.get("input_hash")
        if isinstance(sanitized_input, str) and isinstance(input_hash, str):
            if input_hash != sha256_text(sanitized_input):
                errors.append("audit_record.input_hash does not match sanitized_input")
        raw_output = audit_record.get("raw_output")
        output_hash = audit_record.get("output_hash")
        if isinstance(raw_output, str) and isinstance(output_hash, str):
            if output_hash != sha256_text(raw_output):
                errors.append("audit_record.output_hash does not match raw_output")
    try:
        datetime.fromisoformat(str(audit_record.get("created_at")))
    except ValueError:
        errors.append("audit_record.created_at must be ISO datetime")
    return errors


__all__ = [
    "OUTPUT_SCHEMA_VERSION",
    "SingleStockDecisionOutput",
    "DecisionClaim",
    "DecisionProbability",
    "build_dry_run_decision",
    "confidence_cap",
    "decision_hash_payload",
    "prepare_decision_snapshot",
    "validate_decision_output",
]
