"""Abstract LLM provider interface + selection by LLM_PROVIDER env var."""
from __future__ import annotations

import re
from typing import Protocol

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def strip_markdown_fences(text: str) -> str:
    """Every LLM call in this app asks for a bare JSON array back, but models
    sometimes wrap it in a ```json fence anyway. Part of the LLMProvider
    contract: complete() always returns fence-free text, so callers
    (categorize.py, summarize.py) can json.loads() the result directly
    regardless of which provider is active."""
    return _FENCE_RE.sub("", text).strip()


class LLMProvider(Protocol):
    def complete(self, prompt: str, max_tokens: int = 4096) -> str: ...


class AuthStatus:
    def __init__(self, state: str, detail: str = "") -> None:
        self.state = state  # 'authenticated' | 'unauthenticated' | 'unavailable'
        self.detail = detail

    @property
    def ok(self) -> bool:
        return self.state == "authenticated"

    def __repr__(self) -> str:  # pragma: no cover
        return f"AuthStatus(state={self.state!r}, detail={self.detail!r})"


def check_provider_auth(provider_name: str) -> AuthStatus:
    """Dispatches to the right notion of 'ready to call' per provider: a
    subprocess auth check for claude_cli, a simple key-presence check for
    anthropic_api."""
    if provider_name == "claude_cli":
        from backend.llm.claude_cli import check_auth

        return check_auth()
    if provider_name == "anthropic_api":
        from backend.config import settings

        if settings.anthropic_api_key:
            return AuthStatus("authenticated", "ANTHROPIC_API_KEY is set")
        return AuthStatus("unauthenticated", "ANTHROPIC_API_KEY is not set")
    if provider_name == "manual":
        return AuthStatus(
            "authenticated",
            "Manual categorization stand-in (backend/llm/manual_provider.py) -- "
            "not a real LLM connection. Temporary; see PHASE_PLAN.md.",
        )
    return AuthStatus("unavailable", f"unknown provider {provider_name!r}")


def get_provider(provider_name: str, *, model: str | None = None) -> LLMProvider:
    """model is only meaningful for anthropic_api -- the claude_cli subprocess
    invocation (per spec) has no --model flag, so it always uses whatever
    model the CLI session itself is configured for."""
    if provider_name == "claude_cli":
        from backend.llm.claude_cli import ClaudeCLIProvider

        return ClaudeCLIProvider()
    if provider_name == "anthropic_api":
        from backend.llm.anthropic_api import AnthropicAPIProvider

        return AnthropicAPIProvider(model=model)
    if provider_name == "manual":
        from backend.llm.manual_provider import ManualCategorizationProvider

        return ManualCategorizationProvider()
    raise ValueError(f"Unknown LLM_PROVIDER: {provider_name!r}")
