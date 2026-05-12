"""QAGEvaluator — 主入口，编排三层评估流程。

调用顺序（垂直切片）：
  1. 内容空检测 → 直接返回 redline=["empty_response"]
  2. RedLineChecker（同步，无 LLM）
  3. PhaseDetector + DepthSelector（同步）
  4. depth=fast → 直接返回 health_check 结果
  5. 组装问题列表（Layer 1 baseline + Layer 2 dynamic + Layer 3 output-type override）
  6. BinaryJudge（LLM 批量评判）
  7. depth=deep → ClaimExtractor + WebVerifier（可选）
  8. ScoreAggregator → EvalResult
"""

from __future__ import annotations

from typing import Dict, List, Optional

from loguru import logger

from qag_gate.checkers.binary_judge import BinaryJudge
from qag_gate.checkers.criteria_generator import CriteriaGenerator
from qag_gate.checkers.depth_selector import select_depth
from qag_gate.checkers.phase_detector import detect_phase
from qag_gate.checkers.questions import (
    BASELINE_QUESTIONS,
    BASELINE_WEIGHTS,
    CODE_FILE_OVERRIDE_QUESTIONS,
    STRUCTURAL_COMPLETENESS_QUESTIONS,
    detect_output_type,
)
from qag_gate.checkers.redline import RedLineChecker
from qag_gate.checkers.score_aggregator import aggregate_scores
from qag_gate.domain.models import (
    EvalDepth,
    EvalQuestion,
    EvalResult,
    Verdict,
)
from qag_gate.domain.ports import LLMClient


class QAGEvaluator:
    """5 行代码即可使用的主入口。

    示例::

        from qag_gate import QAGEvaluator
        from qag_gate.infrastructure import OpenAIAdapter

        evaluator = QAGEvaluator(llm_client=OpenAIAdapter(model="gpt-4o-mini"))
        result = await evaluator.evaluate(
            task="分析 Q1 销售数据并生成 PPT",
            content="...（agent 输出）...",
            context={"iteration": 2, "tools_used": ["python_repl"], "tool_results": []},
        )
        print(result.score, result.phase, result.depth)
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._redline = RedLineChecker()
        self._judge = BinaryJudge(llm_client)
        self._criteria_gen = CriteriaGenerator(llm_client)

    async def evaluate(
        self,
        task: str,
        content: str,
        context: Optional[Dict] = None,
    ) -> EvalResult:
        """统一评估入口。

        Args:
            task: 用户原始任务描述。
            content: agent 当前输出（待评估的文本）。
            context: 可选上下文：
                - iteration (int): 当前迭代次数
                - agent_state (str): "planning"|"executing"|"delivering" 等
                - tools_used (List[str]): 本轮使用的工具名列表
                - total_tool_calls (int): 累计工具调用次数
                - tool_results (List[dict]): 工具调用结果列表
                - slope_tracker: OptimizationSlopeTracker 实例（可选）
                - weight_overrides (Dict[str, float]): 覆盖分类权重
                - _skip_dynamic (bool): 为 True 时不调用动态问题生成（消融实验）
                - _force_depth (str): 强制 EvalDepth，如 "standard"（消融实验）

        Returns:
            EvalResult: 包含 score, verdicts, phase, depth, redline_violations 等。
        """
        ctx = context or {}

        # 1. 内容空检测（最早退出，零 LLM 调用）
        if not content or len(content.strip()) < 10:
            logger.info("[QAG-Gate] content 为空，直接返回 redline=empty_response")
            return EvalResult(
                score=0.0,
                redline_violations=["empty_response"],
                is_health_check=True,
            )

        # 2. RedLine 检查（同步，纯规则）— 任何违规立即返回 score=0.0（硬门控）
        redline_result = self._redline.check(content, ctx)
        if redline_result.violations:
            logger.info(
                f"[QAG-Gate] redline hard-gate: violations={redline_result.violations}, score=0.0"
            )
            return EvalResult(
                score=0.0,
                redline_violations=redline_result.violations,
                is_health_check=True,
            )

        # 3. Phase + Depth 推断
        phase = detect_phase(
            iteration=ctx.get("iteration", 0),
            agent_state=ctx.get("agent_state"),
            tools_used=ctx.get("tools_used", []),
            total_tool_calls=ctx.get("total_tool_calls", 0),
        )
        depth = select_depth(
            phase=phase,
            iteration=ctx.get("iteration", 0),
            slope_tracker=ctx.get("slope_tracker"),
            tool_results=ctx.get("tool_results", []),
        )
        # 基准消融：强制某深度（不改 phase 推断逻辑）
        fd = ctx.get("_force_depth")
        if fd:
            try:
                depth = EvalDepth(str(fd).strip().lower())
            except ValueError:
                logger.warning(f"[QAG-Gate] 未知 _force_depth={fd!r}，忽略")

        # 4. fast 模式（仅健康检查，无 LLM）
        if depth == EvalDepth.FAST:
            logger.info(
                f"[QAG-Gate] fast 模式: phase={phase}, redline={redline_result.violations}"
            )
            return EvalResult(
                score=0.0,
                phase=phase,
                depth=depth,
                redline_violations=redline_result.violations,
                is_health_check=True,
            )

        # 5. 组装问题列表（三层架构）
        questions: List[EvalQuestion] = list(BASELINE_QUESTIONS)

        # 文件/研究类任务附加结构完整性问题
        has_files = "/files/" in content or "/static/images/" in content
        is_research = any(
            kw in task.lower()
            for kw in ("论文", "paper", "研究", "research", "分析", "analysis")
        )
        if has_files or is_research:
            questions.extend(STRUCTURAL_COMPLETENESS_QUESTIONS)

        # Layer 2: LLM 动态生成任务特定问题（消融可跳过）
        dynamic_qs: List[EvalQuestion] = []
        if not ctx.get("_skip_dynamic"):
            dynamic_qs = await self._criteria_gen.generate(task, phase, depth, ctx)
        questions.extend(dynamic_qs)

        # Layer 3: output-type override（code/file 类任务替换 factual_accuracy）
        output_type = detect_output_type(ctx.get("tool_results", []), content)
        if output_type.startswith("file:") or output_type == "code":
            questions = [q for q in questions if q.category != "factual_accuracy"]
            questions.extend(CODE_FILE_OVERRIDE_QUESTIONS)

        # 6. BinaryJudge（批量 LLM 评判，失败时降级）
        verdicts = await self._judge.judge(questions, content, task, context=ctx)

        # 7. deep 模式：claim 验证（可选，output_type 为 text 才有意义）
        extra_verdicts: List[Verdict] = []
        if depth == EvalDepth.DEEP and output_type == "text":
            extra_verdicts = await self._verify_claims(content, ctx)
        verdicts.extend(extra_verdicts)

        # 8. 分数聚合（三层权重合并）
        cat_weights = dict(BASELINE_WEIGHTS)
        for q in dynamic_qs:
            cat = q.category
            cat_weights[cat] = max(cat_weights.get(cat, 0.0), q.weight)

        wo = ctx.get("weight_overrides") or {}
        total, cat_scores, failed = aggregate_scores(
            verdicts, cat_weights, weight_overrides=wo
        )

        logger.info(
            f"[QAG-Gate] phase={phase.value} depth={depth.value} "
            f"score={total:.3f} verdicts={len(verdicts)} failed={len(failed)} "
            f"redline={redline_result.violations}"
        )

        return EvalResult(
            score=round(total, 4),
            verdicts=verdicts,
            failed_verdicts=failed,
            phase=phase,
            depth=depth,
            redline_violations=redline_result.violations,
            category_scores=cat_scores,
            metadata={
                "output_type": output_type,
                "dynamic_questions": len(dynamic_qs),
                "baseline_questions": len(BASELINE_QUESTIONS),
            },
        )

    async def _verify_claims(self, content: str, context: Dict) -> List[Verdict]:
        """deep 模式下的 claim 事实验证（LLM 单条验证）。失败时返回 []。"""
        try:
            # 提取关键事实声明
            extract_system = "You extract factual claims from text. Output only JSON."
            extract_prompt = (
                "Extract the top 5 most important factual claims from this text. "
                "A factual claim can be verified as true or false.\n\n"
                f"Text:\n{content[:6000]}\n\n"
                '{"claims": ["claim1", "claim2", ...]}'
            )
            raw = await self._judge._llm.complete(
                extract_system, extract_prompt, max_tokens=500, timeout=20.0
            )
            import json
            import re

            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if not m:
                return []
            data = json.loads(m.group())
            claims = data.get("claims", [])[:5]

            verdicts: List[Verdict] = []
            for claim in claims[:3]:
                verify_prompt = (
                    f"Is this factual claim likely correct based on your knowledge?\n"
                    f'Claim: "{claim}"\n\n'
                    '{"correct": true/false, "reason": "brief explanation"}'
                )
                raw_v = await self._judge._llm.complete(
                    "You are a fact-checker. Output only JSON.",
                    verify_prompt,
                    max_tokens=150,
                    timeout=15.0,
                )
                m2 = re.search(r"\{.*\}", raw_v, re.DOTALL)
                if not m2:
                    continue
                d = json.loads(m2.group())
                is_correct = bool(d.get("correct", False))
                verdicts.append(
                    Verdict(
                        question=f"Is this claim correct: '{claim[:80]}'?",
                        category="factual_accuracy",
                        answer=is_correct,
                        is_positive=is_correct,
                        score_value=1.0 if is_correct else 0.0,
                        reason=d.get("reason", ""),
                        weight=1.5,
                    )
                )
            return verdicts
        except Exception as e:
            logger.debug(f"[QAG-Gate] claim 验证跳过: {e}")
            return []
