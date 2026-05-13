# 第 9 节「混合估值」权重校验表

本文件用于校验 v3.1.1 版本中各行业第 9 节的估值模型权重。

规则：行业之间权重可以不同；同一行业表内权重必须合计 100%。PB、ROE-PB、股息/回购、DCF/FCF、矿山净现值、管线估值均视为行业特化的估值模型扩展，纳入后仍需归一化。

| 编号 | 行业 | 第 9 节估值权重 | 合计 |
|---:|---|---|---:|
| 01 | AI算力硬件与通信设备 | PE 35%；PS 20%；EV/EBITDA 20%；DCF 10%；SOTP 15% | 100% |
| 02 | 半导体设备材料与先进封装 | PE 25%；PS 25%；EV/EBITDA 15%；DCF 10%；SOTP/管线式估值 25% | 100% |
| 03 | 机器人与具身智能高端装备 | PS 30%；PE 25%；EV/EBITDA 15%；DCF 10%；SOTP 20% | 100% |
| 04 | 有色资源黄金铜稀土小金属 | PE 25%；PB 20%；EV/EBITDA 25%；DCF/矿山净现值 20%；股息模型 10% | 100% |
| 05 | 创新药生物医药与生物制造 | SOTP/管线估值 40%；DCF 25%；PS 15%；PE 10%；EV/EBITDA 10% | 100% |
| 06 | 储能电网AI电力与固态电池 | PE 35%；EV/EBITDA 20%；PS 15%；DCF 15%；SOTP 15% | 100% |
| 07 | 出海制造汽车零部件机械家电 | PE 40%；EV/EBITDA 25%；DCF 15%；PB 10%；SOTP 10% | 100% |
| 08 | 金融券商保险银行高股息 | PB 40%；PE 25%；股息模型 20%；ROE-PB模型 10%；SOTP 5% | 100% |
| 09 | 反内卷周期化工建材钢铁 | PB 30%；EV/EBITDA 30%；PE 20%；DCF 10%；股息模型 10% | 100% |
| 10 | 内需服务消费文旅酒店航空医美 | PE 40%；EV/EBITDA 20%；DCF 15%；PS 15%；股息模型 10% | 100% |
| 11 | 港股互联网中概科技与平台经济 | PE 30%；DCF/FCF 25%；PS 20%；SOTP 20%；股息/回购模型 5% | 100% |
| 12 | 消费电子AI终端PCB元件 | PE 35%；EV/EBITDA 20%；PS 15%；DCF 15%；SOTP 15% | 100% |

## 在 YAML 中的命名约定

`config/industry_graphs/<slug>.yaml` 的 `priors.valuation_mix.weights` 字段使用
ASCII 模型名作为 key，权重以小数表示（合计 = 1.0）。模型名映射：

| 表中文名 | YAML key |
|---|---|
| PE | `PE` |
| PS | `PS` |
| EV/EBITDA | `EV_EBITDA` |
| DCF | `DCF` |
| SOTP | `SOTP` |
| PB | `PB` |
| 股息模型 | `Dividend` |
| 股息/回购模型 | `Dividend_Buyback` |
| ROE-PB 模型 | `ROE_PB` |
| SOTP/管线式估值 | `SOTP_Pipeline` |
| DCF/FCF | `DCF_FCF` |
| DCF/矿山净现值 | `DCF_MineNPV` |

例：金融行业的 YAML 应该写成
```yaml
priors:
  valuation_mix:
    weights:
      PB: 0.40
      PE: 0.25
      Dividend: 0.20
      ROE_PB: 0.10
      SOTP: 0.05
    note: "v3.1.1 weight policy"
```
