"""Stage 2.10 canonical contract tier (per SUBPROJECT_TESTING_STANDARD §2).

Two layers (mirroring the announcement / news template, adapted for
graph-engine being a CONSUMER not a PRODUCER of Ex-3):

- **Layer 1 (re-export shape stability)**: graph_engine.models
  re-exports ``CandidateGraphDelta`` / ``GraphSnapshot`` /
  ``GraphImpactSnapshot`` from ``contracts.schemas``. This layer
  asserts the re-exports are the SAME Python object as contracts —
  graph-engine MUST NOT fork the schema. CLAUDE.md domain rule:
  contracts owns Ex-3 canonical shape; graph-engine just consumes.

- **Layer 2 (CONSUMER round-trip)**: a synthetic ``CandidateGraphDelta``
  built from contracts canonical wire shape flows through graph-engine
  promotion validators; the resulting ``GraphSnapshot`` from
  ``build_graph_snapshot`` round-trips via real
  ``contracts.schemas.GraphSnapshot.model_validate``. Gated on
  ``[contracts-schemas]`` extra via ``importorskip``.

Iron rule #4: this tier MUST contain real tests, not just
``__init__.py`` (avoid pytest exit code 5 "no tests collected").
"""
