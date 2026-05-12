# qag-gate

**A phase-aware binary evaluator for long-running coding agents** — Claude Code, OpenAI Codex CLI, Cursor Composer, Aider, AutoGen / CrewAI / Letta loops. Drops in as the scoring step inside any Self-Refine, Reflexion, or custom agent loop and answers two questions on every iteration: *is this output good for the stage the agent is in*, and *is it good enough to ship*.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org)

## Why this exists

Generic LLM-as-a-judge tools (G-Eval, RAGAS) treat every agent output as flat text and ignore which stage the agent is in. Static rubrics ignore output type — a Python script and a planning bullet list get the same checklist. As agents move from human-supervised IDE pairing to *unattended* long-running loops (parallel Claude Code sessions, scheduled Codex jobs, mobile-triggered runs), we need a programmable signal that is cheap, deterministic in the failure cases, and stable enough to wire into a CI pipeline.

QAG-Gate combines (1) a phase classifier (`PLANNING` / `EXECUTING` / `DELIVERING`), (2) depth-adaptive question selection (4 → 20+ binary questions), (3) a three-layer question stack with output-type overrides for code / file / tabular outputs, and (4) a deterministic RedLine hard gate covering six production failure patterns (deflection, tool-failure apologies, fabrication, duplication, empty responses, temporal drift).

## Quick Start

```python
from qag_gate import QAGEvaluator, EvalResult
from qag_gate.infrastructure import OpenAIAdapter

evaluator = QAGEvaluator(llm_client=OpenAIAdapter(model="gpt-4o-mini"))
result: EvalResult = await evaluator.evaluate(
    task="Analyze Q1 sales data and generate a report",
    content="...(agent output)...",
    context={"iteration": 2, "tools_used": ["python_repl"]},
)
print(result.score)    # 0.0 ~ 1.0
print(result.phase)    # EvalPhase.EXECUTING
print(result.verdicts) # List[Verdict]
```

## Install

```bash
pip install qag-gate             # core only (no LLM SDK)
pip install "qag-gate[openai]"   # + OpenAI SDK
pip install "qag-gate[anthropic]"  # + Anthropic SDK
pip install "qag-gate[all]"      # all adapters
```

## Architecture

Three-layer evaluation:
1. **Baseline questions** (always present, task-type agnostic)
2. **Dynamic questions** (LLM-generated, task-specific)
3. **Output-type overrides** (file/code tasks skip factual_accuracy)

Phase-aware depth selection:
- `fast` — planning phase, no LLM calls
- `standard` — executing phase, 1 LLM call
- `deep` — delivering phase, claim verification

## Paper

QAG-Gate: Phase-Aware Binary Evaluation for AI Agent Outputs (arXiv preprint, 2026). See [`docs/PAPER.md`](docs/PAPER.md) for full draft.

## Validation

| Benchmark | Result |
|-----------|--------|
| MT-Bench pairwise (n=380 decisive) | **69.2%** agreement with human preference (binomial *p* ≈ 2.5×10⁻¹⁴, 95% Wilson CI [0.644, 0.736]) |
| FLASK-Eval correlation (n=279) | ρ = 0.226 (G-Eval ρ = 0.487 — different evaluation target, see [`docs/PAPER.md`](docs/PAPER.md) §5) |
| Ablation Δρ on FLASK | phase routing −0.027, RedLine −0.015, dynamic Layer-2 −0.014, fixed STANDARD −0.008 |

Full experiment scripts in [`benchmarks/`](benchmarks/). All caches and seeds preserved for reproduction.

## Works with

QAG-Gate is evaluator-agnostic on the scoring side and consumes plain text + optional tool/context signals — no framework lock-in. Tested integrations:

- **Self-Refine / Reflexion / ReAct** loops (call `evaluator.evaluate()` between iterations)
- **AutoGen, CrewAI, Letta, LangGraph** node-level scoring
- **Claude Code SDK / Codex CLI** wrappers (score each tool / file edit before continuing)
- Custom Python `asyncio` agent loops

## Development

```bash
git clone https://github.com/yoligehude14753/openall
cd openall/projects/qag-gate
pip install -e ".[dev]"
pytest tests/
```
