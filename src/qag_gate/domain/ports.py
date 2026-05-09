"""qag-gate 端口定义 — 外部依赖的抽象接口（Protocol）。

业务域（domain/application/checkers）只依赖此文件，不直接 import openai/anthropic。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """LLM 调用抽象。infrastructure 层负责实现。"""

    async def complete(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 1000,
        temperature: float = 0.1,
        timeout: float = 45.0,
        response_format: Optional[str] = None,  # "json" | None
    ) -> str:
        """返回模型文本回复（已 strip）。失败时抛 LLMError。"""
        ...

    async def complete_json(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 1000,
        temperature: float = 0.1,
        timeout: float = 45.0,
    ) -> Dict[str, Any]:
        """返回解析后的 JSON dict。失败时抛 LLMError 或 LLMParseError。"""
        ...


class LLMError(Exception):
    """LLM 调用失败（网络、超时、限速等）。"""


class LLMParseError(LLMError):
    """LLM 返回非法 JSON。"""
