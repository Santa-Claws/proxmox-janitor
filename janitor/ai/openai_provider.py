from __future__ import annotations

import json
from typing import Any

import openai

from janitor.ai.provider import AIProvider, AIResponse, ToolCall
from janitor.config import AIConfig


class OpenAIProvider(AIProvider):
    """Covers OpenAI, OpenRouter, and Ollama (all OpenAI-compatible)."""

    def __init__(self, config: AIConfig) -> None:
        self._config = config
        kwargs: dict[str, Any] = {}
        if config.api_key:
            kwargs["api_key"] = config.api_key
        if config.base_url:
            kwargs["base_url"] = config.base_url
        elif config.provider == "ollama":
            kwargs["base_url"] = "http://localhost:11434/v1"
            kwargs.setdefault("api_key", "ollama")
        elif config.provider == "openrouter":
            kwargs["base_url"] = "https://openrouter.ai/api/v1"

        self._client = openai.AsyncOpenAI(**kwargs)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
    ) -> AIResponse:
        oai_messages: list[dict[str, Any]] = []
        if system:
            oai_messages.append({"role": "system", "content": system})

        for msg in messages:
            oai_messages.append(msg)

        kwargs: dict[str, Any] = {
            "model": self._config.model,
            "messages": oai_messages,
            "max_tokens": self._config.max_tokens,
            "temperature": self._config.temperature,
        }

        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": t["input_schema"],
                    },
                }
                for t in tools
            ]

        response = await self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]

        content_text = choice.message.content or ""
        tool_calls: list[ToolCall] = []

        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=json.loads(tc.function.arguments),
                    )
                )

        return AIResponse(
            content=content_text,
            tool_calls=tool_calls,
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
        )
