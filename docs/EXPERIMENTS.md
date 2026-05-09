# qag-gate · 实验 Plan（实证优先）

> 版本：v1.0 · 日期：2026-05-08 · 遵循 `15-evidence-first.mdc`

---

## 一、实验四要素

### 假设 H1（主假设）
> QAG-Gate 在 Spearman 等级相关 ρ（与人类专家评分的对齐度）上**显著优于** RAGAS / OpenJudge / G-Eval（baseline）。
> **支持阈值**：ρ_QAG ≥ ρ_baseline + 0.10，且 paired bootstrap p < 0.05
> **反驳阈值**：ρ_QAG < ρ_baseline - 0.05（说明我们更差）
> **不确定**：差距在 [-0.05, +0.10] 之间

### 假设 H2（消融）
> 移除 phase-aware 后，ρ 显著下降。
> **支持阈值**：Δρ ≥ 0.05

### 假设 H3（消融）
> 移除 dynamic question generation 后，ρ 显著下降。
> **支持阈值**：Δρ ≥ 0.05

### 假设 H4（消融）
> 移除 output-type-aware override 后，对文件任务 ρ 显著下降。
> **支持阈值**：在文件类任务子集上 Δρ ≥ 0.10

### 假设 H5（成本-性能）
> standard 模式下，QAG-Gate 单次评估成本 ≤ ¥0.05，P95 延迟 ≤ 5s。
> **支持阈值**：100 次评估的 P95 实测 ≤ 5s

### 假设 H6（一致性）
> 同一输入跑 10 次，verdict 一致率 ≥ 90%。

---

## 二、变量

### 操控变量
- 评估方法：QAG-Gate / RAGAS / OpenJudge / G-Eval / 仅 baseline questions / no phase / no dynamic
- 输入任务类型：text / code / file:pptx / file:docx / file:image

### 保持不变
- 评估器底层 LLM：固定 `gpt-5.4-mini`（temperature=0.1）
- benchmark 数据集：200 个固定 task，800 个固定 candidate output
- 人类标注者：3 名固定（同一组）
- 硬件：MacBook Pro M4 Pro 64GB（详见 ENV.md）
- prompt 版本：`prompts/version.json` 锁定 `v0.1.0`

---

## 三、度量

### 主指标
- **Spearman ρ**：对每个 (task, candidate) 对，比较 QAG-Gate score 排序 vs 人类评分排序
- **Pearson r**：同上的线性相关
- **Kendall τ**：等级一致性

### 辅助指标
- **Verdict-level F1**：对每个 binary verdict，与人类是否同意
- **延迟**：P50 / P95（分 fast/standard/deep）
- **成本**：单次平均 token 数 + 美元换算
- **一致性**：同输入 10 次跑，score 标准差

---

## 四、阈值

| 假设 | 支持 | 反驳 | 不确定 |
|------|------|------|--------|
| H1 | Δρ ≥ 0.10, p < 0.05 | Δρ < -0.05 | -0.05 ≤ Δρ < 0.10 |
| H2 | Δρ ≥ 0.05 | Δρ < 0 | 0 ≤ Δρ < 0.05 |
| H3 | Δρ ≥ 0.05 | Δρ < 0 | 0 ≤ Δρ < 0.05 |
| H4 | Δρ ≥ 0.10（文件子集） | Δρ < 0 | 0 ≤ Δρ < 0.10 |
| H5 | P95 ≤ 5s 且 cost ≤ ¥0.05 | P95 > 8s 或 cost > ¥0.1 | 之间 |
| H6 | 一致率 ≥ 90% | < 80% | 80-90% |

---

## 五、实验批次设计（渐进式，按批次 go/no-go）

> **原则**：每批次有明确通过条件，不通过就停，不进入下一批。
> 参考历史经验：管道 bug、prompt 问题、标注一致性低这三类问题最常在大规模跑之前发现，
> 先用小规模探针暴露，再逐步放大规模。

### P0：管道探针（20 样本，¥30）

**目的**：确认 pipeline 端到端可跑通，格式正确，ρ 可计算。  
**操作**：从 easychat 历史会话随机选 5 个任务，每个生成 4 个 candidate（脚本生成，不人工标注），用 QAG-Gate 跑一次，检查输出结构。

| 检查项 | 通过标准 |
|--------|---------|
| pipeline 无 exception | 100% 通过 |
| EvalResult 格式正确 | score∈[0,1], verdicts 非空 |
| Spearman ρ 可计算 | 不 NaN（哪怕 ρ=0 也算通过） |
| 单次成本 ≤ ¥1.5 | 估算正确 |

**不通过 → 停止，修 pipeline 后重跑 P0。**

---

### P1：试点（50 样本，¥150）

**目的**：信号可见性验证——QAG-Gate 和 G-Eval 有没有区别？  
**样本**：5 种 task 类型各 10 个（文本/代码/PPT/RAG/多步），每个 2 个 candidate（high/low），共 100 条。  
**标注**：仅作者本人打分（1-5），不引入第三方标注者，快速验证方向。

| 指标 | 通过条件 |
|------|---------|
| Spearman ρ(QAG-Gate vs 作者) | ≥ ρ(G-Eval vs 作者) |
| ρ 差距方向一致 | QAG ≥ G-Eval（不要求幅度） |
| 标注耗时 | 100 条 × 60s ≈ 1.7 小时 |

**不通过 → 分析原因，优先修算法或 prompt，再跑一次 P1（追加 ¥150），最多重跑 2 次。**

---

### P2：核心实验（200 样本 × 4 方法 × 1 seed，¥800）

**目的**：主假设初步验证（H1、H2、H3）。  
**样本构建（200 任务 × 4 candidate = 800 条）**：

| 类型 | 数量 |
|------|------|
| 文本分析 | 50 |
| 代码生成 | 40 |
| PPT 生成 | 30 |
| Word 文档生成 | 30 |
| Excel 数据分析 | 20 |
| RAG 问答 | 20 |
| 多步执行（含工具调用） | 10 |

每任务 4 个 candidate（High / Mid / Low / Bad）。

**标注**：3 名标注者，Krippendorff α ≥ 0.7，取 median 为 ground truth，预期 20 人时。

| 假设 | 通过条件 |
|------|---------|
| H1 | Δρ ≥ 0.05（方向正确，P3 再验显著性） |
| H5（成本） | 单次 ≤ ¥0.05, P95 ≤ 5s |

**不通过 → 分析，若 Δρ < 0，需要重大算法调整，视情况终止或重设方案。**

---

### P3：完整实验（200 样本 × 4 方法 × 3 seeds + 消融，¥2,500）

**目的**：论文级统计显著性 + 消融分析。仅在 P2 通过后执行。

**额外运行**：
- 3 个独立 seed 重跑（确认 H6 一致性）
- 5 种消融配置（no-phase / no-dynamic / no-output-aware / no-claim-verify / no-deliverable-coverage）

**通过条件**：H1 p < 0.05（paired bootstrap）。

---

### 数据集开源

`benchmarks/qag-bench-v1/` 完整数据集（任务 + candidate + 人工评分）归档至 `huggingface datasets`，供后续工作复现。

---

## 六、实验目录结构（按 15-evidence-first.mdc）

```
qag-gate/benchmarks/
└── 2026-05-qag-vs-baselines/
    ├── PLAN.md          # 复制本文档第一节
    ├── ENV.md           # 硬件 + LLM 版本
    ├── run.sh           # 一键复现脚本
    ├── data/
    │   ├── tasks.jsonl
    │   ├── candidates.jsonl
    │   ├── human_scores.jsonl
    │   ├── run-qag-gate-01.json
    │   ├── run-ragas-01.json
    │   ├── run-openjudge-01.json
    │   └── run-geval-01.json
    ├── ablations/
    │   ├── run-no-phase-01.json
    │   ├── run-no-dynamic-01.json
    │   └── run-no-output-aware-01.json
    ├── RESULT.md        # 数据表 + 图 + 结论
    └── REPRO.md         # 他人复现路径
```

---

## 七、`run.sh` 设计（分批次，按 PHASE 参数控制）

```bash
#!/usr/bin/env bash
# 渐进式实验：通过 PHASE 参数控制规模，避免一次性大规模调用
# 用法：
#   PHASE=p0 bash run.sh   # 管道探针（¥30，20 样本）
#   PHASE=p1 bash run.sh   # 试点（¥150，50 样本）
#   PHASE=p2 bash run.sh   # 核心实验（¥800，200 样本）
#   PHASE=p3 bash run.sh   # 完整实验（¥2500，含消融 3 seeds）

set -euo pipefail

PHASE=${PHASE:-p0}
echo ">>> Running phase: $PHASE"

# 1. 准备环境
python -m venv .venv && source .venv/bin/activate
pip install -e ".[bench]" -q

# 2. 检查 API key
[ -z "${OPENAI_API_KEY:-}" ] && echo "OPENAI_API_KEY missing" && exit 1

# 3. 按阶段设置参数
case "$PHASE" in
  p0)
    N_TASKS=5; N_CANDIDATES=4; METHODS="qag-gate"; SEEDS="01"; DO_ABLATION=false
    echo ">>> P0 探针：pipeline 冒烟，预计费用 ¥30"
    ;;
  p1)
    N_TASKS=25; N_CANDIDATES=2; METHODS="qag-gate g-eval"; SEEDS="01"; DO_ABLATION=false
    echo ">>> P1 试点：信号可见性，预计费用 ¥150"
    echo ">>> 通过条件：ρ(QAG) ≥ ρ(G-Eval)，不通过请停止"
    ;;
  p2)
    N_TASKS=200; N_CANDIDATES=4; METHODS="qag-gate ragas openjudge g-eval"; SEEDS="01"; DO_ABLATION=false
    echo ">>> P2 核心：主假设初步验证，预计费用 ¥800"
    echo ">>> 通过条件：H1 Δρ ≥ 0.05，不通过分析原因后再决定"
    ;;
  p3)
    N_TASKS=200; N_CANDIDATES=4; METHODS="qag-gate ragas openjudge g-eval"; SEEDS="01 02 03"; DO_ABLATION=true
    echo ">>> P3 完整：论文级数据，预计费用 ¥2500，仅在 P2 通过后运行"
    ;;
  *)
    echo "未知 PHASE: $PHASE（可选 p0/p1/p2/p3）"; exit 1
    ;;
esac

# 4. 加载/生成数据集
python -m qag_gate.bench.prepare \
  --n-tasks "$N_TASKS" \
  --n-candidates "$N_CANDIDATES" \
  --output data/"$PHASE"/

# 5. 跑各方法
for method in $METHODS; do
  for seed in $SEEDS; do
    OUT="data/$PHASE/run-${method}-${seed}.json"
    if [ -f "$OUT" ]; then
      echo ">>> 已存在 $OUT，跳过（如需重跑请删除文件）"
      continue
    fi
    python -m qag_gate.bench.run \
      --method "$method" \
      --tasks "data/$PHASE/tasks.jsonl" \
      --candidates "data/$PHASE/candidates.jsonl" \
      --output "$OUT" \
      --seed "$seed"
    echo ">>> 完成 $method seed=$seed，已写入 $OUT"
  done
done

# 6. 消融（仅 p3）
if [ "$DO_ABLATION" = true ]; then
  for ablation in no-phase no-dynamic no-output-aware no-claim-verify no-deliverable-coverage; do
    python -m qag_gate.bench.run \
      --method "qag-gate-$ablation" \
      --tasks "data/$PHASE/tasks.jsonl" \
      --candidates "data/$PHASE/candidates.jsonl" \
      --output "data/$PHASE/ablations/run-${ablation}-01.json"
  done
fi

# 7. 分析指标 + go/no-go 判断
python -m qag_gate.bench.analyze \
  --phase "$PHASE" \
  --runs "data/$PHASE/run-*.json" \
  --human "data/$PHASE/human_scores.jsonl" \
  --output "data/$PHASE/RESULT.md"

echo ""
echo ">>> 结果见 data/$PHASE/RESULT.md"
echo ">>> 请检查 go/no-go 条件后再决定是否进入下一批次"
```

---

## 八、最小样本量

- **性能类**（H5 延迟）：每个 depth × 100 次 = 300 次（够测 P95）
- **正确率类**（H1-H4）：800 个标注样本（每方法跑 3 个独立 seed = 2400 次评估）
- **一致性**（H6）：30 个固定输入 × 10 次重跑 = 300 次

---

## 九、失败数据处理

按规则要求，失败的实验也归档：

- LLM API 失败 → 记录 retry 次数和最终降级行为，归到 `data/failures/`
- benchmark 跑分明显异常（ρ < 0.1）→ 单独分析为什么，记录在 `RESULT.md` 的 "anomalies" 章节
- 不删除任何数据点，"选择性保留" 是科研伦理红线

---

## 十、与外部基线的精确对比方法

为避免不公平比较，对每个 baseline：

| Baseline | 我们如何运行它 |
|----------|--------------|
| **RAGAS** | 用其官方 metrics（faithfulness, answer_relevancy, context_relevancy）的加权平均 |
| **OpenJudge** | 用其默认 rubric generation + grader |
| **G-Eval** | 实现 paper 中的 form-filling + CoT，用同一个 gpt-5.4 |
| **Static rubric** | 我们手写一份覆盖通用质量的 rubric，模拟 Anthropic Outcomes |

所有 baseline 用**同样的 LLM 后端**（`gpt-5.4-mini`），同样的 task/candidate 输入，避免"用更弱模型给对手"的不公平。

---

## 十一、RESULT.md 模板（待填）

```markdown
# QAG-Gate vs Baselines 实验结果

## 假设回答
- H1 (主假设): 支持/反驳/不确定 — 依据 ρ_QAG = X.XX, ρ_RAGAS = Y.YY, p = Z.ZZ
- H2: ...
- ...

## 主表

| 方法 | Spearman ρ | Pearson r | Kendall τ | 单次成本 | P95 延迟 |
|------|-----------|-----------|-----------|---------|---------|
| QAG-Gate | | | | | |
| RAGAS | | | | | |
| OpenJudge | | | | | |
| G-Eval | | | | | |
| Static rubric | | | | | |

## 消融

| 配置 | Spearman ρ | Δρ vs full |
|------|-----------|-----------|
| Full QAG-Gate | | 0 |
| - phase-aware | | |
| - dynamic generation | | |
| - output-aware override | | |
| - claim verification | | |
| - deliverable coverage | | |

## 偏差与限制
- ...

## 后续动作
- [ ] 更新 ADR
- [ ] 更新 paper draft 的 Results 章节
```
