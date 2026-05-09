"""DepthSelector — 根据 phase + iteration + slope + tool_results 选择评估深度。

fast     → 仅硬规则检查（planning 早期 / 健康检查）
standard → baseline + dynamic 问题，1 次 LLM 调用（executing 主路径）
deep     → standard + claim 验证（delivering 阶段强制）

规则优先级（从高到低）：
  1. delivering 阶段 → 强制 deep
  2. planning 且 iteration ≤ 2 → fast
  3. 有 slope_tracker 且斜率上升 → standard（无需 deep 验证）
  4. 大量工具调用（>10）→ standard（执行中，不是交付时机）
  5. 其他 → standard
"""

from __future__ import annotations

from typing import Any, List, Optional

from qag_gate.domain.models import EvalDepth, EvalPhase


def select_depth(
    phase: EvalPhase,
    iteration: int,
    slope_tracker: Optional[Any],
    tool_results: Optional[List[Any]],
) -> EvalDepth:
    """순수 함수: 컨텍스트 → EvalDepth."""
    if phase == EvalPhase.DELIVERING:
        return EvalDepth.DEEP

    if phase == EvalPhase.PLANNING and iteration <= 2:
        return EvalDepth.FAST

    # slope 上升中 → standard 足够
    if slope_tracker is not None:
        try:
            slope = getattr(slope_tracker, "_compute_slope", lambda: 0.0)()
            if slope > 0.03:
                return EvalDepth.STANDARD
        except Exception:
            pass

    # 执行过程中工具调用很多，暂不需要深度验证
    n_tool_results = len(tool_results or [])
    if n_tool_results > 10 and phase == EvalPhase.EXECUTING:
        return EvalDepth.STANDARD

    return EvalDepth.STANDARD
