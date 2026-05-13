#!/usr/bin/env python3
"""Prepare a bounded real-data mini-cycle runtime profile.

The script creates local artifact directories and reports whether the operator
environment can supply the remaining runtime inputs. It never writes `.env`
files and never prints secret values such as DSNs or tokens.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import unquote, urlsplit
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_DIR = PROJECT_ROOT / "tmp" / "real-data-mini-cycle-runtime"
REQUIRED_ENV_KEYS = (
    "DP_PG_DSN",
    "DP_TUSHARE_TOKEN",
    "DP_RAW_ZONE_PATH",
    "DP_ICEBERG_WAREHOUSE_PATH",
    "DP_DUCKDB_PATH",
    "DP_ICEBERG_CATALOG_NAME",
)
SENSITIVE_ENV_KEYS = ("DP_PG_DSN", "DATABASE_URL", "DP_TUSHARE_TOKEN")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    report = build_runtime_profile(
        base_dir=args.base_dir,
        profile_name=args.profile_name,
        create_dirs=not args.no_create_dirs,
        create_pg_database=args.create_pg_database,
        admin_dsn_env=args.admin_dsn_env,
    )
    _write_json(args.json_report, report)
    if args.print_json:
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    return 0 if report["summary"]["runtime_profile_ready"] else 2


def build_runtime_profile(
    *,
    base_dir: Path,
    profile_name: str | None,
    create_dirs: bool,
    create_pg_database: bool,
    admin_dsn_env: str,
) -> dict[str, Any]:
    suffix = _safe_suffix(profile_name or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    work_dir = base_dir.expanduser().resolve(strict=False) / suffix
    runtime_paths = {
        "DP_RAW_ZONE_PATH": work_dir / "raw",
        "DP_ICEBERG_WAREHOUSE_PATH": work_dir / "warehouse",
        "DP_DUCKDB_PATH": work_dir / "duckdb" / "data_platform.duckdb",
    }
    catalog_name = f"data_platform_real_mini_cycle_{suffix}"

    created_dirs: list[str] = []
    if create_dirs:
        for key, path in runtime_paths.items():
            target = path.parent if key == "DP_DUCKDB_PATH" else path
            target.mkdir(parents=True, exist_ok=True)
            created_dirs.append(str(target))

    env_status = _environment_status()
    pg_status = _pg_status(
        suffix=suffix,
        create_pg_database=create_pg_database,
        admin_dsn_env=admin_dsn_env,
    )

    generated_env = {
        "DP_RAW_ZONE_PATH": str(runtime_paths["DP_RAW_ZONE_PATH"]),
        "DP_ICEBERG_WAREHOUSE_PATH": str(runtime_paths["DP_ICEBERG_WAREHOUSE_PATH"]),
        "DP_DUCKDB_PATH": str(runtime_paths["DP_DUCKDB_PATH"]),
        "DP_ICEBERG_CATALOG_NAME": catalog_name,
        "DP_ENV": "test",
    }
    if pg_status["status"] in {"existing_env", "created"}:
        generated_env["DP_PG_DSN"] = "<redacted:set>"

    missing_after_bootstrap: list[str] = []
    if pg_status["status"] not in {"existing_env", "created"}:
        missing_after_bootstrap.append("DP_PG_DSN")
    if env_status["DP_TUSHARE_TOKEN"] == "missing":
        missing_after_bootstrap.append("DP_TUSHARE_TOKEN")

    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "profile_name": suffix,
        "base_dir": str(base_dir.expanduser().resolve(strict=False)),
        "created_dirs": created_dirs,
        "runtime_paths": {key: str(path) for key, path in runtime_paths.items()},
        "catalog_name": catalog_name,
        "environment": env_status,
        "postgres": pg_status,
        "generated_env": generated_env,
        "summary": {
            "runtime_profile_ready": not missing_after_bootstrap,
            "missing_after_bootstrap": missing_after_bootstrap,
            "secrets_printed": False,
            "env_file_written": False,
        },
    }


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dir", type=Path, default=DEFAULT_BASE_DIR)
    parser.add_argument("--profile-name")
    parser.add_argument("--json-report", type=Path, required=True)
    parser.add_argument("--print-json", action="store_true")
    parser.add_argument("--no-create-dirs", action="store_true")
    parser.add_argument(
        "--create-pg-database",
        action="store_true",
        help="Create a temporary dp_real_mini_cycle_* database from the admin DSN env.",
    )
    parser.add_argument("--admin-dsn-env", default="DATABASE_URL")
    return parser.parse_args(argv)


def _environment_status() -> dict[str, str]:
    status = {key: ("set" if os.environ.get(key) else "missing") for key in REQUIRED_ENV_KEYS}
    status["DATABASE_URL"] = "set" if os.environ.get("DATABASE_URL") else "missing"
    status["external_corpus_root"] = (
        "present" if Path("/Volumes/dockcase2tb/database_all").is_dir() else "missing"
    )
    return status


def _pg_status(*, suffix: str, create_pg_database: bool, admin_dsn_env: str) -> dict[str, Any]:
    existing_dsn = os.environ.get("DP_PG_DSN")
    if existing_dsn:
        return {
            "status": "existing_env",
            "source": "DP_PG_DSN",
            "database": _database_name(existing_dsn),
            "dsn": "<redacted:set>",
        }

    admin_dsn = os.environ.get(admin_dsn_env)
    if not create_pg_database:
        return {
            "status": "missing",
            "source": admin_dsn_env,
            "admin_dsn": "set" if admin_dsn else "missing",
            "reason": "DP_PG_DSN missing and temporary PG creation not requested",
        }
    if not admin_dsn:
        return {
            "status": "missing",
            "source": admin_dsn_env,
            "admin_dsn": "missing",
            "reason": f"{admin_dsn_env} is required to create a temporary PG database",
        }

    database_name = f"dp_real_mini_cycle_{suffix}"
    if not re.fullmatch(r"dp_real_mini_cycle_[a-z0-9_]+", database_name):
        return {
            "status": "failed",
            "source": admin_dsn_env,
            "admin_dsn": "set",
            "reason": "generated database name failed safety validation",
        }

    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.engine import make_url

        from data_platform.ddl.runner import _sqlalchemy_postgres_uri

        admin_engine = create_engine(
            _sqlalchemy_postgres_uri(admin_dsn),
            isolation_level="AUTOCOMMIT",
        )
        try:
            with admin_engine.connect() as connection:
                connection.execute(text(f'CREATE DATABASE "{database_name}"'))
            test_dsn = make_url(admin_dsn).set(database=database_name).render_as_string(
                hide_password=False
            )
        finally:
            admin_engine.dispose()
    except Exception as exc:
        return {
            "status": "failed",
            "source": admin_dsn_env,
            "admin_dsn": "set",
            "database": database_name,
            "reason": _redact(str(exc)),
        }

    return {
        "status": "created",
        "source": admin_dsn_env,
        "admin_dsn": "set",
        "database": database_name,
        "dsn": "<redacted:set>",
        "drop_command": (
            f"DROP DATABASE IF EXISTS \"{database_name}\"; "
            "terminate active sessions first if needed"
        ),
        "dp_pg_dsn_available_to_child_process": bool(test_dsn),
    }


def _database_name(dsn: str) -> str:
    if dsn.startswith("jdbc:postgresql://"):
        dsn = "postgresql://" + dsn.removeprefix("jdbc:postgresql://")
    parsed = urlsplit(dsn)
    return unquote(parsed.path.lstrip("/")) if parsed.path else ""


def _safe_suffix(value: str) -> str:
    suffix = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    if not suffix:
        suffix = uuid4().hex
    return suffix[:48]


def _redact(value: str) -> str:
    text = value
    for key in SENSITIVE_ENV_KEYS:
        secret = os.environ.get(key)
        if secret:
            text = text.replace(secret, f"<redacted:{key}>")
    return text


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
