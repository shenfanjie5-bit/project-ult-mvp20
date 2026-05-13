# 项目任务拆解

## 阶段 0：项目骨架与 Replay 格式 Spike

**目标**：建立 Python 工程骨架与包边界，并用 Spike 验证 replay 语义（read_history）与 manifest 对账路径，为后续 P2c 在线审计闭环铺平道路。
**前置依赖**：无

### ISSUE-001: 项目骨架与内部包边界初始化
**labels**: P0, infrastructure, milestone-0, ready

#### 背景与目标
本 issue 负责把 `audit-eval` 从"只有文档"的状态推进到"具备最小可用 Python 工程骨架"的状态，使后续所有 audit / replay / retrospective / drift / backtest 任务都能在统一的包边界下展开。根据 §14，模块内部必须严格按 `audit_eval.audit`、`audit_eval.retro`、`audit_eval.drift`、`audit_eval.backtest`、`audit_eval.ui` 五个子包组织，且在线审计写入与离线分析同属一个 owner 但内部边界必须清晰。本 issue 同时建立测试、lint 与 CI 本地入口，以保证 §18 的单元/集成/契约/回归测试能够落地。它不承担任何业务逻辑，专注于"让下一个 issue 能够开工"这一目标。此外还会落地 §25.2 所需的目录占位与导入健康检查，避免后续 issue 反复调整骨架。

#### 所属模块
- primary writable paths:
  - `pyproject.toml`
  - `src/audit_eval/__init__.py`
  - `src/audit_eval/audit/__init__.py`
  - `src/audit_eval/retro/__init__.py`
  - `src/audit_eval/drift/__init__.py`
  - `src/audit_eval/backtest/__init__.py`
  - `src/audit_eval/ui/__init__.py`
  - `src/audit_eval/contracts/__init__.py`
  - `src/audit_eval/_boundary.py`
  - `tests/__init__.py`
  - `tests/test_package_boundary.py`
  - `tests/conftest.py`
  - `.github/workflows/ci.yml`
  - `Makefile`
- adjacent read-only / integration paths:
  - `CLAUDE.md`、`AGENTS.md`、`docs/audit-eval.project-doc.md`（只读，作为规范依据）
- off-limits paths:
  - 任何 `src/audit_eval/audit/*.py` 中的业务实现（归 ISSUE-003/004）
  - 任何 retrospective / drift / backtest 的业务实现（后续 issue）

#### 实现范围
- 工程配置:
  - `pyproject.toml`: 将 `packages` 改为使用 `setuptools.find_packages(where="src")`，新增 `[tool.setuptools.package-dir] = {"" = "src"}`；加入 dev 依赖组 `pytest>=8`, `pytest-cov`, `ruff`, `mypy`, `pydantic>=2`；保留 `requires-python = ">=3.11"`。
- 包结构:
  - `src/audit_eval/__init__.py`: 暴露 `__version__: str = "0.1.0"`，不做任何业务 re-export。
  - `src/audit_eval/audit/__init__.py`、`retro/__init__.py`、`drift/__init__.py`、`backtest/__init__.py`、`ui/__init__.py`、`contracts/__init__.py`: 均仅含模块 docstring（一句话说明子包职责）+ `__all__: list[str] = []`。
- 边界守卫:
  - `src/audit_eval/_boundary.py`: 定义 `FORBIDDEN_WRITE_FIELDS: frozenset[str] = frozenset({"feature_weight_multiplier"})` 和 `assert_no_forbidden_write(payload: dict) -> None`，当 payload 的 key 命中禁写字段时抛出 `BoundaryViolationError`。
- 测试脚手架:
  - `tests/conftest.py`: 提供 `pytest fixture tmp_workspace(tmp_path: Path) -> Path`。
  - `tests/test_package_boundary.py`:
    - `test_all_subpackages_importable()` 导入五个子包 + `contracts`。
    - `test_boundary_forbids_feature_weight_multiplier()` 调用 `assert_no_forbidden_write({"feature_weight_multiplier": 1.2})` 期望抛错。
    - `test_boundary_allows_plain_payload()` 对 `{"alert_score": 2}` 不抛错。
- CI 与本地命令:
  - `Makefile`: 目标 `install`, `test`, `lint`, `typecheck`, `ci`（组合 lint + typecheck + test）。
  - `.github/workflows/ci.yml`: 单 job，Python 3.11，运行 `make ci`。

#### 不在本次范围
- 不实现 `AuditRecord` / `ReplayRecord` / `RetrospectiveEvaluation` / `DriftReport` / `BacktestResult` 的 schema（归 ISSUE-003 与后续 issue）。
- 不实现任何 Iceberg / DuckDB / Evidently / Alphalens 的读写适配（归后续 issue）。
- 不实现 manifest 对账脚本或 replay 重建（归 ISSUE-002）。
- 不加入 Streamlit dashboard 代码（归 P5+）。
- 不调整 `docs/audit-eval.project-doc.md` 或 `CLAUDE.md`（这些是规范输入）。
- Blocker：如果需要引入第三方 Iceberg / Evidently SDK，必须另开 issue，不在本骨架 issue 中引入。

#### 关键交付物
- `pyproject.toml` 成功支持 `pip install -e .[dev]`。
- 可导入符号：`audit_eval.__version__`、`audit_eval.audit`、`audit_eval.retro`、`audit_eval.drift`、`audit_eval.backtest`、`audit_eval.ui`、`audit_eval.contracts`。
- `audit_eval._boundary.BoundaryViolationError(Exception)`。
- `audit_eval._boundary.assert_no_forbidden_write(payload: dict[str, object]) -> None`。
- `audit_eval._boundary.FORBIDDEN_WRITE_FIELDS: frozenset[str]`。
- `Makefile` 目标：`install`, `test`, `lint`, `typecheck`, `ci`。
- `.github/workflows/ci.yml`：在 push / pull_request 到 `main` 触发 `make ci`。
- 至少 3 个 pytest 用例位于 `tests/test_package_boundary.py`。
- 依赖 pin：`pytest>=8`, `pydantic>=2`, `ruff`, `mypy`。

#### 验收标准
**Core functionality:**
- [ ] `pip install -e .[dev]` 在干净虚拟环境中成功。
- [ ] `python -c "import audit_eval; print(audit_eval.__version__)"` 输出 `0.1.0`。
- [ ] 五个子包 + `contracts` 均可直接 `import audit_eval.<pkg>` 而无 ImportError。

**Error handling:**
- [ ] `assert_no_forbidden_write({"feature_weight_multiplier": 1.0})` 抛出 `BoundaryViolationError`。
- [ ] `assert_no_forbidden_write({})` 与 `assert_no_forbidden_write({"alert_score": 2})` 不抛错。

**Integration:**
- [ ] `make ci` 本地在 3.11 上通过（lint + typecheck + test 全绿）。
- [ ] GitHub Actions CI workflow 文件可被 `actionlint` 或 `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` 解析通过。

**Tests:**
- [ ] `tests/test_package_boundary.py` 至少 3 个用例并全部通过。
- [ ] 全仓库 pytest 0 failures / 0 errors。

#### 验证命令
```bash
# Unit tests
pytest tests/test_package_boundary.py -v
# Integration check
python -c "import audit_eval, audit_eval.audit, audit_eval.retro, audit_eval.drift, audit_eval.backtest, audit_eval.ui, audit_eval.contracts; print('ok')"
# Regression
make ci
```

#### 依赖
无前置依赖

---

### ISSUE-002: Replay 格式与 manifest 对账 Spike
**labels**: P0, infrastructure, milestone-0, ready

#### 背景与目标
本 issue 对应 §21 阶段 0 的 Spike：在没有任何实际主系统连接的前提下，用 fixture 数据把 replay 语义（read_history）与 manifest 对账路径验证到"给定 sample cycle，能不调用模型完成 replay 重建"。它为后续 ISSUE-004 的真实写入与 ISSUE-005 的查询接口提供参考实现骨架与反例覆盖。根据 §6 原则 2 与原则 4，任何 replay 重建必须读取历史 `sanitized_input/raw_output/parsed_result` 并严格经过 `cycle_publish_manifest`，不得重调当前模型或读取 formal 表 head。本 issue 以 offline fixture + pure-Python 形式落地该语义，并输出 `scripts/spike_replay.py` 演示脚本作为团队对齐的可执行参考。Spike 代码不进入 `audit_eval.audit` 命名空间（它不是正式实现），而是放在 `scripts/` 与 `src/audit_eval/contracts/` 下以便后续 issue 复用 schema 草案。

#### 所属模块
- primary writable paths:
  - `scripts/__init__.py`
  - `scripts/spike_replay.py`
  - `src/audit_eval/contracts/replay_draft.py`
  - `src/audit_eval/contracts/manifest_draft.py`
  - `tests/fixtures/spike/cycle_20260410/audit_records.json`
  - `tests/fixtures/spike/cycle_20260410/replay_records.json`
  - `tests/fixtures/spike/cycle_20260410/manifest.json`
  - `tests/fixtures/spike/cycle_20260410/formal_snapshots/world_state.json`
  - `tests/fixtures/spike/cycle_20260410/formal_snapshots/recommendation.json`
  - `tests/test_spike_replay.py`
  - `docs/spike-replay-notes.md`
- adjacent read-only / integration paths:
  - `src/audit_eval/_boundary.py`（可调用 `assert_no_forbidden_write`，不改写）
  - `docs/audit-eval.project-doc.md`（仅作参考）
- off-limits paths:
  - `src/audit_eval/audit/*.py`（正式实现归 ISSUE-003/004，不要越界）
  - 任何涉及实际 Iceberg / DuckDB SDK 的代码
  - 任何 retrospective / drift / backtest 代码

#### 实现范围
- Schema 草案（仅 Spike 级别，ISSUE-003 会重做正式版）:
  - `src/audit_eval/contracts/replay_draft.py`:
    - `class ReplayBundleFields(pydantic.BaseModel)`，五字段：`sanitized_input: str | None`, `input_hash: str | None`, `raw_output: str | None`, `parsed_result: dict | None`, `output_hash: str | None`。
    - `class AuditRecordDraft(pydantic.BaseModel)` 含 `record_id: str`, `cycle_id: str`, `layer: Literal["L3","L4","L5","L6","L7","L8"]`, `object_ref: str`, `params_snapshot: dict`, `llm_lineage: dict`, `llm_cost: dict`, `degradation_flags: dict`, `created_at: datetime` 以及内嵌 `ReplayBundleFields`。
    - `class ReplayRecordDraft(pydantic.BaseModel)` 含 `replay_id`, `cycle_id`, `object_ref`, `audit_record_ids: list[str]`, `manifest_cycle_id: str`, `formal_snapshot_refs: dict[str,str]`, `dagster_run_id: str`, `replay_mode: Literal["read_history"]`。
  - `src/audit_eval/contracts/manifest_draft.py`:
    - `class CyclePublishManifestDraft(pydantic.BaseModel)` 含 `published_cycle_id: str`, `snapshot_refs: dict[str,str]`, `published_at: datetime`。
- Spike 脚本:
  - `scripts/spike_replay.py`:
    - `load_manifest(path: Path) -> CyclePublishManifestDraft`
    - `load_audit_records(path: Path) -> list[AuditRecordDraft]`
    - `load_replay_record(path: Path, object_ref: str) -> ReplayRecordDraft`
    - `reconstruct_replay_view(cycle_id: str, object_ref: str, fixture_root: Path) -> dict`：返回包含 `audit_records`、`manifest_snapshot_set`、`historical_formal_objects` 的 dict，实现上严格先读 manifest、再按 `formal_snapshot_refs` 从 `formal_snapshots/*.json` 读取历史对象。
    - `main(argv: list[str] | None = None) -> int`：命令行入口，打印 JSON 重建结果。
- 固件数据:
  - `tests/fixtures/spike/cycle_20260410/`：至少一条 L4 `world_state` audit_record、一条 L7 `recommendation` audit_record、对应的 replay_record、manifest 条目与两个 formal snapshot JSON。五字段必须齐全。
- 测试:
  - `tests/test_spike_replay.py`:
    - `test_reconstruct_returns_manifest_bound_snapshots()` 验证 replay view 的 snapshot refs 全部来自 manifest。
    - `test_reconstruct_does_not_call_network()` 通过 monkeypatch `urllib.request.urlopen`、`socket.socket` 抛错守门。
    - `test_replay_record_rejects_non_read_history_mode()` 验证 `replay_mode != "read_history"` 时 pydantic 校验失败。
    - `test_five_fields_required_when_llm_called()` 验证 `AuditRecordDraft` 中若 `llm_lineage.get("called") is True` 但五字段缺失则 pydantic `model_validator` 抛错。
- 文档:
  - `docs/spike-replay-notes.md`：记录 Spike 中验证的约束映射（§6 原则 2/4、§11.1 规则、C1/C2/C5）。

#### 不在本次范围
- 不实现正式的 `persist_audit_records` / `persist_replay_records`（归 ISSUE-004）。
- 不连接真实 Iceberg / DuckDB / Dagster。
- 不实现 `replay_cycle_object` 公共 API（归 ISSUE-005）。
- 不做 retrospective / drift / backtest 任何相关逻辑。
- 不修改 `pyproject.toml` 依赖（复用 pydantic 即可）。
- Blocker：若发现 replay 五字段与主项目 `contracts` 仓库不一致，应在 issue 中标注但不在本 issue 中统一 schema，另开 contract 协调 issue。

#### 关键交付物
- `scripts/spike_replay.py` 可执行：`python -m scripts.spike_replay --cycle-id cycle_20260410 --object-ref recommendation --fixtures tests/fixtures/spike`。
- `src/audit_eval/contracts/replay_draft.py` 暴露 `ReplayBundleFields`, `AuditRecordDraft`, `ReplayRecordDraft`。
- `src/audit_eval/contracts/manifest_draft.py` 暴露 `CyclePublishManifestDraft`。
- `reconstruct_replay_view` 函数签名与返回字段见实现范围。
- Spike fixture 至少包含 1 个 cycle、2 条 audit_record、2 条 replay_record、1 份 manifest、2 份 formal snapshot。
- `docs/spike-replay-notes.md` 明确记录 replay 不调用模型、必须先读 manifest。
- pydantic `model_validator` 实现 C5 五字段校验规则。
- 所有测试 mock 网络以证明"不重调模型"。

#### 验收标准
**Core functionality:**
- [ ] 运行 `python -m scripts.spike_replay --cycle-id cycle_20260410 --object-ref recommendation --fixtures tests/fixtures/spike` 返回 exit code 0 且输出 JSON 中含 `manifest_snapshot_set`、`audit_records`、`historical_formal_objects` 三个键。
- [ ] Replay view 中所有 `historical_formal_objects` 的来源 ref 都出现在 manifest 的 `snapshot_refs` 中。
- [ ] `ReplayRecordDraft(replay_mode="rerun_model")` 抛 `pydantic.ValidationError`。

**Error handling:**
- [ ] LLM 被标记调用但五字段任意一个为 None 时，`AuditRecordDraft` 构造失败。
- [ ] Manifest 中缺失 `object_ref` 对应 snapshot 时，`reconstruct_replay_view` 抛 `KeyError` 或自定义 `ManifestMissingRefError`。

**Integration:**
- [ ] Spike 脚本运行期间无任何 outbound network call（通过 monkeypatch 证伪）。
- [ ] Spike 代码位于 `scripts/` 与 `src/audit_eval/contracts/`，未污染 `audit_eval.audit`。

**Tests:**
- [ ] `tests/test_spike_replay.py` ≥ 4 个用例，全部通过。
- [ ] 全仓库 `pytest` 0 failures / 0 errors。
- [ ] `make ci` 通过。

#### 验证命令
```bash
# Unit tests
pytest tests/test_spike_replay.py -v
# Integration check
python -m scripts.spike_replay --cycle-id cycle_20260410 --object-ref recommendation --fixtures tests/fixtures/spike
# Regression
make ci
```

#### 依赖
依赖 #ISSUE-001（项目骨架与内部包边界初始化）

---

## 阶段 1：P2c 在线审计闭环

**目标**：在骨架与 Spike 之上落地 `audit_record` / `replay_record` 的正式 schema、持久化接口与基础查询，打通 formal 审计闭环。
**前置依赖**：阶段 0

### ISSUE-003: AuditRecord / ReplayRecord 正式 schema 与 AuditWriteBundle 契约
**labels**: P0, feature, milestone-1, ready
**摘要**: 在 `audit_eval.contracts` 下实现 §9.3 定义的 `AuditRecord`、`ReplayRecord` 正式 pydantic schema，以及运行时对象 `AuditWriteBundle`，并用 contract 测试锁死 C1/C2/C5 三条不可协商约束。
**所属模块**: `src/audit_eval/contracts/{audit_record.py,replay_record.py,write_bundle.py,__init__.py}`、`tests/test_contracts_*.py`；只读参考 `src/audit_eval/contracts/replay_draft.py`（ISSUE-002 Spike 产物）以迁移字段定义。
**写入边界**: 允许修改 `src/audit_eval/contracts/**` 与对应 tests；禁止修改 `audit_eval.audit/retro/drift/backtest` 任何业务代码，禁止写入存储层代码。
**实现顺序**: 先迁移 Spike 中的字段定义到正式 schema → 补齐 C5 五字段 `model_validator` → 实现 `AuditWriteBundle` 聚合（含 formal/analytical 分区 tag 与 manifest 引用）→ 编写 contract 测试覆盖字段完整性、replay_mode 限制、`feature_weight_multiplier` 禁写、horizon 枚举；保持在 1000-1200 行范围内（含 schema + 测试）。
**依赖**: #ISSUE-002（Replay 格式 Spike 已验证字段语义）

---

### ISSUE-004: persist_audit_records / persist_replay_records 持久化实现
**labels**: P0, feature, milestone-1, ready
**摘要**: 实现 §16.1 的 `persist_audit_records` 与 `persist_replay_records`，把 `AuditWriteBundle` 写入 formal Iceberg 表（以 DuckDB + Iceberg catalog 适配层实现 Lite 模式），并在写入路径上调用 `_boundary.assert_no_forbidden_write` 守住禁写字段。
**所属模块**: `src/audit_eval/audit/{writer.py,storage.py,__init__.py}`、`tests/test_audit_writer.py`；只读参考 `src/audit_eval/contracts/*`、`src/audit_eval/_boundary.py`。
**写入边界**: 允许修改 `src/audit_eval/audit/**` 与对应 tests；禁止修改 contracts schema、retro/drift/backtest 代码；禁止直接定义 Iceberg 表结构（归 data-platform），仅通过 thin adapter 层写入。
**实现顺序**: 实现 `IcebergWriterAdapter` 协议 + 本地 DuckDB-backed 默认实现 → `persist_audit_records(bundle: AuditWriteBundle) -> list[str]`（返回 record_ids）→ `persist_replay_records(bundle: AuditWriteBundle) -> list[str]` → 写入前 boundary 校验 + manifest_cycle_id 非空校验 → degradation flags 回写；单元测试覆盖正常写、五字段缺失拒绝、禁写字段拒绝、adapter 故障降级；1200-1400 行。
**依赖**: #ISSUE-003（schema 契约）

---

### ISSUE-005: replay_cycle_object 查询接口与 ReplayView 重建
**labels**: P0, feature, milestone-1, ready
**摘要**: 实现 §11.2 的 replay 重建算法：`replay_cycle_object(cycle_id, object_ref) -> ReplayView`，严格走 `replay_record -> audit_record -> manifest snapshot set -> historical formal objects` 的顺序，不调用任何当前模型。
**所属模块**: `src/audit_eval/audit/{query.py,replay_view.py,manifest_gateway.py}`、`tests/test_replay_query.py`；只读参考 ISSUE-004 的 writer、`contracts` 与 Spike fixture。
**写入边界**: 允许修改 `src/audit_eval/audit/**` 新增查询子模块；禁止修改 writer 的写入路径；禁止引入任何 LLM client 依赖；禁止读取 formal 表 head（必须通过 `ManifestGateway` 入口）。
**实现顺序**: 定义 `ReplayView` dataclass → `ManifestGateway.load(cycle_id)` 读取 `cycle_publish_manifest` → `replay_cycle_object` 组合 audit_record + formal snapshot + dagster run summary → 回归测试：无网络调用、manifest 缺失时 fail-fast、`replay_mode != "read_history"` 时拒绝；1000-1300 行。
**依赖**: #ISSUE-004（写入接口已稳定）

---

## 阶段 2：P2c 基础 retrospective (T+1)

**目标**：在审计闭环之上落地 T+1 retrospective 计算与摘要，先形成可解释的偏差曲线与最近窗口聚合。
**前置依赖**：阶段 1

### ISSUE-006: RetrospectiveEvaluation schema 与 T+1 compute_retrospective
**labels**: P0, algorithm, milestone-2, ready
**摘要**: 实现 §9.3 `RetrospectiveEvaluation` schema 与 §11.3 的 T+1 偏差计算：`compute_retrospective(horizon="T+1", date_ref)`，写 analytical 表并严格使用 manifest 读取历史 audit_record，不得读 formal 表 head。
**所属模块**: `src/audit_eval/retro/{schema.py,compute.py,storage.py}`、`src/audit_eval/contracts/retrospective.py`、`tests/test_retro_compute.py`；只读参考 audit writer/query 与 contracts。
**写入边界**: 允许修改 `src/audit_eval/retro/**` 与 `contracts/retrospective.py`；禁止写 `feature_weight_multiplier` 或任何在线控制字段；禁止读取未来时点数据。
**实现顺序**: schema（`alert_score = max(trend,risk)`、`learning_score = trend*0.6 + risk*0.4` 以 `model_validator` 校验）→ `RetrospectiveJob` 运行对象 → `compute_retrospective(horizon: Literal["T+1"], date_ref: date) -> list[RetrospectiveEvaluation]` → analytical writer → 边界测试（禁写字段、未来窗口拒绝）+ 公式单元测试；1000-1300 行。
**依赖**: #ISSUE-005（replay/query 路径已稳定，可读取历史 seed）

---

### ISSUE-007: Retrospective summary 与累积告警
**labels**: P1, algorithm, milestone-2, ready
**摘要**: 实现 §13.3 retrospective summary 与 §11.4 累积告警算法（WARNING/CRITICAL/EMERGENCY 三档阈值），并暴露 `build_retrospective_summary(window)` Python API 供 `main-core` 读取。
**所属模块**: `src/audit_eval/retro/{summary.py,alert.py}`、`tests/test_retro_summary.py`、`tests/test_retro_alert.py`；只读参考 ISSUE-006 schema 与 compute。
**写入边界**: 允许修改 `src/audit_eval/retro/**`；禁止侵入 drift/backtest；禁止写在线控制字段；累积告警只输出 alert summary 对象，不得直接触发 orchestrator 行为（orchestrator 自取）。
**实现顺序**: `build_retrospective_summary(window: RetroWindow) -> RetrospectiveSummary`（聚合均值、趋势、L7 hit_rate_rel）→ `evaluate_cumulative_alert(history: list[RetrospectiveEvaluation]) -> AlertState` 按 §11.4 三档阈值判定 → 持久化 AlertState 到 analytical current view → 阈值边界测试覆盖（连续 3 天 ≥2、连续 3 天 ≥3、5 天中 4 天 ≥2、连续 5 天 ≥2 且 L7 hit_rate_rel < 35%）；1000-1200 行。
**依赖**: #ISSUE-006（T+1 retrospective 已可写入）

---

## 阶段 3：P5 多时域评估与 drift

**目标**：补齐 T+5 / T+20 回填、完整累积告警与 Evidently 第三层结构性告警，形成长期评估闭环。
**前置依赖**：阶段 2

### ISSUE-008: T+5 / T+20 回填与多 horizon 支持
**labels**: P1, algorithm, milestone-3, ready
**摘要**: 将 `compute_retrospective` 扩展到 `T+5` 和 `T+20` horizon，并补齐回填任务 `RetrospectiveJob` 的幂等重入语义与 horizon 覆盖率检查。
**所属模块**: `src/audit_eval/retro/{compute.py,backfill.py,horizon.py}`、`tests/test_retro_multi_horizon.py`。
**写入边界**: 允许扩展 `audit_eval.retro` 已有模块；禁止改动 schema 字段（horizon 字段已在 ISSUE-006 预留为 Literal["T+1","T+5","T+20"]）；禁止窥视未来窗口（必须用历史 manifest 覆盖的日期）。
**实现顺序**: `horizon.py` 定义 `HORIZONS = ("T+1","T+5","T+20")` 与 `resolve_evaluation_date(base, horizon)` → `backfill.py` 的 `run_backfill(date_ref, horizons)` 幂等写入 → multi-horizon 完成率 check（质量指标要求 100%） → 回归测试：T+20 当日未到期时 fail-fast；1000-1200 行。
**依赖**: #ISSUE-007（summary 与告警已就绪，需要多 horizon 输入）

---

### ISSUE-009: Evidently drift_report 与第三层结构性告警
**labels**: P1, algorithm, milestone-3, ready
**摘要**: 实现 §11.5 drift 算法：`run_drift_report(reference_ref, target_ref)` 生成 Evidently 报告、写 analytical `drift_report` 资产，并产出第三层 `regime_warning_level`；严格 fail-fast 拒绝任何写入 `feature_weight_multiplier` 的尝试。
**所属模块**: `src/audit_eval/drift/{runner.py,rules.py,schema.py}`、`src/audit_eval/contracts/drift_report.py`、`tests/test_drift_runner.py`、`tests/test_drift_boundary.py`。
**写入边界**: 允许修改 `src/audit_eval/drift/**`、`contracts/drift_report.py`；禁止修改 retro/audit/backtest 模块；禁止引入任何在线控制字段；报告 JSON 写路径通过 thin adapter 委托给 data-platform namespace（不得自造路径）。
**实现顺序**: 引入 `evidently>=0.4` 依赖 → `schema.py` 定义 `DriftReport`、`DriftAlertPayload` → `rules.py` 实现阈值映射与告警规则版本 → `runner.py` `run_drift_report(reference_ref, target_ref) -> DriftReport` → 边界测试（任何试图写 `feature_weight_multiplier` 的路径抛 `BoundaryViolationError`）+ 报告生成 smoke 测试；1200-1500 行。
**依赖**: #ISSUE-008（多 horizon retrospective 稳定，drift 可作为并列第三层）

---

## 阶段 4：P10 回测能力

**目标**：补齐 point-in-time 检查器、Alphalens 集成与 `backtest_result` 写入，作为 P10 后置离线分析能力。
**前置依赖**：阶段 3

### ISSUE-010: Point-in-time 检查器与 BacktestResult schema
**labels**: P2, feature, milestone-4, ready
**摘要**: 实现 §11.6 的 point-in-time 守门：`PointInTimeChecker.validate(feature_ref, snapshot_range) -> PITCheckResult`，并定义 `BacktestResult` 正式 schema 与 `BacktestJob` 运行对象。任何 PIT 检查未通过的结果一律拒绝入库。
**所属模块**: `src/audit_eval/backtest/{pit_checker.py,schema.py,job.py}`、`src/audit_eval/contracts/backtest_result.py`、`tests/test_pit_checker.py`、`tests/test_backtest_schema.py`。
**写入边界**: 允许修改 `src/audit_eval/backtest/**`、`contracts/backtest_result.py`；禁止修改 retro/drift 已发布模块；禁止引入 NautilusTrader 或第二套研究平台（主文档 §22 与本项目 CLAUDE.md 明确限制）。
**实现顺序**: `PITCheckResult` dataclass（passed: bool, violations: list）→ `PointInTimeChecker.validate(feature_ref, snapshot_range)` 通过 manifest 时点校验排除未来可见特征 → `BacktestResult` schema（`pit_check_passed` 为硬字段）→ `BacktestJob` 运行对象 → 单元测试：look-ahead bias 用例必须被拦截；1000-1200 行。
**依赖**: #ISSUE-009（drift 已闭环，可进入 P10 回测）

---

### ISSUE-011: Alphalens 回测集成与 backtest_result 写入
**labels**: P2, feature, milestone-4, ready
**摘要**: 基于 ISSUE-010 的 PIT 守门，实现 §11.6 与 §16.1 的 `run_backtest(job_config)`：调用 Alphalens 计算 IC / 分组收益 / 衰减，仅在 PIT 通过时写入 analytical `backtest_result`。Backtrader 作为可选扩展，本 issue 只暴露插拔点不强制实现。
**所属模块**: `src/audit_eval/backtest/{runner.py,alphalens_adapter.py,writer.py}`、`tests/test_backtest_runner.py`、`tests/fixtures/backtest/`。
**写入边界**: 允许修改 `src/audit_eval/backtest/**`；禁止写入 formal 表（backtest_result 属 analytical）；禁止在日频 cycle 内触发 run_backtest（只暴露离线入口）。
**实现顺序**: 引入 `alphalens-reloaded` 依赖 → `AlphalensAdapter.run(feature_ref, snapshot_range) -> dict` → `run_backtest(job_config: BacktestJob) -> BacktestResult` 先调用 `PointInTimeChecker.validate`，未通过则抛 `PITViolationError` 且不写库 → `writer.persist_backtest_result` 仅在 PIT 通过时写入 analytical → fixture + 冒烟测试 + look-ahead 防护测试；1200-1500 行。
**依赖**: #ISSUE-010（PIT checker 与 schema 已就绪）

---
