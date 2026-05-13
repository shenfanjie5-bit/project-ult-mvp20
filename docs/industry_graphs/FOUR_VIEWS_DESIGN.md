# 四视图设计 (Four-View Design)

## 设计原则

底层是**一份**统一的因果图谱（节点 + 边），从中**派生**四种展示视图。
单条事件不直接得出"利好/利空"，而是同时跑正向路径与负向路径，比较两者强度。

```
底层统一图谱
│
├── 因果传导图：看事件如何传到 NVDA 股价
├── 核心因子图：看当前最重要的变量是什么
├── 产业链图：看上下游和客户怎么影响 NVDA
└── 风险图：看哪些路径会导致 NVDA 下跌
```

## 四视图职责

| 视图 ID | 职责 | 关注层 (layer) | 节点过滤 | 边过滤 |
|---|---|---|---|---|
| `causal_propagation` | 事件 → 股价的完整传导链 | event / industry_signal / financial / valuation / stock | 沿主路径的全部节点 | `views` 包含 `causal_propagation` |
| `core_factor` | 当前最重要的变量及其状态（高中心度） | industry_signal / financial / valuation | 中心度 top-N（默认 12） | `views` 包含 `core_factor` |
| `supply_chain` | 上下游、客户、供应商对 target 的影响 | stock / supply_chain / industry_signal | 公司、客户、供应商节点 | `views` 包含 `supply_chain` |
| `risk` | 哪些路径会导致 target 下跌 | event / risk / valuation / stock | 风险信号 + 估值压力 | `views` 包含 `risk` |

每条边在 YAML 中通过 `views: [...]` 字段声明它所属的视图——一条边可以同时归
属多个视图（如"Meta Capex → Hyperscaler Demand"既出现在 causal_propagation
也出现在 supply_chain）。

## 完整事件演示：Meta 上调 AI Capex

> 系统不输出"利好/利空"，而是同时给出**正向**与**负向**两条传导，比较强度。

### 第一步：事件进入图谱

```
事件层：
  Meta 上调 AI Capex     # 节点 id: EVENT.meta_ai_capex_upgrade

事件类型：大客户资本开支上修
影响方向（先验）：正向
```

### 第二步：匹配到产业链图

```
下游客户
└── Meta
    └── AI Capex

传导：
  Meta AI Capex 上升
    ↓
  Hyperscaler AI 基建需求上升
    ↓
  GPU / 网络 / 整机柜采购需求上升
```

涉及节点：`COMPANY.META`, `EVENT.meta_ai_capex_upgrade`,
`SIGNAL.hyperscaler_ai_demand`, `SIGNAL.blackwell_orders`。

### 第三步：进入核心因子图

激活的核心因子（节点变大变绿，状态 = 增强）：

- AI Capex
- Blackwell 订单
- 数据中心收入
- EPS 预期
- AI 叙事强度

### 第四步：进入因果传导图（正向主路径）

```
EVENT.meta_ai_capex_upgrade
   ↓ (drives_demand, β_pos=0.85, lag 1-4Q, dedup 需求组)
SIGNAL.hyperscaler_ai_demand
   ↓ (drives_demand, β_pos=0.80, lag 1-2Q, dedup 需求组)
SIGNAL.blackwell_orders
   ↓ (drives_revenue, β_pos=0.75, lag 1-3Q, dedup 需求组)
FIN.nvda_dc_revenue
   ↓ (operates_leverage, β_pos=0.70, lag 1-2Q, dedup 需求组)
FIN.nvda_eps
   ↓ (drives_alpha, β_pos=0.65, lag immediate, dedup 需求组)
COMPANY.NVDA
```

聚合强度 ≈ 0.72。

### 第五步：同时检查风险图（负向路径）

```
EVENT.meta_ai_capex_upgrade
   ↓ (triggers_tail_risk, β_pos=0.40, dedup 风险组)
RISK.ai_capex_excess_concern
   ↓ (amplifies, β_pos=0.55, dedup 风险组)
RISK.fcf_pressure
   ↓ (escalates, β_pos=0.50, dedup 风险组)
RISK.ai_roi_debate
   ↓ (compresses_valuation, β_pos=0.60, dedup 风险组)
VAL.ai_compute_crowding
   ↓ (drags_alpha, β_pos=-0.55, dedup 风险组)
COMPANY.NVDA
```

聚合强度 ≈ 0.41。

### 最终对比

| 路径方向 | 聚合强度 |
|---|---:|
| 正向（Capex → GPU 需求 → NVDA 利好） | **0.72** |
| 负向（Capex 过高 → ROI 争议 → 估值承压） | 0.41 |
| **净方向** | 正向 0.31 |

系统输出"正向 0.72 vs 负向 0.41，净正向 0.31"，而非简单二元判断。

## YAML 中的实现要点

每行业的 `config/industry_graphs/<slug>.yaml`：

```yaml
nodes:
  - id: EVENT.meta_ai_capex_upgrade
    layer: event
    type: customer_capex_event
    label_cn: Meta 上调 AI Capex
    industry_tags: [AI_COMPUTE]
  # ...

edges:
  - id: EDGE.AI.001
    source: EVENT.meta_ai_capex_upgrade
    target: SIGNAL.hyperscaler_ai_demand
    relation: drives_demand
    polarity: positive
    beta_positive: 0.85
    beta_negative: 0.70
    threshold: "Capex 同比加速达全年收入可见贡献"
    lag: "1-4 quarters"
    dedup_group: 需求组
    views: [causal_propagation, supply_chain, core_factor]
  - id: EDGE.AI.RISK.001
    source: EVENT.meta_ai_capex_upgrade
    target: RISK.ai_capex_excess_concern
    relation: triggers_tail_risk
    polarity: positive
    beta_positive: 0.40
    beta_negative: 0.30
    dedup_group: 风险组
    views: [risk]

views:
  causal_propagation:
    description: 事件 → 股价的完整传导链
    include_layers: [event, industry_signal, financial, valuation, stock]
    edge_filter: views_contains(causal_propagation)
  core_factor:
    description: 当前最重要的变量及其状态
    include_layers: [industry_signal, financial, valuation]
    aggregation: top_n_by_centrality
    top_n: 12
    edge_filter: views_contains(core_factor)
  supply_chain:
    description: 上下游和客户怎么影响 target
    include_node_types: [company, customer_capex_event, supplier_signal, downstream_signal]
    edge_filter: views_contains(supply_chain)
  risk:
    description: 哪些路径会导致下跌
    include_layers: [event, risk, valuation, stock]
    edge_filter: views_contains(risk)
```

## 仿真示例 (walk-through fixture)

完整的 NVDA / Meta Capex 双路径示例：
- 数据：`config/industry_graphs/fixtures/meta_capex_propagation.yaml`
- 走查：本文件第 4 节、第 5 节

mvp20 不在本仓实现 `forward_propagation()` 函数；fixture 仅作为 schema
完整性的对照与未来上游 graph-engine 的 golden test 输入。
