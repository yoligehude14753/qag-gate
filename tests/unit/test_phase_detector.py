"""单元测试 — PhaseDetector 纯函数。"""

from qag_gate.checkers.phase_detector import detect_phase
from qag_gate.domain.models import EvalPhase


def test_delivering_state_returns_delivering():
    assert detect_phase(3, "delivering", [], 10) == EvalPhase.DELIVERING
    assert detect_phase(3, "reporting", [], 10) == EvalPhase.DELIVERING
    assert detect_phase(3, "done", [], 10) == EvalPhase.DELIVERING


def test_planning_state_early_returns_planning():
    assert detect_phase(1, "planning", [], 0) == EvalPhase.PLANNING
    assert detect_phase(0, None, [], 0) == EvalPhase.PLANNING


def test_executing_with_tools_returns_executing():
    assert (
        detect_phase(2, None, ["python_repl", "web_search"], 5) == EvalPhase.EXECUTING
    )


def test_delivering_overrides_all():
    """delivering 状态优先级最高。"""
    assert detect_phase(0, "delivering", [], 0) == EvalPhase.DELIVERING


def test_early_iteration_no_tools_is_planning():
    assert detect_phase(1, None, [], 1) == EvalPhase.PLANNING


def test_late_iteration_no_state_is_executing():
    assert detect_phase(5, None, ["python_repl"], 8) == EvalPhase.EXECUTING
