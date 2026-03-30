"""LLM provider adapter — isolates all model-specific logic.

The adapter uses LiteLLM so we can swap between OpenAI, Anthropic, or local
models without changing calling code.  All provider-specific details stay here.

MVP scope: synchronous completion with JSON-mode response.
Future: streaming, function calling, batch, embeddings.
"""

from __future__ import annotations

import json
import os
from typing import Any

import litellm


class LLMAdapter:
    """Thin wrapper around LiteLLM for structured JSON completions."""

    def __init__(
        self,
        model: str | None = None,
        temperature: float = 0.0,
    ) -> None:
        self.model = model or os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.temperature = temperature

    def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a prompt and parse the response as JSON.

        If the provider supports JSON-mode / response_format we use it;
        otherwise we instruct the model via system prompt.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
        }

        response = litellm.completion(**kwargs)
        raw = response.choices[0].message.content or "{}"
        return json.loads(raw)
