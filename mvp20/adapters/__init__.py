"""Adapters wrapping vendored upstream project-ult modules.

Each adapter first serves a checked-in ``upstream/*/artifacts/frontend-api``
JSON artifact when present. Vendor imports are still attempted for version
metadata, but artifact-backed routes are runnable without editable upstream
installs. If neither artifact nor vendor import is available, the handler
returns a structured 503 ``UPSTREAM_UNAVAILABLE`` envelope.

This lets ``mvp20 serve`` expose the locked module contract surface locally
while keeping graceful degradation for heavy runtimes such as Neo4j, DuckDB, or
LLM providers.
"""
