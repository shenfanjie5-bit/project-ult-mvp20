#!/usr/bin/env python3
"""External smoke lane for the local Tushare corpus on /Volumes/dockcase2tb.

This is Phase C of TUSHARE_TEST_FIXTURE_PLAN.md (external smoke lane).
Unlike the git-tracked fixture lanes (audit-eval shared cases +
data-platform local raw fixtures), this smoke verifies the UPSTREAM
corpus itself and the fixture-to-corpus traceability chain.

It deliberately DOES NOT belong in pytest. The corpus lives outside
git on a mounted volume, so running this under CI would produce false
failures. It's meant for:

  - scheduled (cron / launchd) sanity checks that the corpus on the
    developer machine hasn't drifted / the audit CSV is still honest
  - manual local verification right before cutting a new fixture
  - regression-investigation when a shared case starts failing and
    the first question is "did the upstream shape change?"

Exit codes:
  0 - all checks passed, OR the corpus is not mounted (skip is a
      no-op, not a failure — unmounted is the normal state on CI and
      cold-start dev machines)
  1 - at least one check failed; stderr carries a per-check diagnostic
  2 - usage / prerequisite error (e.g. Python import path misconfigured)

Environment:
  DP_EXTERNAL_CORPUS_ROOT  optional override; defaults to
                           /Volumes/dockcase2tb/database_all
  DP_EXTERNAL_SMOKE_STRICT when set to 1/true, treats "unmounted" as
                           a failure instead of a skip (for explicit
                           operator runs that expect the drive to be up)

Checks (in order; first failure keeps going so the final summary is
complete, but exit code is non-zero):

  1. mount probe       — DP_EXTERNAL_CORPUS_ROOT path exists + readable
  2. audit csv gate    — every required dataset has
                         access_status=available
                         completeness_status=未见明显遗漏
                         at the audit snapshot timestamp
  3. dataset presence  — each dataset_path on disk + has a
                         non-trivial file
  4. ts_code presence  — Phase B fixtures reference specific ts_codes;
                         verify each ts_code still has data in its
                         owning corpus dataset
  5. schema alignment  — sample one parquet/csv per dataset, assert
                         column set matches the corresponding
                         TUSHARE_*_SCHEMA from
                         data_platform.adapters.tushare.assets
  6. fixture trace     — every committed fixture's tushare_source
                         block or _source.json sidecar points at a
                         dataset_path that still resolves under
                         DP_EXTERNAL_CORPUS_ROOT

Only check 1 blocks further work: if the drive isn't mounted the
other checks cannot physically run and we exit 0 (skip). All later
checks are independent and we always finish the full sweep.
"""

from __future__ import annotations

import csv
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path


#: Default corpus root on this workspace. Override via DP_EXTERNAL_CORPUS_ROOT.
DEFAULT_CORPUS_ROOT = Path("/Volumes/dockcase2tb/database_all")

#: Audit snapshot file — authoritative allowlist for completeness_status.
AUDIT_CSV_RELPATH = Path(
    "_workspace/_meta/analysis/api_download_completeness_audit_20260420.csv"
)

#: Datasets Phase B actively consumes. Each entry is
#: ``(doc_api, dataset_path_prefix_or_None)``:
#:
#: - ``doc_api`` maps to the audit CSV's ``doc_api`` column (the key
#:   tushare.pro uses internally, e.g. "stock_basic", "trade_cal").
#: - ``dataset_path_prefix`` disambiguates when multiple audit rows
#:   share the same doc_api. Currently only ``trade_cal`` is
#:   duplicated (期货数据/交易日历 + 股票数据/基础数据/交易日历);
#:   the prefix pins it to the stock-side row Phase B depends on.
#:   Codex review #1 P2 fix: previously this was just ``tuple[str, ...]``
#:   and the first-win lookup in audit_rows() silently bound trade_cal
#:   to the futures row.
#:
#: If a future dataset enters ``REQUIRED_TS_CODE_PRESENCE`` and it has
#: duplicate audit CSV rows, update BOTH lists to carry the prefix.
REQUIRED_DATASETS: tuple[tuple[str, str | None], ...] = (
    # shared case 1.1 (minimal_cycle/case_tushare_one_stock_one_cycle)
    ("stock_basic", None),
    ("stock_company", None),
    ("daily", None),
    ("daily_basic", None),
    ("trade_cal", "股票数据/"),  # reject 期货数据/交易日历; Phase B uses the stock row
    # shared case 1.2 (event_cases/case_tushare_namechange_alias)
    ("namechange", None),
    # entity-registry local fixtures
    ("stock_hsgt", None),
    ("bse_mapping", None),
    ("hk_basic", None),
    ("stk_ah_comparison", None),
    # data-platform local raw fixtures
    ("weekly", None),
    ("monthly", None),
)

#: ts_codes Phase B fixtures name explicitly. Each tuple is
#: (ts_code, dataset, reason). "reason" is carried into the
#: diagnostic so a failing check points back at which fixture
#: depends on this ts_code.
REQUIRED_TS_CODE_PRESENCE: tuple[tuple[str, str, str], ...] = (
    # minimal_cycle + weekly + monthly (600519.SH 贵州茅台)
    ("600519.SH", "daily", "minimal_cycle case + data-platform weekly/monthly"),
    ("600519.SH", "weekly", "data-platform local weekly fixture"),
    ("600519.SH", "monthly", "data-platform local monthly fixture"),
    # namechange case (300209.SZ)
    ("300209.SZ", "namechange", "event_cases/case_tushare_namechange_alias"),
    # ah_pair_snapshot A-side
    ("000063.SZ", "stk_ah_comparison", "entity-registry ah_pair_snapshot (中兴通讯)"),
    ("000039.SZ", "stk_ah_comparison", "entity-registry ah_pair_snapshot (中集集团)"),
    ("000002.SZ", "stk_ah_comparison", "entity-registry ah_pair_snapshot (万科A)"),
)

#: Fixture traceability sources we audit. Each entry is a path
#: relative to the data-platform repo root (where this script lives
#: in scripts/) whose JSON payload carries either a `tushare_source`
#: block (audit-eval shared case metadata.json) or the top-level
#: Phase B §7 8-key traceability contract (.source.json sidecars).
#: The "json_pointer" names the field we walk into to find the
#: dataset_path; None means the file itself IS the traceability block.
FIXTURE_TRACEABILITY_PATHS: tuple[tuple[str, str | None], ...] = (
    (
        "../audit-eval/src/audit_eval_fixtures/data/minimal_cycle/"
        "case_tushare_one_stock_one_cycle/metadata.json",
        "tushare_source",
    ),
    (
        "../audit-eval/src/audit_eval_fixtures/data/event_cases/"
        "case_tushare_namechange_alias/metadata.json",
        "tushare_source",
    ),
    (
        "../entity-registry/tests/fixtures/stock_hsgt_snapshot.source.json",
        None,
    ),
    (
        "../entity-registry/tests/fixtures/bse_mapping_snapshot.source.json",
        None,
    ),
    (
        "../entity-registry/tests/fixtures/ah_pair_snapshot.source.json",
        None,
    ),
    (
        "tests/dbt/fixtures/raw/tushare/weekly/dt=20260415/_source.json",
        None,
    ),
    (
        "tests/dbt/fixtures/raw/tushare/monthly/dt=20260415/_source.json",
        None,
    ),
)


@dataclass
class CheckResult:
    name: str
    ok: bool
    summary: str
    details: list[str] = field(default_factory=list)


class ExternalSmokeContext:
    def __init__(self, corpus_root: Path, strict_mount: bool) -> None:
        self.corpus_root = corpus_root
        self.strict_mount = strict_mount
        self.results: list[CheckResult] = []
        self._audit_rows: list[dict[str, str]] | None = None

    def audit_rows(self) -> list[dict[str, str]]:
        """All audit CSV rows in file order (duplicates preserved).

        Codex review #1 P2 fix: the earlier ``dict[doc_api, row]`` with
        first-win semantics silently bound ``trade_cal`` to the 期货
        row while Phase B uses the 股票 row. Callers now iterate and
        disambiguate explicitly via ``_resolve_audit_row``.
        """
        if self._audit_rows is not None:
            return self._audit_rows
        path = self.corpus_root / AUDIT_CSV_RELPATH
        rows: list[dict[str, str]] = []
        with path.open(encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                doc_api = (row.get("doc_api") or "").strip()
                if doc_api:
                    rows.append(row)
        self._audit_rows = rows
        return rows


def _resolve_audit_row(
    rows: list[dict[str, str]],
    doc_api: str,
    dataset_path_prefix: str | None = None,
) -> dict[str, str] | None:
    """Return the first audit CSV row matching ``doc_api`` (and
    optionally a ``dataset_path`` prefix). ``None`` if no match.

    Codex review #1 P2 fix: replaces the previous
    ``rows.get(doc_api)`` pattern that silently lost duplicates.
    """
    for row in rows:
        if (row.get("doc_api") or "").strip() != doc_api:
            continue
        if dataset_path_prefix is not None:
            candidate = (row.get("dataset_path") or "").strip()
            if not candidate.startswith(dataset_path_prefix):
                continue
        return row
    return None


def _remap_to_current_root(
    declared_abs: str,
    declared_root: str,
    current_root: Path,
) -> Path | None:
    """If ``declared_abs`` is a descendant of ``declared_root``, return
    the equivalent path under ``current_root``. Return ``None`` if the
    declared path is not under the declared root (that's a genuine
    fixture-metadata defect, not an override-compat concern).

    Codex review #1 P2 fix: fixture_traceability used to compare
    declared absolute paths string-wise against the current corpus
    root, which falsely failed whenever DP_EXTERNAL_CORPUS_ROOT was
    overridden to a structurally-identical mirror (e.g. a symlink).
    """
    try:
        relative = Path(declared_abs).relative_to(declared_root)
    except ValueError:
        return None
    return current_root / relative


# ────────────────────── Checks ──────────────────────


def check_mount(ctx: ExternalSmokeContext) -> CheckResult:
    if not ctx.corpus_root.exists():
        summary = f"corpus root {ctx.corpus_root} does not exist (drive not mounted)"
        return CheckResult(
            name="mount",
            ok=False,
            summary=summary,
            details=[
                "This is the expected state in CI and on dev machines where the"
                " external drive hasn't been plugged in; the caller usually"
                " treats this as a skip, not a failure.",
            ],
        )
    try:
        # Probe readability by listing the directory.
        next(iter(ctx.corpus_root.iterdir()))
    except StopIteration:
        return CheckResult(
            name="mount",
            ok=False,
            summary=f"corpus root {ctx.corpus_root} is empty",
        )
    except PermissionError as exc:
        return CheckResult(
            name="mount",
            ok=False,
            summary=f"corpus root {ctx.corpus_root} not readable: {exc}",
        )
    return CheckResult(name="mount", ok=True, summary=f"mounted + readable at {ctx.corpus_root}")


def check_audit_csv_gate(ctx: ExternalSmokeContext) -> CheckResult:
    try:
        rows = ctx.audit_rows()
    except FileNotFoundError as exc:
        return CheckResult(
            name="audit_csv_gate",
            ok=False,
            summary=f"audit CSV missing: {exc}",
        )
    except Exception as exc:
        return CheckResult(
            name="audit_csv_gate",
            ok=False,
            summary=f"audit CSV parse failed: {exc!r}",
        )

    missing: list[str] = []
    violations: list[str] = []
    for dataset, prefix in REQUIRED_DATASETS:
        row = _resolve_audit_row(rows, dataset, prefix)
        if row is None:
            label = f"{dataset} [prefix={prefix!r}]" if prefix else dataset
            missing.append(label)
            continue
        access = (row.get("access_status") or "").strip()
        completeness = (row.get("completeness_status") or "").strip()
        if access != "available" or completeness != "未见明显遗漏":
            violations.append(
                f"{dataset}: access_status={access!r} completeness_status={completeness!r}"
            )

    if missing or violations:
        details = []
        if missing:
            details.append(f"datasets missing from audit CSV: {missing}")
        if violations:
            details.append("gate violations:")
            details.extend(f"  {v}" for v in violations)
        return CheckResult(
            name="audit_csv_gate",
            ok=False,
            summary=f"{len(missing) + len(violations)} required dataset(s) not cleanly gated",
            details=details,
        )
    return CheckResult(
        name="audit_csv_gate",
        ok=True,
        summary=f"all {len(REQUIRED_DATASETS)} required datasets are access=available + completeness=未见明显遗漏",
    )


def check_dataset_presence(ctx: ExternalSmokeContext) -> CheckResult:
    try:
        rows = ctx.audit_rows()
    except Exception as exc:
        return CheckResult(
            name="dataset_presence",
            ok=False,
            summary=f"cannot read audit CSV to resolve dataset paths: {exc!r}",
        )

    missing_paths: list[str] = []
    for dataset, prefix in REQUIRED_DATASETS:
        row = _resolve_audit_row(rows, dataset, prefix)
        if row is None:
            continue  # audit gate will already have reported this
        dataset_relpath = (row.get("dataset_path") or "").strip()
        if not dataset_relpath:
            missing_paths.append(f"{dataset}: audit CSV has no dataset_path")
            continue
        absolute = ctx.corpus_root / dataset_relpath
        if not absolute.is_dir():
            missing_paths.append(f"{dataset}: {absolute} does not exist")

    if missing_paths:
        return CheckResult(
            name="dataset_presence",
            ok=False,
            summary=f"{len(missing_paths)} dataset(s) missing on disk",
            details=missing_paths,
        )
    return CheckResult(
        name="dataset_presence",
        ok=True,
        summary=f"all {len(REQUIRED_DATASETS)} dataset_paths present on disk",
    )


def check_ts_code_presence(ctx: ExternalSmokeContext) -> CheckResult:
    try:
        rows = ctx.audit_rows()
    except Exception as exc:
        return CheckResult(
            name="ts_code_presence",
            ok=False,
            summary=f"cannot read audit CSV: {exc!r}",
        )

    violations: list[str] = []
    for ts_code, dataset, reason in REQUIRED_TS_CODE_PRESENCE:
        # Pick the same disambiguator the REQUIRED_DATASETS list uses
        # for this doc_api. If a future entry in this list names a
        # duplicated dataset, add a 4th tuple field (prefix) here and
        # thread it through to _resolve_audit_row.
        prefix = next(
            (p for d, p in REQUIRED_DATASETS if d == dataset),
            None,
        )
        row = _resolve_audit_row(rows, dataset, prefix)
        if row is None:
            violations.append(
                f"{ts_code} @ {dataset} ({reason}): dataset missing from audit CSV"
            )
            continue
        dataset_relpath = (row.get("dataset_path") or "").strip()
        if not dataset_relpath:
            violations.append(
                f"{ts_code} @ {dataset} ({reason}): audit CSV has no dataset_path"
            )
            continue
        dataset_abs = ctx.corpus_root / dataset_relpath
        split_by_symbol = (row.get("split_by_symbol") or "").strip().lower() == "true"
        if split_by_symbol:
            # by_symbol layout: dataset_abs/by_symbol/<ts_code>+<name>.csv
            by_symbol_dir = dataset_abs / "by_symbol"
            if not by_symbol_dir.is_dir():
                violations.append(
                    f"{ts_code} @ {dataset} ({reason}): by_symbol dir missing at {by_symbol_dir}"
                )
                continue
            # Prefix match on ts_code + '+'.
            matches = list(by_symbol_dir.glob(f"{ts_code}+*.csv"))
            if not matches:
                violations.append(
                    f"{ts_code} @ {dataset} ({reason}): no by_symbol file matching {ts_code}+*.csv"
                )
                continue
            try:
                line_count = sum(1 for _ in matches[0].open(encoding="utf-8"))
            except Exception as exc:
                violations.append(
                    f"{ts_code} @ {dataset} ({reason}): {matches[0]} unreadable: {exc!r}"
                )
                continue
            if line_count < 2:  # header + at least one row
                violations.append(
                    f"{ts_code} @ {dataset} ({reason}): {matches[0]} has no data rows"
                )
                continue
        else:
            # all_csv layout: dataset_abs/all.csv
            all_csv = dataset_abs / "all.csv"
            if not all_csv.is_file():
                violations.append(
                    f"{ts_code} @ {dataset} ({reason}): all.csv missing at {all_csv}"
                )
                continue
            # Scan for the ts_code as an exact prefix on any line.
            found = False
            with all_csv.open(encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith(f"{ts_code},"):
                        found = True
                        break
            if not found:
                violations.append(
                    f"{ts_code} @ {dataset} ({reason}): ts_code not present in {all_csv.name}"
                )

    if violations:
        return CheckResult(
            name="ts_code_presence",
            ok=False,
            summary=f"{len(violations)} Phase-B-referenced ts_code(s) missing from corpus",
            details=violations,
        )
    return CheckResult(
        name="ts_code_presence",
        ok=True,
        summary=f"all {len(REQUIRED_TS_CODE_PRESENCE)} Phase-B ts_codes resolve in their datasets",
    )


#: Per-dataset schema-check direction.
#:
#: "strict" (expected ⊆ actual): every TUSHARE_*_SCHEMA column MUST
#:   appear in the corpus CSV header. Use for datasets where fixture
#:   consumers actively depend on every bar/indicator field (daily,
#:   weekly, monthly, daily_basic).
#:
#: "corpus_subset" (actual ⊆ expected): the corpus header may be a
#:   subset of the adapter schema — the full tushare.pro API returns
#:   richer fields than what lands in the local CSV snapshot (e.g.
#:   stock_basic CSV ships only 10 of the 17 TUSHARE_STOCK_BASIC_SCHEMA
#:   columns; fixture consumers cross-fill fullname / enname /
#:   exchange / etc. from stock_company + derivation rules). Check
#:   direction is reversed so extra adapter-schema fields don't
#:   falsely flag the corpus.
_SCHEMA_CHECK_DIRECTION: dict[str, str] = {
    "daily":       "strict",
    "weekly":      "strict",
    "monthly":     "strict",
    "daily_basic": "strict",
    "stock_basic": "corpus_subset",
}


def _load_schema_column_sets() -> dict[str, set[str]]:
    """Pull column-name sets from the actual
    data_platform.adapters.tushare.assets.TUSHARE_*_SCHEMA definitions.

    Importing at module load would require the data-platform venv on
    sys.path before we even know whether the corpus is mounted; lazy
    here so `check mount` can fail/skip cleanly first.
    """
    repo_root = Path(__file__).resolve().parent.parent
    src_path = repo_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    from data_platform.adapters.tushare.assets import (  # type: ignore[import]
        TUSHARE_BAR_SCHEMA,
        TUSHARE_DAILY_BASIC_SCHEMA,
        TUSHARE_STOCK_BASIC_SCHEMA,
    )

    return {
        "daily": set(TUSHARE_BAR_SCHEMA.names),
        "weekly": set(TUSHARE_BAR_SCHEMA.names),
        "monthly": set(TUSHARE_BAR_SCHEMA.names),
        "stock_basic": set(TUSHARE_STOCK_BASIC_SCHEMA.names),
        "daily_basic": set(TUSHARE_DAILY_BASIC_SCHEMA.names),
    }


def _sample_header(dataset_abs: Path, split_by_symbol: bool) -> list[str] | None:
    if split_by_symbol:
        by_symbol_dir = dataset_abs / "by_symbol"
        if not by_symbol_dir.is_dir():
            return None
        try:
            sample = next(by_symbol_dir.glob("*.csv"))
        except StopIteration:
            return None
    else:
        sample = dataset_abs / "all.csv"
        if not sample.is_file():
            return None
    try:
        with sample.open(encoding="utf-8") as handle:
            header = handle.readline().strip()
    except Exception:
        return None
    if not header:
        return None
    return [col.strip() for col in header.split(",")]


def check_schema_alignment(ctx: ExternalSmokeContext) -> CheckResult:
    try:
        expected_by_dataset = _load_schema_column_sets()
    except Exception as exc:
        return CheckResult(
            name="schema_alignment",
            ok=False,
            summary=f"cannot import TUSHARE_*_SCHEMA from data_platform.adapters.tushare.assets: {exc!r}",
        )
    try:
        rows = ctx.audit_rows()
    except Exception as exc:
        return CheckResult(
            name="schema_alignment",
            ok=False,
            summary=f"cannot read audit CSV: {exc!r}",
        )

    violations: list[str] = []
    for dataset, expected in expected_by_dataset.items():
        prefix = next(
            (p for d, p in REQUIRED_DATASETS if d == dataset),
            None,
        )
        row = _resolve_audit_row(rows, dataset, prefix)
        if row is None:
            violations.append(f"{dataset}: no audit row")
            continue
        dataset_abs = ctx.corpus_root / (row.get("dataset_path") or "").strip()
        split_by_symbol = (row.get("split_by_symbol") or "").strip().lower() == "true"
        header = _sample_header(dataset_abs, split_by_symbol)
        if header is None:
            violations.append(f"{dataset}: could not sample header from {dataset_abs}")
            continue
        actual = set(header)
        direction = _SCHEMA_CHECK_DIRECTION.get(dataset, "strict")
        if direction == "strict":
            missing = expected - actual
            if missing:
                violations.append(
                    f"{dataset} [strict]: TUSHARE_*_SCHEMA columns {sorted(missing)} missing from corpus header {sorted(actual)}"
                )
        elif direction == "corpus_subset":
            unknown = actual - expected
            if unknown:
                violations.append(
                    f"{dataset} [corpus_subset]: corpus columns {sorted(unknown)} not in TUSHARE_*_SCHEMA {sorted(expected)}"
                )
        else:
            violations.append(
                f"{dataset}: unknown schema-check direction {direction!r}"
            )

    if violations:
        return CheckResult(
            name="schema_alignment",
            ok=False,
            summary=f"{len(violations)} dataset(s) drifted vs TUSHARE_*_SCHEMA",
            details=violations,
        )
    return CheckResult(
        name="schema_alignment",
        ok=True,
        summary=(
            f"all {len(expected_by_dataset)} schema-checked datasets aligned per per-dataset "
            f"direction (strict / corpus_subset)"
        ),
    )


def _resolve_json_pointer(payload: dict, pointer: str | None) -> dict | None:
    if pointer is None:
        return payload
    node = payload
    for segment in pointer.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(segment)
        if node is None:
            return None
    return node if isinstance(node, dict) else None


def check_fixture_traceability(ctx: ExternalSmokeContext) -> CheckResult:
    try:
        rows = ctx.audit_rows()
    except Exception as exc:
        return CheckResult(
            name="fixture_traceability",
            ok=False,
            summary=f"cannot read audit CSV: {exc!r}",
        )

    repo_root = Path(__file__).resolve().parent.parent
    violations: list[str] = []
    checked = 0
    for relpath, pointer in FIXTURE_TRACEABILITY_PATHS:
        fixture_path = (repo_root / relpath).resolve()
        if not fixture_path.is_file():
            violations.append(f"{relpath}: fixture file not found at {fixture_path}")
            continue
        try:
            payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        except Exception as exc:
            violations.append(f"{relpath}: JSON parse failed: {exc!r}")
            continue

        trace_block = _resolve_json_pointer(payload, pointer)
        if trace_block is None:
            violations.append(
                f"{relpath}: traceability block at pointer {pointer!r} missing or not an object"
            )
            continue

        declared_corpus_root = trace_block.get("corpus_root")
        declared_dataset_path = trace_block.get("dataset_path")
        declared_datasets = trace_block.get("datasets") or []
        if not declared_corpus_root or not declared_dataset_path:
            violations.append(
                f"{relpath}: missing corpus_root/dataset_path ({declared_corpus_root!r}, {declared_dataset_path!r})"
            )
            continue

        # Codex review #1 P2 fix: remap declared absolute paths into
        # the current corpus root instead of string-comparing roots.
        # The declared corpus_root is fixed when the fixture was cut
        # (always the default /Volumes/dockcase2tb/database_all); the
        # current root may be overridden via DP_EXTERNAL_CORPUS_ROOT
        # to a structurally-identical mirror (symlink, secondary
        # mount, etc.). Override is a supported mode, not a failure.
        remapped = _remap_to_current_root(
            declared_dataset_path, declared_corpus_root, ctx.corpus_root
        )
        if remapped is None:
            # The declared path is not under the declared root — this
            # is a genuine fixture-metadata defect, unrelated to the
            # override question.
            violations.append(
                f"{relpath}: declared dataset_path {declared_dataset_path!r} is not a "
                f"descendant of declared corpus_root {declared_corpus_root!r} — "
                f"fixture metadata is malformed"
            )
        elif not remapped.is_dir():
            extra = ""
            if Path(declared_corpus_root) != ctx.corpus_root:
                extra = (
                    f" (declared root {declared_corpus_root!r} was remapped to "
                    f"current root {str(ctx.corpus_root)!r} before resolving)"
                )
            violations.append(
                f"{relpath}: dataset_path {declared_dataset_path!r} does not "
                f"resolve under the current corpus root{extra}"
            )

        # Cross-check each datasets[] entry is accounted for in audit
        # CSV. The fixture's datasets[] list carries bare doc_api
        # names (no prefix), so any matching row is acceptable here —
        # the prefix-sensitive binding is already enforced by the
        # audit_csv_gate + dataset_presence checks above.
        for dataset_name in declared_datasets:
            if _resolve_audit_row(rows, dataset_name, None) is None:
                violations.append(
                    f"{relpath}: declared dataset {dataset_name!r} not in audit CSV"
                )
        checked += 1

    if violations:
        return CheckResult(
            name="fixture_traceability",
            ok=False,
            summary=f"{len(violations)} traceability violation(s) across {checked} fixtures",
            details=violations,
        )
    return CheckResult(
        name="fixture_traceability",
        ok=True,
        summary=f"all {checked} Phase-B fixtures' tushare_source blocks trace to the live corpus",
    )


# ────────────────────── Runner ──────────────────────


def run(ctx: ExternalSmokeContext) -> int:
    # check 1: mount — if fails, the rest cannot run; return exit code 0
    # (skip) unless strict mode demands failure.
    mount = check_mount(ctx)
    ctx.results.append(mount)
    if not mount.ok:
        _emit_summary(ctx)
        if ctx.strict_mount:
            return 1
        return 0

    # checks 2-6 are independent; always run them all.
    ctx.results.append(check_audit_csv_gate(ctx))
    ctx.results.append(check_dataset_presence(ctx))
    ctx.results.append(check_ts_code_presence(ctx))
    ctx.results.append(check_schema_alignment(ctx))
    ctx.results.append(check_fixture_traceability(ctx))

    _emit_summary(ctx)
    return 0 if all(r.ok for r in ctx.results) else 1


def _emit_summary(ctx: ExternalSmokeContext) -> None:
    sys.stdout.write(
        f"external smoke — Tushare corpus @ {ctx.corpus_root}\n"
    )
    sys.stdout.write("─" * 72 + "\n")
    for r in ctx.results:
        tag = "✓" if r.ok else "✗"
        sys.stdout.write(f"  {tag} {r.name}: {r.summary}\n")
        for line in r.details:
            sys.stdout.write(f"      {line}\n")
    sys.stdout.write("─" * 72 + "\n")
    passed = sum(1 for r in ctx.results if r.ok)
    sys.stdout.write(f"  {passed}/{len(ctx.results)} checks passed\n")
    if not all(r.ok for r in ctx.results):
        sys.stdout.write(
            "  NOTE: a failing 'mount' check is normal when the external drive "
            "is not plugged in; use DP_EXTERNAL_SMOKE_STRICT=1 to make that a "
            "hard failure.\n"
        )


def _env_flag(name: str) -> bool:
    value = os.environ.get(name, "").strip().lower()
    return value in {"1", "true", "yes"}


def main() -> int:
    corpus_root_env = os.environ.get("DP_EXTERNAL_CORPUS_ROOT", "").strip()
    corpus_root = Path(corpus_root_env) if corpus_root_env else DEFAULT_CORPUS_ROOT
    strict_mount = _env_flag("DP_EXTERNAL_SMOKE_STRICT")
    ctx = ExternalSmokeContext(corpus_root=corpus_root, strict_mount=strict_mount)
    return run(ctx)


if __name__ == "__main__":
    sys.exit(main())
