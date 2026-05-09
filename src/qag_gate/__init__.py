"""qag-gate — Phase-aware QAG binary evaluation framework for AI agent outputs.

快速开始::

    from qag_gate import QAGEvaluator, EvalResult
    from qag_gate.infrastructure import OpenAIAdapter

    evaluator = QAGEvaluator(llm_client=OpenAIAdapter(model="gpt-4o-mini"))
    result: EvalResult = await evaluator.evaluate(
        task="生成一份市场分析报告",
        content="...（agent 输出）...",
        context={"iteration": 1, "tools_used": ["web_search"]},
    )
    print(result.score)        # 0.0 ~ 1.0
    print(result.phase)        # EvalPhase.EXECUTING
    print(result.depth)        # EvalDepth.STANDARD
    print(result.verdicts)     # List[Verdict]
"""

from qag_gate.application.evaluator import QAGEvaluator
from qag_gate.domain.models import (
    EvalDepth,
    EvalPhase,
    EvalQuestion,
    EvalResult,
    RedLineViolation,
    Verdict,
)

__all__ = [
    "QAGEvaluator",
    "EvalResult",
    "EvalPhase",
    "EvalDepth",
    "EvalQuestion",
    "Verdict",
    "RedLineViolation",
]

__version__ = "0.1.0"
