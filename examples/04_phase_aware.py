"""04_phase_aware.py — Same output, different phases.

Purpose:
    Demonstrate phase-aware behaviour: the same content evaluated under
    `planning` / `executing` / `delivering` produces different `phase`,
    `depth`, and (usually) different scores. Planning uses depth=fast and
    skips LLM calls entirely; delivering uses depth=deep.

Run:
    OPENAI_API_KEY=sk-... python examples/04_phase_aware.py

Env vars:
    OPENAI_API_KEY  required
    OPENAI_BASE_URL optional
    QAG_MODEL       optional (default: gpt-4o-mini)
"""

from __future__ import annotations

import asyncio
import os

from qag_gate import QAGEvaluator
from qag_gate.infrastructure import OpenAIAdapter

CONTENT = (
    "## Q1 Sales Analysis\n\n"
    "Revenue reached $4.2M in Q1, up 18% YoY. The top three SKUs accounted "
    "for 62% of total revenue, with the flagship model contributing $1.8M.\n\n"
    "Cost of goods sold was $2.1M (gross margin 50%). Marketing spend was "
    "$420K with a CAC of $34 (vs. $48 LTM).\n\n"
    "Recommendation: shift 15% of paid-search budget into the highest-margin "
    "SKU and re-test creative on cold audiences in April."
)

TASK = "Analyse Q1 sales data and produce a one-page report with concrete recommendations."

PHASES = [
    {"label": "planning",   "iteration": 0, "agent_state": "planning",   "tools_used": []},
    {"label": "executing",  "iteration": 3, "agent_state": "executing",  "tools_used": ["python_repl"]},
    {"label": "delivering", "iteration": 5, "agent_state": "delivering", "tools_used": ["python_repl", "web_search"]},
]


async def main() -> None:
    adapter = OpenAIAdapter(
        model=os.getenv("QAG_MODEL", "gpt-4o-mini"),
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.getenv("OPENAI_BASE_URL"),
    )
    evaluator = QAGEvaluator(adapter)

    last_score = None
    for p in PHASES:
        r = await evaluator.evaluate(task=TASK, content=CONTENT, context=p)
        last_score = r.score
        print(
            f"phase={p['label']:<10} -> "
            f"detected_phase={r.phase.value:<10} depth={r.depth.value:<8} "
            f"score={r.score:.3f} verdicts={len(r.verdicts)} health_check={r.is_health_check}"
        )

    print(f"\nfinal score (delivering phase): {last_score:.3f}")


if __name__ == "__main__":
    asyncio.run(main())
