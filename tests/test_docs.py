from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_docs_keep_forbidden_claims_negated() -> None:
    forbidden_positive_claims = (
        "Default/full propagation enabled.",
        "Broad production rollout complete.",
        "M4.7/financial-doc complete.",
        "Contracts subtype changes.",
        "New relation types.",
    )
    for path in (ROOT / "README.md", ROOT / "docs" / "RUNBOOK.md"):
        text = path.read_text(encoding="utf-8")
        not_claimed = text.split("## Not Claimed", 1)[1]
        for claim in forbidden_positive_claims:
            assert claim in not_claimed


def test_docs_do_not_reference_runtime_artifacts_or_secrets() -> None:
    forbidden_fragments = (
        "/Users/",
        ".parquet",
        "_manifest.json",
        "stdout_tail",
        "stderr_tail",
        "DP_PG_DSN=",
        "DATABASE_URL=",
        "NEO4J_PASSWORD=",
        "postgresql://",
        "bolt://",
    )
    for path in (ROOT / "README.md", ROOT / "docs" / "RUNBOOK.md"):
        text = path.read_text(encoding="utf-8")
        assert [fragment for fragment in forbidden_fragments if fragment in text] == []
