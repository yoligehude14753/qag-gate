# QAG-Gate: A Phase-Aware, Depth-Adaptive Binary Evaluation Framework for Agentic AI Systems

> 论文草稿 v1.2 · 2026-05-09  
> **v1.2**：E1 消融 C（无动态题）已用 `_skip_dynamic` 实装后重跑并合并结果。  
> 目标：EMNLP 2026 System Demonstrations Track / arXiv 技术报告  
> 字数目标：8,000–10,000 words (camera ready)

---

## Abstract

We present **QAG-Gate**, an open-source framework for evaluating outputs of agentic LLM systems using a phase-aware, depth-adaptive, three-layer binary question design plus a deterministic RedLine hard gate. Our **primary external validation** uses public benchmarks only: on **FLASK-Eval** (n=279 instruction samples, Spearman correlation with FLASK’s reported GPT-4 aggregate scores), QAG-Gate reaches **ρ = 0.226** while **G-Eval** achieves **ρ = 0.487**—showing that QAG-Gate is not a drop-in substitute for strong generic LLM-as-a-judge methods on reading/conciseness-oriented criteria, but measures a partially **orthogonal** quality signal (e.g., executability and structural gates). On **MT-Bench human pairwise preferences** (495 pairs total; **n=380 decisive** pairs after excluding ties), QAG-Gate agrees with humans on **263/380 = 69.2%** of choices (per-category accuracies: writing **63/95**, stem **70/96**, reasoning **47/72**, roleplay **83/117**), **well above chance (50%)**. Ablations on FLASK (n=279) show **removing phase-aware depth selection** lowers ρ by **0.027**, **skipping Layer-2 dynamic questions** (_skip_dynamic_) lowers ρ by **0.014**, and **disabling RedLine** lowers ρ by **0.015**—each component contributes on this proxy. An earlier **internal** pseudo-labeled set (P2) reported ρ = 0.524 vs. a random label baseline for monotonicity checks; we retain it as supplementary material and do not use it as the main claim. Code is Apache 2.0 (`pip install qag-gate`).

**Keywords**: LLM evaluation, agentic AI, binary judgment, phase-aware assessment, QAG

---

## 1. Introduction

The rapid proliferation of agentic AI systems—agents that iteratively plan, execute tools, and produce multi-format deliverables—has created a critical gap in evaluation methodology. Existing approaches fall into two broad categories:

**Static rubric evaluators** (e.g., Anthropic Evals, OpenAI Evals) apply fixed criteria regardless of what stage the agent is in or what type of output it produces. A rubric designed for final report quality becomes misleading when applied to an intermediate planning response.

**LLM-as-a-judge frameworks** (e.g., G-Eval [Liu et al. 2023], MT-Bench [Zheng et al. 2023]) generate evaluation rationales but typically treat all outputs as equivalent text, ignoring the structural differences between a Python script, a PowerPoint outline, and a data analysis narrative.

Neither approach captures the *agent lifecycle*: the same agent output should be judged differently at iteration 1 (is the plan reasonable?) vs. iteration 5 (is the deliverable usable?).

We make the following **contributions**:

1. **Phase-aware evaluation** (§3.1): A lightweight classifier that detects whether an agent response is in the planning, executing, or delivering phase, then selects the corresponding question set.
2. **Depth-adaptive selection** (§3.2): A rule-based selector that dynamically chooses between fast (4 questions), standard (12–14 questions), and deep (20+ questions) evaluation based on agent phase and context signals.
3. **Three-layer QAG architecture** (§3.3): A hierarchical question-answering-grounding system with baseline questions (universal quality gates), dynamically-generated task-specific questions (via LLM), and output-type-aware overrides (code/file/tabular).
4. **Hard-gate RedLine filter** (§3.4): Six deterministic semantic checks (deflection detection, tool failure apology, data fabrication, content duplication, empty response, temporal incoherence) applied before scoring.
5. **External + internal validation** (§5): Primary results on **FLASK** and **MT-Bench** (public); an internal synthetic-tier set (P2) is reported as **supplementary** only.

---

## 2. Background and Related Work

### 2.1 LLM Evaluation Frameworks

**G-Eval** [Liu et al. 2023] uses chain-of-thought prompting with form-filling to evaluate NLG outputs, reporting stronger correlation with human judgments than earlier reference-based metrics. However, G-Eval generates criteria per task without adapting to agent phases or output types.

**RAGAS** [Es et al. 2024] provides component-level evaluation for RAG pipelines (faithfulness, answer relevancy, context recall) but is designed for question-answering systems, not general agentic tasks.

**OpenJudge** [Bai et al. 2024] uses relative pairwise comparison to rank agent outputs, achieving good agreement on competitive benchmarks but requiring O(N²) comparisons for N candidates.

**AgentBench** [Liu et al. 2024] and **AgentEval** [Arabzadeh et al. 2023] provide task-completion metrics for specific agent environments but require ground-truth solutions, making them unsuitable for open-ended creative or analytical tasks.

**Agent-as-a-Judge** [Zhuge et al. 2024] employs a separate judge agent with tool access, improving evaluation quality but significantly increasing cost and latency.

### 2.2 Binary Evaluation

**Binary judgment** (yes/no per criterion) has been shown by [Park et al. 2024] to produce more reliable inter-rater agreement than scalar scoring, particularly for complex outputs. QAG-Gate extends this approach with a three-layer architecture that balances coverage against cost.

### 2.3 Phase-Aware and Adaptive Evaluation

To our knowledge, no existing framework explicitly adapts evaluation criteria based on agent execution phase. The closest work is **HELMET** [Yen et al. 2024], which tests long-context models across different task types, but does not model iterative agent behavior.

---

## 3. QAG-Gate Framework

### 3.1 Phase Detection

Given an agent response text `r` and optional context signals (tool calls, iteration count), `detect_phase(r, ctx)` returns one of three phases:

- **PLANNING**: Response primarily contains structure, outlines, or intentions without concrete artifacts. Detected by: short response (< 200 tokens), presence of planning keywords ("I will", "my approach"), absence of code blocks or tables.
- **EXECUTING**: Response shows partial completion. Detected by: tool call presence, partial code, intermediate results.
- **DELIVERING**: Response contains final, usable artifacts. Detected by: file references, complete code blocks (≥ 30 chars), structured data, actionable deliverables.

Phase assignment maps to a corresponding question subset, prioritizing intent-match and plan coherence in PLANNING phase, and output quality and actionability in DELIVERING phase.

### 3.2 Depth-Adaptive Selection

Evaluation depth is selected based on:

| Phase | Default Depth | Override Conditions |
|-------|---------------|---------------------|
| PLANNING | FAST (4 Qs) | — |
| EXECUTING | STANDARD (12–14 Qs) | Tool failure → DEEP |
| DELIVERING | STANDARD (12–14 Qs) | File output, large content → DEEP |

**FAST** mode runs only 4 baseline questions in a single LLM call (~0.5s, ~¥0.01).  
**STANDARD** mode runs 4 baseline + 8–10 dynamic questions (~1.5s, ~¥0.03).  
**DEEP** mode runs 4 baseline + 10 dynamic + 6 output-specific questions (~3s, ~¥0.06).

### 3.3 Three-Layer Binary Question Architecture

**Layer 1 — Baseline Questions (4, always present)**

Universal quality gates applicable to any agent output:
1. Does the output directly address what the user asked for? (*intent_match*, weight=1.5)
2. Does the output contain a concrete, usable deliverable? (*deliverable*, weight=1.5)
3. Is the output free of obvious errors or incomplete artifacts? (*quality_baseline*, weight=1.0)
4. Can the user directly use this output without significant additional work? (*actionability*, weight=1.0)

**Layer 2 — Dynamic Task-Specific Questions (LLM-generated, 4–10)**

A `CriteriaGenerator` sends the task description to the LLM to produce task-specific binary evaluation questions. Questions are generated once per task (cached) and cover domain-specific quality criteria.

*Example for a Python data-cleaning task:*
- "Does the script handle the case where the input CSV file does not exist?" (error_handling)
- "Does the output preserve the correct data types for each column?" (data_integrity)
- "Is the session boundary logic correct (events within 30 minutes are in the same session)?" (correctness)

**Layer 3 — Output-Type-Aware Overrides**

When the output type is detected as code or file, domain-specific questions replace generic factual accuracy questions:

| Output Type | Added Questions | Removed |
|-------------|----------------|---------|
| Code | `code_completeness`, `code_runnable`, `code_data_quality` | `factual_accuracy` |
| File (PPT/Word/Excel) | `file_structure`, `file_completeness` | `citation_accuracy` |
| Tabular | `data_schema`, `aggregate_correctness` | — |

**Score Aggregation**

Binary verdicts (Yes=1.0, Partial=0.5, No=0.0) are aggregated with layer-specific weights:

```
score = (Σ baseline_i × w_i × 0.4  +  Σ dynamic_i × w_i × 0.4  +  Σ override_i × w_i × 0.2)
        / (Σ baseline weights × 0.4 + Σ dynamic weights × 0.4 + Σ override weights × 0.2)
```

### 3.4 RedLine Hard Gate

Six deterministic checks run *before* LLM scoring. Any violation returns `score = 0.0` immediately:

| Rule | Detection Method |
|------|-----------------|
| Empty response | `len(content.strip()) == 0` |
| Deflection | Regex: "I cannot", "I'm unable to", "As an AI" + short length |
| Tool failure apology | Regex: "the tool failed", "I encountered an error trying to" |
| Data fabrication indicator | Response references data not in context (heuristic) |
| Content duplication | Paragraph-level duplicate detection (Jaccard similarity) |
| Temporal incoherence | Year references inconsistent with current date context |

---

## 4. Datasets: Internal Sketch Set and Public Benchmarks

### 4.1 QAG-Bench-v1 (internal, supplementary)

We collected a **proof-of-concept** set of 200 task descriptions across 7 categories with synthetic quality tiers (High/Mid/Low/Bad) for early pipeline testing. Labels were **author-assigned** for smoke tests (P0–P2); this set is **not** used as the main empirical claim in this revision. It remains useful for regression testing in CI.

### 4.2 FLASK-Eval subset (E1, public)

We use a **filtered** subset of FLASK aligned with instruction-following dimensions (see our preparation script), **n = 279** examples, correlating model scores against FLASK-reported **GPT-4 aggregate** skill scores (`flask_avg` normalized to \([0,1]\)).

### 4.3 MT-Bench human judgments (E2, public)

We use released **human pairwise** annotations comparing two model answers per MT-Bench question. After removing ties, **n = 380** decisive pairs enter accuracy.

---

## 5. Experiments

### 5.1 Experimental Setup

**Primary benchmarks (public):** FLASK-Eval subset (E1), MT-Bench human pairwise (E2).  

**Baselines (E1):** G-Eval (same backbone `gpt-4o-mini`, temperature=0.1), Static Rubric (hand-written aggregate), plus FLASK’s own GPT-4 aggregate as the **reference** target for correlation.

**Metric (E1):** Spearman ρ between method score and normalized `flask_avg`. **Metric (E2):** pairwise accuracy vs. human majority / preference among decisive pairs.

**Ablations (E1, n=279):** Five configurations: full; no phase-aware proxy (context forces lower depth path via `executing`); no dynamic Layer-2 questions (`_skip_dynamic`, implemented in evaluator as of 2026-05-09); RedLine disabled via patch; fixed STANDARD depth (`_force_depth`).

> **Reproducibility:** Scripts under `benchmarks/2026-05-flask-eval/` and `benchmarks/2026-05-mtbench/`; per-query caches optional; requires API keys as documented in repo README.

### 5.2 Main Results — FLASK (E1)

| Method | Spearman ρ | p-value (ρ) | Kendall τ | n |
|--------|-----------|---------------|------------|---|
| QAG-Gate (full) | **0.226** | < 0.001 | 0.161 | 279 |
| G-Eval | **0.487** | < 0.001 | 0.390 | 279 |
| Static Rubric | **0.348** | < 0.001 | 0.241 | 279 |

**Per-tier QAG-Gate vs. FLASK reference:** low (n=79) ρ=0.068; mid (n=100) ρ=0.084; high (n=100) ρ=−0.008.

**Interpretation:** G-Eval aligns more closely with FLASK’s GPT-4 aggregate because both rely on similar LLM-as-judge style criteria (readability, conciseness, tone). QAG-Gate emphasizes **gates and agent-output suitability**; the moderate but significant ρ=0.226 shows **partial alignment**, not redundancy.

### 5.3 Main Results — MT-Bench human preference (E2)

| Category | Correct / Total | Accuracy |
|----------|-----------------|----------|
| writing | 63 / 95 | 0.663 |
| stem | 70 / 96 | 0.729 |
| reasoning | 47 / 72 | 0.653 |
| roleplay | 83 / 117 | 0.709 |
| **All decisive** | **263 / 380** | **0.692** |

495 total pairs; 380 decisive after removing ties. **Binomial test** vs. random (50%): *p* = 2.5 × 10⁻¹⁴ (one-sided); **95% Wilson CI**: [0.644, 0.736].

### 5.4 Ablation Study (E1, same backbone)

| Configuration | Spearman ρ | Δρ vs full |
|---------------|------------|------------|
| A — full QAG-Gate | **0.2254** | 0 |
| B — no phase-aware path (forced `executing`) | 0.1985 | −0.0269 |
| C — no dynamic Layer-2 (`_skip_dynamic`) | **0.2112** | **−0.0142** |
| D — RedLine disabled | 0.2104 | −0.0149 |
| E — fixed STANDARD depth | 0.2176 | −0.0077 |

**C re-measured 2026-05-09** with `_skip_dynamic` implemented; cache cleared; `run_e1_ablation.py --only C_no_dynamic` merged into `e1_ablation_full.json`. **B, D, E** unchanged from May 2026 caches. **Takeaway:** Layer-2 dynamic questions help FLASK alignment (−0.0142 when removed), comparable to turning off RedLine (−0.0149).

**Hypothesis (revised):** Phase-aware depth shows the largest single drop when removed; dynamic layer and RedLine each contribute ~1.4–1.5 points of ρ on this proxy.

### 5.5 Internal preliminary runs (P0–P2, non-primary)

Progressive smoke / tier tests confirm the pipeline runs end-to-end. On an **internal** 800-example pseudo-tier set (P2), QAG-Gate achieved ρ = 0.524 vs. random label baseline ρ = 0.043 — useful for regression testing only.

**Note:** G-Eval baseline in some runs hit API/proxy issues; external E1 uses a repaired `geval.py` caller.

---

## 6. Analysis

### 6.1 When Does Phase Detection Help?

External ablations (§5.4-B, C, D) show ρ falls when **phase-aware depth** is bypassed (~−0.027), when **dynamic Layer-2** is skipped (−0.0142), or when **RedLine** is off (−0.0149)—consistent with all three contributing on this FLASK proxy.

### 6.2 Failure Modes

From P0 analysis, two notable failure modes emerged:

1. **Score compression for mid-quality**: Mid-quality outputs that are structurally clear score near high-quality outputs (T004: high=0.860, mid=0.918). This suggests the dynamic criteria generator over-weights structural completeness relative to content depth. Fix: prompt engineering to emphasize "actionability" over "structure."

2. **RAG task ceiling effect**: For RAG Q&A tasks with well-structured low-quality outputs (T005-B=0.561), the evaluator fails to penalize lack of specificity. Fix: add content-depth probing questions in Layer 3.

### 6.3 Cost Analysis

QAG-Gate standard mode: ~1,200 input tokens + ~200 output tokens per evaluation.  
At gpt-4o-mini pricing ($0.15/1M input, $0.6/1M output): $0.0002/eval ≈ ¥0.001.  
P95 latency: 5–10s (dominated by LLM round-trip; parallelizable with async).

---

## 7. System Description

QAG-Gate is implemented in Python 3.11+ as a zero-dependency core package (only `loguru` for logging, optional `openai` and `anthropic` for LLM backends).

### 7.1 Architecture

```
qag-gate/
├── domain/          # Pure data models (EvalPhase, EvalDepth, Verdict, EvalResult)
├── checkers/        # RedLine, PhaseDetector, DepthSelector, BinaryJudge,
│                    # CriteriaGenerator, ScoreAggregator
├── application/     # QAGEvaluator (orchestrates all checkers)
└── infrastructure/  # OpenAIAdapter, AnthropicAdapter, FallbackChain, MockLLMClient
```

### 7.2 Usage

```python
from qag_gate import QAGEvaluator
from qag_gate.infrastructure import OpenAIAdapter

evaluator = QAGEvaluator(llm_client=OpenAIAdapter(model="gpt-4o-mini"))
result = await evaluator.evaluate(
    task="Write a Python data cleaning script...",
    content="```python\nimport pandas as pd\n...",
    context={"iteration": 2}
)
print(result.score)      # 0.727
print(result.phase)      # EvalPhase.DELIVERING
print(result.verdicts)   # [Verdict(question="...", passed=True, ...), ...]
```

---

## 8. Discussion

### 8.1 Limitations

- **Proxy mismatch**: FLASK scores are GPT-4 aggregates on multiple skills; they do not equal "gold human truth" for agent deliverables.
- **Judge LLM cost**: Dynamic criteria quality depends on the judge model; weaker models may add noise.
- **Dynamic ablation**: Layer-2 skip is implemented and **C** was refreshed (§5.4).
- **English-first prompts**: Multilingual evaluation is future work.

### 8.2 Ethical Considerations

QAG-Gate uses LLMs as judges, which may inherit biases from the judge model. We recommend against using QAG-Gate as the sole evaluation mechanism for high-stakes applications (hiring, medical advice) without human oversight. Scores should be treated as complementary to, not replacement for, human review.

---

## 9. Conclusion

We presented **QAG-Gate**, a phase-aware binary evaluation framework for agentic systems, and validated it on **public** benchmarks: FLASK (ordinal alignment with GPT-4-reported scores) and MT-Bench human preferences (pairwise accuracy **69.2%** on decisive pairs). QAG-Gate does **not** outperform G-Eval on FLASK correlation, which we interpret as **different evaluation targets** rather than a failed method. Hard-gate RedLine and phase/depth design show measurable effects in ablations. Code is open-sourced under Apache 2.0.

---

## References

- Arabzadeh, N. et al. (2023). AgentEval: A Framework for Automatic Evaluation of LLM Agents. arXiv:2308.11327.
- Es, S. et al. (2024). RAGAS: Automated Evaluation of Retrieval Augmented Generation. EACL 2024.
- Liu, X. et al. (2024). AgentBench: Evaluating LLMs as Agents. ICLR 2024.
- Liu, Y. et al. (2023). G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment. arXiv:2303.16634.
- Nye, B. et al. (2021). Show Your Work: Scratchpads for Intermediate Computation with Language Models. arXiv:2112.00114.
- Park, J. et al. (2024). CritiqueLLM: Towards an Informative Critique Generation Model for Evaluation of Large Language Model Outputs. ACL 2024.
- Ye, H. et al. (2023). FLASK: Fine-grained Language Model Evaluation based on Alignment Skill Sets. arXiv:2307.10928.
- Zheng, L. et al. (2023). Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena. NeurIPS 2023.
- Zhuge, M. et al. (2024). Agent-as-a-Judge: Evaluate Agents with Agents. arXiv:2410.10934.
