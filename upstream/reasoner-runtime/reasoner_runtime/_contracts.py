from __future__ import annotations


def ensure_contracts_importable() -> None:
    try:
        import contracts  # noqa: F401
    except ModuleNotFoundError as error:
        if error.name != "contracts":
            raise

        raise ModuleNotFoundError(
            "project-ult-contracts is required. Install the contracts package "
            "or run tests with the repo-local pythonpath configured by pyproject.toml."
        ) from error
