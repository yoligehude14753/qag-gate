# qag-gate · METRICS（北极星 + OKR）

> 版本：v1.0 · 日期：2026-05-08

## 北极星指标（North Star）

> **指标**：QAG-Gate 评分与人类专家评分的 **Spearman 等级相关系数**  
> 当前基线：未测  
> 论文目标：**ρ ≥ 0.65** （G-Eval 是 0.514，提升 ~25%）  
> 测量频率：每次主实验跑

**为什么是这个指标**：
- 业界共识的"评估器对齐人类"度量（G-Eval、GPTScore 都用这个）
- 单一可比较数字，方便和其他框架横评
- 直接反映"评估器有用程度"——分数能否预测人类觉得好不好

**测量协议**（详见 `docs/EXPERIMENTS.md`）：
- 200 个 task × 4 个 candidate output（涵盖 high/mid/low/bad 质量）= 800 个样本
- 3 名标注者独立评分 1-5，取 majority + median
- QAG-Gate 输出 score（0-1）→ 映射到 1-5 → 计算 Spearman

## 输入指标（开发中可观测）

| 指标 | 阈值 | 监测频率 |
|------|------|---------|
| 单元测试覆盖率 | ≥ 85% | 每 PR |
| Fitness Functions 通过率 | 100% | 每 PR |
| 单次 standard 评估 P95 延迟 | ≤ 5s | 每周 |
| 单次 deep 评估 P95 延迟 | ≤ 15s | 每周 |
| LLM API 调用平均成本（standard） | ≤ ¥0.05 | 每周 |
| benchmark 跑通耗时 | ≤ 1 小时 | 每实验 |

## 护栏指标（不能恶化）

| 指标 | 红线 |
|------|------|
| 与 baseline questions（无 dynamic）相比的相关系数下降 | 不允许 |
| 单测试失败率 | ≤ 1% Flaky |
| 安装包大小 | ≤ 30MB |
| Python 兼容性 | ≥ 3.10 |

## 季度 OKR（2026 Q3）

**O1：QAG-Gate 达到学术发表门槛**
- KR1：北极星指标 Spearman ρ ≥ 0.65 ✓
- KR2：与 OpenJudge / RAGAS / LangSmith 在同一 benchmark 上对比，至少 1 项指标显著超越（p < 0.05）
- KR3：完整跑通 200 task benchmark，run.sh 在干净机器复现成功

**O2：开源仓库可用且被发现**
- KR1：GitHub 公开 + 1.0 release，README 有 5 分钟上手
- KR2：arXiv 发布（先于会议截止日）
- KR3：HackerNews / r/MachineLearning / Twitter 至少 1 条引用
