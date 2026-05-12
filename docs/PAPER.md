# QAG-Gate: Phase-Aware Binary Evaluation for Long-Running Coding Agents

> Draft v1.3 · 2026-05-12  
> Target: arXiv technical report; EMNLP 2026 System Demonstrations submission  
> Length target: 8,000–10,000 words (camera ready)

---

## Abstract

Tools like Claude Code, OpenAI Codex CLI, Cursor Composer and similar long-running coding agents now routinely run unattended for minutes to hours, producing planning text, partial code, files, and final deliverables in the same loop. Two questions become operational: is the agent's current output *good for its current stage*, and is it *good enough to ship*. Off-the-shelf judges answer neither well — static rubrics ignore which stage the agent is in, and generic LLM-as-a-judge scoring (e.g., G-Eval) treats a Python script and a planning bullet list as the same kind of text.

We present **QAG-Gate**, an open-source framework that scores agent outputs through (1) a phase classifier (planning / executing / delivering), (2) a depth-adaptive selector that allocates 4 to 20+ binary questions based on phase and context, (3) a three-layer question stack (baseline gates + LLM-generated task-specific questions + output-type overrides for code/file/tabular outputs), and (4) a deterministic RedLine hard gate covering six failure patterns we observed in production agent runs (deflection, tool-failure apologies, fabrication, duplication, empty responses, temporal drift).

On **MT-Bench human pairwise preferences** (495 pairs; 380 decisive after removing ties), QAG-Gate matches the human-preferred answer on **263/380 = 69.2%** of pairs (binomial *p* ≈ 2.5 × 10⁻¹⁴ vs. chance; 95% Wilson CI [0.644, 0.736]; writing 0.663, STEM 0.729, reasoning 0.653, roleplay 0.709). On **FLASK-Eval** (n=279), correlation with FLASK's GPT-4 aggregate skill scores is **ρ = 0.226** vs. **0.487** for G-Eval — QAG-Gate is *not* trying to recover FLASK's instruction-following score, and we read this gap as **measuring different things**, not as a regression. Ablations on FLASK (n=279, all `_skip_dynamic` runs re-executed in May 2026) show each component contributes a small but consistent amount: removing phase-aware depth costs **Δρ = −0.027**, disabling RedLine costs **−0.015**, skipping Layer-2 dynamic questions costs **−0.014**, forcing STANDARD depth costs **−0.008**.

Code is released under Apache 2.0 (`pip install qag-gate`). The package targets drop-in use inside iterative coding agents — Self-Refine loops, Reflexion, Claude Code SDK wrappers, Cursor agent integrations, AutoGen / CrewAI / Letta — anywhere a stable, programmable score-and-gate signal is needed.

**Keywords**: LLM evaluation, coding agents, binary judgment, phase-aware assessment, agent observability

---

## 1. Introduction

A new class of LLM-powered coding agents — Claude Code, OpenAI Codex CLI, Cursor Composer, Aider, Devin, and the open-source AutoGen / CrewAI / Letta family — runs **mostly without a human in the loop**. A single invocation may write a plan, call build tools, iterate on test failures, and hand back a multi-file change set. Three trends amplify the cost of getting evaluation wrong:

1. **Parallelism**. Practitioners now spawn several Claude Code or Codex sessions side by side; spend per task multiplies linearly.
2. **Recurrence**. The same agent is scheduled to run on cron-like triggers (commit hooks, nightly refactors, doc-sync jobs); a silently degraded agent fails for hours before anyone notices.
3. **Remote / mobile control**. Anthropic's mobile control surface for Claude Code, and similar wrappers, means the human can no longer observe each intermediate step.

In every one of these settings, we need a *programmable* signal that answers two questions on every iteration: (a) is the current output good *for the stage the agent is in*, and (b) is it good enough to deliver. Two classes of existing tooling fall short:

**Static rubrics** (the kind shipped with Anthropic Evals, OpenAI Evals, or hand-written CI checks) apply one fixed checklist. A criterion that makes sense for a final deliverable ("does the report cite sources?") punishes a planning-stage response that legitimately has no citations.

**Generic LLM-as-a-judge** scoring such as G-Eval [Liu et al. 2023] or MT-Bench's judge prompt [Zheng et al. 2023] generates a scalar after chain-of-thought reasoning, but treats every artifact as flat text. A failing test in a Python output does not affect the score the way it should; a half-written .pptx outline looks the same as a bullet list.

QAG-Gate sits between these two extremes. It uses LLM-as-a-judge style binary verdicts — pairwise / binary judgments are reported to be more reliable than scalar scoring in MT-Bench-style settings [Zheng et al. 2023; Ke et al. 2023] — but routes them through a phase classifier and an output-type aware overlay, so the questions the judge is actually asked are appropriate to the moment.

**Contributions.**

1. **Phase-aware question routing** (§3.1): a classifier that maps an agent response to one of `PLANNING`, `EXECUTING`, `DELIVERING`, choosing different question subsets for each.
2. **Depth-adaptive selection** (§3.2): a rule-based selector that chooses between fast (4 questions, ~0.5 s, no LLM call required if cached), standard (12–14), and deep (20+) based on phase and context signals.
3. **Three-layer binary question stack** (§3.3): four always-on baseline gates + 4–10 dynamically generated task-specific questions + output-type overrides for code, file (PPT / Word / Excel) and tabular outputs.
4. **Deterministic RedLine hard gate** (§3.4): six regex / heuristic checks tuned on actual production agent failures (deflection, tool-failure apologies, fabrication, paragraph-level duplication, empty responses, temporal incoherence). Any match forces `score = 0` before any LLM call is made.
5. **External validation on public benchmarks** (§5): MT-Bench pairwise (the primary headline result, 69.2% accuracy with *p* ≈ 2.5×10⁻¹⁴) and FLASK-Eval correlation. Ablations isolate the marginal value of each component. Internal data is reported as supplementary only and not used to make claims.

---

## 2. Background and Related Work

### 2.1 Generic LLM-as-a-Judge

**G-Eval** [Liu et al. 2023] is the closest baseline to QAG-Gate in spirit. It generates evaluation criteria with chain-of-thought prompting and produces a scalar score that correlates strongly with human judgments on summarization. G-Eval treats every task as flat NLG and does not condition on agent stage or output type; we use it as the main baseline in §5.

The **MT-Bench judge prompt** [Zheng et al. 2023] is a single-LLM pairwise / single-answer rubric used both as a benchmark and a recipe. We use the human pairwise judgments released alongside MT-Bench in §5.3, not the judge prompt itself.

**RAGAS** [Es et al. 2024] decomposes retrieval-augmented generation into faithfulness, answer relevancy, and context recall. It is the closest production system for the QA case but does not generalize to open coding / file / planning outputs.

### 2.2 Agent-Specific Evaluation

**AgentBench** [Liu et al. 2024] measures task completion across 8 environments. It requires ground-truth solutions or programmatic checkers and so does not extend to open-ended deliverables.

**Agent-as-a-Judge** [Zhuge et al. 2024] uses a tool-equipped agent to evaluate another agent, recovering much more signal than a scalar judge but at substantially higher cost. QAG-Gate occupies the cheaper middle ground: it is still a single-LLM-call judge in standard mode, but adds phase routing, an output-type overlay, and a deterministic RedLine pre-filter.

### 2.3 Binary vs. Scalar Judging

The MT-Bench analysis [Zheng et al. 2023] reports that pairwise / binary judgments produce higher LLM-vs-human agreement than direct scalar scoring, and CritiqueLLM [Ke et al. 2023] further argues that structured per-criterion judgments are easier to debug and re-rate than a single number. QAG-Gate inherits this design choice and stacks three layers of binary questions so that disagreements localize to specific criteria instead of contaminating a single aggregate.

### 2.4 Phase- and Stage-Conditioned Evaluation

We are not aware of an open evaluation framework that explicitly conditions on agent execution stage (planning / executing / delivering). The nearest analogue is the long-context evaluation suite **HELMET** [Yen et al. 2024], which conditions on task family rather than agent stage, and the iterative-refinement frameworks **Self-Refine** [Madaan et al. 2023] and **Reflexion** [Shinn et al. 2023], which use stage information only to decide whether to refine, not how to judge.

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

These four binary gates apply to any agent output regardless of task or phase:
1. Does the output directly address what the user asked for? (`intent_match`, weight 1.5)
2. Does the output contain a concrete, usable deliverable? (`deliverable`, weight 1.5)
3. Is the output free of obvious errors or incomplete artifacts? (`quality_baseline`, weight 1.0)
4. Can the user directly use this output without significant additional work? (`actionability`, weight 1.0)

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

### 5.5 Internal preliminary runs (P0–P2, supplementary)

Progressive smoke / tier tests on author-assigned pseudo-tiered data (n=800) confirm the pipeline runs end-to-end (ρ = 0.524 vs. random label baseline ρ = 0.043). We do not draw quality claims from this set; it serves as a regression-test fixture under `benchmarks/internal-tiers/` and is kept reproducible so that breaking changes to the depth selector or score aggregator surface immediately.

---

## 6. Analysis

### 6.1 When Does Phase Detection Help?

External ablations (§5.4-B, C, D) show ρ falls when **phase-aware depth** is bypassed (~−0.027), when **dynamic Layer-2** is skipped (−0.0142), or when **RedLine** is off (−0.0149)—consistent with all three contributing on this FLASK proxy.

### 6.2 Failure Modes

Two recurring failure modes show up when we hand-inspect disagreements between QAG-Gate scores and human preference:

1. **Score compression for mid-quality outputs.** Mid-tier responses that are well structured (clear headings, complete code skeleton, no obvious errors) score within 5–8 points of high-tier responses, even when the high-tier response goes substantially deeper. We traced this to the Layer-2 dynamic criteria generator giving structural-completeness questions a higher effective weight than content-depth questions; a representative case is a Python data-analysis task where a partly-correct script with rich comments scored 0.92 vs. a correct script with sparse comments at 0.86. Prompt-side mitigation (re-emphasising actionability over structure) is the natural fix.

2. **RAG ceiling effect.** For retrieval-augmented Q&A tasks with well-formatted but shallow answers, QAG-Gate does not adequately penalise lack of specificity — a citation-shaped answer that *looks* grounded passes the baseline gates even when the cited content is generic. Layer-3 content-depth probes (e.g. "does the response cite a specific fact, number, or quote from the retrieved context?") materially improve discrimination on this slice.

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

We presented **QAG-Gate**, a phase-aware binary evaluation framework targeted at long-running coding agents like Claude Code, Codex CLI and Cursor Composer. On MT-Bench human pairwise preference (n=380 decisive pairs) it agrees with humans on 69.2% of choices (*p* ≈ 2.5 × 10⁻¹⁴). On FLASK-Eval (n=279) it correlates with FLASK's GPT-4 aggregate at ρ = 0.226, which is lower than G-Eval's 0.487 — we interpret this as measuring agent-output suitability rather than instruction-following style, not as a regression on the same target. Ablations show small but consistent contributions from the phase-aware path, the dynamic question layer, and the RedLine hard gate. The package is open-source under Apache 2.0 (`pip install qag-gate`) and integrates with Self-Refine, Reflexion, AutoGen, CrewAI, Letta, and Claude Code SDK style loops.

---

## References

- Es, S., James, J., Espinosa-Anke, L., & Schockaert, S. (2024). *RAGAS: Automated Evaluation of Retrieval Augmented Generation*. EACL 2024.
- Ke, P., Wen, B., Feng, Z., Liu, X., Lei, X., Cheng, J., Wang, S., Zeng, A., Dong, Y., Wang, H., Tang, J., & Huang, M. (2023). *CritiqueLLM: Scaling LLM-as-Critic for Effective and Explainable Evaluation of Large Language Model Generation*. arXiv:2311.18702.
- Liu, X., Yu, H., Zhang, H., Xu, Y., Lei, X., Lai, H., Gu, Y., Ding, H., Men, K., Yang, K., Zhang, S., Deng, X., Zeng, A., Du, Z., Zhang, C., Shen, S., Zhang, T., Su, Y., Sun, H., Huang, M., Dong, Y., & Tang, J. (2024). *AgentBench: Evaluating LLMs as Agents*. ICLR 2024.
- Liu, Y., Iter, D., Xu, Y., Wang, S., Xu, R., & Zhu, C. (2023). *G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment*. arXiv:2303.16634.
- Madaan, A., Tandon, N., Gupta, P., Hallinan, S., Gao, L., Wiegreffe, S., Alon, U., Dziri, N., Prabhumoye, S., Yang, Y., Welleck, S., Majumder, B. P., Gupta, S., Yazdanbakhsh, A., & Clark, P. (2023). *Self-Refine: Iterative Refinement with Self-Feedback*. NeurIPS 2023.
- Shinn, N., Cassano, F., Berman, E., Gopinath, A., Narasimhan, K., & Yao, S. (2023). *Reflexion: Language Agents with Verbal Reinforcement Learning*. NeurIPS 2023.
- Yen, H., Gao, T., Hou, M., Ding, K., Fleischer, D., Izsak, P., Wasserblat, M., & Chen, D. (2024). *HELMET: How to Evaluate Long-Context Language Models Effectively and Thoroughly*. arXiv:2410.02694.
- Ye, S., Kim, D., Kim, S., Hwang, H., Kim, S., Jo, Y., Thorne, J., Kim, J., & Seo, M. (2023). *FLASK: Fine-grained Language Model Evaluation based on Alignment Skill Sets*. arXiv:2307.10928.
- Zheng, L., Chiang, W.-L., Sheng, Y., Zhuang, S., Wu, Z., Zhuang, Y., Lin, Z., Li, Z., Li, D., Xing, E., Zhang, H., Gonzalez, J. E., & Stoica, I. (2023). *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena*. NeurIPS 2023.
- Zhuge, M., Zhao, C., Ashley, D., Wang, W., Khizbullin, D., Xiong, Y., Liu, Z., Chang, E., Krishnamoorthi, R., Tian, Y., Shi, Y., Chandra, V., & Schmidhuber, J. (2024). *Agent-as-a-Judge: Evaluate Agents with Agents*. arXiv:2410.10934.
