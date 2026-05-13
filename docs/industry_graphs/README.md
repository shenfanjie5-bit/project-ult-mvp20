# Industry Causal Graphs (v3.1 / v3.1.1)

This directory holds the **human-readable** reference documents for the
13-industry causal-graph templates that power the MVP. The structured,
machine-checkable counterparts live alongside under
`config/industry_graphs/<slug>.yaml`.

## Document layout

- One markdown per industry (12 present, 1 pending):
  - [AI_COMPUTE.md](AI_COMPUTE.md) — AI算力硬件与通信设备
  - [SEMI_EQUIPMENT.md](SEMI_EQUIPMENT.md) — 半导体设备材料与先进封装
  - [ROBOTICS.md](ROBOTICS.md) — 机器人与具身智能高端装备
  - [NONFERROUS_METALS.md](NONFERROUS_METALS.md) — 有色资源黄金铜稀土小金属
  - [INNOVATIVE_PHARMA.md](INNOVATIVE_PHARMA.md) — 创新药生物医药与生物制造
  - [STORAGE_GRID.md](STORAGE_GRID.md) — 储能电网AI电力与固态电池
  - [EXPORT_MFG.md](EXPORT_MFG.md) — 出海制造汽车零部件机械家电
  - [FINANCIAL_HIGH_DIVIDEND.md](FINANCIAL_HIGH_DIVIDEND.md) — 金融券商保险银行高股息
  - [ANTI_INVOLUTION_CYCLICAL.md](ANTI_INVOLUTION_CYCLICAL.md) — 反内卷周期化工建材钢铁
  - [DOMESTIC_CONSUMPTION.md](DOMESTIC_CONSUMPTION.md) — 内需服务消费文旅酒店航空医美
  - [HK_CN_INTERNET.md](HK_CN_INTERNET.md) — 港股互联网中概科技与平台经济
  - [CONSUMER_ELECTRONICS.md](CONSUMER_ELECTRONICS.md) — 消费电子AI终端PCB元件
  - **SPACE_ECONOMY** — 太空经济、卫星互联网（pending; markdown to be added)
- [VALUATION_WEIGHTS_v3.1.1.md](VALUATION_WEIGHTS_v3.1.1.md) — authoritative
  per-industry valuation-weight table (overrides the section-9 weights in
  the per-industry markdowns where they differ from v3.1.1).
- [FOUR_VIEWS_DESIGN.md](FOUR_VIEWS_DESIGN.md) — design for the four render
  views (causal propagation, core factor, supply chain, risk) plus the
  NVDA / Meta Capex walk-through example.

## Per-industry document anatomy (v3.1 template, 16 sections)

Every industry markdown follows the same 16-section template:

| § | Title (CN) | English summary |
|---|---|---|
| 0 | 行业边界 | Sub-segment scope and core judgment |
| 1 | 预测对象 | Excess-return decomposition (`r_i_h = market_β·r_market + sector_β·r_sector + α`) |
| 2 | 行业状态概率分布 | 5-state prior (强多头/温和多头/结构分化/杀估值/等待验证) |
| 3 | 核心因果图谱 | Mermaid flowchart |
| 4 | 有效事件冲击模型 | Surprise-based shock dampening (`Shock_eff = Surprise × ... × D_pre × D_post`) |
| 5 | 主因果路径卡片 | 6 path cards with β_pos / β_neg / threshold / lag / dedup_group |
| 6 | 路径去重 | Group-level deduplication formula |
| 7 | 公司暴露度模型 | Exposure factors and 1-5 scoring |
| 8 | 财务向量影响 | `Y = [Revenue, GrossMargin, ..., Leverage]` |
| 9 | 混合估值模型 | Blended valuation weights (see VALUATION_WEIGHTS_v3.1.1.md) |
| 10 | 尾部风险模型 | Risk factors and CVaR adjustment |
| 11 | 验证指标清单 | Bayesian-style path-validity update |
| 12 | 反向证伪路径 | Bullish vs bearish triggers |
| 13 | 可交易性输出面板 | Per-stock μ / σ / probability / tradability |
| 14 | 简化落地流程 | 8-step workflow |
| 15 | 一句话总结 | One-line takeaway |

## Relationship to the structured YAML

The markdowns are the **prose source** kept in sync with v3.1 of the design
document (single upstream input file:
`/Users/fanjie/Downloads/00_行业股价因果图谱_v3.1_12个行业完整版.md`).
The YAML files in `config/industry_graphs/` extract the structured fields
(state probabilities, β values, valuation weights, nodes, edges, views)
from these markdowns, with the **section-9 weights overridden** to match
`VALUATION_WEIGHTS_v3.1.1.md`.

When a markdown changes, regenerate or update the YAML and re-run
`mvp20 validate-graphs`.

## Adding the pending industry

To activate `SPACE_ECONOMY`:

1. Author the v3.1 markdown for 太空经济、卫星互联网 in
   `docs/industry_graphs/SPACE_ECONOMY.md`.
2. Create the structured YAML at `config/industry_graphs/SPACE_ECONOMY.yaml`
   following the same Pydantic schema (`mvp20/graph.py`).
3. Flip `graph_status` from `pending` to `present` in
   `config/mvp20.industries.yaml`.
4. Re-run `mvp20 validate-graphs`.
