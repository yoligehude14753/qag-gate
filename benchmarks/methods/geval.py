"""G-Eval baseline implementation with retry logic.

Ref: Liu et al. (2023) "G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment"
Simplified form-filling variant: generate criteria → CoT score.
"""

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from qag_gate.domain.ports import LLMClient

_CRITERIA_PROMPT = """\
You are an evaluation expert. Given the following task description, \
generate 5 evaluation criteria for assessing the quality of a task response.
Output ONLY a numbered list (1-5), one criterion per line, no additional text.

Task: {task}
"""

_EVAL_PROMPT = """\
You are an impartial evaluator. Evaluate the following response step-by-step, \
then assign an overall score.

Task: {task}

Response to evaluate:
{content}

Evaluation Criteria:
{criteria}

Think step-by-step about how well the response meets each criterion.
Then output your evaluation in this exact format:
<score>X</score>
where X is an integer from 1 to 5 (1=very poor, 5=excellent).
"""


async def geval_score(
    task: str,
    content: str,
    llm: LLMClient,
    max_retries: int = 3,
    retry_delay: float = 2.0,
) -> dict:
    """Run G-Eval on a single (task, content) pair with retry logic."""
    if not content or not content.strip():
        return {"score": 0.0, "raw_score": 1, "criteria": "", "error": "empty content"}

    # Step 1: Generate criteria (with retry)
    # OpenAIAdapter.complete(system, user, ...) — split prompt into system+user
    criteria = None
    for attempt in range(max_retries):
        try:
            criteria_resp = await llm.complete(
                "You are an evaluation expert.",
                _CRITERIA_PROMPT.format(task=task),
                temperature=0.1,
                max_tokens=300,
            )
            criteria = criteria_resp.strip()
            break
        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (attempt + 1))
            else:
                return {"score": 0.5, "raw_score": 3, "criteria": "", "error": f"criteria gen failed after {max_retries} retries: {e}"}

    # Step 2: Evaluate with CoT (with retry)
    for attempt in range(max_retries):
        try:
            eval_resp = await llm.complete(
                "You are an impartial evaluator.",
                _EVAL_PROMPT.format(task=task, content=content, criteria=criteria),
                temperature=0.1,
                max_tokens=600,
            )
            match = re.search(r"<score>(\d)</score>", eval_resp)
            raw_score = int(match.group(1)) if match else 3
            raw_score = max(1, min(5, raw_score))
            score = (raw_score - 1) / 4.0
            return {"score": score, "raw_score": raw_score, "criteria": criteria, "error": None}
        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (attempt + 1))
            else:
                return {"score": 0.5, "raw_score": 3, "criteria": criteria, "error": f"eval failed after {max_retries} retries: {e}"}

    return {"score": 0.5, "raw_score": 3, "criteria": criteria or "", "error": "unexpected"}


async def run_geval_batch(
    samples: list[dict],
    llm: LLMClient,
    concurrency: int = 2,
    inter_batch_delay: float = 1.0,
) -> list[dict]:
    """Run G-Eval on a batch with rate-limit-aware concurrency."""
    sem = asyncio.Semaphore(concurrency)

    async def _one(sample: dict) -> dict:
        async with sem:
            await asyncio.sleep(inter_batch_delay)  # rate limit buffer
            result = await geval_score(sample["task"], sample["content"], llm)
            return {
                **sample,
                "geval_score": result["score"],
                "geval_raw": result.get("raw_score"),
                "geval_error": result.get("error"),
            }

    return await asyncio.gather(*[_one(s) for s in samples])
