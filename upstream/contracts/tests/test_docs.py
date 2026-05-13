from __future__ import annotations

import pathlib
import re

from contracts import __version__


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
README = PROJECT_ROOT / "README.md"
MODULE_SPEC = PROJECT_ROOT / "docs" / "MODULE_SPEC.md"
PROGRESS = PROJECT_ROOT / "docs" / "PROGRESS.md"
TESTPLAN = PROJECT_ROOT / "docs" / "TESTPLAN.md"


def read_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def section_between(text: str, start_heading: str, end_heading: str) -> str:
    start = text.index(start_heading)
    end = text.index(end_heading, start)
    return text[start:end]


def test_stage_zero_docs_start_with_required_metadata() -> None:
    for path, expected_version in [
        (README, __version__),
        (MODULE_SPEC, "0.1.0"),
        (TESTPLAN, "0.1.0"),
    ]:
        lines = read_text(path).splitlines()

        assert lines[0] == "> 文档状态: Draft"
        assert lines[1] == f"> 版本: {expected_version}"


def test_readme_contains_issue_required_quickstart_and_references() -> None:
    readme = read_text(README)

    assert "contracts" in readme
    assert __version__ in readme
    assert "pip install -e .[dev,shared-fixtures]" in readme
    assert "合同真相源：`src/contracts/schemas`" in readme
    assert "导出产物：`artifacts/json_schema/`（阶段 2 生成）" in readme
    assert "[完整项目文档](docs/contracts.project-doc.md)" in readme
    assert "[变更记录](docs/CHANGELOG.md)" in readme
    assert "[Claude 指令](CLAUDE.md)" in readme
    assert "[Codex / Agent 指令](AGENTS.md)" in readme


def test_module_spec_contains_required_contract_terms() -> None:
    module_spec = read_text(MODULE_SPEC)

    for required_text in [
        "Ex-0",
        "Ex-1",
        "Ex-2",
        "Ex-3",
        "Formal Object",
        "Ingest Metadata",
    ]:
        assert required_text in module_spec


def test_testplan_contains_required_performance_targets() -> None:
    testplan = read_text(TESTPLAN)

    assert "JSON Schema 全量导出耗时" in testplan
    assert "< 5 秒" in testplan
    assert "< 10 秒" in testplan


def test_docs_do_not_describe_generated_schema_as_truth_source() -> None:
    for path in [README, MODULE_SPEC, TESTPLAN]:
        text = read_text(path)

        assert "Pydantic 模型是唯一" in text or path == TESTPLAN
        assert "JSON Schema 为唯一真相来源" not in text
        assert "JSON Schema 是唯一真相来源" not in text


def test_avro_mentions_are_limited_to_ci_generated_artifacts() -> None:
    for path in [README, MODULE_SPEC, TESTPLAN]:
        avro_lines = [
            line for line in read_text(path).splitlines() if "Avro" in line
        ]

        for line in avro_lines:
            assert "CI 自动导出产物" in line


def test_required_docs_exist() -> None:
    docs = {path.name for path in (PROJECT_ROOT / "docs").glob("*.md")}

    assert {
        "contracts.project-doc.md",
        "CHANGELOG.md",
        "MODULE_SPEC.md",
        "TESTPLAN.md",
    }.issubset(docs)


def test_progress_marks_completed_stage_zero_without_ambiguous_issue_ids() -> None:
    progress = read_text(PROGRESS)
    stage_zero = section_between(
        progress,
        "## 阶段 0：合同骨架（milestone-0）",
        "## 阶段 1：核心合同冻结（milestone-1）",
    )

    assert "| 阶段 0 | milestone-0 · 合同骨架 |" in progress
    assert (
        "| 阶段 0 | milestone-0 · 合同骨架 | "
        "建立包骨架、版本号、文档、冒烟测试 | 5 | 已完成 |"
    ) in progress
    assert "**总体状态**：已完成" in stage_zero
    assert "#ISSUE-" not in progress

    github_issue_numbers = range(2, 7)
    for issue_offset, github_issue_number in enumerate(github_issue_numbers, start=1):
        row_pattern = (
            rf"\| ISSUE-{issue_offset:03d} \| GH #{github_issue_number} \| "
            r".+ \| P0 \| .+ \| 已完成 \|"
        )
        assert re.search(row_pattern, stage_zero)

    for acceptance_item in [
        "全部 5 个 issue 通过各自验收标准",
        '`python -c "import contracts"` 成功',
        "`bash scripts/ci.sh` 入口存在",
        "README / MODULE_SPEC / TESTPLAN 三份文档就绪",
    ]:
        assert f"- [x] {acceptance_item}" in stage_zero

    ci_script = PROJECT_ROOT / "scripts" / "ci.sh"
    ci_script_text = read_text(ci_script)
    assert ci_script.is_file()
    assert "-m pip install -e '.[dev,shared-fixtures]'" in ci_script_text
    assert "pytest -q" in ci_script_text
    assert README.is_file()
    assert MODULE_SPEC.is_file()
    assert TESTPLAN.is_file()
