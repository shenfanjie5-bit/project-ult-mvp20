"""Build canonical graph promotion plans from internal promotion deltas."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from contracts.schemas import CandidateGraphDelta

from graph_engine.evidence import evidence_refs_from_mapping, evidence_refs_from_value
from graph_engine.models import (
    FrozenGraphDelta,
    GraphAssertionRecord,
    GraphEdgeRecord,
    GraphNodeRecord,
    PromotionPlan,
)
from graph_engine.promotion.interfaces import EntityAnchorReader
from graph_engine.schema.definitions import NodeLabel, RelationshipType

_FORBIDDEN_PAYLOAD_FIELDS = {
    "chunk",
    "light_rag_artifact",
    "lightrag_artifact",
    "raw_text",
}
_VALID_NODE_LABELS = {label.value for label in NodeLabel}
_VALID_RELATIONSHIP_TYPES = {relationship.value for relationship in RelationshipType}
_HOLDINGS_UPSERT_RELATIONSHIP_TYPES = {
    RelationshipType.CO_HOLDING.value,
    RelationshipType.NORTHBOUND_HOLD.value,
}
_STABLE_CONTRACT_EDGE_TIMESTAMP_BASE = datetime(2000, 1, 1, tzinfo=timezone.utc)
_STABLE_CONTRACT_EDGE_TIMESTAMP_SPAN_SECONDS = 10 * 365 * 24 * 60 * 60
_InternalContractDeltaType = Literal["edge_add"]
_CONTRACT_DELTA_TYPE_TO_INTERNAL: Mapping[str, _InternalContractDeltaType] = {
    "add": "edge_add",
    "add_edge": "edge_add",
    "edge_upsert": "edge_add",
    "upsert_edge": "edge_add",
    "upsert_relation": "edge_add",
}
_CONTRACT_RELATION_TYPE_TO_INTERNAL: Mapping[str, str] = {
    **{
        relationship.value.lower(): relationship.value
        for relationship in RelationshipType
    },
    "supplier_of": RelationshipType.SUPPLY_CHAIN.value,
    "supply_contract": RelationshipType.SUPPLY_CHAIN.value,
}


def freeze_contract_delta(
    cycle_id: str,
    contract_delta: CandidateGraphDelta,
    *,
    node_entity_ids: Mapping[str, str],
) -> FrozenGraphDelta:
    """Adapt a contract graph delta into the internal promotion planner record."""

    delta_type = _internal_delta_type_for_contract_delta(contract_delta)
    source_entity_ids = _resolved_endpoint_entity_ids(contract_delta, node_entity_ids)
    return FrozenGraphDelta(
        delta_id=contract_delta.delta_id,
        cycle_id=cycle_id,
        delta_type=delta_type,
        source_entity_ids=source_entity_ids,
        payload=contract_delta.model_dump(),
        validation_status="frozen",
    )


def freeze_contract_deltas(
    cycle_id: str,
    contract_deltas: Sequence[CandidateGraphDelta],
    entity_reader: EntityAnchorReader,
) -> list[FrozenGraphDelta]:
    """Adapt contract graph deltas after resolving endpoint nodes to entity anchors."""

    endpoint_node_ids = _supported_contract_endpoint_node_ids(contract_deltas)
    upsert_node_entity_ids = _node_upsert_entity_ids_by_node_id(contract_deltas)
    node_entity_ids = (
        entity_reader.canonical_entity_ids_for_node_ids(endpoint_node_ids)
        if endpoint_node_ids
        else {}
    )
    _validate_node_upserts_match_existing_endpoint_mappings(
        upsert_node_entity_ids,
        node_entity_ids,
    )
    resolved_node_entity_ids = {**upsert_node_entity_ids, **node_entity_ids}
    _validate_endpoint_entity_resolution(endpoint_node_ids, resolved_node_entity_ids)
    return [
        freeze_contract_delta(
            cycle_id,
            contract_delta,
            node_entity_ids=resolved_node_entity_ids,
        )
        for contract_delta in contract_deltas
    ]


def _internal_delta_type_for_contract_delta(
    contract_delta: CandidateGraphDelta,
) -> _InternalContractDeltaType:
    delta_type = _CONTRACT_DELTA_TYPE_TO_INTERNAL.get(
        _contract_token(contract_delta.delta_type),
    )
    if delta_type is None:
        raise ValueError(
            "unsupported contract delta_type "
            f"{contract_delta.delta_type!r} for delta {contract_delta.delta_id}",
        )
    return delta_type


def _supported_contract_endpoint_node_ids(
    contract_deltas: Sequence[CandidateGraphDelta],
) -> set[str]:
    node_ids: set[str] = set()
    for contract_delta in contract_deltas:
        _internal_delta_type_for_contract_delta(contract_delta)
        node_ids.add(contract_delta.source_node)
        node_ids.add(contract_delta.target_node)
    return node_ids


def _validate_endpoint_entity_resolution(
    endpoint_node_ids: set[str],
    node_entity_ids: Mapping[str, str],
) -> None:
    missing_node_ids = sorted(
        node_id
        for node_id in endpoint_node_ids
        if not node_entity_ids.get(node_id)
    )
    if missing_node_ids:
        raise ValueError(
            "missing canonical entity ids for graph nodes: "
            + ", ".join(missing_node_ids),
        )


def _resolved_endpoint_entity_ids(
    contract_delta: CandidateGraphDelta,
    node_entity_ids: Mapping[str, str],
) -> list[str]:
    return [
        node_entity_ids[contract_delta.source_node],
        node_entity_ids[contract_delta.target_node],
    ]


def validate_entity_anchors(
    deltas: Sequence[FrozenGraphDelta],
    entity_reader: EntityAnchorReader,
) -> None:
    """Fail if any source entity ids referenced by deltas are missing."""

    entity_ids = {
        entity_id
        for delta in deltas
        for entity_id in delta.source_entity_ids
    }
    existing_entity_ids = entity_reader.existing_entity_ids(entity_ids)
    missing_entity_ids = sorted(entity_ids - existing_entity_ids)
    if missing_entity_ids:
        raise ValueError(
            "missing entity anchors: " + ", ".join(missing_entity_ids),
        )


def build_promotion_plan(
    cycle_id: str,
    selection_ref: str,
    deltas: Sequence[FrozenGraphDelta],
) -> PromotionPlan:
    """Parse frozen candidate deltas into a stable promotion plan."""

    sorted_deltas = sorted(deltas, key=lambda delta: delta.delta_id)
    node_records_by_id: dict[str, GraphNodeRecord] = {}
    edge_records: list[GraphEdgeRecord] = []
    assertion_records: list[GraphAssertionRecord] = []

    for delta in sorted_deltas:
        _validate_delta_header(delta, cycle_id)
        _reject_forbidden_payload_fields(delta.payload)

        if delta.delta_type == "node_add":
            node_record = _parse_node_record(delta)
            node_records_by_id[node_record.node_id] = node_record
        elif delta.delta_type in {"edge_add", "edge_update"}:
            for node_record in _parse_node_upsert_records(delta):
                node_records_by_id[node_record.node_id] = node_record
            edge_records.append(_parse_edge_record(delta))
        elif delta.delta_type == "assertion_add":
            assertion_records.append(_parse_assertion_record(delta))

    return PromotionPlan(
        cycle_id=cycle_id,
        selection_ref=selection_ref,
        delta_ids=[delta.delta_id for delta in sorted_deltas],
        node_records=list(node_records_by_id.values()),
        edge_records=edge_records,
        assertion_records=assertion_records,
        created_at=datetime.now(timezone.utc),
    )


def _validate_delta_header(delta: FrozenGraphDelta, cycle_id: str) -> None:
    if delta.cycle_id != cycle_id:
        raise ValueError(
            f"delta {delta.delta_id} belongs to cycle {delta.cycle_id!r}, "
            f"not {cycle_id!r}",
        )
    if delta.validation_status != "frozen":
        raise ValueError(f"delta {delta.delta_id} is not frozen")


def _parse_node_record(delta: FrozenGraphDelta) -> GraphNodeRecord:
    payload = _required_payload_section(delta, "node")
    node_record = GraphNodeRecord.model_validate(payload)
    if node_record.label not in _VALID_NODE_LABELS:
        raise ValueError(
            f"delta {delta.delta_id} uses unsupported node label {node_record.label!r}",
        )
    return node_record


def _parse_edge_record(delta: FrozenGraphDelta) -> GraphEdgeRecord:
    contract_delta = _contract_delta_from_payload(delta.payload)
    payload = _edge_payload(delta, contract_delta=contract_delta)
    edge_record = GraphEdgeRecord.model_validate(payload)
    if edge_record.relationship_type not in _VALID_RELATIONSHIP_TYPES:
        raise ValueError(
            "delta "
            f"{delta.delta_id} uses unsupported relationship type "
            f"{edge_record.relationship_type!r}",
        )
    return edge_record


def _parse_node_upsert_records(delta: FrozenGraphDelta) -> list[GraphNodeRecord]:
    contract_delta = _contract_delta_from_payload(delta.payload)
    if contract_delta is None:
        return []

    return _node_upsert_records_from_contract_delta(delta.delta_id, contract_delta)


def _node_upsert_records_from_contract_delta(
    delta_id: str,
    contract_delta: CandidateGraphDelta,
) -> list[GraphNodeRecord]:
    node_records: list[GraphNodeRecord] = []
    for node_payload in _node_upsert_payloads_from_contract_delta(contract_delta):
        node_record = GraphNodeRecord.model_validate(node_payload)
        if node_record.label not in _VALID_NODE_LABELS:
            raise ValueError(
                f"delta {delta_id} uses unsupported node label {node_record.label!r}",
            )
        node_records.append(node_record)
    return node_records


def _parse_assertion_record(delta: FrozenGraphDelta) -> GraphAssertionRecord:
    contract_delta = _contract_delta_from_payload(delta.payload)
    payload = dict(_required_payload_section(delta, "assertion"))
    evidence_refs = _delta_evidence_refs(delta, contract_delta)
    if evidence_refs:
        evidence = payload.get("evidence")
        evidence_mapping = dict(evidence) if isinstance(evidence, Mapping) else {}
        existing_refs = set(evidence_refs_from_mapping(evidence_mapping))
        evidence_mapping["evidence_refs"] = sorted(existing_refs | set(evidence_refs))
        payload["evidence"] = evidence_mapping
    return GraphAssertionRecord.model_validate(payload)


def _edge_payload(
    delta: FrozenGraphDelta,
    *,
    contract_delta: CandidateGraphDelta | None,
) -> Mapping[str, Any]:
    payload_section = _optional_payload_section(delta, "edge")
    evidence_refs = _delta_evidence_refs(delta, contract_delta)
    if payload_section is not None:
        return _edge_payload_with_evidence_refs(payload_section, evidence_refs)
    if contract_delta is None:
        raise ValueError(f"delta {delta.delta_id} payload must include 'edge'")
    return _edge_payload_from_contract_delta(
        delta,
        contract_delta,
        evidence_refs=evidence_refs,
    )


def _edge_payload_from_contract_delta(
    delta: FrozenGraphDelta,
    contract_delta: CandidateGraphDelta,
    *,
    evidence_refs: list[str],
) -> dict[str, Any]:
    created_at = _stable_contract_edge_timestamp(delta, contract_delta)
    properties = dict(contract_delta.properties)
    existing_refs = set(evidence_refs_from_mapping(properties))
    properties["evidence_refs"] = sorted(existing_refs | set(evidence_refs))
    relationship_type = _internal_relationship_type_for_contract_delta(contract_delta)
    return {
        "edge_id": _edge_id_for_contract_delta(contract_delta, relationship_type),
        "source_node_id": contract_delta.source_node,
        "target_node_id": contract_delta.target_node,
        "relationship_type": relationship_type,
        "properties": properties,
        "weight": _edge_weight(properties),
        "created_at": created_at,
        "updated_at": created_at,
    }


def _internal_relationship_type_for_contract_delta(
    contract_delta: CandidateGraphDelta,
) -> str:
    relationship_type = _CONTRACT_RELATION_TYPE_TO_INTERNAL.get(
        _contract_token(contract_delta.relation_type),
    )
    if relationship_type is None:
        raise ValueError(
            "unsupported contract relation_type "
            f"{contract_delta.relation_type!r} for delta {contract_delta.delta_id}",
        )
    return relationship_type


def _contract_token(value: str) -> str:
    return value.strip().lower().replace("-", "_")


def _edge_id_for_contract_delta(
    contract_delta: CandidateGraphDelta,
    relationship_type: str,
) -> str:
    if relationship_type not in _HOLDINGS_UPSERT_RELATIONSHIP_TYPES:
        return contract_delta.delta_id

    explicit_edge_id = contract_delta.properties.get("edge_id")
    if isinstance(explicit_edge_id, str) and explicit_edge_id.strip():
        return explicit_edge_id.strip()

    explicit_edge_key = contract_delta.properties.get("edge_key")
    material = (
        explicit_edge_key
        if isinstance(explicit_edge_key, str) and explicit_edge_key.strip()
        else "|".join(
            (
                relationship_type,
                contract_delta.source_node,
                contract_delta.target_node,
            )
        )
    )
    digest = hashlib.sha256(str(material).encode("utf-8")).hexdigest()[:24]
    return f"{relationship_type.lower()}:{digest}"


def _node_upsert_entity_ids_by_node_id(
    contract_deltas: Sequence[CandidateGraphDelta],
) -> dict[str, str]:
    upsert_entity_ids: dict[str, str] = {}
    for contract_delta in contract_deltas:
        delta_endpoint_node_ids = {
            contract_delta.source_node,
            contract_delta.target_node,
        }
        for node_record in _node_upsert_records_from_contract_delta(
            contract_delta.delta_id,
            contract_delta,
        ):
            if node_record.node_id not in delta_endpoint_node_ids:
                raise ValueError(
                    "graph_node_upserts are endpoint-only; unsupported node ids: "
                    f"{node_record.node_id}",
                )
            existing_entity_id = upsert_entity_ids.get(node_record.node_id)
            if (
                existing_entity_id is not None
                and existing_entity_id != node_record.canonical_entity_id
            ):
                raise ValueError(
                    "graph_node_upserts conflict for endpoint node "
                    f"{node_record.node_id}: "
                    f"{existing_entity_id} != {node_record.canonical_entity_id}",
                )
            upsert_entity_ids[node_record.node_id] = node_record.canonical_entity_id
    return upsert_entity_ids


def _validate_node_upserts_match_existing_endpoint_mappings(
    upsert_node_entity_ids: Mapping[str, str],
    node_entity_ids: Mapping[str, str],
) -> None:
    conflicts = [
        (
            node_id,
            upsert_entity_id,
            node_entity_ids[node_id],
        )
        for node_id, upsert_entity_id in sorted(upsert_node_entity_ids.items())
        if node_id in node_entity_ids and node_entity_ids[node_id] != upsert_entity_id
    ]
    if not conflicts:
        return

    details = ", ".join(
        f"{node_id} ({upsert_entity_id} != {existing_entity_id})"
        for node_id, upsert_entity_id, existing_entity_id in conflicts
    )
    raise ValueError(
        "graph_node_upserts conflict with existing endpoint canonical entity "
        f"mappings: {details}",
    )


def _node_upsert_payloads_from_contract_delta(
    contract_delta: CandidateGraphDelta,
) -> list[Mapping[str, Any]]:
    producer_context = contract_delta.producer_context
    if not isinstance(producer_context, Mapping):
        return []
    raw_upserts = producer_context.get("graph_node_upserts")
    if raw_upserts is None:
        return []
    relationship_type = _internal_relationship_type_for_contract_delta(contract_delta)
    if relationship_type not in _HOLDINGS_UPSERT_RELATIONSHIP_TYPES:
        raise ValueError(
            "graph_node_upserts are only supported for "
            f"{RelationshipType.CO_HOLDING.value} and "
            f"{RelationshipType.NORTHBOUND_HOLD.value}",
        )
    return _coerce_node_upsert_payloads(raw_upserts)


def _coerce_node_upsert_payloads(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        if "node_id" in value:
            return [value]
        payloads: list[Mapping[str, Any]] = []
        for key in ("source", "source_node", "target", "target_node"):
            nested_value = value.get(key)
            if isinstance(nested_value, Mapping):
                payloads.append(nested_value)
        return payloads
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        payloads = []
        for item in value:
            if not isinstance(item, Mapping):
                raise ValueError("graph_node_upserts entries must be mappings")
            payloads.append(item)
        return payloads
    raise ValueError("graph_node_upserts must be a mapping or sequence of mappings")


def _edge_payload_with_evidence_refs(
    payload_section: Mapping[str, Any],
    evidence_refs: list[str],
) -> Mapping[str, Any]:
    if not evidence_refs:
        return payload_section
    payload = dict(payload_section)
    properties = payload.get("properties")
    if not isinstance(properties, Mapping):
        return payload
    existing_refs = set(evidence_refs_from_mapping(properties))
    payload["properties"] = {
        **dict(properties),
        "evidence_refs": sorted(existing_refs | set(evidence_refs)),
    }
    return payload


def _required_payload_section(
    delta: FrozenGraphDelta,
    key: str,
) -> Mapping[str, Any]:
    payload_section = delta.payload.get(key)
    if not isinstance(payload_section, Mapping):
        raise ValueError(f"delta {delta.delta_id} payload must include {key!r}")
    return payload_section


def _optional_payload_section(
    delta: FrozenGraphDelta,
    key: str,
) -> Mapping[str, Any] | None:
    payload_section = delta.payload.get(key)
    if payload_section is None:
        return None
    if not isinstance(payload_section, Mapping):
        raise ValueError(f"delta {delta.delta_id} payload section {key!r} must be a mapping")
    return payload_section


def _contract_delta_from_payload(payload: Mapping[str, Any]) -> CandidateGraphDelta | None:
    for key in ("contract_delta", "candidate_delta", "graph_delta"):
        candidate = payload.get(key)
        if isinstance(candidate, CandidateGraphDelta):
            return candidate
        if isinstance(candidate, Mapping):
            return CandidateGraphDelta.model_validate(candidate)

    if _looks_like_contract_delta(payload):
        return CandidateGraphDelta.model_validate(payload)
    return None


def _looks_like_contract_delta(payload: Mapping[str, Any]) -> bool:
    return {
        "delta_id",
        "delta_type",
        "source_node",
        "target_node",
        "relation_type",
        "properties",
        "evidence",
        "subsystem_id",
    } <= set(payload)


def _delta_evidence_refs(
    delta: FrozenGraphDelta,
    contract_delta: CandidateGraphDelta | None,
) -> list[str]:
    refs: set[str] = set()
    refs.update(evidence_refs_from_value(delta.payload.get("evidence_refs")))
    refs.update(evidence_refs_from_value(delta.payload.get("evidence_ref")))
    refs.update(
        evidence_refs_from_value(delta.payload.get("evidence"), allow_mapping=True),
    )
    if contract_delta is not None:
        refs.update(evidence_refs_from_value(contract_delta.evidence))
    return sorted(refs)


def _stable_contract_edge_timestamp(
    delta: FrozenGraphDelta,
    contract_delta: CandidateGraphDelta,
) -> datetime:
    material = "|".join(
        (
            delta.cycle_id,
            delta.delta_id,
            contract_delta.delta_id,
            contract_delta.source_node,
            contract_delta.target_node,
            contract_delta.relation_type,
        )
    )
    digest = hashlib.sha256(material.encode("utf-8")).digest()
    offset_seconds = (
        int.from_bytes(digest[:8], byteorder="big")
        % _STABLE_CONTRACT_EDGE_TIMESTAMP_SPAN_SECONDS
    )
    return _STABLE_CONTRACT_EDGE_TIMESTAMP_BASE + timedelta(seconds=offset_seconds)


def _edge_weight(properties: Mapping[str, Any]) -> float:
    weight = properties.get("weight")
    if weight is None:
        return 1.0
    return float(weight)


def _reject_forbidden_payload_fields(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, nested_value in value.items():
            if isinstance(key, str) and key in _FORBIDDEN_PAYLOAD_FIELDS:
                raise ValueError(f"candidate payload includes forbidden field {key!r}")
            _reject_forbidden_payload_fields(nested_value)
        return

    if isinstance(value, list):
        for item in value:
            _reject_forbidden_payload_fields(item)
