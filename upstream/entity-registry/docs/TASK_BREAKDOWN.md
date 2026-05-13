# 项目任务拆解

## 阶段 0：P1 最小实体锚点

**目标**：基于 `stock_basic` 建立最小 ENT_* registry，使全部 A 股上市公司拥有正式 canonical_entity_id
**前置依赖**：无

### ISSUE-001: 项目基础设施与核心领域对象模型
**labels**: P0, infrastructure, milestone-0, model

#### 背景与目标
`entity-registry` 是主项目中唯一负责 ENT_* 命名空间的模块（§1），在编写任何业务逻辑之前，需要先建立项目骨架、定义全部领域对象的 Pydantic 模型、枚举类型、ENT_* canonical ID 生成规则，以及数据存取的 Repository 抽象层。本 issue 覆盖 §9 中定义的全部 4 类持久层对象（CanonicalEntity、EntityAlias、EntityReference、ResolutionCase）和 4 类运行时对象（MentionCandidateSet、ResolutionContext、ResolutionDecision、BatchResolutionJob），以及 §11.1 中 ID 格式规则和 §10.2 中存储接口的抽象定义。这些模型是后续所有初始化、解析、审计功能的公共基础，必须在第一个 issue 中一次性落地，确保类型安全和对象契约从项目开始即保持一致。

#### 所属模块
**主要写入路径（primary writable）**：
- `src/entity_registry/__init__.py`
- `src/entity_registry/core.py`
- `src/entity_registry/references.py`
- `src/entity_registry/resolution_types.py`
- `src/entity_registry/storage.py`
- `tests/__init__.py`
- `tests/test_core.py`
- `tests/test_references.py`
- `tests/test_storage.py`
- `pyproject.toml`

**只读参考路径（read-only）**：
- `docs/entity-registry.project-doc.md`（§9 对象定义、§10 存储方案）
- `CLAUDE.md`（OWN/BAN/EDGE 约束）

**禁止触碰路径（off-limits）**：
- `src/entity_registry/init.py`（归 ISSUE-002）
- `src/entity_registry/aliases.py`（归 ISSUE-002）
- `src/entity_registry/resolution.py`（归 ISSUE-003/004）
- 任何 `data-platform` 或 `reasoner-runtime` 的内部实现

#### 实现范围
**项目骨架搭建**：
- `pyproject.toml`：添加 `pydantic>=2.0` 依赖，设置 `requires-python = ">=3.12"`，配置 `packages = ["src/entity_registry"]`，添加 `pytest>=8.0` 到 dev 依赖
- `src/entity_registry/__init__.py`：导出版本号 `__version__ = "0.1.0"` 和核心公共类型

**枚举与常量定义（core.py）**：
- `EntityType(str, Enum)`：`STOCK / CORP / PERSON / ORG / INDEX`
- `EntityStatus(str, Enum)`：`ACTIVE / INACTIVE / MERGED`
- `AliasType(str, Enum)`：`FULL_NAME / SHORT_NAME / CODE / ENGLISH / FORMER_NAME / CNSPELL`
- `ResolutionMethod(str, Enum)`：`DETERMINISTIC / FUZZY / LLM / MANUAL / UNRESOLVED`
- `DecisionType(str, Enum)`：`AUTO / LLM_ASSISTED / MANUAL_REVIEW`
- `FinalStatus(str, Enum)`：`RESOLVED / UNRESOLVED / MANUAL_REVIEW`

**持久层对象模型（core.py + references.py）**：
- `core.py` — `CanonicalEntity(BaseModel)`：字段 `canonical_entity_id: str, entity_type: EntityType, display_name: str, status: EntityStatus, anchor_code: str | None, cross_listing_group: str | None, created_at: datetime, updated_at: datetime`；含 `model_validator` 校验 `ENT_STOCK_*` 格式时 `anchor_code` 必填
- `core.py` — `EntityAlias(BaseModel)`：字段 `canonical_entity_id: str, alias_text: str, alias_type: AliasType, confidence: float, source: str, is_primary: bool, created_at: datetime`；含 `field_validator` 校验 `confidence` 范围 [0.0, 1.0]
- `references.py` — `EntityReference(BaseModel)`：字段 `reference_id: str, raw_mention_text: str, source_context: dict, resolved_entity_id: str | None, resolution_method: ResolutionMethod, resolution_confidence: float | None, created_at: datetime`
- `references.py` — `ResolutionCase(BaseModel)`：字段 `case_id: str, reference_id: str, candidate_entity_ids: list[str], selected_entity_id: str | None, decision_type: DecisionType, decision_rationale: str, created_at: datetime`

**运行时对象模型（resolution_types.py）**：
- `MentionCandidateSet(BaseModel)`：字段 `raw_mention_text: str, deterministic_hits: list[str], fuzzy_hits: list[str], llm_required: bool, final_status: FinalStatus`
- `ResolutionContext(BaseModel)`：字段 `raw_mention_text: str, document_context: str, source_type: str, timestamp: datetime`
- `ResolutionDecision(BaseModel)`：字段 `selected_entity_id: str | None, method: ResolutionMethod, confidence: float | None, rationale: str`
- `BatchResolutionJob(BaseModel)`：字段 `job_id: str, reference_ids: list[str], status: str, created_at: datetime, completed_at: datetime | None`

**ID 生成规则（core.py）**：
- `def generate_stock_entity_id(ts_code: str) -> str`：按 `ENT_STOCK_{ts_code}` 格式生成上市公司 ID，含输入校验（不能为空、格式合法）
- `def validate_entity_id(entity_id: str) -> bool`：校验 canonical ID 格式是否合法，支持 `ENT_STOCK_*` 和后续扩展格式

**存储抽象层（storage.py）**：
- `EntityRepository(Protocol)`：定义 `get(entity_id: str) -> CanonicalEntity | None`、`save(entity: CanonicalEntity) -> None`、`list_all() -> list[CanonicalEntity]`、`exists(entity_id: str) -> bool`
- `AliasRepository(Protocol)`：定义 `find_by_text(alias_text: str) -> list[EntityAlias]`、`find_by_entity(entity_id: str) -> list[EntityAlias]`、`save(alias: EntityAlias) -> None`、`save_batch(aliases: list[EntityAlias]) -> None`
- `ReferenceRepository(Protocol)`：定义 `save(ref: EntityReference) -> None`、`get(reference_id: str) -> EntityReference | None`、`find_unresolved() -> list[EntityReference]`
- `InMemoryEntityRepository`：实现 `EntityRepository`，用 `dict[str, CanonicalEntity]` 存储
- `InMemoryAliasRepository`：实现 `AliasRepository`，用 `dict[str, list[EntityAlias]]` 双索引（按 entity_id 和 alias_text）
- `InMemoryReferenceRepository`：实现 `ReferenceRepository`

**测试（tests/）**：
- `tests/test_core.py`：CanonicalEntity / EntityAlias 模型构建与校验、枚举值完整性、ID 生成、ID 校验、A+H 独立 ID 约束
- `tests/test_references.py`：EntityReference / ResolutionCase 模型构建与校验、resolution_types 各模型测试
- `tests/test_storage.py`：InMemory 各 Repository 的 CRUD 测试、批量写入、查询过滤

#### 不在本次范围
- 不实现 `initialize_from_stock_basic()` 初始化流程（归 ISSUE-002）
- 不实现 `AliasManager` 别名管理业务逻辑（归 ISSUE-002）
- 不实现任何解析算法（deterministic/fuzzy/LLM，归 ISSUE-003 及后续）
- 不创建实际 PostgreSQL 迁移脚本或 Iceberg 表定义（当前阶段只定义 Protocol 和内存实现）
- 不连接 `data-platform` 或 `reasoner-runtime`（仅定义抽象接口）
- 如需新增模型字段超出 §9 定义范围，应另开 issue 讨论而非在本 issue 中扩展

#### 关键交付物
- `EntityType / EntityStatus / AliasType / ResolutionMethod / DecisionType / FinalStatus` 六个枚举类
- `CanonicalEntity(BaseModel)` 含 `model_validator` 校验 anchor_code 必填规则
- `EntityAlias(BaseModel)` 含 `field_validator` 校验 confidence 范围
- `EntityReference(BaseModel)` 含 resolved/unresolved 双态支持
- `ResolutionCase(BaseModel)` 含候选集与决策理由结构
- `MentionCandidateSet / ResolutionContext / ResolutionDecision / BatchResolutionJob` 四个运行时模型
- `generate_stock_entity_id(ts_code: str) -> str`：ID 生成函数，空输入抛 `ValueError`
- `validate_entity_id(entity_id: str) -> bool`：ID 校验函数
- `EntityRepository(Protocol) / AliasRepository(Protocol) / ReferenceRepository(Protocol)`：三个 Repository 协议
- `InMemoryEntityRepository / InMemoryAliasRepository / InMemoryReferenceRepository`：三个内存实现
- `pyproject.toml` 更新后可通过 `pip install -e .` 安装

#### 验收标准
**核心对象模型：**
- [ ] `CanonicalEntity` 模型可正确构建，包含 §9.3 定义的全部字段，序列化/反序列化无数据丢失
- [ ] `EntityAlias` 模型 `confidence` 字段校验：< 0.0 或 > 1.0 时抛出 `ValidationError`
- [ ] `CanonicalEntity` 当 `entity_type == STOCK` 时，`anchor_code` 为 None 触发校验错误
- [ ] 全部 6 个枚举类型值域与 §9.3 / §3 术语表一致
- [ ] 运行时对象（MentionCandidateSet 等 4 个）可正确构建和序列化

**ID 生成规则：**
- [ ] `generate_stock_entity_id("300750.SZ")` 返回 `"ENT_STOCK_300750.SZ"`
- [ ] `generate_stock_entity_id("")` 抛出 `ValueError`
- [ ] `validate_entity_id("ENT_STOCK_300750.SZ")` 返回 `True`
- [ ] `validate_entity_id("RANDOM_ID")` 返回 `False`
- [ ] A 股和 H 股同一公司生成不同 canonical ID（如 `ENT_STOCK_300750.SZ` != `ENT_STOCK_06888.HK`）

**存储抽象层：**
- [ ] `InMemoryEntityRepository` 实现 `save / get / list_all / exists` 全部方法
- [ ] `InMemoryAliasRepository` 支持按 `alias_text` 和 `entity_id` 双向查询
- [ ] `InMemoryReferenceRepository` 的 `find_unresolved()` 仅返回 `resolved_entity_id is None` 的记录

**项目基础设施：**
- [ ] `pip install -e .` 无错误完成
- [ ] `python -c "from entity_registry.core import CanonicalEntity"` 可正常导入

**测试：**
- [ ] 单元测试 ≥ 25 个，覆盖模型构建、校验失败、ID 生成、Repository CRUD 全部场景
- [ ] `pytest tests/` 全部通过，无警告

#### 验证命令
```bash
# 安装项目
pip install -e ".[dev]"

# 单元测试
pytest tests/test_core.py tests/test_references.py tests/test_storage.py -v

# 导入检查
python -c "from entity_registry.core import CanonicalEntity, EntityAlias, generate_stock_entity_id; print('OK')"
python -c "from entity_registry.references import EntityReference, ResolutionCase; print('OK')"
python -c "from entity_registry.storage import InMemoryEntityRepository; print('OK')"

# 回归测试
pytest tests/ -v
```

#### 依赖
无前置依赖

---

### ISSUE-002: stock_basic 初始化管线与别名生成
**labels**: P0, feature, milestone-0, integration

#### 背景与目标
§21 阶段 0 的核心交付物是"全部 A 股上市公司有正式 canonical_entity_id"。本 issue 实现 §11.1 定义的初始化算法：从 `data-platform` 提供的 `stock_basic` canonical 表读取上市公司数据，按 `ENT_STOCK_{ts_code}` 规则生成 CanonicalEntity，并从 name/fullname/enname/cnspell/symbol 等字段生成 EntityAlias 记录。同时实现 §14 中 `entity_registry.aliases` 模块的别名管理基础能力和 `entity_registry.init` 模块的初始化入口。A+H 双上市公司必须生成独立 canonical ID 并通过 `cross_listing_group` 关联（§5.4），这是零容忍约束。本 issue 完成后，entity-registry 即具备最小实体锚点能力，满足 §21 阶段 0 退出条件。

#### 所属模块
**主要写入路径（primary writable）**：
- `src/entity_registry/init.py`
- `src/entity_registry/aliases.py`
- `tests/test_init.py`
- `tests/test_aliases.py`
- `tests/fixtures/stock_basic_sample.json`
- `tests/fixtures/__init__.py`

**只读集成路径（read-only integration）**：
- `src/entity_registry/core.py`（使用 CanonicalEntity / EntityAlias / generate_stock_entity_id）
- `src/entity_registry/storage.py`（使用 Repository 接口）
- `docs/entity-registry.project-doc.md`（§11.1 初始化算法、§9.3 对象字段定义）

**禁止触碰路径（off-limits）**：
- `src/entity_registry/resolution.py`（归后续 issue）
- `data-platform` 私有 adapter 实现（BAN 约束：只读 `stock_basic` canonical 表的公共接口）
- 任何 Tushare SDK 直连代码

#### 实现范围
**stock_basic 数据模型（init.py）**：
- `StockBasicRecord(BaseModel)`：字段 `ts_code: str, symbol: str, name: str, fullname: str | None, enname: str | None, cnspell: str | None, market: str, exchange: str, list_status: str, list_date: str | None, is_hs: str | None`
- `InitializationResult(BaseModel)`：字段 `entities_created: int, aliases_created: int, cross_listing_groups: int, errors: list[str]`

**初始化管线（init.py）**：
- `def load_stock_basic_records(snapshot_ref: str) -> list[StockBasicRecord]`：从 snapshot 路径（JSON/CSV）读取 stock_basic 数据，此函数只做 I/O 读取，不依赖 `data-platform` 私有接口
- `def detect_cross_listing_groups(records: list[StockBasicRecord]) -> dict[str, str]`：根据 `is_hs` 字段和公司名匹配，检测 A+H 双上市关系，返回 `{ts_code: group_id}` 映射
- `def initialize_from_stock_basic(snapshot_ref: str, entity_repo: EntityRepository, alias_repo: AliasRepository) -> InitializationResult`：主入口函数，读取数据 → 生成 CanonicalEntity → 生成 EntityAlias → 写入 Repository → 返回结果统计；对每条 stock_basic 记录依次执行：(1) 调用 `generate_stock_entity_id(ts_code)` 生成 ID，(2) 创建 CanonicalEntity，(3) 调用 `generate_aliases_from_stock_basic()` 生成别名列表，(4) 写入 Repository

**别名生成与管理（aliases.py）**：
- `def generate_aliases_from_stock_basic(record: StockBasicRecord, canonical_entity_id: str) -> list[EntityAlias]`：从 stock_basic 记录的 name/fullname/enname/cnspell/symbol 字段生成对应 alias_type 的 EntityAlias 列表，name 标记 `is_primary=True`
- `class AliasManager`：
  - `__init__(self, alias_repo: AliasRepository) -> None`
  - `add_alias(self, alias: EntityAlias) -> None`：添加单条别名，检查重复
  - `add_aliases_batch(self, aliases: list[EntityAlias]) -> int`：批量添加，返回成功数
  - `lookup(self, alias_text: str) -> list[EntityAlias]`：按别名文本查找（精确匹配），后续 ISSUE-003 将扩展为模糊查找
  - `get_entity_aliases(self, canonical_entity_id: str) -> list[EntityAlias]`：获取某实体的全部别名

**测试数据与测试**：
- `tests/fixtures/stock_basic_sample.json`：包含 ≥ 20 条 A 股记录（覆盖主板/创业板/科创板）、≥ 2 对 A+H 双上市记录、≥ 2 条退市公司记录
- `tests/test_init.py`：初始化全流程测试（正常路径、空输入、重复初始化幂等性、A+H 分离验证）
- `tests/test_aliases.py`：别名生成测试（各字段映射、缺失字段处理、is_primary 标记）、AliasManager CRUD 测试

#### 不在本次范围
- 不实现 `lookup_alias()` 的模糊匹配能力（归 ISSUE-003，本 issue 只做精确匹配）
- 不实现 `resolve_mention()` 解析逻辑（归 ISSUE-003/004）
- 不对接真实 `data-platform` 服务（本 issue 从本地 JSON/CSV fixture 读取）
- 不实现增量更新逻辑（仅全量初始化，增量归后续 issue）
- 不实现 PostgreSQL/Iceberg 持久化（使用 ISSUE-001 的 InMemory Repository）
- 如发现 `stock_basic` 字段与 §9.3 对象定义不匹配，应记录 gap 但不修改核心模型（另开 issue）

#### 关键交付物
- `StockBasicRecord(BaseModel)`：stock_basic 输入数据模型
- `InitializationResult(BaseModel)`：初始化结果统计模型
- `load_stock_basic_records(snapshot_ref: str) -> list[StockBasicRecord]`：数据加载函数
- `detect_cross_listing_groups(records: list[StockBasicRecord]) -> dict[str, str]`：A+H 双上市检测，零容忍合并约束
- `initialize_from_stock_basic(snapshot_ref: str, entity_repo, alias_repo) -> InitializationResult`：初始化主入口
- `generate_aliases_from_stock_basic(record, canonical_entity_id) -> list[EntityAlias]`：别名生成函数，映射规则：name→SHORT_NAME(primary), fullname→FULL_NAME, enname→ENGLISH, cnspell→CNSPELL, symbol→CODE
- `AliasManager` 类：含 `add_alias / add_aliases_batch / lookup / get_entity_aliases` 四个方法
- `tests/fixtures/stock_basic_sample.json`：≥ 24 条测试数据覆盖全部边界场景
- 错误处理：`load_stock_basic_records` 对不存在的路径抛 `FileNotFoundError`，对格式错误抛 `ValueError`

#### 验收标准
**初始化流程：**
- [ ] `initialize_from_stock_basic()` 处理 20+ 条 fixture 数据，生成对应数量的 CanonicalEntity
- [ ] 每条 stock_basic 记录至少生成 2 条 EntityAlias（name + symbol 为必填）
- [ ] 初始化结果 `InitializationResult.entities_created` 与输入记录数一致
- [ ] 重复调用 `initialize_from_stock_basic()` 具有幂等性（不产生重复实体）

**A+H 双上市：**
- [ ] A+H 双上市公司生成两个独立 canonical_entity_id（如宁德时代 A 股 vs H 股）
- [ ] 两个独立 ID 通过 `cross_listing_group` 字段关联到同一组
- [ ] `detect_cross_listing_groups()` 正确识别 fixture 中的全部 A+H 对

**别名生成：**
- [ ] name 字段映射为 `alias_type=SHORT_NAME, is_primary=True`
- [ ] fullname/enname/cnspell/symbol 分别映射为对应 alias_type
- [ ] 缺失字段（如 enname 为 None）不生成对应 alias，不报错

**别名管理：**
- [ ] `AliasManager.lookup("宁德时代")` 返回匹配的 EntityAlias 列表
- [ ] `AliasManager.get_entity_aliases(entity_id)` 返回该实体全部别名

**错误处理：**
- [ ] 不存在的 snapshot_ref 路径抛出 `FileNotFoundError`
- [ ] 格式不合法的 JSON 抛出 `ValueError`

**测试：**
- [ ] 单元测试 ≥ 20 个，覆盖初始化正常路径、边界场景、A+H 分离、别名生成映射、AliasManager CRUD
- [ ] 全部既有测试（ISSUE-001）仍然通过，无回归

#### 验证命令
```bash
# 单元测试
pytest tests/test_init.py tests/test_aliases.py -v

# 初始化流程端到端验证
python -c "
from entity_registry.init import initialize_from_stock_basic
from entity_registry.storage import InMemoryEntityRepository, InMemoryAliasRepository
er, ar = InMemoryEntityRepository(), InMemoryAliasRepository()
result = initialize_from_stock_basic('tests/fixtures/stock_basic_sample.json', er, ar)
print(f'Entities: {result.entities_created}, Aliases: {result.aliases_created}')
assert result.entities_created >= 20
"

# 回归测试
pytest tests/ -v
```

#### 依赖
依赖 #ISSUE-001（核心领域对象模型与存储抽象层）

---

## 阶段 1：P1-P2 确定性解析

**目标**：打通 alias 查表、代码匹配和基础 profile 查询，使主系统和图谱能稳定读取 ENT_* 锚点
**前置依赖**：阶段 0

### ISSUE-003: 别名查表与确定性匹配引擎
**labels**: P1, algorithm, milestone-1, feature
**摘要**: 实现 §11.2 两级解析的 Level 1 确定性匹配——基于 alias 表的精确查表、代码匹配和规则匹配，当唯一命中时直接返回 canonical_entity_id，多候选时标记进入 Level 2
**所属模块**: `src/entity_registry/resolution.py`（主要写入）+ `src/entity_registry/aliases.py`（扩展 lookup 能力）；只读集成 `src/entity_registry/core.py`、`src/entity_registry/storage.py`
**写入边界**: 允许修改 `resolution.py`（新建）、`aliases.py`（扩展精确/代码/规则匹配）；禁止修改 `core.py` 模型定义、`init.py` 初始化逻辑
**实现顺序**: 先扩展 AliasManager 支持代码匹配和规则匹配 → 再实现 DeterministicMatcher 类（exact_match / code_match / rule_match 三步流水线）→ 实现 `lookup_alias(alias_text: str) -> list[EntityAlias]` 公共 API → 编写覆盖唯一命中/多候选/无命中三种路径的测试（含 alias 解析延迟 < 50ms 基准测试）
**依赖**: 依赖 #ISSUE-002（AliasManager 和已初始化的别名数据）

---

### ISSUE-004: 实体画像查询与 resolve_mention 确定性路径
**labels**: P1, feature, milestone-1, integration
**摘要**: 实现 §16.1 中 `get_entity_profile(canonical_entity_id)` 画像查询 API 和 `resolve_mention(raw_mention_text, context)` 的确定性路径版本——调用 ISSUE-003 的 DeterministicMatcher，成功时写 EntityReference 记录，未解析时调用 `register_unresolved_reference()` 显式记录（§4.2 禁止静默丢弃）
**所属模块**: `src/entity_registry/resolution.py`（扩展 resolve_mention）+ `src/entity_registry/references.py`（EntityReference 写入逻辑）+ `src/entity_registry/profile.py`（新建）；只读集成 `src/entity_registry/storage.py`
**写入边界**: 允许修改 `resolution.py`（添加 resolve_mention 确定性路径）、`references.py`（添加 save/query 业务方法）、新建 `profile.py`；禁止修改 `core.py` 模型定义、禁止实现任何 fuzzy/LLM 解析逻辑
**实现顺序**: 先实现 `get_entity_profile()` 画像聚合（entity + aliases + cross_listing 信息）→ 再实现 `register_unresolved_reference(reference)` 未解析记录 → 实现 `resolve_mention()` 确定性路径（调用 DeterministicMatcher → 写 EntityReference → 返回结果或 unresolved）→ 测试覆盖 §16.1 全部公共 API 签名 + 返回结构稳定性验证
**依赖**: 依赖 #ISSUE-003（DeterministicMatcher 确定性匹配能力）

---

## 阶段 2：P4 模糊解析与 LLM 辅助

**目标**：接入 HanLP、Splink 和 `reasoner-runtime`，使复杂新闻/公告 mention 能进入完整解析链
**前置依赖**：阶段 1

### ISSUE-005: HanLP NER 集成与 Splink 模糊候选生成
**labels**: P2, algorithm, milestone-2, integration
**摘要**: 实现 §11.2 Level 2 的前半段——集成 HanLP Lite 进行中文实体命名识别（NER），集成 Splink 进行 blocking + 相似度计算 + clustering 候选生成，输出 MentionCandidateSet 供后续 LLM 辅助裁决或直接解析
**所属模块**: `src/entity_registry/resolution.py`（扩展 fuzzy 路径）+ `src/entity_registry/ner.py`（新建 HanLP 封装）+ `src/entity_registry/fuzzy.py`（新建 Splink 封装）；只读集成 `src/entity_registry/aliases.py`、`src/entity_registry/storage.py`
**写入边界**: 允许新建 `ner.py`、`fuzzy.py`，扩展 `resolution.py`；禁止修改 `core.py` 模型定义；HanLP/Splink 在 P4 前可为空实现（§15 最低要求）；禁止直连任何 LLM provider SDK
**实现顺序**: 先实现 `NERExtractor` 协议和 HanLP 适配器（含空实现 fallback）→ 再实现 `FuzzyMatcher` 协议和 Splink 适配器（blocking 策略 + 相似度阈值配置）→ 将 fuzzy 路径接入 `resolve_mention()` 流水线（deterministic 未命中时触发）→ 测试覆盖中文公司名 NER 抽取、多候选相似度排序、MentionCandidateSet 生成
**依赖**: 依赖 #ISSUE-004（resolve_mention 确定性路径框架）

---

### ISSUE-006: reasoner-runtime LLM 辅助消歧与完整解析链
**labels**: P2, algorithm, milestone-2, integration
**摘要**: 实现 §11.2 Level 2 后半段——当 Splink 候选集仍不明确时，将候选集 + 上下文通过 `reasoner-runtime` 公开结构化接口进行 LLM 辅助裁决，并完成 EntityReference + ResolutionCase 的完整审计记录写入，打通 Deterministic → Fuzzy → LLM → Unresolved 四级完整解析链
**所属模块**: `src/entity_registry/resolution.py`（完整解析链）+ `src/entity_registry/llm_client.py`（新建 reasoner-runtime 客户端封装）+ `src/entity_registry/references.py`（ResolutionCase 写入）；只读集成 `src/entity_registry/fuzzy.py`
**写入边界**: 允许新建 `llm_client.py`（仅封装 reasoner-runtime 公开接口），扩展 `resolution.py` 和 `references.py`；禁止直连 OpenAI/Anthropic 等 provider SDK（BAN 约束）；禁止复制 PII scrub、retry/backoff、lineage 逻辑（归 reasoner-runtime）
**实现顺序**: 先定义 `ReasonerRuntimeClient` 协议 + mock 实现 → 实现 LLM 辅助消歧逻辑（构建 prompt 语义、解析结构化响应）→ 将 LLM 路径接入完整 resolve_mention() 流水线 → 实现 ResolutionCase 完整写入 → 测试覆盖 §11.3 mention resolution 全流程（含 reasoner-runtime mock）+ mention resolution 平均耗时 < 2 秒验证
**依赖**: 依赖 #ISSUE-005（Splink 模糊候选生成能力）

---

## 阶段 3：P4-P5 批量回补与人工复核

**目标**：建立 unresolved 批处理与 review 闭环，使未解析引用不再静默堆积
**前置依赖**：阶段 2

### ISSUE-007: 批量解析与未解析引用回补
**labels**: P2, feature, milestone-3
**摘要**: 实现 §11.4 批量回补算法和 §16.1 中 `batch_resolve(references)` API——收集未解析引用，通过 Splink clustering 生成候选组，自动解析可判定部分，其余标记进入人工复核队列，完成 BatchResolutionJob 生命周期管理
**所属模块**: `src/entity_registry/batch.py`（新建）；只读集成 `src/entity_registry/resolution.py`、`src/entity_registry/fuzzy.py`、`src/entity_registry/storage.py`
**写入边界**: 允许新建 `batch.py`；禁止修改 `resolution.py` 的单次解析逻辑（batch 应组合调用而非重写）；禁止绕过 resolve_mention 直接写 EntityReference
**实现顺序**: 先实现 `BatchResolutionJob` 生命周期管理（创建 → 运行 → 完成/失败）→ 实现 unresolved 引用收集与 Splink clustering 分组 → 实现自动解析 + 人工复核分流逻辑 → 实现 `batch_resolve(references)` 公共 API → 测试覆盖批量解析全流程 + 幂等性 + 错误恢复
**依赖**: 依赖 #ISSUE-006（完整解析链，batch 内部复用 resolve_mention）

---

### ISSUE-008: 人工复核队列与解析审计链
**labels**: P2, feature, milestone-3, integration
**摘要**: 实现 §14 中 `entity_registry.review` 模块——建立 UnresolvedQueueItem 管理、人工复核工作流（领取 → 裁决 → 晋升/驳回）、Resolution Audit Payload 输出（§13.3），使审计人员和 `audit-eval` 系统可追踪全部消歧决策链路
**所属模块**: `src/entity_registry/review.py`（新建）；只读集成 `src/entity_registry/references.py`、`src/entity_registry/storage.py`、`src/entity_registry/core.py`
**写入边界**: 允许新建 `review.py`，可小幅扩展 `storage.py`（添加 ReviewRepository 协议）；禁止修改 `resolution.py` 解析逻辑；禁止让未解析 mention 绕过复核直接晋升为 canonical entity
**实现顺序**: 先定义 `UnresolvedQueueItem` 模型和 `ReviewRepository` 协议 → 实现复核工作流（claim → decide → promote/reject）→ 实现 Resolution Audit Payload 聚合输出（§13.3 结构）→ 实现晋升为正式实体/别名的写入逻辑 → 测试覆盖完整复核闭环 + 审计链完整性 + unresolved 不静默丢弃验证
**依赖**: 依赖 #ISSUE-007（批量解析产生的人工复核分流结果）

---
