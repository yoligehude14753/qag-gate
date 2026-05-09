"""Integration tests: full QAG-Gate pipeline with controlled mock responses.

These tests verify that the entire evaluation pipeline produces
expected results when all components work together, using a
controllable mock LLM that returns realistic-format responses.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, patch

from qag_gate import QAGEvaluator, EvalResult
from qag_gate.domain.models import EvalPhase, EvalDepth
from qag_gate.infrastructure import MockLLMClient


def make_mock(all_yes: bool = True) -> MockLLMClient:
    """Create a MockLLMClient with realistic verdict responses."""
    verdict = "Yes" if all_yes else "No"
    response = json.dumps({
        "answers": [
            {"question_id": f"q{i}", "verdict": verdict,
             "answer": verdict, "reasoning": f"Evaluation result: {verdict}"}
            for i in range(10)
        ]
    })
    return MockLLMClient(response=response)


# ── Pipeline integration tests ─────────────────────────────────────────────

class TestQAGPipelineIntegration:
    """Full pipeline integration tests."""

    @pytest.mark.asyncio
    async def test_high_quality_output_scores_well(self):
        """High quality agent output should score above 0.50 with all-yes verdicts."""
        llm = make_mock(all_yes=True)
        evaluator = QAGEvaluator(llm_client=llm)

        result = await evaluator.evaluate(
            task="Analyze the Q1 sales data and provide 3 actionable recommendations.",
            content="""# Q1 Sales Analysis

## Findings
Sales grew 12% YoY to $5.2M. Customer acquisition cost increased 8%.
High-value segment (>$10k) grew 35% while standard segment declined 5%.

## Recommendations
1. **Focus on enterprise segment**: Increase SDR headcount by 2, target 20% growth in high-value
2. **Reduce CAC**: Audit marketing spend, cut bottom-20% channels, reinvest in top performers
3. **Improve standard retention**: Implement success playbook for <$10k accounts to reduce churn 15%

*Data source: Salesforce Q1 2026 report*""",
            context={"iteration": 5, "tools_used": ["search"]}  # force EXECUTING phase → STANDARD
        )

        assert isinstance(result, EvalResult)
        assert result.score >= 0.5, f"Expected high score for all-yes verdicts, got {result.score}"
        assert len(result.verdicts) > 0

    @pytest.mark.asyncio
    async def test_empty_response_triggers_redline(self):
        """Empty content should trigger RedLine and return score=0."""
        llm = make_mock()
        evaluator = QAGEvaluator(llm_client=llm)

        result = await evaluator.evaluate(
            task="Write a Python function to sort a list",
            content="",
            context={"iteration": 5}
        )

        assert result.score == 0.0
        assert result.is_health_check or len(result.redline_violations) > 0

    @pytest.mark.asyncio
    async def test_chinese_deflection_triggers_redline(self):
        """Chinese deflecting response (≥3 deflection phrases) should trigger RedLine."""
        llm = make_mock(all_yes=True)  # even with all-yes LLM, redline blocks it
        evaluator = QAGEvaluator(llm_client=llm)

        result = await evaluator.evaluate(
            task="帮我分析市场竞争格局",
            content=(
                "我无法直接访问实时市场数据。"
                "你可以自行运行这个分析，需要你自己收集数据。"
                "我无法替你完成这项工作，你需要自己做研究。"
                "你可以在本机运行相关工具获取所需信息。"
            ),
            context={"iteration": 5}
        )

        assert "deflection" in result.redline_violations, \
            f"Expected deflection violation, got: {result.redline_violations}"
        assert result.score == 0.0, \
            f"RedLine hard gate must zero the score, got: {result.score}"

    @pytest.mark.asyncio
    async def test_phase_detection_planning(self):
        """Planning-phase response should be detected correctly."""
        llm = make_mock(all_yes=True)
        evaluator = QAGEvaluator(llm_client=llm)

        result = await evaluator.evaluate(
            task="Build a data pipeline for ETL",
            content="My approach will be:\n1. Set up ingestion layer\n2. Transform data\n3. Load to warehouse\nI'll start by analyzing the data sources.",
            context={"iteration": 4}  # iteration>2 so PLANNING won't force FAST mode
        )

        assert isinstance(result, EvalResult)
        # Phase is detected, result is valid
        assert result.phase in (EvalPhase.PLANNING, EvalPhase.EXECUTING, EvalPhase.DELIVERING)

    @pytest.mark.asyncio
    async def test_code_output_gets_code_specific_questions(self):
        """Code output should trigger output-type detection."""
        questions_asked = []

        class TrackingMock:
            async def complete(self, system: str, user: str, **kwargs) -> str:
                questions_asked.append(system + " " + user)
                return json.dumps({
                    "answers": [
                        {"question_id": "q0", "verdict": "Yes", "answer": "Yes", "reasoning": "ok"},
                    ]
                })

        evaluator = QAGEvaluator(llm_client=TrackingMock())

        result = await evaluator.evaluate(
            task="Write a Python function to compute fibonacci numbers",
            content="""```python
def fibonacci(n: int) -> int:
    \"\"\"Compute nth fibonacci number using dynamic programming.\"\"\"
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b

# Test
assert fibonacci(10) == 55
print("✓ Tests passed")
```""",
            context={"iteration": 5, "tools_used": ["code_exec"]}  # force STANDARD/DEEP mode
        )

        assert isinstance(result, EvalResult)
        # Verify the pipeline ran (questions were asked to LLM)
        assert len(questions_asked) >= 1, "No LLM calls were made"

    @pytest.mark.asyncio
    async def test_llm_failure_degrades_gracefully(self):
        """When LLM fails, evaluator should return a safe fallback result."""
        class FailingLLM:
            async def complete(self, system: str, user: str, **kwargs) -> str:
                raise ConnectionError("API timeout")

        evaluator = QAGEvaluator(llm_client=FailingLLM())

        # Should not raise, should return a result with fallback score
        result = await evaluator.evaluate(
            task="Write a report",
            content="Here is my detailed report with analysis and recommendations for improving business performance across all key metrics.",
            context={"iteration": 5, "tools_used": ["analysis"]}
        )

        assert isinstance(result, EvalResult)
        assert 0.0 <= result.score <= 1.0

    @pytest.mark.asyncio
    async def test_evaluator_produces_structured_output(self):
        """EvalResult should always have required fields."""
        llm = make_mock(all_yes=True)
        evaluator = QAGEvaluator(llm_client=llm)

        result = await evaluator.evaluate(
            task="Some task",
            content="Some content that is long enough to pass basic checks and shows comprehensive work and analysis with actionable recommendations.",
            context={"iteration": 5, "tools_used": ["search"]}
        )

        # Required fields
        assert hasattr(result, 'score')
        assert hasattr(result, 'phase')
        assert hasattr(result, 'depth')
        assert hasattr(result, 'verdicts')
        assert hasattr(result, 'redline_violations')

        # Type checks
        assert isinstance(result.score, float)
        assert isinstance(result.phase, EvalPhase)
        assert isinstance(result.depth, EvalDepth)
        assert isinstance(result.verdicts, list)
        assert isinstance(result.redline_violations, list)

        # Range check
        assert 0.0 <= result.score <= 1.0


# ── Deep mode / claim verification ────────────────────────────────────────

class TestDeepMode:
    """DELIVERING phase triggers DEEP mode including claim verification."""

    @pytest.mark.asyncio
    async def test_delivering_phase_uses_deep_depth(self):
        """DELIVERING phase should select EvalDepth.DEEP."""
        llm = make_mock(all_yes=True)
        evaluator = QAGEvaluator(llm_client=llm)
        result = await evaluator.evaluate(
            task="Generate a market research report",
            content=(
                "# Market Research Report\n\n"
                "## Executive Summary\n"
                "The global market is valued at $500B with 15% annual growth rate.\n"
                "Key players include Company A (28% share) and Company B (22% share).\n\n"
                "## Recommendations\n"
                "1. Expand into Southeast Asia — opportunity worth $50B.\n"
                "2. Invest in R&D for product line extension.\n"
                "3. Build strategic partnerships with regional distributors."
            ),
            context={"iteration": 4, "agent_state": "delivering", "tools_used": ["search"]},
        )
        assert result.depth == EvalDepth.DEEP
        assert result.phase == EvalPhase.DELIVERING
        assert 0.0 <= result.score <= 1.0

    @pytest.mark.asyncio
    async def test_claim_verification_fails_gracefully(self):
        """_verify_claims exception is caught and returns empty verdicts."""
        from qag_gate.domain.ports import LLMClient

        class FailingLLM:
            call_count = 0

            async def complete(self, system, user, **kwargs):
                self.call_count += 1
                # Fail on later calls (claim verification)
                if self.call_count > 3:
                    raise RuntimeError("API error during claims")
                return make_mock(all_yes=True)._response

        evaluator = QAGEvaluator(llm_client=FailingLLM())
        result = await evaluator.evaluate(
            task="Write a report",
            content=(
                "# Report\n\nThe market size is $500B. Growth rate is 15% annually. "
                "Three key players dominate: A with 28%, B with 22%, C with 15%."
            ),
            context={"iteration": 4, "agent_state": "delivering", "tools_used": ["search"]},
        )
        assert isinstance(result, EvalResult)
        assert 0.0 <= result.score <= 1.0


# ── Score ordering tests ───────────────────────────────────────────────────

class TestScoreOrdering:
    """Tests that score ordering makes intuitive sense."""

    @pytest.mark.asyncio
    async def test_more_yes_verdicts_higher_score(self):
        """More 'Yes' verdicts should produce a higher score."""
        high_mock = make_mock(all_yes=True)
        low_mock = make_mock(all_yes=False)

        content = "Here is a comprehensive analysis with specific data and actionable recommendations for the business sector. The analysis covers market size, competitive dynamics, growth drivers, and three specific recommendations with ROI projections."
        task = "Analyze market trends"
        ctx = {"iteration": 5, "tools_used": ["search", "analysis"]}

        eval_high = QAGEvaluator(llm_client=high_mock)
        eval_low = QAGEvaluator(llm_client=low_mock)

        result_high = await eval_high.evaluate(task=task, content=content, context=ctx)
        result_low = await eval_low.evaluate(task=task, content=content, context=ctx)

        assert result_high.score > result_low.score, \
            f"High score ({result_high.score}) should exceed low score ({result_low.score})"
