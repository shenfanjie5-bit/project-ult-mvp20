# graph-engine

Graph promotion + propagation + Cold Reload + readonly subgraph
queries. Sole owner of:

- Layer A canonical graph truth → Neo4j live-graph promotion
- fundamental / event / reflexive propagation channels
- `graph_snapshot` + `graph_impact_snapshot` writeback
- `neo4j_graph_status` + Cold Reload closed loop
- readonly subgraph queries + readonly local impact simulation

Source of truth:

- `docs/graph-engine.project-doc.md`
- `docs/PROPAGATION_CANARY_RUNBOOK.md` (holdings-only propagation
  canary guardrails and evidence checklist)
- `CLAUDE.md` (project-specific guardrails — domain rules, status
  guard, blocker triggers)

## Position in the system

graph-engine is a **CONSUMER** of canonical Ex-3
(`CandidateGraphDelta`) re-exported from `contracts.schemas`. It does
NOT produce Ex-1/2/3 wire payloads (those come from announcement /
news / other subsystem producers). It does NOT exercise
`subsystem-sdk.SubmitClient` — that's the producer side.

M4.4 live bridge evidence was produced on 2026-05-03 from a real
`data-platform.candidate_queue` Ex-3 row through `PostgresCandidateDeltaReader`
into `promote_graph_deltas(..., sync_to_live_graph=False)`, yielding a
`PromotionPlan` with edge output. Evidence is recorded under assembly's
`reports/stabilization/m4-bridge-live-proof-20260503.md`.

## Holdings graph support plan

The next domain extension is holdings graph support, but it must stay within
the existing graph-engine boundary: consume canonical Ex-3 only, promote to
Layer A first, then sync Neo4j.

Implemented interface/type decisions:

- Do **not** add holdings-specific Pydantic models in `contracts`; producers
  continue to submit `Ex3CandidateGraphDelta`.
- Add only two graph relationship enum values for holdings:
  `RelationshipType.CO_HOLDING` and `RelationshipType.NORTHBOUND_HOLD`.
- `CO_HOLDING` means a fund/portfolio entity holds a listed-security entity;
  holdings producers may include `producer_context.graph_node_upserts` when
  a source or target endpoint node is not already present. `graph_node_upserts`
  are holdings-only (`CO_HOLDING` / `NORTHBOUND_HOLD`), endpoint-only, must
  not conflict with an existing endpoint mapping, and every upserted
  `canonical_entity_id` must already exist as a public entity-registry anchor
  confirmed by `EntityAnchorReader.existing_entity_ids`; graph-engine and
  producers do not create canonical entities in issue #56.
- `NORTHBOUND_HOLD` means northbound aggregate capital holds or changes a
  position in a listed-security entity.
- Represent top shareholder relationships with existing `OWNERSHIP`.
- Represent pledge status as `OWNERSHIP` properties such as `pledge_ratio`;
  do not add a separate `PLEDGE_STATUS` relationship.
- Issue #56 covers enum, planner, query, and propagation-channel support only.
- Issue #55 is narrowed to holdings-only algorithms. The current
  implementation adds explicit entry points for `CO_HOLDING`
  co-holding crowding and `NORTHBOUND_HOLD` northbound anomaly:
  `HoldingsAlgorithmConfig`, `run_co_holding_crowding`,
  `run_northbound_anomaly`, and `run_holdings_algorithms`.
- The #55 implementation is deliberately **not** wired into
  `run_full_propagation`; callers must opt in through the explicit
  holdings entry points so the generic event/reflexive channels do not
  double-count the same holdings edges.
- Old #55 references to guarantees, related-party/financial-doc
  propagation, contracts subtype work, `MAJOR_CUSTOMER`, and
  `MAJOR_SUPPLIER` are superseded for the current execution scope.
  This module still does not add `TOP_SHAREHOLDER` or `PLEDGE_STATUS`.
- This is algorithm-level support over a ready live graph read. It does
  not claim production rollout to live Neo4j, graph writeback, or new
  cross-module contracts.

Current bounded canary / live-evidence state:

- Bounded gated canary / live production evidence status: **PASS** for
  the guarded proof/canary path only. This covers holdings-scoped
  `CO_HOLDING` / `NORTHBOUND_HOLD` candidates, Layer A artifact evidence,
  guarded live-graph sync/readback, explicit holdings algorithm summaries,
  and CI evidence from the proof/canary hardening PRs.
- Production hardening prerequisites and guards have landed for that
  bounded path: explicit environment confirmation, safe namespace and
  artifact-root validation, non-default disposable Neo4j database labels,
  client database match checks, ready-status checks, relationship
  allowlists, evidence manifests, and sanitized proof outputs.
- This PASS does **not** mean default or full propagation is enabled. It
  does **not** mean broad production rollout is complete. It does **not**
  complete M4.7 / financial-doc scope, add contracts subtypes, or expand
  the relationship scope beyond `CO_HOLDING` / `NORTHBOUND_HOLD`.

Next step after the bounded canary evidence is post-canary
operationalization using the hardened runbook in
`docs/PROPAGATION_CANARY_RUNBOOK.md`. Only after that should the project
evaluate a controlled opt-in canary for default propagation; it should
still remain gated and should not be documented as default-enabled or
broadly rolled out until separate evidence lands.

## MVP20 Read Context

`graph_engine.query.query_mvp20_context_subgraph` is the MVP20 read-side
helper. It delegates to the status-gated `query_subgraph` path with graph
depth fixed at `2`, requires exactly 20 decision target entity ids, and
annotates returned nodes/edges as `decision_target` or `context_only`.

This helper is context-only. It does not enable default propagation, full
propagation, write routes, new relationships, financial-doc/M4.7 behavior,
or broad rollout semantics.

CLAUDE.md §10 domain invariants this module enforces by construction:

- **Truth Before Mirror** (#1): Iceberg is canonical truth; Neo4j is
  the hot mirror only. Cold Reload always rebuilds from Iceberg.
- **Promotion Before Propagation** (#2): Layer A write succeeds first,
  then Neo4j sync. Never write Neo4j without Layer A first.
- **Regime Is Read-only** (#3): `world_state_snapshot` is data input
  only; this module never imports `main_core.*`.
- **Readonly Simulation** (#4): event-driven local simulation reads
  the live graph, never writes it; never produces formal snapshots.
- **No Raw Text** (#6): no `lightrag` / `langchain` / `docling`; only
  contracted `CandidateGraphDelta`.
- **Status Guard** (#7): `Neo4jGraphStatus.graph_status` Literal is
  pinned to the canonical 3-state set
  `{"ready", "rebuilding", "failed"}`. Live-graph reads must check
  status before proceeding.

## Public API surface

`graph_engine.public` exposes 5 module-level singleton instances that
match the assembly Protocols
(`assembly.contracts.entrypoints`):

| singleton | method | purpose |
|---|---|---|
| `health_probe` | `check(*, timeout_sec: float)` | probe domain invariants without IO; returns `HealthResult`-conformant dict |
| `smoke_hook` | `run(*, profile_id: str)` | drive `promote_graph_deltas` with stub IO; one-shot end-to-end |
| `init_hook` | `initialize(*, resolved_env: dict[str, str])` | no-op (no global mutable state) |
| `version_declaration` | `declare()` | `{module_id, module_version, contract_version, compatible_contract_range, consumed_ex_types, neo4j_status_enum_values, canonical_truth_layer}` |
| `cli` | `invoke(argv: list[str])` | `version` / `health` / `smoke` subcommands |

## Health probe boundary (4-way `kind` taxonomy)

`_probe_contracts_re_exports()` distinguishes four structurally
distinct failure modes — the probe boundary went through codex review
#11 / #12 / #13 to land at this shape. The caller branches on `kind`
directly without parsing reason strings.

| `kind` | trigger | health status |
|---|---|---|
| `contracts_missing` | top-level `contracts` package absent (exact `No module named 'contracts'`) | `degraded` (offline-first dev only) |
| `contracts_broken` | `contracts.schemas` submodule (or any other `contracts.*` submodule, or transitive dep) missing while `contracts` itself is installed | `blocked` (structural break in installed package) |
| `graph_engine_models_broken` | any failure importing `graph_engine.models` (renamed/deleted internal namespace, broken in-repo dep) | `blocked` (in-repo regression) |
| `drift` | `graph_engine.models.{CandidateGraphDelta, GraphSnapshot, GraphImpactSnapshot}` is not the SAME Python object as `contracts.schemas.*` | `blocked` (forked schema — CLAUDE.md domain violation) |

The exact-match check on the FULL dotted missing-module name is
deliberate: a missing submodule of an installed package is a
structural regression, not a benign offline-first miss. Submodule
misses must NOT be silently downgraded.

The boundary is regression-protected by 5 tests in
`tests/contract/test_runtime_contract.py::TestContractsReExportProbeBoundary`
including `test_probe_tags_contracts_schemas_submodule_miss_as_contracts_broken`
which guards against re-introducing the codex #13 P2 conflation.

## Test baseline

```bash
.venv/bin/python -m pytest tests/contract/                    # public API + kind-tag boundary
.venv/bin/python -m pytest tests/smoke/                       # 5 singletons end-to-end
.venv/bin/python -m pytest tests/boundary/                    # CLAUDE.md red-line guards
.venv/bin/python -m pytest tests/regression/                  # shared-fixture cases
.venv/bin/python -m pytest tests/integration/                 # subgraph query / propagation
```

Focused #56 holdings evidence:

```bash
.venv/bin/python -m pytest tests/contract/test_contracts_alignment.py \
  tests/unit/test_schema.py tests/unit/test_promotion.py \
  tests/unit/test_query.py tests/unit/test_propagation_channels.py \
  tests/boundary/test_red_lines.py -q
```

Focused #55 holdings-only algorithm evidence:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider -q \
  tests/unit/test_propagation_holdings.py tests/unit/test_propagation_merge.py \
  tests/unit/test_snapshots.py tests/unit/test_propagation_channels.py \
  tests/unit/test_schema.py tests/boundary/test_red_lines.py
```

Focused propagation canary / runbook hardening evidence:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider -q \
  tests/unit/test_rollout.py tests/unit/test_rollout_runbook.py \
  tests/unit/test_holdings_live_graph_proof.py
```

Refresh global pass/skip counts only after running the full suite in the
current venv; this README intentionally avoids a stale full-suite count.

## Execution rules

1. Read `docs/graph-engine.project-doc.md` and the §10 red-line list
   in `CLAUDE.md` first.
2. Keep work inside this module; never reverse-import `main-core` /
   `data-platform` / `subsystem-*` / `audit-eval` / `orchestrator` /
   `assembly`. Cross-module data flows through `contracts.schemas`
   types.
3. Single Issue covers one capability — promotion / propagation /
   reload-status / query-simulation. Do not bundle.
4. Health probe + smoke hook MUST stay offline-first (no real Neo4j /
   Postgres connection at module load or probe time).

## Position in module set

| upstream | this module | downstream |
|---|---|---|
| contracts (Ex-3 schema), entity-registry (canonical IDs) | graph-engine (promotion + propagation) | main-core (snapshot reads), audit-eval (history), orchestrator (Phase 0/1) |
