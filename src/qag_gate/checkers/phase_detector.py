"""PhaseDetector — 根据上下文推断当前 agent 所在阶段。

三个阶段：
  planning   — 还在分解任务、制定方案，尚未产出实质内容
  executing  — 正在调用工具、生成中间结果
  delivering — 工具已全部完成，准备最终输出

规则：
  1. agent_state 显式为 "reporting"/"delivering" → delivering
  2. iteration <= 1 且 tool_calls 极少 → planning
  3. 其余 → executing（默认）
"""

from __future__ import annotations

from typing import List, Optional

from qag_gate.domain.models import EvalPhase

_DELIVERING_STATES = frozenset({"reporting", "delivering", "done", "complete"})
_PLANNING_STATES = frozenset({"planning", "thinking", "init"})

_EXEC_TOOLS = frozenset(
    {
        "python_repl",
        "web_search",
        "web_fetch",
        "notte_browse",
        "write_file",
        "read_file",
        "bash",
        "code_exec",
        "pptx_generator",
        "docx_generator",
        "xlsx_generator",
    }
)


def detect_phase(
    iteration: int,
    agent_state: Optional[str],
    tools_used: List[str],
    total_tool_calls: int,
) -> EvalPhase:
    """순수 함수: 컨텍스트 → EvalPhase."""
    state = (agent_state or "").lower()

    if state in _DELIVERING_STATES:
        return EvalPhase.DELIVERING

    if state in _PLANNING_STATES:
        return EvalPhase.PLANNING

    exec_tools_used = _EXEC_TOOLS.intersection(set(tools_used or []))
    if iteration <= 1 and total_tool_calls <= 2 and not exec_tools_used:
        return EvalPhase.PLANNING

    return EvalPhase.EXECUTING
