"""LLM providers. Only one call shape is needed by the platform: prompt in, JSON out."""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.config import settings


@dataclass
class LLMResult:
    data: dict
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


class LLMProvider(ABC):
    name = "base"

    @abstractmethod
    def complete_json(self, system: str, user: str) -> LLMResult: ...


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str):
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key, timeout=60)
        self.model = model

    def complete_json(self, system: str, user: str) -> LLMResult:
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        usage = resp.usage
        return LLMResult(
            data=json.loads(resp.choices[0].message.content or "{}"),
            model=self.model,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )


def get_llm() -> LLMProvider | None:
    """The configured LLM, or None when the platform should use its rule-based fallback."""
    if settings.use_openai:
        return OpenAIProvider(settings.openai_api_key, settings.openai_model)
    return None
