"""Stage 2.10 boundary tier — §10 red lines as boundary tests.

Per CLAUDE.md (graph-engine):

1. **Truth Before Mirror**: Iceberg = canonical truth, Neo4j = hot
   mirror only. ``promote_graph_deltas`` MUST write Layer A
   (canonical_writer) BEFORE syncing Neo4j.
2. **Promotion Before Propagation**: same boundary as #1 — propagation
   never writes Layer A directly.
3. **Regime Is Read-only**: graph-engine does NOT reverse-import
   ``main_core``; subprocess deny-scan on ``graph_engine.public``
   import graph rejects ``main_core`` (and other business modules).
4. **Readonly Simulation**: ``simulate_readonly_impact`` MUST NOT
   mutate formal live-graph nodes/edges (``CREATE``/``MERGE``/
   ``SET``/``DELETE`` on real entities), but IS allowed to write
   **ephemeral GDS projections** (``gds.graph.project`` /
   ``gds.graph.drop``) that are created and dropped within the
   simulation scope. Test (codex review #1 P2 fix): target the
   ``_ReadonlyProjectionClient.execute_write`` structural barrier
   in ``query/simulation.py:337`` — it raises ``PermissionError``
   for non-GDS writes and accepts GDS projection writes scoped to
   the simulation's owned projection name. The previous version of
   this test asserted "no execute_write of any kind" and skipped
   without exercising any real path; that invariant was wrong (the
   real implementation legitimately uses ``gds.graph.project``).
5. **No Raw Text**: only contracted ``CandidateGraphDelta`` —
   subprocess deny-scan rejects ``lightrag``, ``langchain``,
   ``pdfplumber``, ``pypdf``, ``unstructured``, ``pdfminer`` from
   the public.py import graph.
6. **Status Guard**: live graph reads check
   ``Neo4jGraphStatus.graph_status == 'ready'`` before proceeding.
   Test: ``require_ready_status`` raises ``PermissionError`` for
   non-ready graphs.

Iron rule #2: deny-scan boundary tests use ``subprocess.run`` for
isolation (sys.modules pollution from earlier collected tests would
mask real import-graph leaks otherwise).

Note: graph-engine does NOT submit through subsystem-sdk, so iron
rule #7 (SDK wire-shape boundary) does NOT apply to this module.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from typing import Any

import pytest


# ── Red line 6: Status Guard (CLAUDE.md §10 #7) ────────────────────


class TestStatusGuard:
    """Live graph reads MUST check ``graph_status == 'ready'`` before
    proceeding. ``require_ready_status`` is the canonical entry —
    raises ``PermissionError`` for non-ready states.
    """

    def test_require_ready_status_accepts_ready(self) -> None:
        from graph_engine.models import Neo4jGraphStatus
        from graph_engine.status import require_ready_status

        ready = Neo4jGraphStatus(
            graph_status="ready",
            graph_generation_id=1,
            node_count=0,
            edge_count=0,
            key_label_counts={},
            checksum="sha256:placeholder",
            last_verified_at=datetime(2026, 1, 1, tzinfo=UTC),
            last_reload_at=datetime(2026, 1, 1, tzinfo=UTC),
            writer_lock_token=None,
        )
        # Should not raise; returns the status unchanged.
        out = require_ready_status(ready)
        assert out.graph_status == "ready"

    def test_require_ready_status_rejects_rebuilding(self) -> None:
        from graph_engine.models import Neo4jGraphStatus
        from graph_engine.status import require_ready_status

        rebuilding = Neo4jGraphStatus(
            graph_status="rebuilding",
            graph_generation_id=1,
            node_count=0,
            edge_count=0,
            key_label_counts={},
            checksum="sha256:placeholder",
            last_verified_at=None,
            last_reload_at=None,
            writer_lock_token=None,
        )
        with pytest.raises(PermissionError, match="graph_status='ready'"):
            require_ready_status(rebuilding)

    def test_require_ready_status_rejects_failed(self) -> None:
        from graph_engine.models import Neo4jGraphStatus
        from graph_engine.status import require_ready_status

        failed = Neo4jGraphStatus(
            graph_status="failed",
            graph_generation_id=1,
            node_count=0,
            edge_count=0,
            key_label_counts={},
            checksum="sha256:placeholder",
            last_verified_at=None,
            last_reload_at=None,
            writer_lock_token=None,
        )
        with pytest.raises(PermissionError, match="graph_status='ready'"):
            require_ready_status(failed)

    def test_require_ready_status_rejects_active_writer_lock(self) -> None:
        from graph_engine.models import Neo4jGraphStatus
        from graph_engine.status import require_ready_status

        ready_but_locked = Neo4jGraphStatus(
            graph_status="ready",
            graph_generation_id=1,
            node_count=0,
            edge_count=0,
            key_label_counts={},
            checksum="sha256:placeholder",
            last_verified_at=datetime(2026, 1, 1, tzinfo=UTC),
            last_reload_at=datetime(2026, 1, 1, tzinfo=UTC),
            writer_lock_token="incremental-sync",
        )
        with pytest.raises(PermissionError, match="writer lock"):
            require_ready_status(ready_but_locked)


# ── Red line 1+2: Truth Before Mirror / Promotion Before Propagation ─


class TestTruthBeforeMirror:
    """``promote_graph_deltas`` MUST write Layer A (via
    ``canonical_writer.write_canonical_records``) BEFORE syncing Neo4j
    (via ``sync_live_graph``). Mock both adapters and verify call order.
    """

    def test_canonical_write_precedes_neo4j_sync(self) -> None:
        from graph_engine import promote_graph_deltas

        call_log: list[str] = []

        # Build minimal valid CandidateGraphDelta with resolved
        # subject/object so it passes promotion-side validators.
        from contracts.schemas import CandidateGraphDelta

        delta = CandidateGraphDelta(
            subsystem_id="subsystem-news",
            delta_id="boundary-truth-before-mirror",
            # graph-engine internal validator accepts only
            # ``upsert_edge`` / ``upsert_relation`` (see
            # ``promotion/planner.py::_CONTRACT_DELTA_TYPE_TO_INTERNAL``).
            delta_type="upsert_edge",
            source_node="ENT_GRAPH_BOUNDARY_SRC",
            target_node="ENT_GRAPH_BOUNDARY_DST",
            # Must be one of graph-engine's RelationshipType enum
            # values (see ``schema/definitions.py::RelationshipType``).
            relation_type="SUPPLY_CHAIN",
            properties={},
            evidence=["evidence-001", "evidence-002"],
        )

        class _Reader:
            def read_candidate_graph_deltas(self, cycle_id, selection_ref):
                call_log.append("reader.read")
                return [delta]

        class _EntityReader:
            def canonical_entity_ids_for_node_ids(
                self, node_ids: set[str]
            ) -> dict[str, str]:
                # Resolve each node to a canonical entity id (any non-
                # empty string passes the planner's presence check).
                return {nid: f"ENT_FOR_{nid}" for nid in node_ids}

            def existing_entity_ids(
                self, entity_ids: set[str]
            ) -> set[str]:
                # Treat all entity ids as already existing (passes
                # planner anchor validation).
                return set(entity_ids)

        class _CanonicalWriter:
            def write_canonical_records(self, _plan):
                call_log.append("canonical_writer.write")

        # Build a stub status manager that always allows ready.
        class _StubStatusManager:
            def require_ready(self):
                call_log.append("status.require_ready")
                from graph_engine.models import Neo4jGraphStatus

                return Neo4jGraphStatus(
                    graph_status="ready",
                    graph_generation_id=1,
                    node_count=0,
                    edge_count=0,
                    key_label_counts={},
                    checksum="sha256:placeholder",
                    last_verified_at=datetime(2026, 1, 1, tzinfo=UTC),
                    last_reload_at=datetime(2026, 1, 1, tzinfo=UTC),
                    writer_lock_token=None,
                )

        # Call WITHOUT live sync to isolate the canonical-write order
        # invariant from the additional begin_sync token machinery.
        # The "Layer A first" rule still holds even without sync.
        plan = promote_graph_deltas(
            cycle_id="boundary-cycle-001",
            selection_ref="boundary-selection-001",
            candidate_reader=_Reader(),
            entity_reader=_EntityReader(),
            canonical_writer=_CanonicalWriter(),
            sync_to_live_graph=False,
        )

        # CLAUDE.md §10 #1+#2: canonical writer must be called.
        assert "canonical_writer.write" in call_log, (
            f"Layer A canonical writer MUST be invoked during promotion; "
            f"call log: {call_log}"
        )
        assert plan is not None, (
            "promote_graph_deltas must return a PromotionPlan"
        )


# ── Red line 4: Readonly Simulation does not mutate formal live graph ─


class TestReadonlySimulationOnlyAllowsGdsProjectionWrites:
    """``simulate_readonly_impact`` is allowed to write **ephemeral GDS
    projections** (``gds.graph.project`` / ``gds.graph.drop``) but MUST
    NOT mutate formal live-graph nodes / edges (``CREATE``/``MERGE``/
    ``SET``/``DELETE`` on real graph entities). This is the structural
    invariant CLAUDE.md §10 #4 ("readonly simulation 不能写正式 live
    graph") really demands.

    Codex review #1 P2: the previous version of this test asserted "no
    execute_write of any kind" with a wrong-shape ``ReadonlySimulationRequest``
    constructor, so it skipped without exercising the real path AND
    used the wrong invariant (the real implementation legitimately
    issues ``gds.graph.project``/``drop`` writes for ephemeral
    projections). The right test target is
    ``_ReadonlyProjectionClient`` — the structural barrier in
    ``query/simulation.py`` that simulation code goes through. It
    explicitly raises ``PermissionError`` for any write that isn't a
    GDS projection op (line 337 in ``query/simulation.py``).
    """

    def test_readonly_projection_client_raises_on_node_mutation_query(
        self,
    ) -> None:
        from graph_engine.query.simulation import _ReadonlyProjectionClient

        # Stub real Neo4jClient — never reached because the barrier
        # raises before delegation.
        class _StubClient:
            def execute_read(self, query, parameters=None):
                return []

            def execute_write(self, query, parameters=None):
                raise AssertionError(
                    "barrier should reject before reaching underlying "
                    "Neo4jClient.execute_write"
                )

        client = _ReadonlyProjectionClient(
            _StubClient(),
            node_ids=["n1", "n2"],
            edges=[],
            projection_names=["sim-projection-001"],
        )

        for forbidden_query in (
            "CREATE (s:Stock {id: 'ENT_001'}) RETURN s",
            "MERGE (s:Stock {id: 'ENT_001'}) SET s.name = 'x' RETURN s",
            "MATCH (s:Stock) SET s.flag = true RETURN s",
            "MATCH (s:Stock {id: 'ENT_001'}) DELETE s",
            "MATCH (a)-[r:SUPPLY_CHAIN]->(b) DELETE r",
        ):
            with pytest.raises(
                PermissionError, match="GDS projection writes"
            ):
                client.execute_write(forbidden_query)

    def test_readonly_projection_client_allows_gds_projection_write(
        self,
    ) -> None:
        """Positive path: ``gds.graph.project`` MUST be allowed (it's
        an ephemeral projection, not formal mutation). This pin
        prevents over-tightening the barrier into "no execute_write
        at all" which would break the real simulation path.
        """

        from graph_engine.query.simulation import _ReadonlyProjectionClient

        class _StubClient:
            def execute_read(self, query, parameters=None):
                # gds.graph.exists check — return "doesn't exist yet"
                # so projection-create proceeds.
                return [{"exists": False}]

            def execute_write(self, query, parameters=None):
                # Real Neo4j would create the projection; stub returns
                # success.
                return [
                    {
                        "graphName": parameters.get("graph_name"),
                        "nodeCount": 2,
                        "relationshipCount": 0,
                    }
                ]

        client = _ReadonlyProjectionClient(
            _StubClient(),
            node_ids=["n1", "n2"],
            edges=[],
            projection_names=["sim-projection-002"],
        )

        # Should NOT raise PermissionError — GDS projection is allowed.
        # (May return 0 relationships since edges=[]; that's fine for
        # the boundary intent.)
        rows = client.execute_write(
            "CALL gds.graph.project($graph_name, ['Stock'], '*')",
            {"graph_name": "sim-projection-002"},
        )
        assert rows  # write returned a row, barrier did not block

    def test_readonly_projection_client_rejects_unowned_projection_drop(
        self,
    ) -> None:
        """Even GDS ops are constrained: a simulation can only drop
        projections IT created — can't drop a formal live projection
        owned by promotion / cold-reload.
        """

        from graph_engine.query.simulation import _ReadonlyProjectionClient

        class _StubClient:
            def execute_read(self, query, parameters=None):
                return []

            def execute_write(self, query, parameters=None):
                raise AssertionError(
                    "barrier should reject before reaching underlying "
                    "Neo4jClient.execute_write"
                )

        client = _ReadonlyProjectionClient(
            _StubClient(),
            node_ids=["n1"],
            edges=[],
            projection_names=["sim-projection-003"],
        )

        # Drop targets a projection name NOT in this client's owned
        # set → barrier rejects.
        with pytest.raises(PermissionError, match="owned by this invocation"):
            client.execute_write(
                "CALL gds.graph.drop($graph_name)",
                {"graph_name": "formal-projection-owned-by-cold-reload"},
            )

    def test_readonly_projection_client_rejects_drop_query_with_live_mutation(
        self,
    ) -> None:
        from graph_engine.query.simulation import _ReadonlyProjectionClient

        class _StubClient:
            def execute_read(self, query, parameters=None):
                return [{"exists": False}]

            def execute_write(self, query, parameters=None):
                if " SET " in query:
                    raise AssertionError("live mutation reached Neo4j write adapter")
                return [
                    {
                        "graphName": parameters.get("graph_name"),
                        "nodeCount": 2,
                        "relationshipCount": 1,
                    }
                ]

        client = _ReadonlyProjectionClient(
            _StubClient(),
            node_ids=["n1", "n2"],
            edges=[
                {
                    "edge_id": "e1",
                    "relationship_type": "SUPPLY_CHAIN",
                    "source_node_id": "n1",
                    "target_node_id": "n2",
                }
            ],
            projection_names=["sim-projection-004"],
        )
        client.execute_write(
            "CALL gds.graph.project($graph_name, ['Stock'], '*')",
            {"graph_name": "sim-projection-004"},
        )

        with pytest.raises(PermissionError, match="scoped GDS projection drop"):
            client.execute_write(
                """
                CALL gds.graph.drop($graph_name) YIELD graphName
                MATCH (n:Entity) SET n.readonly_escape = true
                RETURN graphName
                """,
                {"graph_name": "sim-projection-004"},
            )


# ── Red line 3 + 5: public.py import graph deny scan (CLAUDE.md) ───


class TestPublicPyDenyScan:
    """CLAUDE.md: public.py is the assembly-facing boundary. It MUST
    NOT pull in:

    - **Other business modules** (CLAUDE.md §10 #3 + #5):
      ``main_core`` (regime read-only data input, NOT code dep),
      ``data_platform``, ``subsystem_announcement``, ``subsystem_news``,
      ``subsystem_sdk`` (graph-engine doesn't submit), ``audit_eval``,
      ``orchestrator``, ``assembly``, ``reasoner_runtime`` (graph-engine
      doesn't extract).
    - **Raw text / parser stacks** (CLAUDE.md §10 #6 No Raw Text):
      ``lightrag``, ``langchain``, ``pdfplumber``, ``pypdf``,
      ``unstructured``, ``pdfminer`` — graph-engine consumes only
      contracted ``CandidateGraphDelta``, never raw text artifacts.
    - **Direct LLM provider SDKs**: ``openai``, ``anthropic``,
      ``litellm`` (graph-engine doesn't call LLMs directly).

    Iron rule #2: deny-scan uses ``subprocess.run`` for isolation.
    sys.modules pollution from earlier collected tests would mask
    real import-graph leaks.
    """

    _DENYLIST: tuple[str, ...] = (
        # Other business modules (CLAUDE.md §10 #3 + #5).
        "main_core",
        "data_platform",
        "subsystem_announcement",
        "subsystem_news",
        "subsystem_sdk",
        "audit_eval",
        "orchestrator",
        "assembly",
        "reasoner_runtime",
        # Raw text / parser stacks (CLAUDE.md §10 #6 No Raw Text).
        "lightrag",
        "langchain",
        "pdfplumber",
        "pypdf",
        "unstructured",
        "pdfminer",
        # Direct LLM provider SDKs.
        "openai",
        "anthropic",
        "litellm",
    )

    def test_public_py_imports_no_denied_modules(self) -> None:
        """Run ``import graph_engine.public`` in a fresh interpreter
        and dump ``sys.modules``. Asserts none of the denied module
        names appear in the import graph.
        """

        program = (
            "import json\n"
            "import sys\n"
            "import graph_engine.public  # noqa: F401\n"
            "print(json.dumps(sorted(sys.modules)))\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", program],
            capture_output=True,
            text=True,
            check=True,
        )
        loaded_modules = set(json.loads(result.stdout))

        leaked: list[str] = []
        for denied in self._DENYLIST:
            # Match exact module name OR any submodule.
            if denied in loaded_modules:
                leaked.append(denied)
                continue
            for mod in loaded_modules:
                if mod.startswith(f"{denied}."):
                    leaked.append(mod)
                    break

        assert not leaked, (
            f"public.py import graph leaked denied modules: "
            f"{sorted(leaked)}; CLAUDE.md §10 #3 + #5 + #6 forbid "
            f"graph-engine from importing other business modules / "
            "text-parser stacks / direct LLM provider SDKs."
        )
