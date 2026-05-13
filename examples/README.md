# qag-gate examples

Self-contained scripts showing how to integrate **qag-gate** with mainstream
LLM agent patterns in 2026. Every example is < 80 lines of Python and runs
end-to-end with a single command.

## Install

```bash
pip install "qag-gate[openai]"
```

## Common env vars

| Variable | Required | Default | Notes |
| --- | --- | --- | --- |
| `OPENAI_API_KEY` | yes (except `03_redline_demo`) | — | any OpenAI-compatible key |
| `OPENAI_BASE_URL` | no | OpenAI | point to DeepSeek / Moonshot / OpenRouter etc. |
| `QAG_MODEL` | no | `gpt-4o-mini` | judge model |

## Examples

### `01_minimal_openai.py` — smallest possible integration
Build a `QAGEvaluator` with `OpenAIAdapter`, evaluate one `(task, response)`
pair and print `score / phase / depth / verdicts`.

```bash
OPENAI_API_KEY=sk-... python examples/01_minimal_openai.py
```

Expected output (truncated):

```
score        : 0.83
phase        : delivering
depth        : deep
redlines     : []
verdicts     : 9 (failed: 1)
  [+] intent_match            Does the output directly address what the user asked...
final score: 0.83, phase: delivering
```

### `02_self_refine_loop.py` — Self-Refine driven by QAG feedback
A 4-iteration loop that asks the LLM to refine a Python leap-year function;
each round the failed-verdict reasons become the critique for the next prompt.

```bash
OPENAI_API_KEY=sk-... python examples/02_self_refine_loop.py
```

Expected output:

```
iter=0 score=0.55 failed_verdicts=4
iter=1 score=0.71 failed_verdicts=2
iter=2 score=0.84 failed_verdicts=1
iter=3 score=0.89 failed_verdicts=0
final score: 0.89, best answer length: 612 chars
```

### `03_redline_demo.py` — fire each of the four redlines
Constructs four outputs that each trigger one redline (empty response,
deflection, tool-failure apology, data fabrication). No real LLM call;
`MockLLMClient` is wired in only to satisfy the constructor.

```bash
python examples/03_redline_demo.py
```

Expected output:

```
[OK] empty_response           score=0.00 violations=['empty_response']
[OK] deflection               score=0.00 violations=['deflection']
[OK] tool_failure_apology     score=0.00 violations=['tool_failure_apology_delivery']
[OK] data_fabrication         score=0.00 violations=['data_fabrication']
final: 4 cases evaluated, all expected to score 0.0 due to redline hard-gate.
```

### `04_phase_aware.py` — same content, different phases
Evaluates the same Q1 sales report under `planning` / `executing` /
`delivering` contexts so you can see `phase`, `depth`, and `score` shift.
`planning` short-circuits to `depth=fast` (no LLM call); `delivering`
escalates to `depth=deep` (claim verification).

```bash
OPENAI_API_KEY=sk-... python examples/04_phase_aware.py
```

Expected output:

```
phase=planning   -> detected_phase=planning   depth=fast     score=0.000 verdicts=0  health_check=True
phase=executing  -> detected_phase=executing  depth=standard score=0.78  verdicts=6  health_check=False
phase=delivering -> detected_phase=delivering depth=deep     score=0.84  verdicts=9  health_check=False
final score (delivering phase): 0.84
```

## More integrations

For copy-paste-ready snippets that wire QAG-Gate into Claude Code SDK, Aider,
AutoGen, CrewAI, Letta, LangGraph, and others — beyond the four scripts here —
see [`docs/INTEGRATIONS.md`](../docs/INTEGRATIONS.md).

## Notes

- Examples 1, 2, 4 perform real OpenAI calls — set `OPENAI_API_KEY` first.
- Example 3 requires no network access.
- All scripts print a single final-summary line so you can `grep "^final"`
  in CI smoke tests.
