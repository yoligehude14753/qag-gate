"""BinaryJudge — 批量 LLM 评判，返回 Yes/Partial/No 判决列表。

单次调用处理所有问题（最小化 LLM 调用次数）。
LLM 失败时降级为全 False fallback，不抛异常。
"""

from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

from loguru import logger

from qag_gate.domain.models import EvalQuestion, Verdict
from qag_gate.domain.ports import LLMClient, LLMError

_JUDGE_SYSTEM = (
    "You are a precise, objective quality evaluator. "
    "You will receive a list of questions about an AI assistant's response. "
    "For each question, answer one of: Yes, Partial, or No, plus a brief reason (1 sentence).\n"
    "- Yes: the criterion is fully satisfied\n"
    "- Partial: mostly satisfied, with minor gaps\n"
    "- No: clearly not satisfied\n\n"
    "CRITICAL RULES:\n"
    "- If the AI used tools to gather data, treat that data as grounded evidence.\n"
    "- Ignore tone and style. Focus ONLY on substance and facts.\n"
    "- Length is NOT quality.\n"
    'Output JSON only: {"answers": [{"q": 1, "answer": "yes"|"partial"|"no", "reason": "..."}]}'
)

_SCORE_MAP: Dict[str, float] = {
    "yes": 1.0,
    "true": 1.0,
    "y": 1.0,
    "是": 1.0,
    "partial": 0.5,
    "partially": 0.5,
    "部分": 0.5,
    "no": 0.0,
    "false": 0.0,
    "n": 0.0,
    "否": 0.0,
}

_MAX_CONTENT = 16_000


class BinaryJudge:
    """批量 LLM 问题评判器。"""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    async def judge(
        self,
        questions: List[EvalQuestion],
        content: str,
        task: str,
        context: Optional[Dict] = None,
    ) -> List[Verdict]:
        if not questions:
            return []

        truncated_content = self._truncate(content)
        q_list = "\n".join(f"{i + 1}. {q.text}" for i, q in enumerate(questions))

        tool_ctx = ""
        if context:
            tools = context.get("tools_used", [])
            n_calls = context.get("total_tool_calls", 0)
            if tools:
                tool_ctx = (
                    f"Tools the AI used: {', '.join(tools)}\n"
                    f"Total tool calls: {n_calls}\n\n"
                )

        user_prompt = (
            f"Task:\n{task[:600]}\n\n"
            f"{tool_ctx}"
            f"AI response:\n{truncated_content}\n\n"
            f"Questions (answer Yes/Partial/No with brief reason):\n{q_list}\n\n"
            'Output JSON: {"answers": [{"q": 1, "answer": "yes"|"partial"|"no", "reason": "..."}, ...]}'
        )

        try:
            raw = await self._llm.complete(
                _JUDGE_SYSTEM, user_prompt, max_tokens=1500, timeout=45.0
            )
            data = self._parse_json(raw)
            return self._parse_verdicts(data, questions)
        except LLMError as e:
            logger.warning(f"[BinaryJudge] LLM 调用失败，降级为 fallback: {e}")
            return self._fallback_verdicts(questions, reason="parser failed")
        except Exception as e:
            logger.warning(f"[BinaryJudge] 异常，降级为 fallback: {e}")
            return self._fallback_verdicts(questions, reason="parser failed")

    # ── 内部方法 ─────────────────────────────────────────────

    @staticmethod
    def _truncate(content: str) -> str:
        if len(content) <= _MAX_CONTENT:
            return content
        headers = list(re.finditer(r"^(#{1,4}\s+.+)$", content, re.MULTILINE))
        if len(headers) >= 3:
            budget = _MAX_CONTENT // len(headers)
            parts = []
            for i, h in enumerate(headers):
                start = h.start()
                end = headers[i + 1].start() if i + 1 < len(headers) else len(content)
                sec = content[start:end]
                if len(sec) > budget:
                    sec = sec[:budget] + "\n[...truncated]\n"
                parts.append(sec)
            return "".join(parts)
        return content[:_MAX_CONTENT]

    @staticmethod
    def _parse_json(raw: str) -> dict:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            raise LLMError(f"LLM 返回无法解析的 JSON: {raw[:200]}")
        return json.loads(m.group())

    @staticmethod
    def _parse_verdicts(data: dict, questions: List[EvalQuestion]) -> List[Verdict]:
        answers = data.get("answers", [])
        if not answers:
            for v in data.values():
                if isinstance(v, list) and v:
                    answers = v
                    break

        verdicts: List[Verdict] = []
        for i, q in enumerate(questions):
            ans_data = answers[i] if i < len(answers) else {}
            if isinstance(ans_data, dict):
                raw_answer = str(ans_data.get("answer", "partial")).strip().lower()
                reason = str(ans_data.get("reason", ""))
            else:
                raw_answer = "partial"
                reason = ""

            score = _SCORE_MAP.get(raw_answer, 0.5)
            answer_bool = score >= 0.5
            if not q.positive_answer:
                score = 1.0 - score
            is_positive = score >= 0.5

            verdicts.append(
                Verdict(
                    question=q.text,
                    category=q.category,
                    answer=answer_bool,
                    is_positive=is_positive,
                    score_value=score,
                    reason=reason,
                    section=q.section_target or "",
                    weight=q.weight,
                )
            )
        return verdicts

    @staticmethod
    def _fallback_verdicts(
        questions: List[EvalQuestion], reason: str = "parser failed"
    ) -> List[Verdict]:
        return [
            Verdict(
                question=q.text,
                category=q.category,
                answer=False,
                is_positive=False,
                score_value=0.0,
                reason=reason,
                weight=q.weight,
            )
            for q in questions
        ]
