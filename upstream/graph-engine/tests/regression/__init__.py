"""Stage 2.10 canonical regression tier (per SUBPROJECT_TESTING_STANDARD §2).

Iron rule #1: regression tests MUST hard-import ``audit_eval_fixtures``
(NO ``pytest.skip(allow_module_level=True)`` cushion). Missing fixture
pack must fail collection so dev-only venvs surface the gap loudly.

Iron rule #5: regression must invoke real graph-engine runtime
(``promote_graph_deltas`` in this module's case) — NOT just inspect
fixture JSON.

Fixture: ``audit_eval_fixtures.event_cases.case_ex3_negative``
(audit-eval v0.2.2 release). Same case used by subsystem-announcement
Stage 2.8 follow-up #3 + subsystem-news Stage 2.9 regression. The
case's business expectation is shape-neutral: given weak evidence +
non-official source + unresolved target entity anchor, the consuming
subsystem's Ex-3 high-threshold guard MUST emit 0 graph deltas.

For graph-engine: the case's ``candidate_graph_delta_attempt`` shape
is fed through ``CandidateGraphDelta.model_validate`` (canonical
contracts wire shape) and then through graph-engine's promotion-side
validators; the test asserts the candidate is rejected before any
Layer A write or Neo4j sync.
"""
