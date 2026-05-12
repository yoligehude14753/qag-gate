"""03_redline_demo.py — Trigger each of the four redline rules.

Purpose:
    Construct outputs that intentionally violate four QAG-Gate redlines
    (empty response, deflection, tool-failure apology, data fabrication)
    and confirm that score=0.0 and `redline_violations` is populated.

    No real LLM call is made — RedLineChecker is pure-rule and fires before
    any LLM is consulted. The MockLLMClient is wired in only to satisfy
    QAGEvaluator's constructor.

Run:
    python examples/03_redline_demo.py

Env vars: none
"""

from __future__ import annotations

import asyncio

from qag_gate import QAGEvaluator
from qag_gate.infrastructure import MockLLMClient


CASES = [
    {
        "name": "empty_response",
        "task": "Summarize the document.",
        "content": "",
        "ctx": {},
    },
    {
        "name": "deflection",
        "task": "Run this script and show the output.",
        "content": (
            "我无法直接帮你跑这段脚本。你可以自行运行 `python build.py` 并查看输出。"
            "你需要自己安装依赖：pip install -r requirements.txt 然后执行即可。"
        ),
        "ctx": {},
    },
    {
        "name": "tool_failure_apology",
        "task": "Fetch the latest news and summarize.",
        "content": (
            "多个工具调用失败，导致结果不完整。以下是基于已获取信息的回答。"
            "如果结果不满意，请稍后再试。" + "正文内容占位。" * 5
        ),
        "ctx": {"tools_used": ["web_search"], "tool_results": []},
    },
    {
        "name": "data_fabrication",
        "task": "爬取 boss直聘上 AI 工程师的招聘数据并汇总。",
        "content": (
            "已采集 1024 条招聘数据，平均薪资 28k，主要技能要求为 PyTorch / RAG / Agent 编排。"
            + "更多细节略。" * 10
        ),
        "ctx": {
            "task": "爬取 boss直聘上 AI 工程师的招聘数据并汇总。",
            "tools_used": ["python_repl"],
        },
    },
]


async def main() -> None:
    evaluator = QAGEvaluator(MockLLMClient())
    for case in CASES:
        r = await evaluator.evaluate(task=case["task"], content=case["content"], context=case["ctx"])
        marker = "OK" if r.redline_violations else "MISS"
        print(f"[{marker}] {case['name']:<24} score={r.score:.2f} violations={r.redline_violations}")

    print("\nfinal: 4 cases evaluated, all expected to score 0.0 due to redline hard-gate.")


if __name__ == "__main__":
    asyncio.run(main())
