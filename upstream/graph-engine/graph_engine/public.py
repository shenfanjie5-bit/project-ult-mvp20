"""Assembly-facing public entrypoints for graph-engine.

This module is the single boundary that ``assembly`` (registry + compat
checks + bootstrap) imports to introspect this package. The five
``module-level singleton instances`` below match the assembly Protocols
in ``assembly/src/assembly/contracts/entrypoints.py`` and the signature
shape enforced by ``assembly/src/assembly/compat/checks/public_api_boundary.py``:

- ``health_probe.check(*, timeout_sec: float)``
- ``smoke_hook.run(*, profile_id: str)``
- ``init_hook.initialize(*, resolved_env: dict[str, str])``
- ``version_declaration.declare()``
- ``cli.invoke(argv: list[str])``

CLAUDE.md guardrails this file enforces by construction (graph-engine
§10 red lines):

- **Truth Before Mirror** (#1) — the version declaration carries
  ``canonical_truth_layer="iceberg"`` as a structural marker; assembly
  cross-checks via boundary tier deny scan that no Neo4j-as-truth
  shortcut got introduced.
- **Promotion Before Propagation** (#2) — smoke_hook drives only the
  promotion path, never the live-graph-first shortcut.
- **No Raw Text** (#6) — public.py never imports ``lightrag``,
  ``langchain``, or any text/parser stack; only consumes contracted
  ``CandidateGraphDelta`` from contracts.
- **No business module imports** (CLAUDE.md §10 #5 + #3) — public.py
  never imports ``main_core`` (regime is read-only data input, not
  code dependency), nor any of ``data_platform`` /
  ``subsystem_announcement`` / ``subsystem_news`` / ``audit_eval`` /
  ``orchestrator`` / ``assembly``.
- **Status Guard** (#7) — health_probe verifies ``Neo4jGraphStatus``
  enum is intact (initializing / ready / reloading / inconsistent /
  blocked); smoke_hook does NOT execute live queries (no real Neo4j
  needed).

graph-engine is a CONSUMER of canonical Ex-3 (re-exports
``CandidateGraphDelta`` / ``GraphSnapshot`` / ``GraphImpactSnapshot``
from contracts), NOT a producer that goes through subsystem-sdk. So
unlike announcement/news public.py, this file does NOT exercise the
``subsystem-sdk.SubmitClient`` path or canonical-wire-mapper.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Final

from graph_engine.version import __version__ as _GRAPH_ENGINE_VERSION


_HEALTHY: Final[str] = "healthy"
_DEGRADED: Final[str] = "degraded"
_DOWN: Final[str] = "blocked"

# Ex types graph-engine CONSUMES (from contracts). graph-engine does
# NOT produce Ex-1/2/3 wire payloads (it consumes Ex-3 / writes Layer
# A snapshots / mirrors to Neo4j); listed here so assembly's compat
# matrix can verify cross-module lineage.
_CONSUMED_EX_TYPES: Final[tuple[str, ...]] = ("Ex-3",)


#: The ONLY missing-module name (exact, full dotted) that the probe
#: accepts as a legitimate offline-first dev miss and downgrades to
#: ``degraded``. Must be the top-level ``contracts`` package itself —
#: an installed ``contracts`` package whose ``schemas`` submodule
#: (or any other ``contracts.*`` submodule, or a transitive dep)
#: is absent is a STRUCTURAL break in the installed package (not a
#: benign offline-first state) and must surface as ``contracts_broken``
#: → ``blocked``. Codex review #13 P2 strict call.
_OFFLINE_FIRST_BENIGN_MISSING_MODULE: Final[str] = "contracts"


def _extract_full_missing_module_name(reason: str) -> str | None:
    """Extract the FULL dotted missing-module name from a
    ``ModuleNotFoundError`` repr embedded in a probe reason string.

    Unlike announcement/news where missing-submodule-of-optional-dep is
    a legitimate offline-first miss (e.g. ``docling.datamodel.base_models``
    is whitelisted in that module's optional-deps set), graph-engine's
    only contracts touchpoint is ``contracts.schemas``. A missing
    ``contracts.schemas`` while ``contracts`` itself is installed
    signals a broken contracts package, not a benign dev miss. So this
    helper deliberately does NOT strip to the top-level segment — the
    caller compares the full dotted name against an exact whitelist.
    Returns ``None`` if the reason doesn't carry a recognizable payload.
    """

    import re

    match = re.search(r"No module named '([^']+)'", reason)
    if match is None:
        return None
    return match.group(1)


def _probe_contracts_re_exports() -> dict[str, Any]:
    """Confirm contracts schemas re-exported by graph_engine.models are
    the IDENTITY (same Python object) of what contracts itself exports.
    A drift here means graph-engine forked the schema (forbidden — only
    contracts owns Ex-3 canonical shape per CLAUDE.md domain rules).

    Codex review #12 P2 fix: split the external ``contracts.schemas``
    import from the in-repo ``graph_engine.models`` import into two
    distinct try blocks — a ``ModuleNotFoundError`` from the in-repo
    chain no longer masquerades as a benign ``contracts_missing``
    state.

    Codex review #13 P2 follow-up: tighten the ``contracts_missing``
    boundary to accept ONLY the literal top-level ``contracts`` package
    being absent. The previous version ran the missing module name
    through a top-level-stripping helper, which conflated "contracts
    package not installed" (legitimate offline-first) with "contracts
    package installed but its ``schemas`` submodule or a transitive
    dep is missing" (structural regression) — the latter was silently
    downgraded to degraded. Now the full dotted name must exactly
    equal ``contracts`` to qualify; everything else → blocked.
    """

    # Step 1: external contracts package (legitimately optional in
    # offline-first dev venvs — but ONLY when the top-level
    # ``contracts`` package itself is absent; a missing submodule of
    # an installed ``contracts`` is a structural break).
    try:
        from contracts.schemas import (
            CandidateGraphDelta as ContractsCandidateGraphDelta,
        )
        from contracts.schemas import GraphImpactSnapshot as ContractsImpact
        from contracts.schemas import GraphSnapshot as ContractsSnapshot
    except ModuleNotFoundError as exc:
        # Exact-match check on the FULL dotted missing-module name.
        # Only ``No module named 'contracts'`` (no dots) qualifies as
        # a benign offline-first dev miss. Anything else — including
        # ``contracts.schemas``, ``contracts.foo``, or transitive
        # deps like ``pydantic`` — signals a broken environment /
        # structural regression and must surface as ``contracts_broken``
        # so the caller blocks.
        missing = _extract_full_missing_module_name(repr(exc))
        if missing == _OFFLINE_FIRST_BENIGN_MISSING_MODULE:
            return {
                "available": False,
                "kind": "contracts_missing",
                "missing_module": missing,
                "reason": (
                    f"top-level 'contracts' package not installed "
                    f"(offline-first dev miss): {exc!r}"
                ),
            }
        return {
            "available": False,
            "kind": "contracts_broken",
            "missing_module": missing,
            "reason": (
                f"contracts schema import failed: {exc!r} "
                f"(missing_module={missing!r} is NOT the literal "
                f"top-level 'contracts' package — this is a structural "
                f"regression in the installed contracts package or "
                f"one of its transitive deps, not a benign dev miss)"
            ),
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {
            "available": False,
            "kind": "contracts_broken",
            "reason": f"contracts schema import failed: {exc!r}",
        }

    # Step 2: in-repo graph_engine.models. Any failure here — including
    # ``ModuleNotFoundError`` for an internal namespace we renamed or
    # deleted by accident — is a real source-side regression and must
    # NOT be tagged ``contracts_missing``.
    try:
        from graph_engine.models import (
            CandidateGraphDelta,
            GraphImpactSnapshot,
            GraphSnapshot,
        )
    except Exception as exc:
        return {
            "available": False,
            "kind": "graph_engine_models_broken",
            "reason": f"graph_engine.models import failed: {exc!r}",
        }

    drift: list[str] = []
    if CandidateGraphDelta is not ContractsCandidateGraphDelta:
        drift.append("CandidateGraphDelta")
    if GraphSnapshot is not ContractsSnapshot:
        drift.append("GraphSnapshot")
    if GraphImpactSnapshot is not ContractsImpact:
        drift.append("GraphImpactSnapshot")
    if drift:
        return {
            "available": False,
            "kind": "drift",
            "reason": (
                "graph_engine.models forked contracts schema for: "
                f"{drift}; CLAUDE.md violation (only contracts owns "
                "canonical Ex-3 / GraphSnapshot / GraphImpactSnapshot)"
            ),
        }
    return {"available": True, "re_exports_verified": ["CandidateGraphDelta", "GraphSnapshot", "GraphImpactSnapshot"]}


def _probe_neo4j_status_literal() -> dict[str, Any]:
    """Confirm ``Neo4jGraphStatus.graph_status`` Literal is intact (3
    canonical states per CLAUDE.md §10 #7 status guard). Drift here
    means a state was silently added/removed and downstream readers
    may guard on a stale set.

    Note: ``Neo4jGraphStatus`` is a ``BaseModel`` (not an Enum); the
    canonical state set is encoded as a ``Literal`` on the
    ``graph_status`` field. We pull it via Pydantic's
    ``model_fields[...].annotation``.
    """

    try:
        from typing import get_args

        from graph_engine.models import Neo4jGraphStatus
    except Exception as exc:  # pragma: no cover - defensive
        return {
            "available": False,
            "reason": f"Neo4jGraphStatus import failed: {exc!r}",
        }

    annotation = Neo4jGraphStatus.model_fields["graph_status"].annotation
    actual = set(get_args(annotation))
    expected = {"ready", "rebuilding", "failed"}
    if actual != expected:
        return {
            "available": False,
            "reason": (
                f"Neo4jGraphStatus.graph_status drifted: expected "
                f"{sorted(expected)}, got {sorted(actual)}"
            ),
        }
    return {"available": True, "status_values": sorted(actual)}


class _HealthProbe:
    """Probe graph-engine-internal invariants without doing any network
    IO or opening a real Neo4j / Postgres connection.

    `check(*, timeout_sec)` returns a structured dict with status one of
    ``healthy`` / ``degraded`` / ``down``. ``timeout_sec`` is accepted
    for assembly Protocol compliance but unused — none of these checks
    do IO.
    """

    _PROBE_NAME: Final[str] = "graph_engine.health"

    def check(self, *, timeout_sec: float) -> dict[str, Any]:
        # Stage 4 §4.3 Lite-stack e2e fix: assembly's
        # ``HealthResult.model_validate`` (per ``assembly.contracts.models
        # .HealthResult``) requires ``module_id``/``probe_name``/
        # ``latency_ms``/``message`` in addition to the ``status``/
        # ``details`` block. Status enum must be one of
        # ``healthy``/``degraded``/``blocked`` (NOT ``"down"`` — that
        # was an internal nomenclature that diverged from the assembly
        # contract). The previous return shape returned only
        # ``status``/``details``/``timeout_sec`` and used ``"down"``,
        # which made assembly's e2e healthcheck collapse this module to
        # ``blocked`` with a generic "validation failed" message,
        # blocking Stage 4 §4.3 evidence collection.
        from time import perf_counter

        started_at = perf_counter()
        details: dict[str, Any] = {
            "consumed_ex_types": list(_CONSUMED_EX_TYPES),
            "canonical_truth_layer": "iceberg",
            "timeout_sec": timeout_sec,
        }

        # Invariant 1: contracts re-exports are identity (no fork —
        # CLAUDE.md domain rule). Codex review #12 P2 fix: probe now
        # splits the external ``contracts.schemas`` import from the in-
        # repo ``graph_engine.models`` import into two separate try
        # blocks, each producing a distinct ``kind`` tag. The caller
        # branches on ``kind`` directly — only ``contracts_missing``
        # (top-level ``contracts`` package absent from this venv —
        # legitimate offline-first dev state) downgrades to
        # ``degraded``. ``graph_engine_models_broken`` /
        # ``contracts_broken`` / ``drift`` always block, so a renamed
        # or deleted in-repo namespace surfaces as a real regression
        # instead of being masked as benign dev-only mode.
        re_exports = _probe_contracts_re_exports()
        details["contracts_re_exports"] = re_exports
        if not re_exports["available"]:
            kind = re_exports.get("kind")
            if kind == "contracts_missing":
                status_after_re_exports = _DEGRADED
                message_after_re_exports = (
                    "graph-engine running in dev-only mode (contracts "
                    "package not importable; functional path unavailable)"
                )
            elif kind == "drift":
                return self._build_result(
                    started_at,
                    status=_DOWN,
                    message=(
                        "graph-engine contracts re-exports forked from "
                        "contracts package — domain invariant violated"
                    ),
                    details=details,
                )
            elif kind == "graph_engine_models_broken":
                return self._build_result(
                    started_at,
                    status=_DOWN,
                    message=(
                        "graph-engine in-repo models import failed — "
                        "source-side regression in graph_engine.models "
                        "or its transitive in-repo deps"
                    ),
                    details=details,
                )
            elif kind == "contracts_broken":
                return self._build_result(
                    started_at,
                    status=_DOWN,
                    message=(
                        "graph-engine contracts schema import failed "
                        "with non-whitelisted error — contracts env "
                        "broken (not a benign offline-first miss)"
                    ),
                    details=details,
                )
            else:
                # Unknown kind — defensive: treat as blocked.
                return self._build_result(
                    started_at,
                    status=_DOWN,
                    message=(
                        "graph-engine contracts re-export check failed "
                        "with unknown error kind — investigate"
                    ),
                    details=details,
                )
        else:
            status_after_re_exports = _HEALTHY
            message_after_re_exports = (
                "graph-engine contracts re-exports identity verified"
            )

        # Invariant 2: Neo4jGraphStatus.graph_status Literal stable
        # (CLAUDE.md §10 #7 status guard depends on this exact 3-state
        # set: ready / rebuilding / failed).
        status_enum = _probe_neo4j_status_literal()
        details["neo4j_status_literal"] = status_enum
        if not status_enum["available"]:
            return self._build_result(
                started_at,
                status=_DOWN,
                message=(
                    "graph-engine Neo4jGraphStatus.graph_status Literal "
                    "drifted — CLAUDE.md §10 #7 status guard broken"
                ),
                details=details,
            )

        return self._build_result(
            started_at,
            status=status_after_re_exports,
            message=message_after_re_exports,
            details=details,
        )

    def _build_result(
        self,
        started_at: float,
        *,
        status: str,
        message: str,
        details: dict[str, Any],
    ) -> dict[str, Any]:
        from time import perf_counter

        return {
            "module_id": "graph-engine",
            "probe_name": self._PROBE_NAME,
            "status": status,
            "latency_ms": max(0.0, (perf_counter() - started_at) * 1000.0),
            "message": message,
            "details": details,
        }


class _SmokeHook:
    """Run a one-shot end-to-end smoke that exercises the canonical
    delta -> promotion plan path WITHOUT opening Neo4j / Postgres.

    1. Build a minimal valid ``CandidateGraphDelta`` (canonical Ex-3
       wire shape that announcement / news produce).
    2. Drive it through the REAL ``promote_graph_deltas`` consumer
       service with stub reader / entity reader / canonical writer
       — covers ``freeze_contract_deltas`` + ``validate_entity_anchors``
       + ``build_promotion_plan`` end-to-end (NOT just schema
       re-validation).
    3. Asserts the resulting ``PromotionPlan`` carries the canonical
       delta forward (cycle / selection / delta_id / edge record
       source/target preserved).

    Codex stage 2.10 review #1 P2 fix: the previous version stopped
    at ``CandidateGraphDelta.model_validate(...)`` which is the
    contracts re-export — calling it didn't exercise any graph-engine
    code and would stay green if ``promote_graph_deltas`` was broken.
    This rewrite drives the real consumer service with
    ``sync_to_live_graph=False`` so no Neo4j / Postgres connection
    is needed (preserves the offline-first smoke contract).

    Profile-aware only insofar as it rejects unknown profile_ids.
    Heavy deps (Neo4j driver / Postgres / GDS) are NEVER imported here.
    """

    _SUPPORTED_PROFILES: Final[frozenset[str]] = frozenset(
        {"lite-local", "full-dev"}
    )

    def run(self, *, profile_id: str) -> dict[str, Any]:
        if profile_id not in self._SUPPORTED_PROFILES:
            return {
                "passed": False,
                "failure_reason": (
                    f"unknown profile_id={profile_id!r}; supported: "
                    f"{sorted(self._SUPPORTED_PROFILES)}"
                ),
                "profile_id": profile_id,
            }

        try:
            from typing import get_args

            from graph_engine import promote_graph_deltas
            from graph_engine.models import (
                CandidateGraphDelta,
                Neo4jGraphStatus,
                PromotionPlan,
            )
        except Exception as exc:
            return {
                "passed": False,
                "failure_reason": (
                    f"graph_engine import failed: {exc!r}"
                ),
                "profile_id": profile_id,
            }

        # Confirm Neo4jGraphStatus.graph_status has the canonical 3
        # states (status guard contract). Smoke does NOT open a real
        # Neo4j connection (would violate the offline-first smoke
        # contract).
        graph_status_values = set(
            get_args(
                Neo4jGraphStatus.model_fields["graph_status"].annotation
            )
        )
        if graph_status_values != {"ready", "rebuilding", "failed"}:
            return {
                "passed": False,
                "failure_reason": (
                    "Neo4jGraphStatus.graph_status drifted from "
                    "canonical 3-state set"
                ),
                "profile_id": profile_id,
            }

        # Build a synthetic but minimally valid CandidateGraphDelta.
        # ``delta_type="upsert_edge"`` and ``relation_type="SUPPLY_CHAIN"``
        # are required to pass graph-engine's promotion-side validators
        # (see promotion/planner.py::_CONTRACT_DELTA_TYPE_TO_INTERNAL +
        # schema/definitions.py::RelationshipType).
        try:
            delta = CandidateGraphDelta(
                subsystem_id="subsystem-news",
                delta_id="smoke-graph-delta-001",
                delta_type="upsert_edge",
                source_node="ENT_GRAPH_SMOKE_SRC",
                target_node="ENT_GRAPH_SMOKE_DST",
                relation_type="SUPPLY_CHAIN",
                properties={"smoke": "minimal"},
                evidence=[
                    "smoke-evidence-ref-001",
                    "smoke-evidence-ref-002",
                ],
            )
        except Exception as exc:
            return {
                "passed": False,
                "failure_reason": (
                    f"CandidateGraphDelta construction failed: {exc!r}"
                ),
                "profile_id": profile_id,
            }

        # Drive REAL ``promote_graph_deltas`` (CONSUMER service) with
        # in-memory stub reader / entity reader / canonical writer so
        # no IO is required. ``sync_to_live_graph=False`` skips the
        # Neo4j sync path (which would need a real driver).
        cycle_id = "smoke-graph-cycle-001"
        selection_ref = "smoke-graph-selection-001"
        canonical_writes: list[Any] = []

        class _StubReader:
            def read_candidate_graph_deltas(
                self, _cid: str, _sref: str
            ) -> list[CandidateGraphDelta]:
                return [delta]

        class _StubEntityReader:
            def canonical_entity_ids_for_node_ids(
                self, node_ids: set[str]
            ) -> dict[str, str]:
                # Resolve every node id to itself (sentinel: smoke
                # entities are already canonical).
                return {nid: nid for nid in node_ids}

            def existing_entity_ids(
                self, entity_ids: set[str]
            ) -> set[str]:
                return set(entity_ids)

        class _StubCanonicalWriter:
            def write_canonical_records(self, plan: PromotionPlan) -> None:
                canonical_writes.append(plan)

        try:
            plan = promote_graph_deltas(
                cycle_id=cycle_id,
                selection_ref=selection_ref,
                candidate_reader=_StubReader(),
                entity_reader=_StubEntityReader(),
                canonical_writer=_StubCanonicalWriter(),
                sync_to_live_graph=False,
            )
        except Exception as exc:
            return {
                "passed": False,
                "failure_reason": (
                    f"promote_graph_deltas raised: {exc!r}"
                ),
                "profile_id": profile_id,
            }

        # Verify CLAUDE.md §10 #1 (truth-before-mirror): canonical
        # writer was invoked with the returned plan exactly once.
        if canonical_writes != [plan]:
            return {
                "passed": False,
                "failure_reason": (
                    f"canonical_writer.write_canonical_records called "
                    f"{len(canonical_writes)} times with "
                    f"{[id(p) for p in canonical_writes]} (expected "
                    f"exactly [plan id={id(plan)}])"
                ),
                "profile_id": profile_id,
            }

        # Verify the plan carries the canonical delta forward.
        if delta.delta_id not in plan.delta_ids:
            return {
                "passed": False,
                "failure_reason": (
                    f"PromotionPlan.delta_ids missing canonical "
                    f"delta_id {delta.delta_id!r}; got {plan.delta_ids}"
                ),
                "profile_id": profile_id,
            }
        if not plan.edge_records:
            return {
                "passed": False,
                "failure_reason": (
                    "PromotionPlan.edge_records empty; "
                    "upsert_edge candidate must produce at least one "
                    "GraphEdgeRecord"
                ),
                "profile_id": profile_id,
            }

        return {
            "passed": True,
            "profile_id": profile_id,
            "details": {
                "delta_id": delta.delta_id,
                "delta_type": delta.delta_type,
                "relation_type": delta.relation_type,
                "evidence_count": len(delta.evidence),
                "promotion_plan_cycle_id": plan.cycle_id,
                "promotion_plan_delta_count": len(plan.delta_ids),
                "promotion_plan_edge_record_count": len(plan.edge_records),
                "consumed_ex_types": list(_CONSUMED_EX_TYPES),
                "canonical_truth_layer": "iceberg",
            },
        }


class _InitHook:
    """No-op initialization. graph-engine has no global mutable state to
    set up at bootstrap (Neo4j driver / Postgres status store are
    constructed per-call inside the runtime services, not eagerly at
    import time). Returns ``None`` per assembly Protocol;
    ``resolved_env`` is accepted for compliance.
    """

    def initialize(self, *, resolved_env: dict[str, str]) -> None:
        _ = resolved_env
        return None


class _VersionDeclaration:
    """Declare the graph-engine + contracts schema versions assembly
    should reconcile in the registry. Returns a stable dict shape:

        {
            "module_id": "graph-engine",
            "module_version": "<package version>",
            "consumed_ex_types": ["Ex-3"],
            "contract_version": "<contracts schema version or 'unknown'>",
            "neo4j_status_enum_values": [...],
            "canonical_truth_layer": "iceberg",
        }

    Note: ``consumed_ex_types`` (NOT ``supported_ex_types``) — graph-
    engine is a CONSUMER of Ex-3 candidates, not a producer. The
    semantic distinction matters for assembly's cross-module lineage
    matrix (announcement / news / etc. PRODUCE Ex-1/2/3; graph-engine
    CONSUMES Ex-3 + WRITES GraphSnapshot / GraphImpactSnapshot back to
    Layer A).
    """

    def declare(self) -> dict[str, Any]:
        # Stage 4 §4.1.5: include compatible_contract_range so assembly's
        # VersionInfo (model_config = ConfigDict(extra="forbid")) accepts
        # this declaration. Without compatible_contract_range, VersionInfo
        # validation reports `Field required` and the contract suite
        # blocks Stage 4 promotion. The range matches the contracts
        # package versions graph-engine is built against.
        return {
            "module_id": "graph-engine",
            "module_version": _GRAPH_ENGINE_VERSION,
            "contract_version": self._safe_contract_version(),
            "compatible_contract_range": ">=0.1.3,<0.2.0",
            "consumed_ex_types": list(_CONSUMED_EX_TYPES),
            "neo4j_status_enum_values": self._safe_status_enum_values(),
            # CLAUDE.md §10 #1 truth-before-mirror invariant: Iceberg is
            # the canonical truth, Neo4j is the hot mirror only. Marker
            # is structural so assembly compat checks can verify it.
            "canonical_truth_layer": "iceberg",
        }

    @staticmethod
    def _safe_contract_version() -> str:
        # Returns the contracts package version with the canonical ``v``
        # prefix required by assembly's ``ContractVersion`` regex
        # (``^v\d+\.\d+\.\d+$``); see
        # ``assembly/src/assembly/contracts/primitives.py``. The bare
        # ``contracts.__version__`` (e.g. ``"0.1.3"``) would fail that
        # regex, blocking any registry contract_version upgrade.
        # Exception path keeps ``"unknown"`` as the explicit degraded-state
        # marker — callers (Stage 4 §4.1 registry upgrade) detect it and
        # leave the registry's ``contract_version`` at ``v0.0.0``.
        try:
            from contracts import __version__ as contracts_version

            return f"v{contracts_version}"
        except Exception:
            return "unknown"

    @staticmethod
    def _safe_status_enum_values() -> list[str]:
        try:
            from typing import get_args

            from graph_engine.models import Neo4jGraphStatus

            return sorted(
                get_args(
                    Neo4jGraphStatus.model_fields["graph_status"].annotation
                )
            )
        except Exception:
            return []


class _Cli:
    """Tiny graph-engine CLI for assembly's smoke probes; intentionally
    minimal to keep iron rule #2 boundary (no business logic in CLI).
    Supported argv:

    - ``["version"]`` — print version_declaration JSON to stdout, exit 0
    - ``["health", "--timeout-sec", "<float>"]`` — print health JSON,
      exit 0 on healthy/degraded, 1 on down
    - ``["smoke", "--profile-id", "<id>"]`` — print smoke JSON, exit 0
      on passed, 1 on failed
    """

    def invoke(self, argv: list[str]) -> int:
        if not argv:
            sys.stderr.write(
                "usage: graph-engine-cli "
                "{version|health|smoke} [args]\n"
            )
            return 2

        command = argv[0]
        rest = argv[1:]

        if command == "version":
            sys.stdout.write(
                json.dumps(version_declaration.declare()) + "\n"
            )
            return 0

        if command == "health":
            timeout_sec = self._parse_kw_float(
                rest, "--timeout-sec", default=1.0
            )
            if timeout_sec is None:
                return 2
            result = health_probe.check(timeout_sec=timeout_sec)
            sys.stdout.write(json.dumps(result) + "\n")
            return 0 if result["status"] in {_HEALTHY, _DEGRADED} else 1

        if command == "smoke":
            profile_id = self._parse_kw_str(
                rest, "--profile-id", default=None
            )
            if profile_id is None:
                sys.stderr.write("smoke requires --profile-id <id>\n")
                return 2
            result = smoke_hook.run(profile_id=profile_id)
            sys.stdout.write(json.dumps(result) + "\n")
            return 0 if result.get("passed") else 1

        sys.stderr.write(f"unknown command: {command!r}\n")
        return 2

    @staticmethod
    def _parse_kw_float(
        rest: list[str], flag: str, *, default: float
    ) -> float | None:
        if flag not in rest:
            return default
        idx = rest.index(flag)
        if idx + 1 >= len(rest):
            sys.stderr.write(f"{flag} requires a value\n")
            return None
        try:
            return float(rest[idx + 1])
        except ValueError:
            sys.stderr.write(
                f"{flag} must be a float; got {rest[idx + 1]!r}\n"
            )
            return None

    @staticmethod
    def _parse_kw_str(
        rest: list[str], flag: str, *, default: str | None
    ) -> str | None:
        if flag not in rest:
            return default
        idx = rest.index(flag)
        if idx + 1 >= len(rest):
            sys.stderr.write(f"{flag} requires a value\n")
            return None
        return rest[idx + 1]


# Module-level singleton instances — assembly registry references these
# by their lowercase attribute names (not the underscore-prefixed classes).
health_probe = _HealthProbe()
smoke_hook = _SmokeHook()
init_hook = _InitHook()
version_declaration = _VersionDeclaration()
cli = _Cli()


__all__ = [
    "cli",
    "health_probe",
    "init_hook",
    "smoke_hook",
    "version_declaration",
]
