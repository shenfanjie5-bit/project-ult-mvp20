from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DBT_MODELS = PROJECT_ROOT / "src" / "data_platform" / "dbt" / "models"
MARTS_DIR = DBT_MODELS / "marts"
FORMAL_SERVING_MODULES = (
    PROJECT_ROOT / "src" / "data_platform" / "serving" / "formal.py",
    PROJECT_ROOT / "src" / "data_platform" / "formal_registry.py",
)
FORBIDDEN_BUSINESS_TOKENS = ("doc_api", "tushare_", "stg_tushare_", "source('tushare'")


def test_curated_marts_do_not_expose_provider_specific_contracts() -> None:
    violations: list[str] = []
    for path in sorted(MARTS_DIR.glob("*.sql")):
        text = path.read_text(encoding="utf-8").lower()
        for token in FORBIDDEN_BUSINESS_TOKENS:
            if token in text:
                violations.append(f"{path.relative_to(PROJECT_ROOT)} contains {token}")
        if "ref('stg_" in text or 'ref("stg_' in text:
            violations.append(
                f"{path.relative_to(PROJECT_ROOT)} depends directly on source staging"
            )

    assert violations == []


def test_formal_serving_registry_is_provider_neutral() -> None:
    violations: list[str] = []
    for path in FORMAL_SERVING_MODULES:
        text = path.read_text(encoding="utf-8").lower()
        for token in FORBIDDEN_BUSINESS_TOKENS:
            if token in text:
                violations.append(f"{path.relative_to(PROJECT_ROOT)} contains {token}")

    assert violations == []
