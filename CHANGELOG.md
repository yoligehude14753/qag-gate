# Changelog

All notable changes to `qag-gate` are documented in this file. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-05-13

First public release.

### Added

- **Phase-aware binary evaluator**: classifies an agent's current output
  as `planning`, `executing`, or `delivering` and applies a depth-adaptive
  question stack accordingly.
- **Three-layer question architecture**:
  1. **Baseline gates** — intent match, deliverable, quality baseline,
     code runnable.
  2. **LLM-generated dynamic questions** — task-specific binary checks
     synthesised on demand.
  3. **Output-type overrides** — extra binary gates for code, files, and
     tabular outputs.
- **`RedLineChecker`**: deterministic hard gate covering six failure
  patterns observed in production agent runs (deflection, tool-failure
  apologies, fabrication, duplication, empty responses, temporal drift).
- **`QAGEvaluator`** — high-level API: `evaluate(task, response,
  context=None) -> EvaluationResult`.
- **`OpenAIAdapter`** / **`AnthropicAdapter`** — drop-in `LLMClient`
  implementations for OpenAI- and Anthropic-compatible APIs.
- **`MockLLMClient`** — deterministic stub for unit tests.
- Apache 2.0 license.

### Validated against

- **MT-Bench human preferences** — 263/380 = 69.2% pairwise agreement
  (binomial *p* ≈ 2.5 × 10⁻¹⁴; 95% Wilson CI [0.644, 0.736]).
- **FLASK-Eval** (n = 279) — ρ = 0.226 with FLASK's GPT-4 aggregate
  skill scores. See [`docs/PAPER.md`](docs/PAPER.md) for the discussion
  of why this gap is *measuring different things*, not a regression
  versus G-Eval.
- **Ablation**: removing phase-aware depth costs Δρ = −0.027, disabling
  RedLine costs −0.015, skipping Layer-2 dynamic questions costs −0.014.

### Known limitations

- Judge calls cost one LLM round-trip per evaluation; cache responses if
  the same `(task, response)` pair is re-evaluated.
- Depth selector is calibrated on coding-agent traces; non-code domains
  may need a custom `_depth_policy` (see `qag_gate/core/depth.py`).
- All public APIs are considered **stable from 0.1.x onward**, but minor
  internal modules (e.g., `qag_gate.internal.*`) may move without notice.

[Unreleased]: https://github.com/yoligehude14753/qag-gate/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/yoligehude14753/qag-gate/releases/tag/v0.1.0
