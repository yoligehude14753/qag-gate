"""LLM 适配器 — 实现 LLMClient protocol，隔离第三方 SDK 依赖。

提供：
  OpenAIAdapter  — 对接 openai SDK（包括所有兼容接口，如 DeepSeek、Moonshot）
  AnthropicAdapter — 对接 anthropic SDK
  FallbackChain  — 多 adapter 按优先级降级
  MockLLMClient  — 测试用，无网络依赖
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from loguru import logger

from qag_gate.domain.ports import LLMClient, LLMError, LLMParseError


class OpenAIAdapter:
    """openai SDK 适配器（支持所有 OpenAI 兼容 API）。"""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        try:
            import openai
        except ImportError as e:
            raise ImportError("请安装 openai: pip install 'qag-gate[openai]'") from e

        self._model = model
        self._client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            **kwargs,
        )

    async def complete(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 1000,
        temperature: float = 0.1,
        timeout: float = 45.0,
        response_format: Optional[str] = None,
    ) -> str:
        try:
            kwargs: Dict[str, Any] = dict(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
            if response_format == "json":
                kwargs["response_format"] = {"type": "json_object"}

            resp = await self._client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content.strip()
        except Exception as e:
            raise LLMError(f"OpenAI 调用失败 ({self._model}): {e}") from e

    async def complete_json(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 1000,
        temperature: float = 0.1,
        timeout: float = 45.0,
    ) -> Dict[str, Any]:
        raw = await self.complete(
            system,
            user,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
            response_format="json",
        )
        return _parse_json_safe(raw)


class AnthropicAdapter:
    """anthropic SDK 适配器。"""

    def __init__(
        self,
        model: str = "claude-3-5-haiku-20241022",
        api_key: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        try:
            import anthropic
        except ImportError as e:
            raise ImportError(
                "请安装 anthropic: pip install 'qag-gate[anthropic]'"
            ) from e

        self._model = model
        self._client = anthropic.AsyncAnthropic(api_key=api_key, **kwargs)

    async def complete(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 1000,
        temperature: float = 0.1,
        timeout: float = 45.0,
        response_format: Optional[str] = None,
    ) -> str:
        try:
            resp = await self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=[{"role": "user", "content": user}],
                timeout=timeout,
            )
            return resp.content[0].text.strip()
        except Exception as e:
            raise LLMError(f"Anthropic 调用失败 ({self._model}): {e}") from e

    async def complete_json(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 1000,
        temperature: float = 0.1,
        timeout: float = 45.0,
    ) -> Dict[str, Any]:
        raw = await self.complete(
            system,
            user,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
        )
        return _parse_json_safe(raw)


class FallbackChain:
    """按顺序尝试多个 LLM adapter，全部失败才抛异常。"""

    def __init__(self, adapters: List[LLMClient]) -> None:
        if not adapters:
            raise ValueError("FallbackChain 至少需要 1 个 adapter")
        self._adapters = adapters

    async def complete(self, system: str, user: str, **kwargs: Any) -> str:
        last_err: Optional[Exception] = None
        for adapter in self._adapters:
            try:
                return await adapter.complete(system, user, **kwargs)
            except LLMError as e:
                logger.warning(
                    f"[FallbackChain] adapter={type(adapter).__name__} 失败: {e}"
                )
                last_err = e
        raise LLMError(f"所有 LLM adapter 均失败: {last_err}") from last_err

    async def complete_json(
        self, system: str, user: str, **kwargs: Any
    ) -> Dict[str, Any]:
        last_err: Optional[Exception] = None
        for adapter in self._adapters:
            try:
                return await adapter.complete_json(system, user, **kwargs)
            except LLMError as e:
                logger.warning(
                    f"[FallbackChain] adapter={type(adapter).__name__} JSON 失败: {e}"
                )
                last_err = e
        raise LLMError(f"所有 LLM adapter 均失败: {last_err}") from last_err


class MockLLMClient:
    """测试用 Mock，无网络调用。返回固定 JSON 或自定义响应。"""

    def __init__(self, response: str = '{"answers": []}') -> None:
        self._response = response
        self.calls: List[Dict[str, Any]] = []

    async def complete(self, system: str, user: str, **kwargs: Any) -> str:
        self.calls.append({"system": system, "user": user, **kwargs})
        return self._response

    async def complete_json(
        self, system: str, user: str, **kwargs: Any
    ) -> Dict[str, Any]:
        self.calls.append({"system": system, "user": user, **kwargs})
        return _parse_json_safe(self._response)


def _parse_json_safe(raw: str) -> Dict[str, Any]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```\w*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise LLMParseError(f"LLM 返回无法解析的 JSON: {raw[:200]}")
    try:
        return json.loads(m.group())
    except json.JSONDecodeError as e:
        raise LLMParseError(f"JSON 解析失败: {e}") from e
