"""Skeleton adapters wrapping the 6 vendored upstream project-ult modules.

Each adapter tries to ``import`` its vendor package at module load time.
- On success: provides handler(s) that return a 200 envelope with fixture data
  plus the vendor's reported ``__version__`` and ``wire_depth: skeleton``.
- On failure (vendor not installed / runtime deps missing / import error):
  handler returns a 503 ``UPSTREAM_UNAVAILABLE`` envelope with the import
  error message in ``details.import_error``.

This lets ``mvp20 serve`` route every former 503-only path to local code while
keeping graceful degradation if a vendor's heavy runtime deps (Neo4j /
DuckDB / LLM / etc.) aren't configured yet.
"""
