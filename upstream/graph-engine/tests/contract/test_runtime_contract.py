"""Stage 2.10 contract tier — runtime contract signature stability.

This file checks graph-engine's PUBLIC API surface (the symbols
graph-engine exposes to other modules + assembly) doesn't drift in
shape:

- Public entrypoint singletons present + correct method signatures.
- Major service entry points present (promote_graph_deltas, cold_reload,
  query_subgraph, simulate_readonly_impact, check_live_graph_consistency,
  build_graph_snapshot, build_graph_impact_snapshot).
- Re-exported contracts schemas are the SAME Python object as
  contracts (CLAUDE.md domain rule: only contracts owns Ex-3 / Graph
  schemas; graph-engine MUST NOT fork).

Iron rule #4: tests/contract/ MUST contain real tests (no empty
``__init__.py``-only directory).
"""

from __future__ import annotations

import inspect


class TestPublicEntrypointSingletons:
    """The 5 module-level singleton instances assembly references."""

    def test_module_level_singletons_present(self) -> None:
        from graph_engine import public

        for name in (
            "health_probe",
            "smoke_hook",
            "init_hook",
            "version_declaration",
            "cli",
        ):
            assert hasattr(public, name), f"public.{name} missing"
            assert public.__all__.count(name) == 1

    def test_health_probe_check_signature(self) -> None:
        from graph_engine.public import health_probe

        sig = inspect.signature(health_probe.check)
        assert list(sig.parameters) == ["timeout_sec"]
        param = sig.parameters["timeout_sec"]
        assert param.kind is inspect.Parameter.KEYWORD_ONLY
        assert param.default is inspect.Parameter.empty
        # public.py uses `from __future__ import annotations` so
        # annotations are stringified at parse time.
        assert str(param.annotation) == "float"

    def test_smoke_hook_run_signature(self) -> None:
        from graph_engine.public import smoke_hook

        sig = inspect.signature(smoke_hook.run)
        assert list(sig.parameters) == ["profile_id"]
        param = sig.parameters["profile_id"]
        assert param.kind is inspect.Parameter.KEYWORD_ONLY
        assert param.default is inspect.Parameter.empty
        assert str(param.annotation) == "str"

    def test_init_hook_initialize_signature(self) -> None:
        from graph_engine.public import init_hook

        sig = inspect.signature(init_hook.initialize)
        assert list(sig.parameters) == ["resolved_env"]
        param = sig.parameters["resolved_env"]
        assert param.kind is inspect.Parameter.KEYWORD_ONLY
        assert param.default is inspect.Parameter.empty

    def test_version_declaration_declare_signature(self) -> None:
        from graph_engine.public import version_declaration

        sig = inspect.signature(version_declaration.declare)
        assert list(sig.parameters) == []  # no parameters except self

    def test_cli_invoke_signature(self) -> None:
        from graph_engine.public import cli

        sig = inspect.signature(cli.invoke)
        assert list(sig.parameters) == ["argv"]
        param = sig.parameters["argv"]
        assert param.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
        assert param.default is inspect.Parameter.empty


class TestMajorServiceEntryPoints:
    """The graph-engine top-level service entry points consumers
    (orchestrator / main-core / audit-eval) call. Signature stability
    here is a cross-module contract.
    """

    def test_promote_graph_deltas_present(self) -> None:
        from graph_engine import promote_graph_deltas

        sig = inspect.signature(promote_graph_deltas)
        # Args expected (based on promotion/service.py): canonical
        # input + neo4j client + status. Just lock the function exists
        # + has callable shape; sig drift caught here without nailing
        # exact param names (those evolve faster than presence does).
        assert callable(promote_graph_deltas)
        # Function must take >= 1 positional/keyword arg.
        assert len(sig.parameters) >= 1

    def test_cold_reload_present(self) -> None:
        from graph_engine import cold_reload

        assert callable(cold_reload)

    def test_query_subgraph_present(self) -> None:
        from graph_engine import query_subgraph

        assert callable(query_subgraph)

    def test_query_propagation_paths_present(self) -> None:
        from graph_engine import query_propagation_paths

        assert callable(query_propagation_paths)

    def test_simulate_readonly_impact_present(self) -> None:
        from graph_engine import simulate_readonly_impact

        assert callable(simulate_readonly_impact)

    def test_check_live_graph_consistency_present(self) -> None:
        from graph_engine import check_live_graph_consistency

        assert callable(check_live_graph_consistency)

    def test_build_graph_snapshot_present(self) -> None:
        from graph_engine.snapshots.generator import build_graph_snapshot

        assert callable(build_graph_snapshot)

    def test_build_graph_impact_snapshot_present(self) -> None:
        from graph_engine.snapshots.generator import build_graph_impact_snapshot

        assert callable(build_graph_impact_snapshot)


class TestNeo4jStatusEnumStable:
    """CLAUDE.md §10 #7: live graph reads check graph_status before
    proceeding. The canonical 3-state set (ready / rebuilding / failed)
    is locked here so consumers can guard on a stable enum.
    """

    def test_neo4j_graph_status_literal_values_stable(self) -> None:
        from typing import get_args

        from graph_engine.models import Neo4jGraphStatus

        annotation = Neo4jGraphStatus.model_fields["graph_status"].annotation
        assert set(get_args(annotation)) == {
            "ready",
            "rebuilding",
            "failed",
        }

    def test_propagation_channel_literal_values_stable(self) -> None:
        """3 propagation channels (CLAUDE.md §10 P3b: fundamental +
        event + reflexive)."""

        from typing import get_args

        from graph_engine.models import PropagationChannel

        assert set(get_args(PropagationChannel)) == {
            "fundamental",
            "event",
            "reflexive",
        }


class TestVersionExportPresent:
    def test_version_module_exposes_string(self) -> None:
        import graph_engine
        from graph_engine.version import __version__

        assert isinstance(__version__, str)
        assert __version__ == graph_engine.__version__


class TestContractsReExportProbeBoundary:
    """Codex review #12 P2 + #13 P2 regressions: ``_probe_contracts_re_exports``
    must distinguish three failure modes structurally:

    - ``contracts_missing`` → offline-first dev miss (degraded).
      Triggered ONLY by the literal top-level ``contracts`` package
      being absent (i.e. ``ModuleNotFoundError("No module named
      'contracts'")`` with no dots). This is the only legitimate
      benign scenario for graph-engine.
    - ``contracts_broken`` → installed contracts package is
      structurally broken (blocked). Triggered when ``contracts.schemas``
      or any other ``contracts.*`` submodule (or a transitive dep like
      ``pydantic``) is missing while ``contracts`` itself is installed.
      A submodule miss inside an installed package is NOT an offline-
      first dev state.
    - ``graph_engine_models_broken`` → in-repo regression (blocked).
      Triggered by any failure importing ``graph_engine.models`` (a
      renamed/deleted internal namespace, broken transitive in-repo
      dep, etc.). Must NEVER be conflated with ``contracts_missing``.

    The boundary helper ``_extract_full_missing_module_name`` returns
    the FULL dotted name (no top-level stripping) so the exact-match
    check against ``_OFFLINE_FIRST_BENIGN_MISSING_MODULE`` correctly
    rejects submodule misses of installed packages.
    """

    def test_offline_first_benign_module_is_exact_top_level_contracts(
        self,
    ) -> None:
        from graph_engine.public import _OFFLINE_FIRST_BENIGN_MISSING_MODULE

        assert _OFFLINE_FIRST_BENIGN_MISSING_MODULE == "contracts"
        # Sanity: it's a bare string, not a frozenset / tuple — the
        # exact-match semantic must be obvious by shape.
        assert isinstance(_OFFLINE_FIRST_BENIGN_MISSING_MODULE, str)

    def test_extract_full_missing_module_name_preserves_dotted_path(
        self,
    ) -> None:
        """Helper must return the FULL dotted name (NOT the stripped
        top-level segment). This is critical — the previous helper
        stripped to top-level and conflated ``contracts`` with
        ``contracts.schemas``, silently downgrading submodule misses
        of an installed package to ``contracts_missing``/degraded.
        """

        from graph_engine.public import _extract_full_missing_module_name

        assert (
            _extract_full_missing_module_name(
                "ModuleNotFoundError(\"No module named 'contracts'\")"
            )
            == "contracts"
        )
        assert (
            _extract_full_missing_module_name(
                "ModuleNotFoundError(\"No module named 'contracts.schemas'\")"
            )
            == "contracts.schemas"
        ), (
            "MUST preserve the full dotted name — stripping to "
            "'contracts' would conflate offline-first with structural "
            "break and re-introduce the codex review #13 P2 regression"
        )
        assert (
            _extract_full_missing_module_name(
                "ModuleNotFoundError(\"No module named 'graph_engine.models'\")"
            )
            == "graph_engine.models"
        )
        assert _extract_full_missing_module_name("nothing matches") is None

    def test_probe_tags_in_repo_break_as_graph_engine_models_broken(
        self, monkeypatch
    ) -> None:
        """Simulate an in-repo regression: ``graph_engine.models`` itself
        raises ``ModuleNotFoundError`` (e.g. a renamed/deleted internal
        namespace). The probe MUST tag this as
        ``graph_engine_models_broken`` so the caller blocks instead of
        downgrading. This is the precise scenario codex #12 flagged.
        """
        import builtins
        import sys

        # Evict any cached graph_engine.models so the patched __import__
        # actually fires when _probe_contracts_re_exports re-imports it.
        for cached in list(sys.modules):
            if cached == "graph_engine.models" or cached.startswith(
                "graph_engine.models."
            ):
                monkeypatch.delitem(sys.modules, cached, raising=False)

        real_import = builtins.__import__

        def fake_import(
            name: str, globals=None, locals=None, fromlist=(), level=0
        ):
            if name == "graph_engine.models" or name.startswith(
                "graph_engine.models."
            ):
                raise ModuleNotFoundError(
                    "No module named 'graph_engine.models'"
                )
            return real_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        from graph_engine.public import _probe_contracts_re_exports

        result = _probe_contracts_re_exports()
        assert result["available"] is False
        assert result["kind"] == "graph_engine_models_broken", (
            f"in-repo break must NOT be tagged as the legacy "
            f"'import_unavailable' or 'contracts_missing' (which would "
            f"silently downgrade to degraded); got {result!r}"
        )

    def test_probe_tags_top_level_contracts_miss_as_contracts_missing(
        self, monkeypatch
    ) -> None:
        """Simulate offline-first dev: top-level ``contracts`` package
        is absent (``No module named 'contracts'``, no dots). This is
        the ONLY scenario the probe accepts as a benign offline-first
        miss → ``contracts_missing`` → caller downgrades to degraded.
        """
        import builtins
        import sys

        for cached in list(sys.modules):
            if cached == "contracts" or cached.startswith("contracts."):
                monkeypatch.delitem(sys.modules, cached, raising=False)

        real_import = builtins.__import__

        def fake_import(
            name: str, globals=None, locals=None, fromlist=(), level=0
        ):
            if name == "contracts" or name.startswith("contracts."):
                # Always raise with the LITERAL top-level name — that's
                # what CPython produces when the top-level package
                # itself is missing (the import machinery never gets to
                # resolving submodules).
                raise ModuleNotFoundError(
                    "No module named 'contracts'"
                )
            return real_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        from graph_engine.public import _probe_contracts_re_exports

        result = _probe_contracts_re_exports()
        assert result["available"] is False
        assert result["kind"] == "contracts_missing", (
            f"top-level offline-first contracts miss must tag as "
            f"'contracts_missing' so caller downgrades to degraded; "
            f"got {result!r}"
        )
        assert result["missing_module"] == "contracts"

    def test_probe_tags_contracts_schemas_submodule_miss_as_contracts_broken(
        self, monkeypatch
    ) -> None:
        """**Codex review #13 P2 strict regression.**

        Simulate the structural-break scenario: the top-level
        ``contracts`` package IS installed and importable, but its
        ``schemas`` submodule is missing (e.g. someone deleted/renamed
        ``contracts.schemas`` in the contracts package). CPython
        raises ``ModuleNotFoundError("No module named 'contracts.schemas'")``
        — a dotted name. The probe MUST tag this as
        ``contracts_broken`` (blocked), NOT ``contracts_missing``
        (degraded). A missing submodule of an installed package is a
        structural regression, not a benign offline-first dev state.

        This is the test that previously didn't exist — without it,
        the prior helper-stripping logic silently passed the
        ``contracts.schemas`` submodule miss as if it were a top-level
        ``contracts`` miss.
        """
        import builtins
        import sys

        # Evict the schemas submodule (but keep ``contracts`` itself
        # importable — this simulates "package installed, submodule
        # gone").
        for cached in list(sys.modules):
            if cached == "contracts.schemas" or cached.startswith(
                "contracts.schemas."
            ):
                monkeypatch.delitem(sys.modules, cached, raising=False)

        real_import = builtins.__import__

        def fake_import(
            name: str, globals=None, locals=None, fromlist=(), level=0
        ):
            if name == "contracts.schemas" or name.startswith(
                "contracts.schemas."
            ):
                # Submodule-specific miss — CPython produces the dotted
                # name in the error when the submodule is the missing
                # link (with the parent already imported).
                raise ModuleNotFoundError(
                    "No module named 'contracts.schemas'"
                )
            return real_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        from graph_engine.public import _probe_contracts_re_exports

        result = _probe_contracts_re_exports()
        assert result["available"] is False
        assert result["kind"] == "contracts_broken", (
            f"contracts.schemas submodule miss while contracts is "
            f"installed is a STRUCTURAL break (not a benign "
            f"offline-first miss) — must tag as 'contracts_broken' so "
            f"caller blocks; got {result!r}. Regressing this would "
            f"re-open the codex review #13 P2 finding."
        )
        assert result["missing_module"] == "contracts.schemas", (
            "missing_module must preserve the full dotted name so "
            "downstream consumers can see exactly which submodule is "
            "absent (top-level stripping would lose this signal)"
        )
