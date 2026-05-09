# qag-gate · PRD

> 版本：v1.0 · 日期：2026-05-08 · 状态：草稿待确认

---

## 6W2H 需求分析

### What — 做什么

QAG-Gate 是一个**嵌入 LLM Agent 运行循环的运行时质量评估引擎**。给定一个任务描述、当前迭代的输出和工具执行上下文，它输出：

```python
EvalResult(
    score: float,              # 0-1 加权聚合分
    verdicts: List[Verdict],   # 二值判定 + 推理
    hard_failures: List[Fail], # 硬性失败（不参与评分）
    redline_violations: List,  # 语义红线（推脱、伪造等）
    phase: str,                # planning / executing / delivering
    depth: str,                # fast / standard / deep
)
```

下游可以是 SlopeNav（决定是否继续迭代），也可以是任何其他决策器。

### Why — 为什么做

**核心痛点**：现有开源 agent 评估框架（RAGAS、LangSmith、OpenAI Evals、AgentEvals 等）都假设"评估在交付后做一次"。但实际 agent 系统在迭代中需要"每一步都判断要不要继续优化"，且评估标准应**适应任务类型**而非固定模板。

**不做的后果**：
- agent 只会用"模型自我汇报完成"作为停止条件 → 大量假交付
- 写不动 rubric 的开发者只能用通用质量分 → 任务专属问题永远漏检
- Anthropic Outcomes 用静态 markdown rubric → 适应性差

### Who — 谁来用

**主要用户**：
- 在做 LLM agent 产品的工程师，需要把"质量门"嵌入 iteration loop
- 评估方向的研究者，需要一个 baseline 框架做对比

**反面用户**（明确不服务）：
- 只想做 LLM 模型基准测试的研究者（→ 用 OpenAI Evals）
- RAG 单管道评估（→ 用 RAGAS）
- 一次性 prompt 回归测试（→ 用 PromptFoo）

### Where — 在哪用

- **形式**：Python 包（`pip install qag-gate`），命令行工具，REST API（可选）
- **嵌入位置**：用户的 agent 框架的 iteration loop 中，每次产出后调用
- **依赖**：兼容 OpenAI / Anthropic / 本地 LLM 任一 backend（通过适配器层）

### When — 什么时候用

- **触发频率**：agent 每次产出 candidate output 后调用 1 次
- **延迟容忍**：fast 模式 ≤ 100ms（无 LLM）；standard ≤ 5s（1 次 LLM）；deep ≤ 15s（多次 LLM + claim 验证）
- **使用频率**：单任务可能调用 3-10 次（伴随 agent iterations）

### Which — 哪种方案

**备选方案对比**：

| 方案 | 优势 | 劣势 | 选择 |
|------|------|------|------|
| A. 用 OpenAI Evals 直接做 | 学术圈认可 | 不支持 phase-aware、不支持运行时调用 | × |
| B. 用 LangSmith 做 trace | 可观测性强 | 闭源 SaaS，不能嵌入 agent 内 | × |
| C. **自研 + 开源（QAG-Gate）** | 完全可控、覆盖现有空白 | 需要自己建 benchmark | ✓ |
| D. 在 easychat 内部维护 | 最简单 | 没有学术贡献，没有社区 | × |

选择 C 的理由：现有方案均不解决"嵌入 agent 内的动态评估"这个问题，且 easychat 已有 ~1500 行成熟代码可直接拆出。

### How — 怎么做（核心流程）

```
[输入] task + content + tool_results + iteration_meta
   ↓
[阶段1] detect_phase(planning/executing/delivering)
   ↓
[阶段2] select_depth(fast/standard/deep)
   ↓
[阶段3] scan_hard_gates → infra failure / tool all-failed / no file
   ↓
[阶段4] build questions = baseline ⊕ dynamic(LLM 生成) ⊕ output_type_specific
   ↓
[阶段5] BinaryJudge.judge(questions, content) → verdicts
   ↓
[阶段6] (deep only) ClaimExtractor + WebVerifier
   ↓
[阶段7] (有 spec) DeliverableSpec coverage 验证
   ↓
[阶段8] aggregate_scores(verdicts, weights) → total
   ↓
[阶段9] RedLineChecker.check(content, context)
   ↓
[输出] EvalResult
```

### How Much — 成本与收益

**开发成本**：
- 代码解耦 + 适配器层：3 周（1 名工程师 0.7 人力）
- benchmark 数据集（200 个 task）：2 周
- 实验跑通 + paper draft：3 周
- 合计 ~168 人时

**运行成本**（用户视角）：
- fast 模式：~¥0.001/次（无 LLM）
- standard 模式：~¥0.05/次（1 次 mini）
- deep 模式：~¥0.3/次（3-4 次 mini + 搜索）

**预期收益**：
- arXiv 优先权 + 学术信誉 → 对 easychat 融资和招募有正向影响
- 开源社区维护成本可由社区分担
- 论文中稿后 → 简历价值、项目权威性

### How Well — 质量标准

| 维度 | 标准 |
|------|------|
| 与人类评分的 Spearman 相关 | ≥ 0.65（G-Eval 是 0.514） |
| 单次 standard 评估延迟 | P95 ≤ 5s |
| 适用任务类型覆盖 | 文本、代码、文件（Word/PPT/Excel/PDF）、图像 |
| API 兼容性 | OpenAI / Anthropic / 本地 vLLM 任一 |
| 可复现性 | 单 seed 下 verdict 一致率 ≥ 90% |

---

## 验收标准（业务目标三问）

### 主路径
- [ ] 用户安装 `pip install qag-gate`，传入 task + content，能拿到 `EvalResult`
- [ ] 在 easychat 替换原有评估调用后，回归测试集通过率不下降

### 失败路径
- [ ] LLM API 不可用时，降级到 baseline questions + 默认评分
- [ ] 输入 content 为空时，返回明确的 `empty_response` 红线
- [ ] tool_results 字段缺失时，跳过 deliverable 验证，不崩溃

### 完整状态
- [ ] 三种 depth（fast/standard/deep）均有完整实现
- [ ] 三种 phase（planning/executing/delivering）均有完整实现
- [ ] 5 种红线类型均有规则 + LLM 双验证

---

## 排期

| 里程碑 | 计划完成 | 输出 |
|--------|----------|------|
| 架构设计确认 | W1 末 | ARCHITECTURE.md 用户确认 |
| 测试用例清单确认 | W2 末 | TESTING.md 用户确认 |
| 核心模块开发完成 | W4 末 | 单元测试 100% 通过 |
| Benchmark 数据集就位 | W4 末 | 200 个标注样本 |
| 主实验完成 | W6 末 | EXPERIMENTS.md 的 RESULT |
| Paper draft v1 | W6 末 | PAPER.md 全文 |
| arXiv 发布 + GitHub public | W11 | arXiv 链接 |
| 论文投稿 | W12 | 投稿确认 |
