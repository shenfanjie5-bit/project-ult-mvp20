"""Command line interface for MVP20 orchestration checks."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import click

from mvp20.fixture import run_fixture_e2e
from mvp20.lock import validate_lock
from mvp20.manifest import validate_manifest
from mvp20.planning import build_backfill_plan


@click.group()
def main() -> None:
    """MVP20 orchestration commands."""


@main.command("validate-manifest")
@click.option("--manifest", type=click.Path(path_type=Path), required=True)
def validate_manifest_command(manifest: Path) -> None:
    result = validate_manifest(manifest)
    _emit_result(asdict(result))
    if not result.ok:
        raise click.ClickException("; ".join(result.errors))


@main.command("verify-lock")
@click.option("--lock", "lock_path", type=click.Path(path_type=Path), required=True)
def verify_lock_command(lock_path: Path) -> None:
    result = validate_lock(lock_path)
    _emit_result(asdict(result))
    if not result.ok:
        raise click.ClickException("; ".join(result.errors))


@main.command("plan-backfill")
@click.option("--manifest", type=click.Path(path_type=Path), required=True)
def plan_backfill_command(manifest: Path) -> None:
    result = build_backfill_plan(manifest)
    _emit_result(asdict(result))


@main.command("run-fixture-e2e")
def run_fixture_e2e_command() -> None:
    result = run_fixture_e2e()
    _emit_result(asdict(result) | {"ok": result.ok})
    if not result.ok:
        raise click.ClickException("fixture e2e did not satisfy MVP20 invariants")


def _emit_result(payload: dict[str, object]) -> None:
    for key, value in payload.items():
        click.echo(f"{key}: {value}")
