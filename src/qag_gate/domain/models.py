"""qag-gate 领域模型 — 纯数据类，无外部依赖。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class EvalPhase(str, Enum):
    PLANNING = "planning"
    EXECUTING = "executing"
    DELIVERING = "delivering"


class EvalDepth(str, Enum):
    FAST = "fast"       # 仅硬规则检查，无 LLM 调用
    STANDARD = "standard"  # baseline + dynamic 问题，1 次 LLM 调用
    DEEP = "deep"       # standard + claim 验证，2-4 次 LLM 调用


@dataclass
class EvalQuestion:
    """单条二元评估问题。"""
    text: str
    category: str
    weight: float = 1.0
    positive_answer: bool = True   # True 表示 Yes 为好
    section_target: Optional[str] = None


@dataclass
class Verdict:
    """单条问题的二元判决结果。"""
    question: str
    category: str
    answer: bool               # 模型回答（Yes=True / No=False）
    is_positive: bool          # 考虑 positive_answer 后是否为正面
    score_value: float         # 0.0 / 0.5 / 1.0
    reason: str = ""
    section: str = ""
    weight: float = 1.0


@dataclass
class RedLineViolation:
    """单条红线违规。"""
    type: str     # empty_response | deflection | tool_failure_apology | ...
    detail: str = ""
    severity: int = 1  # 1=soft 2=hard


@dataclass
class EvalResult:
    """QAGEvaluator 标准化输出。下游（SlopeNav 等）消费此结构。"""
    score: float                              # [0, 1]
    verdicts: List[Verdict] = field(default_factory=list)
    failed_verdicts: List[Verdict] = field(default_factory=list)
    phase: EvalPhase = EvalPhase.EXECUTING
    depth: EvalDepth = EvalDepth.STANDARD
    redline_violations: List[str] = field(default_factory=list)   # 违规类型列表
    hard_failures: List[Dict[str, Any]] = field(default_factory=list)
    category_scores: Dict[str, float] = field(default_factory=dict)
    is_health_check: bool = False              # fast 模式健康检查结果
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def passed_redline(self) -> bool:
        return len(self.redline_violations) == 0

    @property
    def verdict_dict_list(self) -> List[Dict[str, Any]]:
        """兼容 SlopeNav 的序列化格式。"""
        return [
            {
                "question": v.question,
                "category": v.category,
                "answer": v.answer,
                "is_positive": v.is_positive,
                "score_value": v.score_value,
                "reason": v.reason,
                "weight": v.weight,
            }
            for v in self.verdicts
        ]
