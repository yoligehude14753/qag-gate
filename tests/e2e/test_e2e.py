"""E2E 测试 — 用户视角：5 行代码拿到 EvalResult。

使用 MockLLMClient，不调用真实 API。
验证主路径、失败路径、边界场景从用户视角看起来都是对的。
"""

import pytest

from qag_gate import EvalDepth, EvalPhase, EvalResult, QAGEvaluator
from qag_gate.infrastructure import MockLLMClient


# ── Fixtures ─────────────────────────────────────────────────────────────


def _make_judge_response(n_questions: int = 6, all_yes: bool = True) -> str:
    answer = "yes" if all_yes else "no"
    answers = [
        {"q": i + 1, "answer": answer, "reason": "test"} for i in range(n_questions)
    ]
    import json

    return json.dumps({"answers": answers})


def _make_criteria_response() -> str:
    return '{"questions": ["Did the output cover all required sections?", "Was the data sourced from tools?"]}'


@pytest.fixture
def mock_llm_all_yes():
    """Mock LLM：criteria 生成 + judge 全 Yes。"""
    responses = [_make_criteria_response(), _make_judge_response(8, all_yes=True)]
    call_count = 0

    class SequentialMock:
        calls = []

        async def complete(self, system, user, **kwargs):
            nonlocal call_count
            resp = responses[min(call_count, len(responses) - 1)]
            call_count += 1
            self.calls.append({"system": system, "user": user})
            return resp

        async def complete_json(self, system, user, **kwargs):
            import json

            return json.loads(await self.complete(system, user, **kwargs))

    return SequentialMock()


@pytest.fixture
def evaluator_yes(mock_llm_all_yes):
    return QAGEvaluator(llm_client=mock_llm_all_yes)


# ── 主路径 (Happy Path) ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path_returns_eval_result(evaluator_yes):
    """主路径：5 行代码拿到 EvalResult，格式正确。"""
    result = await evaluator_yes.evaluate(
        task="分析 Q1 销售数据并生成总结报告",
        content=(
            "## Q1 销售分析\n\n"
            "根据数据显示，Q1 总销售额为 520 万元，同比增长 12%。\n"
            "各地区表现：华东区 180 万，华南区 140 万，华北区 200 万。\n"
            "主要增长驱动力来自新产品线上线（+35%）和渠道扩展（+18%）。\n"
            "重点客户复购率提升至 68%，新客获取成本下降 8%。\n"
            "建议 Q2 重点投入华南区渠道建设并强化新产品营销力度。"
        ),
        context={"iteration": 2, "tools_used": ["python_repl"], "tool_results": []},
    )

    assert isinstance(result, EvalResult)
    assert 0.0 <= result.score <= 1.0, f"score 应在 [0,1]，实际: {result.score}"
    assert result.verdicts, "verdicts 不应为空"
    assert result.phase in EvalPhase, f"phase 无效: {result.phase}"
    assert result.depth in EvalDepth, f"depth 无效: {result.depth}"


@pytest.mark.asyncio
async def test_happy_path_phase_is_executing(evaluator_yes):
    """executing 阶段推断正确（有工具调用，非 delivering）。"""
    result = await evaluator_yes.evaluate(
        task="爬取竞品数据",
        content=(
            "已通过 web_search 获取到竞品价格数据，整理如下：\n"
            "品牌A：旗舰款 ¥3999，中端款 ¥2499；品牌B：旗舰款 ¥4299，中端款 ¥2799。\n"
            "综合来看，竞品定价集中在 ¥2000-¥4500 区间，我方产品溢价空间约 8%。"
        ),
        context={
            "iteration": 1,
            "tools_used": ["web_search", "python_repl"],
            "total_tool_calls": 5,
        },
    )
    assert result.phase == EvalPhase.EXECUTING


@pytest.mark.asyncio
async def test_happy_path_delivering_forces_deep(evaluator_yes):
    """delivering 阶段强制 depth=deep。"""
    result = await evaluator_yes.evaluate(
        task="生成最终报告",
        content=(
            "# 最终分析报告\n\n"
            "## 执行摘要\n本次分析覆盖 Q1-Q2 市场数据，样本量 5,200 条。\n\n"
            "## 核心发现\n1. 整体增速 12.3%，超预期 2.1 个百分点。\n"
            "2. 华东区贡献 38% 份额，同比+5%。\n"
            "3. 新客获取成本同比下降 8%，说明渠道效率提升。\n\n"
            "## 建议\n- 加大华南区投入，补充渠道空白。\n"
            "- 优化产品定价策略，提升中端线竞争力。\n"
            "- 建立数据监控机制，实现月度复盘。"
        ),
        context={
            "iteration": 3,
            "agent_state": "delivering",
            "tools_used": ["python_repl"],
            "tool_results": [],
        },
    )
    assert result.phase == EvalPhase.DELIVERING
    assert result.depth == EvalDepth.DEEP


# ── 失败路径 (Sad Path) ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_content_returns_redline():
    """content 为空 → redline=empty_response，零 LLM 调用。"""
    mock = MockLLMClient('{"answers": []}')
    evaluator = QAGEvaluator(llm_client=mock)

    result = await evaluator.evaluate(task="任何任务", content="")

    assert "empty_response" in result.redline_violations
    assert result.score == 0.0
    assert len(mock.calls) == 0, "空 content 不应调用 LLM"


@pytest.mark.asyncio
async def test_short_content_returns_redline():
    """过短 content → redline=empty_response。"""
    mock = MockLLMClient('{"answers": []}')
    evaluator = QAGEvaluator(llm_client=mock)

    result = await evaluator.evaluate(task="分析", content="太短了")

    assert "empty_response" in result.redline_violations
    assert len(mock.calls) == 0


@pytest.mark.asyncio
async def test_llm_timeout_degrades_gracefully():
    """LLM 超时 → 降级返回 fallback verdicts，不抛异常。"""
    from qag_gate.domain.ports import LLMError

    class TimeoutMock:
        calls = []

        async def complete(self, system, user, **kwargs):
            self.calls.append("complete")
            raise LLMError("Connection timeout")

        async def complete_json(self, system, user, **kwargs):
            raise LLMError("Connection timeout")

    evaluator = QAGEvaluator(llm_client=TimeoutMock())
    result = await evaluator.evaluate(
        task="分析数据",
        content=(
            "根据历史销售数据，我们对 Q3 的预测结果如下：\n"
            "总销售额预测：580 万元，置信区间 [530, 630] 万元。\n"
            "影响因素：季节性波动、新产品上线节奏、市场促销活动安排。"
        ),
        context={"iteration": 1, "tools_used": ["python_repl"]},
    )

    # 不应抛异常，应该降级返回
    assert isinstance(result, EvalResult)
    assert result.score == 0.0  # 全 fallback → is_positive=False
    assert result.verdicts  # verdicts 存在（fallback）
    for v in result.verdicts:
        assert "parser failed" in v.reason


@pytest.mark.asyncio
async def test_deflection_detected_in_content():
    """content 包含推脱语言 → redline 包含 deflection。"""
    mock = MockLLMClient(_make_judge_response(8))
    evaluator = QAGEvaluator(llm_client=mock)

    deflection_content = (
        "我无法直接帮你完成这个任务。"
        "你可以自行运行以下代码。"
        "你可以自己运行脚本得到结果。"
        "你需要自行安装依赖环境才能运行。"
        "当前在这个对话环境中我无法执行实际代码。"
        "你运行即可得到结果。"
    ) * 3

    result = await evaluator.evaluate(
        task="运行数据分析脚本",
        content=deflection_content,
        context={"iteration": 1, "tools_used": []},
    )

    assert "deflection" in result.redline_violations


# ── 边界场景 ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_planning_phase_early_returns_fast(evaluator_yes):
    """planning 阶段 + iteration <= 2 → depth=fast，无 LLM 调用。"""
    mock = MockLLMClient(_make_judge_response(6))
    evaluator = QAGEvaluator(llm_client=mock)

    result = await evaluator.evaluate(
        task="制定竞品分析计划",
        content="我将分以下步骤完成此任务：\n1. 收集竞品数据\n2. 分析数据\n3. 生成报告",
        context={
            "iteration": 1,
            "agent_state": "planning",
            "tools_used": [],
            "total_tool_calls": 0,
        },
    )

    assert result.phase == EvalPhase.PLANNING
    assert result.depth == EvalDepth.FAST
    assert result.is_health_check is True
    assert len(mock.calls) == 0, "fast 模式不应调用 LLM"


@pytest.mark.asyncio
async def test_code_output_removes_factual_accuracy_questions(evaluator_yes):
    """code 类输出 → 替换 factual_accuracy 类问题，不问引用来源。"""
    result = await evaluator_yes.evaluate(
        task="生成 Python 数据分析脚本",
        content="```python\nimport pandas as pd\n\ndf = pd.read_csv('data.csv')\nprint(df.describe())\n```\n\n脚本已执行，输出结果如上。",
        context={
            "iteration": 2,
            "tools_used": ["python_repl"],
            "tool_results": [{"success": True, "output": "执行完成"}],
        },
    )

    categories = {v.category for v in result.verdicts}
    assert "factual_accuracy" not in categories, (
        "code 类输出不应有 factual_accuracy 问题"
    )
    assert "code_completeness" in categories or "data_quality" in categories


@pytest.mark.asyncio
async def test_missing_tool_results_no_crash(evaluator_yes):
    """context 缺失 tool_results → 正常运行，不崩溃。"""
    result = await evaluator_yes.evaluate(
        task="分析市场",
        content=(
            "市场分析显示，当前市场规模约为 500 亿元，增速为 15%。\n"
            "细分市场中，线上渠道占比 62%，线下占比 38%。\n"
            "主要参与者：品牌A 市占率 28%，品牌B 22%，其余为分散长尾。\n"
            "增长机会集中在下沉市场和海外扩张两大方向。"
        ),
        context={"iteration": 1},  # 故意省略 tool_results
    )

    assert isinstance(result, EvalResult)
    assert 0.0 <= result.score <= 1.0
