"""RedLineChecker — 纯规则的硬性门控，无 LLM 依赖。

触发任意一条红线即返回失败，不参与评分。
六类红线：空回答、推脱、工具失败道歉、数据伪造、内容重复、计划未完成。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class RedLineResult:
    passed: bool
    violations: List[str]
    action: str = "continue"
    # action: continue | retry | force_continue | dedup_and_recheck | honest_fail


_DEFLECTION_PHRASES = [
    "我无法直接",
    "我无法替你",
    "我无法为你",
    "你可以自行运行",
    "你可以自己运行",
    "你可以在本机运行",
    "你需要自行",
    "你需要自己",
    "当前在这个对话环境中我无法",
    "你运行即可",
    "你跑即可",
    "你执行即可",
]

_TOOL_FAILURE_APOLOGY_PHRASES = [
    "多个工具调用失败",
    "工具调用失败，导致结果",
    "工具调用均失败",
    "由于工具执行失败",
    "执行过程中出现多次错误",
    "多次工具调用均未成功",
    "由于多次执行失败",
    "以下是基于已获取信息的回答。如果结果不满意",
]

_FETCH_TOOLS = frozenset(
    {
        "notte_browse",
        "web_crawler",
        "web_fetch",
        "web_search",
        "playwright",
        "stock_data",
        "paper_search",
    }
)

_DATA_ACQ_PATTERNS = ["爬取", "抓取", "采集", "直聘", "zhipin", "linkedin", "boss直聘"]


class RedLineChecker:
    """纯规则硬性门控。同步，无网络调用。"""

    def check(self, content: str, context: Dict) -> RedLineResult:
        violations: List[str] = []

        # 1. 空回答
        if not content or len(content.strip()) < 10:
            violations.append("empty_response")

        if not content:
            return RedLineResult(passed=False, violations=violations, action="retry")

        content_lower = content.lower()

        # 2. 推脱（≥3 条触发，避免误报）
        deflect_count = sum(1 for p in _DEFLECTION_PHRASES if p in content_lower)
        if deflect_count >= 3:
            violations.append("deflection")

        # 3a. 工具失败道歉式交付
        if any(p in content for p in _TOOL_FAILURE_APOLOGY_PHRASES):
            violations.append("tool_failure_apology_delivery")

        # 3b. 多数工具调用失败（>50%）且回答过短
        tool_results = context.get("tool_results", [])
        if tool_results:
            failed = [
                r
                for r in tool_results
                if isinstance(r, dict) and not r.get("success", True)
            ]
            fail_rate = len(failed) / len(tool_results)
            if fail_rate > 0.5 and len(content.strip()) < 500:
                violations.append("unhandled_tool_error")

        # 4. 段落重复
        paragraphs = [p.strip() for p in content.split("\n") if len(p.strip()) > 30]
        if len(paragraphs) >= 4:
            seen: Dict[str, bool] = {}
            dup_count = 0
            for para in paragraphs:
                fp = para[:50].lower()
                if fp in seen:
                    dup_count += 1
                else:
                    seen[fp] = True
            if dup_count >= 3:
                violations.append("content_duplication")

        # 5. 计划未完成（短回答 + 多步骤 + 完成标记不足）
        if len(content.strip()) < 500:
            plan_steps = re.findall(
                r"(?:第[一二三四五六七八九十\d]+步|步骤\s*\d+|Step\s*\d+)", content
            )
            if plan_steps:
                done_markers = re.findall(
                    r"(?:已完成|完成|✅|done|completed)", content_lower
                )
                if len(plan_steps) >= 3 and len(done_markers) < len(plan_steps) * 0.3:
                    violations.append("plan_incomplete")

        # 6. 数据伪造（声称爬取但未使用任何 fetch 工具）
        tools_used = context.get("tools_used", [])
        task_text = context.get("task", "")
        if any(p in task_text.lower() for p in _DATA_ACQ_PATTERNS):
            if tools_used and not _FETCH_TOOLS.intersection(set(tools_used)):
                violations.append("data_fabrication")

        if not violations:
            return RedLineResult(passed=True, violations=[], action="continue")

        # 决定处置动作
        retry_count = context.get("retry_count", 0)
        systemic = {"tool_failure_apology_delivery", "unhandled_tool_error"}
        has_systemic = bool(systemic.intersection(set(violations)))

        if "content_duplication" in violations and len(violations) == 1:
            action = "dedup_and_recheck"
        elif "plan_incomplete" in violations and len(violations) == 1:
            action = "force_continue"
        elif has_systemic and retry_count >= 2:
            action = "honest_fail"
        else:
            action = "retry"

        return RedLineResult(passed=False, violations=violations, action=action)

    def improvement_hint(self, result: RedLineResult) -> str:
        prompts = {
            "empty_response": "你的回答为空！请提供实质性内容。",
            "deflection": "禁止推脱！删除所有'你可以自行运行'类的内容，用工具实际执行并输出结果。",
            "unhandled_tool_error": "工具执行出错了但你没有处理！请修复错误或换一种方法重试。",
            "content_duplication": "输出有大段重复！重新组织回答，每段内容只出现一次。",
            "plan_incomplete": "你声明了多个步骤但没全部完成！继续执行未完成的步骤。",
            "data_fabrication": (
                "你声称获取了外部数据，但实际上没有使用任何数据抓取工具。"
                "必须先用 web_fetch/web_search/notte_browse 获取真实数据，禁止凭空编造。"
            ),
        }
        parts = [prompts.get(v, f"问题: {v}") for v in result.violations]
        return "【红线问题】" + " ".join(parts)
