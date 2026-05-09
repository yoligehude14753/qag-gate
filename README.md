# qag-gate

**Phase-aware, output-type-adaptive QAG binary evaluation framework for AI agent outputs.**

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org)

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
| MT-Bench pairwise (380 decisive pairs) | **69.2%** accuracy vs human preference; *p* = 2.5×10⁻¹⁴ vs random |
| FLASK-Eval correlation (n=279) | ρ = 0.226 vs G-Eval ρ = 0.487—measures orthogonal agent-specific quality |

Full experiment scripts in [`benchmarks/`](benchmarks/).

## Development

```bash
git clone https://github.com/yoligehude14753/openall
cd openall/projects/qag-gate
pip install -e ".[dev]"
pytest tests/
```
