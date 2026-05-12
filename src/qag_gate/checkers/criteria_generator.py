"""CriteriaGenerator — LLM 动态生成任务特定的评估问题（Layer 2）。

失败时返回空列表（BinaryJudge 继续用 baseline questions 作为 fallback）。
"""

from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

from loguru import logger

from qag_gate.domain.models import EvalDepth, EvalPhase, EvalQuestion
from qag_gate.domain.ports import LLMClient, LLMError

_GEN_SYSTEM = (
    "You generate binary evaluation questions for AI outputs. Output only JSON."
)

_GEN_PROMPT = (
    "Based on the following task description, generate 3-5 binary (Yes/No) evaluation questions "
    "that determine if an AI assistant's response successfully completed this specific task.\n\n"
    "Rules:\n"
    "- Each question must be answerable with only Yes or No\n"
    "- Questions must be specific to THIS task, not generic quality questions\n"
    "- Focus on: did it produce the right thing? did it cover what was asked?\n"
    "- Do NOT ask gradient questions like 'Is the quality above 90%?'\n\n"
    "Task: {task}\n"
    "Phase: {phase}\n\n"
    'Output JSON: {{"questions": ["question1", "question2", ...]}}'
)


class CriteriaGenerator:
    """生成任务特定的动态评估问题。"""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    async def generate(
        self,
        task: str,
        phase: EvalPhase,
        depth: EvalDepth,
        context: Optional[Dict] = None,
    ) -> List[EvalQuestion]:
        if depth == EvalDepth.FAST:
            return []

        prompt = _GEN_PROMPT.format(task=task[:800], phase=phase.value)
        try:
            raw = await self._llm.complete(
                _GEN_SYSTEM, prompt, max_tokens=400, timeout=20.0
            )
            data = self._parse_json(raw)
            raw_qs = data.get("questions", [])
            if not raw_qs:
                for v in data.values():
                    if isinstance(v, list) and v and isinstance(v[0], str):
                        raw_qs = v
                        break

            return [
                EvalQuestion(text=q, category="dynamic", weight=1.0)
                for q in raw_qs[:5]
                if isinstance(q, str) and len(q) > 10
            ]
        except LLMError as e:
            logger.warning(f"[CriteriaGenerator] LLM 调用失败: {e}")
            return []
        except Exception as e:
            logger.warning(f"[CriteriaGenerator] 异常: {e}")
            return []

    @staticmethod
    def _parse_json(raw: str) -> dict:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            raise LLMError(f"无法解析 JSON: {raw[:200]}")
        return json.loads(m.group())
