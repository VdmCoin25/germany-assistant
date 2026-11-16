"""Provider-agnostic AI interface (implemented in stage B).

Business logic depends only on `AIProvider`. Concrete providers (OpenAI, Anthropic,
a self-hosted EU model, ...) are selected with AI_PROVIDER in .env.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


class AINotConfigured(RuntimeError):
    """Raised when no provider is configured. Handlers must tell the user honestly."""


@dataclass
class AIMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


class AIProvider(ABC):
    @abstractmethod
    async def complete(self, messages: list[AIMessage], *, max_tokens: int = 1000) -> str: ...


class NoProvider(AIProvider):
    async def complete(self, messages, *, max_tokens: int = 1000) -> str:
        raise AINotConfigured("AI provider is not configured (AI_PROVIDER=none)")


def get_provider(name: str, api_key: str | None, model: str | None) -> AIProvider:
    if name == "none" or not api_key:
        return NoProvider()
    raise AINotConfigured(f"Provider '{name}' is not implemented yet (stage B)")
