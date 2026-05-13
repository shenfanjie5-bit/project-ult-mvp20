from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_propagation_canary_runbook_pins_holdings_scope_and_hygiene() -> None:
    text = (REPO_ROOT / "docs" / "PROPAGATION_CANARY_RUNBOOK.md").read_text(
        encoding="utf-8",
    )
    normalized = " ".join(text.split())

    required_phrases = [
        "Issue #55 is CLOSED/COMPLETED for holdings-only explicit algorithms",
        "`CO_HOLDING` and `NORTHBOUND_HOLD`",
        "does not enable default or full propagation",
        "does not mean broad rollout is complete",
        "financial-doc",
        "contracts subtype",
        "Use a disposable Neo4j database",
        "The default `neo4j` database and production database labels are forbidden",
        "Verify the actual Neo4j client database matches the guarded config",
        "Do not call or route through `run_full_propagation`",
        "Do not commit runtime artifacts",
        "tokens, DSNs, or raw provider payloads",
    ]

    for phrase in required_phrases:
        assert phrase in normalized


def test_readme_and_progress_reference_propagation_canary_runbook() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    progress = (REPO_ROOT / "docs" / "PROGRESS.md").read_text(encoding="utf-8")

    assert "docs/PROPAGATION_CANARY_RUNBOOK.md" in readme
    assert "PROPAGATION_CANARY_RUNBOOK.md" in progress
