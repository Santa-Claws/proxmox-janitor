from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from janitor.config import AIConfig


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class AIResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


class AIProvider(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
    ) -> AIResponse: ...


def create_provider(config: AIConfig) -> AIProvider:
    if config.provider == "anthropic":
        from janitor.ai.anthropic_provider import AnthropicProvider

        return AnthropicProvider(config)
    else:
        # openai, openrouter, ollama all use OpenAI-compatible API
        from janitor.ai.openai_provider import OpenAIProvider

        return OpenAIProvider(config)
