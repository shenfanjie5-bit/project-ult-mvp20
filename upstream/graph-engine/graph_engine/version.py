"""Package version metadata.

0.1.1 — stage 2.10 (milestone-test-baseline): public.py + canonical
test tier dirs + 5 CI lanes + iron rules 1-6 (no #7 — graph-engine
does not submit through subsystem-sdk so SDK wire-shape boundary
doesn't apply) + 2-step Plan A install (contracts@v0.1.3 -> repo;
no SDK third step). graph-engine is a CONSUMER of Ex-3
(``CandidateGraphDelta`` / ``GraphSnapshot`` / ``GraphImpactSnapshot``
re-exported from contracts) — no canonical wire mapper needed
(unlike announcement / news which produce Ex-1/2/3 wire payloads).
"""

__version__: str = "0.1.1"
