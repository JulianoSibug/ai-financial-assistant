"""Fallback LLM provider: direct HTTP calls to the Anthropic Messages API.
Needed if this app is ever hosted/shared, where a shared interactive Claude
Pro CLI session isn't available or appropriate -- billed per token via
ANTHROPIC_API_KEY rather than drawing on a Claude Pro subscription.
"""
from __future__ import annotations

import httpx

from backend.config import settings
from backend.llm.provider import strip_markdown_fences

_API_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"


class AnthropicAPIError(RuntimeError):
    pass


class AnthropicAPIProvider:
    def __init__(self, *, model: str | None = None) -> None:
        self._model = model or settings.categorize_model

    def complete(self, prompt: str, max_tokens: int = 4096) -> str:
        if not settings.anthropic_api_key:
            raise AnthropicAPIError(
                "ANTHROPIC_API_KEY is not set. Set it in .env, or switch LLM_PROVIDER to claude_cli."
            )
        response = httpx.post(
            _API_URL,
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": _ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            json={
                "model": self._model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=180,
        )
        if response.status_code != 200:
            raise AnthropicAPIError(f"Anthropic API returned {response.status_code}: {response.text[:500]}")

        data = response.json()
        text_parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
        return strip_markdown_fences("".join(text_parts).strip())
