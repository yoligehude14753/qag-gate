"""02_self_refine_loop.py — Self-Refine loop scored by QAG-Gate.

Purpose:
    Implement a 4-iteration Self-Refine loop. Each round the LLM produces an
    answer, QAG-Gate scores it, and the failed-verdict reasons become the
    critique fed back into the next prompt. Scores should rise across rounds.

Run:
    OPENAI_API_KEY=sk-... python examples/02_self_refine_loop.py

Env vars:
    OPENAI_API_KEY  required
    OPENAI_BASE_URL optional
    QAG_MODEL       optional (default: gpt-4o-mini)
"""

from __future__ import annotations

import asyncio
import os

from openai import AsyncOpenAI

from qag_gate import QAGEvaluator
from qag_gate.infrastructure import OpenAIAdapter

TASK = (
    "Write a Python function `is_leap_year(year: int) -> bool` that correctly "
    "implements the Gregorian rule (divisible by 4, except centuries unless "
    "divisible by 400). Include a docstring and at least 3 assert-based tests."
)

INITIAL_HINT = "Start with the minimum viable solution. No docstring, no tests yet."


async def generate(client: AsyncOpenAI, model: str, prev: str, critique: str) -> str:
    user = (
        f"Task:\n{TASK}\n\nPrevious attempt:\n{prev or '(none)'}\n\n"
        f"Critique to address in this revision:\n{critique}\n\n"
        "Return ONLY a single Python code block with the improved solution."
    )
    resp = await client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": user}], temperature=0.2,
    )
    return resp.choices[0].message.content or ""


async def main() -> None:
    api_key = os.environ["OPENAI_API_KEY"]
    base_url = os.getenv("OPENAI_BASE_URL")
    model = os.getenv("QAG_MODEL", "gpt-4o-mini")

    gen = AsyncOpenAI(api_key=api_key, base_url=base_url)
    evaluator = QAGEvaluator(OpenAIAdapter(model=model, api_key=api_key, base_url=base_url))

    answer, critique = "", INITIAL_HINT
    best_score = 0.0

    for i in range(4):
        answer = await generate(gen, model, answer, critique)
        result = await evaluator.evaluate(
            task=TASK, content=answer,
            context={"iteration": i, "agent_state": "executing", "tools_used": ["code_exec"]},
        )
        best_score = max(best_score, result.score)
        failed = [f"{v.category}: {v.reason}" for v in result.failed_verdicts[:3]]
        critique = "; ".join(failed) or "Improve code clarity and add comprehensive tests."
        print(f"iter={i} score={result.score:.3f} failed_verdicts={len(result.failed_verdicts)}")

    print(f"\nfinal score: {best_score:.3f}")


if __name__ == "__main__":
    asyncio.run(main())
