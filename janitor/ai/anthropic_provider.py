from __future__ import annotations

import json
from typing import Any

import anthropic

from janitor.ai.provider import AIProvider, AIResponse, ToolCall
from janitor.config import AIConfig


class AnthropicProvider(AIProvider):
    def __init__(self, config: AIConfig) -> None:
        self._config = config
        self._client = anthropic.AsyncAnthropic(api_key=config.api_key)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
    ) -> AIResponse:
        kwargs: dict[str, Any] = {
            "model": self._config.model,
            "max_tokens": self._config.max_tokens,
            "messages": messages,
        }

        if system:
            kwargs["system"] = system

        if tools:
            kwargs["tools"] = [
                {
                    "name": t["name"],
                    "description": t["description"],
                    "input_schema": t["input_schema"],
                }
                for t in tools
            ]

        response = await self._client.messages.create(**kwargs)

        content_text = ""
        tool_calls: list[ToolCall] = []

        for block in response.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=dict(block.input)
                        if isinstance(block.input, dict)
                        else json.loads(block.input),
                    )
                )

        return AIResponse(
            content=content_text,
            tool_calls=tool_calls,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
