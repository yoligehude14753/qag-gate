"""单元测试 — DepthSelector 纯函数，所有分支覆盖。"""

import pytest

from qag_gate.checkers.depth_selector import select_depth
from qag_gate.domain.models import EvalDepth, EvalPhase


# ── Rule 1: delivering → DEEP ────────────────────────────────────────────────

def test_delivering_phase_returns_deep():
    result = select_depth(EvalPhase.DELIVERING, iteration=5, slope_tracker=None, tool_results=None)
    assert result == EvalDepth.DEEP


def test_delivering_ignores_iteration():
    assert select_depth(EvalPhase.DELIVERING, iteration=0, slope_tracker=None, tool_results=[]) == EvalDepth.DEEP


# ── Rule 2: planning early → FAST ────────────────────────────────────────────

def test_planning_early_returns_fast():
    result = select_depth(EvalPhase.PLANNING, iteration=0, slope_tracker=None, tool_results=None)
    assert result == EvalDepth.FAST


def test_planning_iteration_2_is_fast():
    assert select_depth(EvalPhase.PLANNING, iteration=2, slope_tracker=None, tool_results=None) == EvalDepth.FAST


def test_planning_iteration_3_is_standard():
    assert select_depth(EvalPhase.PLANNING, iteration=3, slope_tracker=None, tool_results=None) == EvalDepth.STANDARD


# ── Rule 3: slope tracker rising → STANDARD ──────────────────────────────────

class _MockSlope:
    def __init__(self, slope_val: float):
        self._slope_val = slope_val

    def _compute_slope(self) -> float:
        return self._slope_val


def test_slope_tracker_rising_returns_standard():
    tracker = _MockSlope(0.05)  # > 0.03
    result = select_depth(EvalPhase.EXECUTING, iteration=5, slope_tracker=tracker, tool_results=None)
    assert result == EvalDepth.STANDARD


def test_slope_tracker_flat_falls_through():
    tracker = _MockSlope(0.01)  # ≤ 0.03
    result = select_depth(EvalPhase.EXECUTING, iteration=5, slope_tracker=tracker, tool_results=None)
    assert result == EvalDepth.STANDARD


def test_slope_tracker_raises_exception_is_swallowed():
    class _BrokenSlope:
        def _compute_slope(self):
            raise RuntimeError("broken")

    result = select_depth(EvalPhase.EXECUTING, iteration=5, slope_tracker=_BrokenSlope(), tool_results=None)
    assert result == EvalDepth.STANDARD


# ── Rule 4: many tool results → STANDARD ─────────────────────────────────────

def test_many_tool_results_executing_returns_standard():
    tool_results = [{}] * 11  # > 10
    result = select_depth(EvalPhase.EXECUTING, iteration=5, slope_tracker=None, tool_results=tool_results)
    assert result == EvalDepth.STANDARD


def test_many_tools_not_executing_falls_through():
    tool_results = [{}] * 11
    result = select_depth(EvalPhase.PLANNING, iteration=5, slope_tracker=None, tool_results=tool_results)
    # planning phase with iteration=5 doesn't hit FAST rule, falls through to STANDARD
    assert result == EvalDepth.STANDARD


# ── Default ───────────────────────────────────────────────────────────────────

def test_default_returns_standard():
    result = select_depth(EvalPhase.EXECUTING, iteration=5, slope_tracker=None, tool_results=None)
    assert result == EvalDepth.STANDARD
