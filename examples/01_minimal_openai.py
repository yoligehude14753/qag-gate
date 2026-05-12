"""01_minimal_openai.py — Minimal QAG-Gate evaluation with OpenAI.

Purpose:
    Show the smallest possible integration: build a QAGEvaluator backed by
    OpenAIAdapter, evaluate a single (task, response) pair, print the result.

Run:
    OPENAI_API_KEY=sk-... python examples/01_minimal_openai.py

Env vars:
    OPENAI_API_KEY  required, OpenAI-compatible API key
    OPENAI_BASE_URL optional, custom base URL (DeepSeek / Moonshot / etc.)
    QAG_MODEL       optional, model name (default: gpt-4o-mini)
"""

from __future__ import annotations

import asyncio
import os

from qag_gate import QAGEvaluator
from qag_gate.infrastructure import OpenAIAdapter


TASK = "Write a one-paragraph summary of how photosynthesis works for a 10-year-old."

RESPONSE = (
    "Plants use sunlight as energy to mix water from their roots with carbon dioxide "
    "from the air. Inside their green leaves, this mixture becomes sugar (food the plant "
    "uses to grow) and oxygen (which it releases for us to breathe). So sunlight, water, "
    "and air go in, and food + oxygen come out."
)


async def main() -> None:
    adapter = OpenAIAdapter(
        model=os.getenv("QAG_MODEL", "gpt-4o-mini"),
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.getenv("OPENAI_BASE_URL"),
    )
    evaluator = QAGEvaluator(llm_client=adapter)

    result = await evaluator.evaluate(
        task=TASK,
        content=RESPONSE,
        context={"iteration": 1, "agent_state": "delivering", "tools_used": []},
    )

    print(f"score        : {result.score:.3f}")
    print(f"phase        : {result.phase.value}")
    print(f"depth        : {result.depth.value}")
    print(f"redlines     : {result.redline_violations}")
    print(f"verdicts     : {len(result.verdicts)} (failed: {len(result.failed_verdicts)})")
    for v in result.verdicts[:3]:
        marker = "+" if v.is_positive else "-"
        print(f"  [{marker}] {v.category:<22} {v.question[:60]}...")

    print(f"\nfinal score: {result.score:.3f}, phase: {result.phase.value}")


if __name__ == "__main__":
    asyncio.run(main())
