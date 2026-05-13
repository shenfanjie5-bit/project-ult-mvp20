"""Stage 2.10 canonical boundary tier (per SUBPROJECT_TESTING_STANDARD §2).

§10 red lines from CLAUDE.md (graph-engine):
1. **Truth Before Mirror**: Iceberg = canonical truth, Neo4j = hot
   mirror only.
2. **Promotion Before Propagation**: Layer A write succeeds before
   Neo4j sync runs.
3. **Regime Is Read-only**: ``graph_engine`` does NOT reverse-import
   ``main_core`` (subprocess deny-scan on public.py import graph).
4. **Readonly Simulation**: ``simulate_readonly_impact`` does not
   write the formal live graph (no Neo4j write API calls).
5. **No Raw Text**: only contracted ``CandidateGraphDelta`` —
   subprocess deny-scan rejects ``lightrag``, ``langchain``,
   ``pdfplumber``, ``pypdf``, ``unstructured``, ``pdfminer`` in the
   public.py import graph.
6. **Status Guard**: live graph reads check
   ``Neo4jGraphStatus == ready`` before proceeding.

Iron rule #2: deny-scan boundary tests use ``subprocess.run`` for
isolation — sys.modules pollution from earlier collected tests would
mask real import-graph leaks otherwise.

Note: graph-engine does NOT submit through subsystem-sdk, so iron
rule #7 (SDK wire-shape boundary) is N/A for this module.
"""
