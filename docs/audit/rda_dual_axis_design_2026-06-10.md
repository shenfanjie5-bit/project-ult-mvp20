# RD-A merit/timing 双轴 —— 实施设计(2026-06-10)

> 重设计提案(base_score_redesign_proposal.md §4)中唯一未实施的结构项。
> 失效模式:单轴 base 里 timing 方差垄断,"好公司但贵"被压成 AVOID(寒武纪/天孚型,实测仍在)。

## 核心决策:并行运行 + 数据晋升(不直接改 headline)

trading_signal 的语义改动**不拍脑袋切换**——P&L 闭环刚好是为此而建的:

```
v1(现状):base = f + eg + vr + cs − r − p  → 单轴阈值 signal(保持不动)
v2(新增):M = f + eg − r_fund        # 公司质量轴(基本面风险归 M)
          T = vr + cs − p − r_mkt    # 时机轴(市场/拥挤风险归 T)
          signal_v2 = 2D 矩阵:
                       T>0        T≈0        T<0
            M>0       BUY        HOLD       HOLD/WATCH   ← 好公司但贵≠AVOID
            M≈0       HOLD       HOLD       WATCH
            M<0       WATCH      WATCH      AVOID
```

- `/score` 响应新增 `merit / timing / trading_signal_v2`(并列展示,headline 仍 v1)
- **P&L 快照两个信号都存**(scores 表加 signal_v2 列),T+10/20 对账两套 hit-rate/BUY 桶收益
- **晋升标准(预注册)**:≥20 个到期快照日后,v2 的 BUY 桶平均前向收益及 BUY−AVOID 价差在 ≥60% 日期上不劣于 v1,且"M>0,T<0"格的前向收益显著高于 v1 给它的 AVOID 桶 → headline 切 v2;否则 v2 留作展示轴
- 风险项拆分(**实施修订 2026-06-10,经对抗评审**):score_target 桶级无法区分,实际按 **dp 前缀份额切分**——`L8.val.*`/`L8.cap.*`(overvalued/priced_in/outflow/short_increase 等市场型)按其在 risk rollup 分子中的份额计入 T,其余(L8.fin/op/gov 公司型)计入 M;damp 分母共用故份额分解精确,M+T≡core base 不破坏。晋升对比评的就是这个公式

## 改动面(预估)

| 文件 | 改动 |
|---|---|
| scoring.py | M/T 组装(复用现有 6 分量,只重分组)+ 2D 矩阵 + 响应字段;**不动 v1 路径** |
| pnl_loop.py | scores 表 + signal_v2 列(ALTER TABLE 向后兼容);eval 增 v1 vs v2 对比块 |
| server.py | /score 与 /ranking 透出 merit/timing/signal_v2 |
| tests | 矩阵语义(M>0,T<0→非AVOID)、快照双信号、eval 对比 |

不改:aggregator 节点层、阈值常数(v2 用相对刻度:M/T 各自横截面 z 或既有绝对刻度+矩阵)、FE(后续)。
