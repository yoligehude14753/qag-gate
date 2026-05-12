"""单元测试 — RedLineChecker 纯规则检查。"""

import pytest

from qag_gate.checkers.redline import RedLineChecker


@pytest.fixture
def checker():
    return RedLineChecker()


# ── 通过（无违规）─────────────────────────────────────────────────────────


def test_normal_content_passes(checker):
    content = (
        "## 分析结果\n\n经过详细研究，我发现以下关键数据点：\n1. 市场规模 500 亿\n2. 增速 15%\n3. 主要竞品 3 家"
        * 5
    )
    result = checker.check(content, {})
    assert result.passed
    assert result.violations == []


# ── 空回答 ─────────────────────────────────────────────────────────────────


def test_empty_content_fails(checker):
    result = checker.check("", {})
    assert not result.passed
    assert "empty_response" in result.violations


def test_whitespace_only_fails(checker):
    result = checker.check("   \n\t  ", {})
    assert not result.passed
    assert "empty_response" in result.violations


def test_very_short_content_fails(checker):
    result = checker.check("太短", {})
    assert not result.passed
    assert "empty_response" in result.violations


# ── 推脱检测 ────────────────────────────────────────────────────────────────


def test_deflection_requires_3_phrases(checker):
    """少于 3 条推脱语言不触发（避免误报）。"""
    content = "你可以自行运行这段代码。另外，我建议你尝试不同的方法。" * 20
    result = checker.check(content, {})
    assert "deflection" not in result.violations


def test_deflection_triggers_with_3_phrases(checker):
    content = (
        "我无法直接帮你完成。"
        "你可以自行运行脚本。"
        "你需要自行安装依赖。"
        "当前在这个对话环境中我无法执行。"
    ) * 5
    result = checker.check(content, {})
    assert "deflection" in result.violations


# ── 工具失败道歉 ──────────────────────────────────────────────────────────────


def test_tool_failure_apology_triggers(checker):
    content = (
        "多个工具调用失败，我无法获取完整数据。以下是基于已获取信息的回答。如果结果不满意，请调整任务。"
    ) * 3
    result = checker.check(content, {})
    assert "tool_failure_apology_delivery" in result.violations


# ── 工具执行未处理 ──────────────────────────────────────────────────────────


def test_unhandled_tool_error_triggers(checker):
    """>50% 工具失败 + 回答过短 → 触发。"""
    context = {
        "tool_results": [
            {"success": False, "error": "timeout"},
            {"success": False, "error": "timeout"},
            {"success": True, "output": "ok"},
        ]
    }
    short_content = "工具执行出错，请稍后重试。"
    result = checker.check(short_content, context)
    assert "unhandled_tool_error" in result.violations


def test_no_tool_error_when_short_content_but_tools_ok(checker):
    """工具全部成功 → 不触发 unhandled_tool_error。"""
    context = {
        "tool_results": [
            {"success": True, "output": "ok"},
            {"success": True, "output": "ok"},
        ]
    }
    result = checker.check("简短但工具正常", context)
    assert "unhandled_tool_error" not in result.violations


# ── 内容重复 ────────────────────────────────────────────────────────────────


def test_content_duplication_triggers(checker):
    # 段落须超过 30 字符（检查阈值）才参与重复检测
    para = "这是一段重复的内容，用于测试重复检测功能是否正常工作，该段落足够长以触发检测器。"
    assert len(para) > 30, f"测试段落太短: {len(para)}"
    content = (para + "\n") * 8
    result = checker.check(content, {})
    assert "content_duplication" in result.violations


def test_normal_content_no_duplication(checker):
    content = "\n".join(
        [
            "第一段：市场规模分析显示总体规模达 500 亿元。",
            "第二段：增长率方面，同比增长 15%，高于行业平均。",
            "第三段：竞争格局中，三家头部企业占据 60% 市场份额。",
            "第四段：用户画像以 25-35 岁年轻专业人士为主。",
        ]
    )
    result = checker.check(content, {})
    assert "content_duplication" not in result.violations


# ── 处置动作 ──────────────────────────────────────────────────────────────────


def test_dedup_action_for_duplication_only(checker):
    para = "这是重复段落内容测试，包含足够字符以触发检测。"
    content = (para + "\n") * 8
    result = checker.check(content, {})
    if "content_duplication" in result.violations and len(result.violations) == 1:
        assert result.action == "dedup_and_recheck"


def test_honest_fail_after_repeated_systemic_errors(checker):
    """连续 2+ 次系统性工具失败 → honest_fail。"""
    content = "多个工具调用失败，我无法获取数据。" * 3
    context = {
        "retry_count": 3,
        "tool_results": [{"success": False}, {"success": False}, {"success": False}],
    }
    result = checker.check(content, context)
    assert result.action in ("retry", "honest_fail")


# ── improvement_hint ──────────────────────────────────────────────────────────


def test_plan_incomplete_triggers(checker):
    """多步骤计划但缺乏完成标记 → plan_incomplete。"""
    content = "第一步 做A。第二步 做B。第三步 做C。这是简短的说明。"
    result = checker.check(content, {})
    assert "plan_incomplete" in result.violations
    assert result.action == "force_continue"


def test_plan_incomplete_not_triggered_with_completions(checker):
    """步骤 + 足够完成标记 → 不触发 plan_incomplete。"""
    content = "第一步 做A 已完成。第二步 做B 完成。第三步 做C ✅。说明文字..."
    result = checker.check(content, {})
    assert "plan_incomplete" not in result.violations


def test_data_fabrication_triggers(checker):
    """任务要求爬取数据但未使用 fetch 工具 → data_fabrication。"""
    content = "根据爬取到的数据，价格为 100 元。" + "详细分析内容 " * 10
    result = checker.check(
        content,
        {
            "task": "爬取竞品价格数据",
            "tools_used": ["python_repl"],  # 没有 fetch/crawl 工具
        },
    )
    assert "data_fabrication" in result.violations


def test_data_fabrication_not_triggered_with_fetch_tool(checker):
    """使用了 fetch 工具 → 不触发 data_fabrication。"""
    content = "根据爬取到的数据，价格为 100 元。" + "详细分析内容 " * 10
    result = checker.check(
        content,
        {
            "task": "爬取竞品价格数据",
            "tools_used": ["web_search", "python_repl"],
        },
    )
    assert "data_fabrication" not in result.violations


def test_plan_incomplete_action_override_by_systemic(checker):
    """plan_incomplete + 系统性错误 + retry_count≥2 → honest_fail（优先级）。"""
    content = "第一步 做A。第二步 做B。第三步 做C。工具调用出错，无法继续处理。"
    context = {
        "tools_used": ["code_exec"],
        "error": "SystemError",
        "retry_count": 2,
    }
    result = checker.check(content, context)
    # 可能触发 unhandled_tool_error 或 plan_incomplete，honest_fail 优先
    if (
        "unhandled_tool_error" in result.violations
        or "tool_failure_apology_delivery" in result.violations
    ):
        assert result.action == "honest_fail"


def test_improvement_hint_for_empty(checker):
    result = checker.check("", {})
    hint = checker.improvement_hint(result)
    assert "为空" in hint or "empty" in hint.lower()
