from pathlib import Path

from scripts import audit_code_index


def test_code_index_counts_python_defs_and_imports(tmp_path: Path) -> None:
    root = tmp_path
    pkg = root / "mvp20"
    pkg.mkdir()
    (pkg / "sample.py").write_text(
        "import os\n\nclass A:\n    def method(self):\n        return os.getcwd()\n\n"
        "def f():\n    return 1\n",
        encoding="utf-8",
    )

    index = audit_code_index.build_index(root, roots=("mvp20",))
    summary = audit_code_index.summarize(index)

    assert summary["totals"]["files"] == 1
    assert summary["totals"]["imports"] == 1
    assert summary["totals"]["classes"] == 1
    assert summary["totals"]["functions"] == 2
    assert summary["totals"]["definitions"] == 3
    assert summary["parse_error_count"] == 0


def test_code_index_counts_ts_and_prunes_node_modules(tmp_path: Path) -> None:
    root = tmp_path
    src = root / "FrontEnd" / "src"
    src.mkdir(parents=True)
    (src / "App.tsx").write_text(
        "import React from 'react';\n"
        "export const App = () => <main />;\n",
        encoding="utf-8",
    )
    ignored = root / "FrontEnd" / "src" / "node_modules"
    ignored.mkdir()
    (ignored / "ignored.ts").write_text("export const Bad = () => null;\n", encoding="utf-8")

    index = audit_code_index.build_index(root, roots=("FrontEnd/src",))
    summary = audit_code_index.summarize(index)

    assert summary["totals"]["files"] == 1
    assert summary["totals"]["imports"] == 1
    assert summary["totals"]["exports"] == 1
    assert summary["totals"]["definitions"] == 1
    assert summary["groups"]["FrontEnd/src"]["files"] == 1
